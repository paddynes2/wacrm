"""Read-only provider reconciliation into the product's transactional engine.

All messages from a chat are validated before the first engine mutation. External
effects are never performed here; repeated polling relies on engine event dedup.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

from .store import account_id, encode
from .providers import ProviderError, PARTY, ID


def _party(value):
    """Only a corroborated E.164 identity maps to its phone JID, never a LID guess."""
    if isinstance(value, str) and PARTY.fullmatch(value):
        return value
    if isinstance(value, str) and re.fullmatch(r"\+[1-9][0-9]{7,14}", value):
        return value[1:] + "@s.whatsapp.net"
    return None


def _match(engine, doc, recipients, chat_id):
    candidates = []
    for prospect in doc["prospects"]:
        if prospect.get("chat_id") and prospect["chat_id"] != chat_id:
            continue
        state = engine.state(doc, prospect["id"])
        identity = state.get("identity") or {}
        if state.get("status") == "unconfigured":
            continue
        recipient = _party(identity.get("recipient_id"))
        if recipient is None and prospect.get("phone_status") == "operator_verified":
            recipient = _party(prospect.get("phone"))
        principal = _party(identity.get("principal_id"))
        # A principal-only chat cannot identify which of their prospects it concerns.
        allowed = ({recipient}, {recipient, principal}) if principal else ({recipient},)
        if recipient and recipients in allowed and len(recipients) == 1:
            candidates.append(prospect["id"])
    return candidates[0] if len(candidates) == 1 else None


def _validated(snapshot, provider_account, chat_id):
    if (not isinstance(snapshot, dict) or snapshot.get("account_id") != provider_account
            or snapshot.get("chat_id") != chat_id or snapshot.get("all_history") is not True):
        raise ProviderError("incomplete or mismatched conversation evidence")
    recipients = snapshot.get("recipients")
    if (not isinstance(recipients, list) or not recipients or len(set(recipients)) != len(recipients)
            or any(not isinstance(party, str) or not PARTY.fullmatch(party) for party in recipients)):
        raise ProviderError("invalid conversation recipients")
    messages = snapshot.get("messages")
    if not isinstance(messages, list):
        raise ProviderError("missing conversation messages")
    seen, normalized = set(), []
    for message in messages:
        if not isinstance(message, dict):
            raise ProviderError("invalid conversation message")
        mid = message.get("message_id")
        if (not isinstance(mid, str) or not mid or len(mid) > 150 or mid in seen
                or message.get("account_id") != provider_account or message.get("chat_id") != chat_id
                or type(message.get("is_sender")) is not bool):
            raise ProviderError("invalid conversation message identity")
        seen.add(mid)
        if not message["is_sender"] and message.get("sender_id") not in recipients:
            raise ProviderError("unresolved incoming sender requires review")
        if message.get("text") is not None and not isinstance(message["text"], str):
            raise ProviderError("invalid message content")
        try:
            stamp = dt.datetime.fromisoformat(message["timestamp"].replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp > dt.datetime.now(dt.timezone.utc):
                raise ValueError()
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ProviderError("invalid provider timestamp") from None
        normalized.append({**message, "timestamp": stamp.astimezone(dt.timezone.utc).isoformat()})
    return set(recipients), sorted(normalized, key=lambda m: (m["timestamp"], m["message_id"]))


def _known_echo(doc, prospect_id, provider_account, chat_id, message):
    # Require an actual recorded non-simulated outbound in the same chat/account.
    # A model-generated draft ID or merely is_sender=true cannot establish origin.
    return any(m.get("id") == message["message_id"] and m.get("prospect_id") == prospect_id
               and m.get("direction") == "outbound" and m.get("simulated") is False
               and m.get("chat_id") == chat_id and m.get("provider_account_id") == provider_account
               and m.get("text") == message.get("text")
               and m.get("purpose") != "manual"
               for m in doc["messages"])


def sync_account(engine, account):
    account = account_id(account)
    client = engine.unipile.get(account)
    if client is None:
        raise ProviderError("Unipile account is not configured")
    provider_account = client.account_id
    if not isinstance(provider_account, str) or not ID.fullmatch(provider_account):
        raise ProviderError("invalid bound provider account")
    # Finish reading/validating every chat before applying any messages. A partial
    # provider result must not leave an apparent successful account-wide sync.
    try:
        identity = client.verify_account()
        if identity.get("id") != provider_account or identity.get("type") != "WHATSAPP":
            raise ProviderError("provider identity mismatch")
        chats = client.list_chats()
        if not isinstance(chats, list):
            raise ProviderError("invalid chat list")
        seen, snapshots = set(), []
        for chat in chats:
            cid = chat.get("id") if isinstance(chat, dict) else None
            if not isinstance(cid, str) or not ID.fullmatch(cid) or cid in seen or chat.get("account_id") != provider_account:
                raise ProviderError("invalid chat list identity")
            seen.add(cid)
            snapshot = client.fetch_conversation(cid)
            recipients, messages = _validated(snapshot, provider_account, cid)
            snapshots.append((cid, recipients, messages))
        if engine.unipile.get(account) is not client or client.account_id != provider_account:
            raise ProviderError("provider binding changed during sync")
    except Exception:
        with engine.store.transaction() as db:
            doc = engine.store.load(db, account, engine.mode)
            doc["connections"].update(last_sync_error="Provider evidence incomplete; synchronization was not applied.")
            engine.event(doc, "sync_failed", reason="Provider evidence incomplete")
            engine.store.save(db, doc)
        raise ProviderError("Provider evidence incomplete; sync failed") from None

    result = {"chats_checked": len(snapshots), "messages_checked": 0, "unknown_chats": [],
              "assistant_echoes": 0, "manual_outbound": 0, "inbound": 0,
              "connection_verified": True, "live_delivery_verified": False}
    checkpoints = {}
    with engine.store.transaction() as db:
        doc = engine.store.load(db, account, engine.mode)
        matches = {cid: _match(engine, doc, recipients, cid) for cid, recipients, _ in snapshots}
    for cid, recipients, messages in snapshots:
        with engine.store.transaction() as db:
            doc = engine.store.load(db, account, engine.mode)
            pid = _match(engine, doc, recipients, cid)
            if pid and sum(value == pid for value in matches.values()) > 1:
                pid = None
        if pid is None:
            result["unknown_chats"].append(cid)
            continue
        for message in messages:
            if engine.unipile.get(account) is not client or client.account_id != provider_account:
                raise ProviderError("provider binding changed during ingestion")
            with engine.store.transaction() as db:
                doc = engine.store.load(db, account, engine.mode)
                if _match(engine, doc, recipients, cid) != pid:
                    raise ProviderError("prospect binding changed during ingestion")
                echo = message["is_sender"] and _known_echo(doc, pid, provider_account, cid, message)
            if echo:
                result["assistant_echoes"] += 1
            else:
                source = "unipile:sha256:" + hashlib.sha256(encode({"account": provider_account, "message": message}).encode()).hexdigest()
                args = (account, pid, message.get("text"), message["message_id"], cid,
                        message.get("sender_id"), message["timestamp"], source)
                if message["is_sender"]:
                    engine.manual_outbound(*args)
                    result["manual_outbound"] += 1
                else:
                    engine.ingest(*args)
                    result["inbound"] += 1
            result["messages_checked"] += 1
        checkpoints[cid] = {"last_message_id": messages[-1]["message_id"] if messages else None,
                            "last_message_at": messages[-1]["timestamp"] if messages else None,
                            "provider_pagination_complete": True}
    with engine.store.transaction() as db:
        doc = engine.store.load(db, account, engine.mode)
        now = engine.stamp(doc)
        doc["connections"].update(account_id=provider_account, verified_at=now, last_sync=now,
            last_sync_error=None, chat_checkpoints=checkpoints, unknown_chats=result["unknown_chats"],
            live_delivery_verified=False)
        engine.event(doc, "account_synced", **result)
        engine.store.save(db, doc)
    return result


def main():
    """Interactive credential entry for a read-only account readiness probe."""
    import argparse
    import getpass
    import json
    from .providers import UnipileClient
    parser = argparse.ArgumentParser(description="Read-only Unipile identity and chat-list probe; never sends")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--account-id", required=True)
    args = parser.parse_args()
    try:
        client = UnipileClient(base_url=args.base_url, api_key=getpass.getpass("Unipile API key (not saved): "), account_id=args.account_id)
        identity = client.verify_account()
        chats = client.list_chats()
        print(json.dumps({**identity, "chats_checked": len(chats), "live_delivery_verified": False}))
    except ProviderError as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
