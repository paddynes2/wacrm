"""Inert exact-action WhatsApp executor with mandatory host authorization gates.

This module installs no routes, grants, permission flags or default callbacks.
An OS integration must wrap the callable with the canonical HR12 guarded_send.
"""
from __future__ import annotations

import hashlib
import json
import re

from .providers import ID, PARTY, ProviderError, _request, _text
from .store import account_id


class UncertainDelivery(ProviderError):
    """A write may have happened. Reconcile evidence; never automatically retry."""


def freeze(action):
    required = {"action_id", "workspace_id", "prospect_id", "account_id", "recipients", "text", "revision", "purpose"}
    if not isinstance(action, dict) or set(action) - required - {"chat_id"} or not required.issubset(action):
        raise ProviderError("invalid reviewed action fields")
    value = json.loads(json.dumps(action, allow_nan=False))
    account_id(value["workspace_id"])
    for key in ("action_id", "prospect_id", "account_id"):
        if not isinstance(value[key], str) or not ID.fullmatch(value[key]):
            raise ProviderError("invalid reviewed action identity")
    value["text"] = _text(value["text"], "reviewed message")
    if not isinstance(value["revision"], str) or not re.fullmatch(r"[a-f0-9]{64}", value["revision"]):
        raise ProviderError("invalid reviewed conversation revision")
    people = value["recipients"]
    if not isinstance(people, list) or not people or any(not isinstance(p, str) or not PARTY.fullmatch(p) for p in people) or len(set(people)) != len(people):
        raise ProviderError("invalid reviewed recipients")
    purpose = value["purpose"]
    if purpose == "introduction":
        if not 2 <= len(people) <= 8 or "chat_id" in value:
            raise ProviderError("introduction requires 2..8 exact members and a new group")
    elif purpose not in {"approach", "reply", "schedule", "booking_link", "manual"} or len(people) != 1:
        raise ProviderError("invalid direct message purpose or recipients")
    if "chat_id" in value and (not isinstance(value["chat_id"], str) or not ID.fullmatch(value["chat_id"])):
        raise ProviderError("invalid reviewed chat")
    if purpose == "reply" and not value.get("chat_id"):
        raise ProviderError("reply requires its verified chat")
    return value


def canonical_action(action):
    value = freeze(action)
    # All fields are in the canonical HR12 bound-key allowlist; all product context
    # stays inside payload, so unknown top-level keys cannot escape the digest.
    return {"kind": "concierge", "channel": "whatsapp", "sender": value["account_id"],
            "endpoint": "create_group" if value["purpose"] == "introduction" else "message",
            "recipients": list(value["recipients"]), "payload": value}


def execute_reviewed(client, action, *, gate=None, validate_current=None, inspect_thread=None, claim=None, record=None):
    """Ask an external gate to authorize exactly one immutable callable.

    gate(canonical, send_fn) must enforce human authorization, kill/suppression/caps.
    validate_current(frozen) -> True checks current ownership/state/consent/revision.
    inspect_thread(snapshot, frozen) -> True applies verified history/decline checks.
    claim(digest, frozen) -> True atomically reserves the action once across processes.
    record(digest, frozen, status, evidence) -> True persists started/verified/unknown.
    No callback is optional at runtime. Callbacks receive independent snapshots.
    """
    if any(not callable(callback) for callback in (gate, validate_current, inspect_thread, claim, record)):
        raise ProviderError("reviewed transport requires all host authorization and durable ledger callbacks")
    frozen = freeze(action)
    canonical = canonical_action(frozen)
    serialized = json.dumps(frozen, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    canonical_serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False)
    attempted = False

    def copy():
        return json.loads(serialized)

    def check_current():
        if client.account_id != frozen["account_id"] or validate_current(copy()) is not True:
            raise ProviderError("reviewed action state or sender changed")

    def send_fn():
        nonlocal attempted
        if attempted:
            raise ProviderError("reviewed action callable already attempted")
        if json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False) != canonical_serialized:
            raise ProviderError("authorization mutated the reviewed action")
        check_current()
        identity = client.verify_account()
        if identity.get("id") != frozen["account_id"] or identity.get("type") != "WHATSAPP":
            raise ProviderError("provider identity mismatch")
        target_seen = not frozen.get("chat_id")
        for chat in client.list_chats():
            snapshot = client.fetch_conversation(chat["id"])
            if (snapshot.get("account_id") != frozen["account_id"] or snapshot.get("chat_id") != chat["id"]
                    or snapshot.get("all_history") is not True):
                raise ProviderError("Provider history ownership or completeness changed")
            recipients = set(snapshot["recipients"])
            if recipients & set(frozen["recipients"]):
                if inspect_thread(snapshot, copy()) is not True:
                    raise ProviderError("verified thread check refused")
            if chat["id"] == frozen.get("chat_id"):
                if recipients != set(frozen["recipients"]):
                    raise ProviderError("reviewed chat membership changed")
                target_seen = True
        if not target_seen:
            raise ProviderError("reviewed chat absent from verified history")
        check_current()
        if claim(digest, copy()) is not True:
            raise ProviderError("reviewed action already claimed or ledger unavailable")
        attempted = True
        if record(digest, copy(), "started", {}) is not True:
            raise ProviderError("dispatch start could not be persisted")
        # Any exception from this point may represent an external effect. The host
        # must reconcile, including when read-back or receipt persistence fails.
        try:
            check_current()
            if frozen.get("chat_id"):
                path = f"/chats/{frozen['chat_id']}/messages"
                body = {"account_id": frozen["account_id"], "text": frozen["text"]}
            else:
                path = "/chats"
                body = {"account_id": frozen["account_id"], "attendees_ids": frozen["recipients"], "text": frozen["text"]}
            _, response = _request({"http": client.http}, "POST", client.base + path,
                {"X-API-KEY": client.key, "Accept": "application/json", "Content-Type": "application/json"}, body)
            mid = response.get("message_id")
            cid = response.get("chat_id") or response.get("id") or frozen.get("chat_id")
            if not isinstance(mid, str) or not mid or not isinstance(cid, str) or not ID.fullmatch(cid):
                raise ProviderError("provider write receipt missing")
            if frozen.get("chat_id") and cid != frozen["chat_id"]:
                raise ProviderError("provider write receipt chat mismatch")
            snapshot = client.fetch_conversation(cid)
            if (client.account_id != frozen["account_id"] or snapshot.get("account_id") != frozen["account_id"]
                    or snapshot.get("chat_id") != cid or snapshot.get("all_history") is not True):
                raise ProviderError("Provider read-back ownership or completeness changed")
            if set(snapshot["recipients"]) != set(frozen["recipients"]):
                raise ProviderError("provider read-back membership mismatch")
            matches = [m for m in snapshot["messages"] if m["message_id"] == mid]
            if len(matches) != 1 or matches[0]["is_sender"] is not True or matches[0].get("text") != frozen["text"]:
                raise ProviderError("provider sent message read-back mismatch")
            evidence = {"message_id": mid, "chat_id": cid, "account_id": frozen["account_id"],
                        "membership_verified": True, "message_verified": True,
                        "timestamp": matches[0]["timestamp"], "delivered_to_recipient": False}
            if record(digest, copy(), "verified", evidence) is not True:
                raise ProviderError("provider receipt could not be persisted")
            return evidence
        except Exception:
            try:
                record(digest, copy(), "unknown", {"reason": "External effect requires reconciliation"})
            except Exception:
                pass
            raise UncertainDelivery("Delivery is uncertain; reconcile before any further action") from None

    return gate(canonical, send_fn)
