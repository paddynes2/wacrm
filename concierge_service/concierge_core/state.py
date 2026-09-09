"""Pure concierge state rules extracted from Fleet; see docs/CORE-EXTRACTION.md.

Storage, external dispatch and approval are host responsibilities.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any


def _parse(value: str) -> datetime:
    ts = datetime.fromisoformat(value)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


MAX_EVENTS = 10000



SCOPES = frozenset({"contact", "introduction", "group", "scheduling", "booking"})



OBSERVATIONS = frozenset({"identified", "consent", "inbound", "manual_outbound", "takeover",
                         "opt_out", "declined", "resume", "dispatch_started",
                         "dispatch_verified", "dispatch_unknown", "dispatch_not_sent", "reconciled_absent",
                         "booking_verified", "meeting_attended"})



FIELDS = frozenset({"event_id", "pursuit_id", "account_id", "kind", "occurred_at",
                    "source_ref", "data"})



DATA_FIELDS = {
    "identified": {"crm_ref", "principal_id", "recipient_id", "name", "principal_name",
                   "offer", "fit", "profile_url"},
    "consent": {"party_id", "scope", "proposal_id"},
    "inbound": {"message_id", "chat_id", "sender_id"},
    "manual_outbound": {"message_id", "chat_id"},
    "takeover": {"reason"},
    "opt_out": {"party_id"}, "declined": {"party_id"},
    "resume": {"reason"},
    "dispatch_started": {"action_id", "purpose", "revision"},
    "dispatch_verified": {"action_id", "purpose", "provider_id"},
    "dispatch_unknown": {"action_id", "purpose"},
    "dispatch_not_sent": {"action_id", "purpose"},
    "reconciled_absent": {"action_id"},
    "booking_verified": {"event_id", "request_sha"},
    "meeting_attended": {"event_id"},
}



def _text(value: Any, name: str, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} requires nonempty text, at most {limit} characters")
    if any(ord(c) < 32 for c in value):
        raise ValueError(f"{name} contains control characters")
    return value



def validate(event: dict) -> dict:
    if not isinstance(event, dict) or set(event) != FIELDS:
        raise ValueError("observation has missing or unknown fields")
    e = json.loads(json.dumps(event, allow_nan=False))
    for key in FIELDS - {"data"}:
        _text(e[key], key)
    if e["kind"] not in OBSERVATIONS:
        raise ValueError("unknown observation kind")
    try:
        timestamp = _parse(e["occurred_at"])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must have an offset")
        # clock.parse may normalise naive input; check the source too.
        from datetime import datetime
        original = datetime.fromisoformat(e["occurred_at"].replace("Z", "+00:00"))
        if original.tzinfo is None:
            raise ValueError("timestamp must have an offset")
    except (TypeError, ValueError) as exc:
        raise ValueError("occurred_at requires an ISO timestamp with offset") from exc
    data = e["data"]
    allowed = DATA_FIELDS[e["kind"]]
    optional = {"request_sha"} if e["kind"] == "dispatch_verified" else set()
    if not isinstance(data, dict) or not allowed.issubset(data) or set(data) - allowed - optional:
        raise ValueError("observation data has missing or unknown fields")
    for key, val in data.items():
        _text(val, key, 2000 if key in {"offer", "fit"} else 500)
    if e["kind"] == "consent" and data["scope"] not in SCOPES:
        raise ValueError("unknown consent scope")
    return e



def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()



def derive(observations: list[dict]) -> dict:
    """Pure reducer. Arrival order controls cancellation; timestamps cannot undo a stop.

    Consent references a proposal (here the external pursuit id). It cannot confer tool
    permissions. A human must explicitly resume after takeover; opt-out is permanent in
    this pursuit, including when older evidence arrives later.
    """
    if len(observations) > MAX_EVENTS:
        raise ValueError("too many observations; read is incomplete")
    seen: dict[str, dict] = {}
    events = []
    identity = None
    binding = None
    consents: set[tuple[str, str]] = set()
    stopped = None
    manual = False
    unresolved: dict[str, str] = {}
    sent: set[str] = set()
    introduced = booked = attended = False
    latest_inbound = None
    latest_inbound_at = None
    attempted: set[str] = set()
    booking_id = None
    inbounds: dict[str, tuple[Any, dict]] = {}
    answered: set[str] = set()
    replies: dict[str, str] = {}
    for raw in observations:
        e = validate(raw)
        key = e["event_id"]
        if key in seen:
            if seen[key] != e:
                raise ValueError("event id collision")
            continue
        seen[key] = e
        this_binding = (e["pursuit_id"], e["account_id"])
        if binding is not None and binding != this_binding:
            raise ValueError("mixed pursuit or account evidence")
        binding = this_binding
        kind, d = e["kind"], e["data"]
        if kind == "identified":
            if identity is not None and identity != d:
                raise ValueError("identity changed; use a new pursuit")
            if d["principal_id"] == d["recipient_id"]:
                raise ValueError("introduction needs two different parties")
            identity = d
        elif identity is None:
            raise ValueError("identity evidence must precede observations")
        elif kind == "consent":
            if d["party_id"] not in {identity["principal_id"], identity["recipient_id"]}:
                raise ValueError("consent from an unrelated party")
            if d["proposal_id"] != e["pursuit_id"]:
                raise ValueError("consent names a different proposal")
            consents.add((d["party_id"], d["scope"]))
        elif kind in {"opt_out", "declined"}:
            if d["party_id"] not in {identity["principal_id"], identity["recipient_id"]}:
                raise ValueError("stop from an unrelated party")
            stopped = "opted_out" if kind == "opt_out" or stopped == "opted_out" else "declined"
        elif kind in {"manual_outbound", "takeover"}:
            manual = True
        elif kind == "resume":
            manual = False
        elif kind == "inbound":
            if d["sender_id"] not in {identity["principal_id"], identity["recipient_id"]}:
                raise ValueError("inbound from an unrelated party")
            if latest_inbound_at is None or _parse(e["occurred_at"]) > latest_inbound_at:
                latest_inbound = d
                latest_inbound_at = _parse(e["occurred_at"])
            prior_inbound = inbounds.get(d["sender_id"])
            when = _parse(e["occurred_at"])
            if prior_inbound is None or when > prior_inbound[0]:
                inbounds[d["sender_id"]] = (when, d)
        elif kind == "dispatch_started":
            if d["action_id"] in attempted:
                raise ValueError("duplicate dispatch")
            attempted.add(d["action_id"])
            unresolved[d["action_id"]] = d["purpose"]
            if d["purpose"] == "reply":
                waiting = sorted((item for item in inbounds.values() if item[1]["message_id"] not in answered), key=lambda item: item[0])
                if not waiting:
                    raise ValueError("reply dispatch has no unanswered observation")
                replies[d["action_id"]] = waiting[-1][1]["message_id"]
        elif kind in {"dispatch_verified", "dispatch_unknown", "dispatch_not_sent", "reconciled_absent"}:
            aid = d["action_id"]
            if aid not in unresolved:
                raise ValueError("result without a pending dispatch")
            if kind != "reconciled_absent" and unresolved[aid] != d["purpose"]:
                raise ValueError("result belongs to another action")
            if kind == "dispatch_verified":
                sent.add(aid)
                introduced |= d["purpose"] == "introduction"
                if d["purpose"] == "reply":
                    answered.add(replies[aid])
                if d["purpose"] == "booking":
                    if not re.fullmatch(r"[0-9a-f]{64}", d.get("request_sha", "")):
                        raise ValueError("verified booking must include its request digest")
                    booked, booking_id = True, d["provider_id"]
            if kind != "dispatch_unknown":
                del unresolved[aid]
        elif kind == "booking_verified":
            if not introduced or not all((party, "booking") in consents for party in
                                         (identity["principal_id"], identity["recipient_id"])):
                raise ValueError("booking evidence requires introduction and both parties' booking agreement")
            booked = True
            booking_id = d["event_id"]
        elif kind == "meeting_attended":
            if not booked or d["event_id"] != booking_id:
                raise ValueError("attendance requires the same verified booking")
            attended = True
        events.append(e)
    if not identity:
        return {"status": "unconfigured", "revision": _digest([]), "events": 0}
    both = {identity["principal_id"], identity["recipient_id"]}
    waiting = sorted((item for item in inbounds.values() if item[1]["message_id"] not in answered), key=lambda item: item[0])
    if waiting:
        latest_inbound = waiting[-1][1]
    def agreed(scope: str) -> bool:
        return all((party, scope) in consents for party in both)
    status = (stopped or ("human_owned" if manual else None) or
              ("reconcile" if unresolved else None) or
              ("attended" if attended else "booked" if booked else
               "scheduling" if introduced and agreed("scheduling") else
               "introduced" if introduced else "agreed" if agreed("introduction") else
               "replied" if latest_inbound else "proposed"))
    return {"status": status, "revision": _digest(events), "events": len(events),
            "pursuit_id": binding[0], "account_id": binding[1], "identity": identity,
            "consents": [list(x) for x in sorted(consents)], "group_agreed": agreed("group"),
            "introduction_agreed": agreed("introduction"), "scheduling_agreed": agreed("scheduling"),
            "booking_agreed": agreed("booking"), "unresolved": unresolved,
            "introduced": introduced, "booking_id": booking_id,
            "reply_required": bool(waiting),
            "latest_inbound": latest_inbound, "sent_actions": sorted(sent)}



def scoped_view(all_events: list[dict], pursuit_id: str) -> dict:
    state = derive([e for e in all_events if e["pursuit_id"] == pursuit_id])
    if state["status"] == "unconfigured":
        return state
    parties = {state["identity"]["principal_id"], state["identity"]["recipient_id"]}
    external_stops = [e for e in all_events if e["kind"] == "opt_out"
                      and e["account_id"] == state["account_id"] and e["pursuit_id"] != pursuit_id
                      and e["data"]["party_id"] in parties]
    if external_stops:
        # "Stop contact" belongs to a person on this account, not just this opportunity.
        # Starting a fresh pursuit must not silently revoke their opt-out.
        state["status"] = "opted_out"
        state["revision"] = _digest([state["revision"], external_stops])
    return state



def check_action(state: dict, purpose: str, revision: str) -> None:
    _text(purpose, "purpose")
    _text(revision, "revision")
    if state["revision"] != revision:
        raise ValueError("new evidence invalidated this action; reload and restage")
    if state["status"] in {"unconfigured", "human_owned", "declined", "opted_out", "reconcile", "attended"}:
        raise ValueError(f"concierge is {state['status']}; no dispatch")
    consents = {tuple(x) for x in state["consents"]}
    if purpose == "approach":
        if (state["identity"]["recipient_id"], "contact") not in consents:
            raise ValueError("initial contact eligibility evidence is missing")
    elif purpose == "reply":
        if not state["latest_inbound"] or not state["reply_required"]:
            raise ValueError("reply requires a verified inbound")
    elif purpose == "introduction":
        if state["reply_required"]:
            raise ValueError("acknowledge the pending reply in its conversation before introducing")
        if state["introduced"]:
            raise ValueError("introduction already verified")
        if not state["introduction_agreed"] or not state["group_agreed"]:
            raise ValueError("both parties must agree to the introduction and group")
    elif purpose in {"schedule", "booking_link"}:
        if not state["scheduling_agreed"]:
            raise ValueError("both parties must agree to scheduling")
    elif purpose == "booking":
        if state["booking_id"]:
            raise ValueError("meeting already booked; reconcile or amend the existing event")
        if not state["introduced"] or not state["scheduling_agreed"] or not state["booking_agreed"]:
            raise ValueError("introduction and both parties' scheduling and booking agreement required")
    else:
        raise ValueError("unknown dispatch purpose")



def introduction_draft(state: dict) -> str:
    d = state["identity"]
    return (f"Hi {d['name']}, I'm Chris, {d['principal_name']}'s AI assistant. "
            f"{d['offer']} {d['fit']} Would you be open to an introduction?")

