"""Host-only exact-authorized dispatch integration. No HTTP route or default gate.

The mandatory gate is supplied by the host's real human-approval mechanism. OS
callers must use canonical HR12 guarded_send; this module never creates go tokens.
"""
from __future__ import annotations

from datetime import datetime
import json
import re

from .concierge_core import state as core
from .providers import PARTY, ProviderError
from .reviewed_transport import execute_reviewed
from .store import account_id, encode

# Preserve the canonical thread check's conservative decline families.
DECLINE = re.compile(r"\b(not interested|no thanks|no thank you|please (stop|remove)|unsubscribe|"
    r"take me off|do not contact|don'?t contact|not a fit|we'?re all set|already have (a|one|someone)|"
    r"stop (messaging|emailing|mailing|contacting)|a big no\b|big L in my books|"
    r"do(?:n'?t| not) (?:waste|waist) my time|(?:never|don'?t|do not).{0,40}\b(?:email|mail|contact) me again)", re.I)


def _jid(value):
    if isinstance(value, str) and PARTY.fullmatch(value):
        return value
    if isinstance(value, str) and re.fullmatch(r"\+[1-9][0-9]{7,14}", value):
        return value[1:] + "@s.whatsapp.net"
    raise ProviderError("Verified provider party identity is required")


def _digest(value):
    return core._digest(value)


def execute_decision(engine, account, decision_id, gate, *, principal_provider_id=None):
    """Execute one reviewed live decision through a mandatory external gate.

    No route calls this automatically. principal_provider_id, when needed, comes
    from host-owned verified routing and is shown in the exact authorization card.
    """
    account = account_id(account)
    if engine.mode != "live" or not callable(gate):
        raise ProviderError("Live execution requires an explicit host authorization gate")
    client = engine.unipile.get(account)
    if client is None:
        raise ProviderError("Explicit Unipile account binding required")
    with engine.store.transaction() as db:
        doc = engine.store.load(db, account, engine.mode)
        decision = next((d for d in doc["decisions"] if d["id"] == decision_id), None)
        if not decision or decision["status"] != "pending":
            raise ProviderError("Pending reviewed decision not found")
        frozen_decision = json.loads(encode(decision))
        prospect = engine.prospect(doc, decision["prospect_id"])
        engine.eligible(doc, prospect)
        state = engine.state(doc, prospect["id"])
        core.check_action(state, decision["purpose"], decision["revision"])
        expected = {k: v for k, v in decision.items() if k not in {"id", "status", "created_at"}}
        if _digest(expected) != decision_id or decision.get("mode") != "live" or decision.get("account_id") != account:
            raise ProviderError("Reviewed decision digest or account mismatch")
        if prospect.get("phone_status") != "operator_verified":
            raise ProviderError("Phone attribution must be verified before live dispatch")
        recipient = _jid(state["identity"]["recipient_id"])
        if recipient != _jid(prospect.get("phone")):
            raise ProviderError("Prospect phone changed from established identity")
        recipients = [recipient]
        expected_recipients = [state["identity"]["recipient_id"]]
        if decision["purpose"] == "introduction":
            principal = _jid(principal_provider_id)
            if principal == recipient:
                raise ProviderError("Introduction parties must differ")
            recipients = [principal, recipient]
            expected_recipients.insert(0, state["identity"]["principal_id"])
        if decision.get("recipients") != expected_recipients:
            raise ProviderError("Decision recipient identity mismatch")
        latest_inbound = state.get("latest_inbound")
        action = {"action_id": decision_id, "workspace_id": account, "prospect_id": prospect["id"],
                  "account_id": client.account_id, "recipients": recipients, "text": decision["text"],
                  "revision": decision["revision"], "purpose": decision["purpose"]}
        if decision["purpose"] == "reply":
            if not latest_inbound or not latest_inbound.get("chat_id"):
                raise ProviderError("Reply must bind verified incoming chat")
            action["chat_id"] = latest_inbound["chat_id"]
        elif decision["purpose"] != "introduction" and prospect.get("chat_id"):
            action["chat_id"] = prospect["chat_id"]

    context = {"db": None, "revision": decision["revision"], "phase": "prepared"}

    def current():
        db = context["db"]
        if db is None:
            raise ProviderError("Dispatch transaction required")
        return db, engine.store.load(db, account, engine.mode)

    def validate_current(frozen):
        db, doc = current()
        if engine.unipile.get(account) is not client or client.account_id != action["account_id"]:
            return False
        p = engine.prospect(doc, action["prospect_id"])
        d = next((d for d in doc["decisions"] if d["id"] == decision_id), None)
        if not d or d != frozen_decision or doc["paused"] or doc["brief_revision"] != d["brief_revision"]:
            return False
        engine.eligible(doc, p)
        s = engine.state(doc, p["id"])
        if s["revision"] != context["revision"]:
            return False
        if context["phase"] == "prepared":
            core.check_action(s, d["purpose"], d["revision"])
        return p.get("phone_status") == "operator_verified" and _jid(p.get("phone")) == recipient

    def inspect_thread(snapshot, frozen):
        if snapshot.get("all_history") is not True or snapshot.get("account_id") != client.account_id:
            return False
        messages = snapshot.get("messages", [])
        last_out, last_in = None, None
        for m in messages:
            value = m.get("text")
            if not isinstance(value, str) or not value.strip():
                return False
            stamp = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
            if m["is_sender"]:
                if " ".join(value.split()).casefold() == " ".join(frozen["text"].split()).casefold():
                    return False
                if last_out is None or stamp >= last_out[0]:
                    last_out = (stamp, m)
            else:
                if DECLINE.search(value) or value.strip().casefold().rstrip(".! ") in {"stop", "remove me"}:
                    return False
                if last_in is None or stamp >= last_in[0]:
                    last_in = (stamp, m)
        if last_in and last_out and last_in[0] == last_out[0]:
            return False
        if last_in and (not last_out or last_in[0] > last_out[0]):
            return bool(frozen["purpose"] == "reply" and latest_inbound
                and last_in[1]["message_id"] == latest_inbound["message_id"]
                and snapshot["chat_id"] == latest_inbound["chat_id"]
                and _jid(latest_inbound["sender_id"]) == recipient)
        if frozen["purpose"] == "reply" and snapshot["chat_id"] == frozen.get("chat_id"):
            return False
        return True

    def claim(digest, frozen):
        db, doc = current()
        claims = doc.setdefault("live_dispatch_claims", {})
        if decision_id in claims:
            return False
        claims[decision_id] = {"digest": digest, "status": "claimed", "created_at": engine.stamp(doc)}
        engine.store.save(db, doc)
        return True

    def record(digest, frozen, status, evidence):
        db, doc = current()
        p = engine.prospect(doc, action["prospect_id"])
        claim_record = doc["live_dispatch_claims"][decision_id]
        if claim_record["digest"] != digest:
            return False
        source = "unipile:sha256:" + _digest({"action": frozen, "evidence": evidence})
        data = {"action_id": decision_id, "purpose": action["purpose"]}
        if status == "started":
            engine.observe(doc, p["id"], "dispatch_started", {**data, "revision": decision["revision"]}, source=source)
            context["revision"] = engine.state(doc, p["id"])["revision"]
            context["phase"] = "started"
        elif status == "verified":
            engine.observe(doc, p["id"], "dispatch_verified", {**data, "provider_id": evidence["message_id"]}, source=source)
            engine.message(doc, p, action["text"], "outbound", action["purpose"], evidence["message_id"])
            doc["messages"][-1].update(chat_id=evidence["chat_id"], provider_account_id=client.account_id,
                provider_timestamp=evidence["timestamp"], source_ref=source, group=action["purpose"] == "introduction")
            p["group_chat_id" if action["purpose"] == "introduction" else "chat_id"] = evidence["chat_id"]
            next(d for d in doc["decisions"] if d["id"] == decision_id)["status"] = "executed"
        elif status == "unknown":
            engine.observe(doc, p["id"], "dispatch_unknown", data, source=source)
        else:
            return False
        claim_record.update(status=status, evidence=evidence)
        engine.event(doc, "live_dispatch_" + status, prospect_id=p["id"], action_id=decision_id)
        engine.store.save(db, doc)
        # Commit the started/claim BEFORE any POST so a process death cannot erase
        # replay protection. Reacquire and revalidate the state before writing.
        db.commit()
        db.execute("BEGIN IMMEDIATE")
        return True

    def authorize(canonical, invoke):
        def locked_invoke():
            with engine.store.transaction() as db:
                context["db"] = db
                try:
                    return invoke()
                finally:
                    context["db"] = None
        return gate(canonical, locked_invoke)

    return execute_reviewed(client, action, gate=authorize, validate_current=validate_current,
                            inspect_thread=inspect_thread, claim=claim, record=record)

