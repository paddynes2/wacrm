"""Calendar amendment preparation and receipt verification; no writes or consent.

Callbacks are trusted host adapters, not model-supplied provider responses. The
digest detects accidental mutation; approval must separately bind that digest.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, time, timedelta
import hashlib
import json
from typing import Callable

from .calendar import (
    UTC, MAX_READ_AGE, Interval, Participant, WorkingWindow, aware_datetime,
    recheck_booking, zone,
)


def _string(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise ValueError("Required calendar identifier or evidence missing")
    return value


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Calendar proposal must be JSON serializable") from exc


def _stamp(value):
    if isinstance(value, dict):
        stamp = value.get("dateTime")
        instant = aware_datetime(stamp)
        if "timeZone" in value:
            tz = zone(value["timeZone"])
            # An explicit offset disambiguates repeated hours, but cannot make a
            # nonexistent wall time or a contradictory timezone valid.
            supplied = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if supplied.replace(tzinfo=None) != instant.astimezone(tz).replace(tzinfo=None):
                raise ValueError("Event offset does not match its IANA timezone")
        return instant.isoformat()
    return aware_datetime(value).isoformat()


def _event(value):
    if not isinstance(value, dict):
        raise ValueError("Authoritative calendar event required")
    result = deepcopy(value)
    _string(result.get("id"))
    if result.get("status") not in {"confirmed", "cancelled"}:
        raise ValueError("Unknown calendar event status")
    result["start"] = _stamp(result.get("start"))
    result["end"] = _stamp(result.get("end"))
    Interval(result["start"], result["end"])
    attendees = result.get("attendees")
    if not isinstance(attendees, list) or not attendees:
        raise ValueError("Verified event attendees required")
    normalized = []
    for attendee in attendees:
        item = {"email": attendee} if isinstance(attendee, str) else deepcopy(attendee)
        if not isinstance(item, dict):
            raise ValueError("Malformed attendee")
        email = _string(item.get("email")).casefold()
        if email.count("@") != 1 or not all(email.split("@")) or any(c.isspace() for c in email):
            raise ValueError("Attendee email required")
        item["email"] = email
        normalized.append(item)
    if len({a["email"] for a in normalized}) != len(normalized):
        raise ValueError("Duplicate attendees")
    result["attendees"] = sorted(normalized, key=lambda a: a["email"])
    _json(result)
    return result


def _read(ownership, read_event, now):
    received = read_event(**ownership)
    if not isinstance(received, dict) or any(received.get(k) != ownership[k] for k in ("account_id", "calendar_id")):
        raise ValueError("Calendar event account or calendar mismatch")
    _string(received.get("source_ref"))
    fetched = aware_datetime(received.get("fetched_at"))
    if not timedelta(0) <= aware_datetime(now()) - fetched <= MAX_READ_AGE:
        raise ValueError("Calendar event evidence is stale or future-dated")
    event = _event(received.get("event"))
    if event["id"] != ownership["event_id"]:
        raise ValueError("Calendar event identity changed")
    return event, {"source_ref": received["source_ref"], "fetched_at": fetched.isoformat()}


def _digest(proposal):
    return hashlib.sha256(_json({k: v for k, v in proposal.items() if k != "digest"}).encode()).hexdigest()


def _validate(proposal):
    if not isinstance(proposal, dict) or proposal.get("digest") != _digest(proposal):
        raise ValueError("Calendar amendment proposal was mutated")
    if proposal.get("version") != 1 or proposal.get("amendment_authorized") is not False or proposal.get("operation") not in {"reschedule", "cancel"}:
        raise ValueError("Invalid calendar amendment proposal")
    before, after, ownership = proposal.get("before"), proposal.get("after"), proposal.get("ownership")
    if not isinstance(ownership, dict) or set(ownership) != {"account_id", "calendar_id", "event_id"}:
        raise ValueError("Invalid amendment ownership")
    for value in ownership.values():
        _string(value)
    if not isinstance(after, dict) or set(after) != {"id", "status", "start", "end", "attendees"}:
        raise ValueError("Invalid amendment target")
    if _event(before) != before or before["status"] != "confirmed" or after["id"] != ownership["event_id"] or before["id"] != after["id"] or after["attendees"] != before["attendees"]:
        raise ValueError("Amendment identity or attendees changed")
    _event(after)
    if proposal["operation"] == "cancel":
        if after["status"] != "cancelled" or any(after[k] != before[k] for k in ("start", "end")):
            raise ValueError("Cancellation must preserve the original event")
    elif after["status"] != "confirmed":
        raise ValueError("Reschedule must retain confirmed status")


def _participants(rows):
    return [Participant(r["id"], r["timezone"], tuple(WorkingWindow(w["weekday"], time.fromisoformat(w["start"]), time.fromisoformat(w["end"])) for w in r["windows"])) for r in rows]


def prepare_amendment(existing: dict, operation: str, desired_slot: dict | None = None, *,
                      participants: list[Participant], bindings: dict,
                      read_event: Callable, read_freebusy: Callable,
                      now: Callable = lambda: datetime.now(UTC)) -> dict:
    """Prepare immutable-by-digest JSON. Existing includes account_id/calendar_id.

    Participant IDs are attendee emails here; callers must explicitly resolve CRM
    identities to calendar attendees. Partial calendar access cannot prove a move.
    """
    if operation not in {"reschedule", "cancel"} or not isinstance(existing, dict):
        raise ValueError("Expected reschedule or cancel")
    ownership = {"account_id": _string(existing.get("account_id")), "calendar_id": _string(existing.get("calendar_id")), "event_id": _string(existing.get("id"))}
    before = _event({k: v for k, v in existing.items() if k not in {"account_id", "calendar_id"}})
    if before["status"] != "confirmed" or aware_datetime(before["start"]) <= aware_datetime(now()):
        raise ValueError("Only a future confirmed event can be amended")
    if not isinstance(participants, list) or not participants or not all(isinstance(p, Participant) for p in participants) or len({p.id.casefold() for p in participants}) != len(participants) or {p.id.casefold() for p in participants} != {a["email"] for a in before["attendees"]}:
        raise ValueError("Calendar participants differ from the verified event")
    if not isinstance(bindings, dict) or set(bindings) != {p.id for p in participants}:
        raise ValueError("Explicit bindings for all participants required")
    for binding in bindings.values():
        if not isinstance(binding, dict) or set(binding) != {"account_id", "calendar_ids"} or not isinstance(binding["calendar_ids"], list) or not binding["calendar_ids"] or len(set(binding["calendar_ids"])) != len(binding["calendar_ids"]):
            raise ValueError("Invalid participant calendar binding")
        _string(binding["account_id"])
        for calendar in binding["calendar_ids"]:
            _string(calendar)
    if not any(b["account_id"] == ownership["account_id"] and ownership["calendar_id"] in b["calendar_ids"] for b in bindings.values()):
        raise ValueError("Event ownership is not bound to a participant calendar")
    latest, evidence = _read(ownership, read_event, now)
    if latest != before:
        raise ValueError("Calendar event changed; refresh before preparing an amendment")
    after = {"id": before["id"], "status": "cancelled" if operation == "cancel" else "confirmed", "start": before["start"], "end": before["end"], "attendees": before["attendees"]}
    calendar_evidence = {}
    if operation == "cancel":
        if desired_slot is not None:
            raise ValueError("Cancellation cannot specify a new slot")
    else:
        if not isinstance(desired_slot, dict) or set(desired_slot) != {"start", "end"}:
            raise ValueError("Exact desired slot required")
        slot = Interval(desired_slot["start"], desired_slot["end"])
        old = Interval(before["start"], before["end"])
        if slot.start < old.end and slot.end > old.start:
            raise ValueError("Overlapping moves require event-aware availability; aggregated busy time cannot safely exclude this event")
        check = recheck_booking(desired_slot, participants, bindings, read_freebusy, now=now)
        calendar_evidence = check["calendar_evidence"]
        after.update(start=slot.start.isoformat(), end=slot.end.isoformat())
    if aware_datetime(before["start"]) <= aware_datetime(now()) or aware_datetime(now()) - aware_datetime(evidence["fetched_at"]) > MAX_READ_AGE:
        raise ValueError("Event evidence expired during preparation")
    proposal = {"version": 1, "operation": operation, "ownership": ownership, "before": before, "after": after, "participants": [{"id": p.id, "timezone": p.timezone, "windows": [{"weekday": w.weekday, "start": w.start.isoformat(), "end": w.end.isoformat()} for w in p.windows]} for p in participants], "bindings": deepcopy(bindings), "event_evidence": evidence, "calendar_evidence": calendar_evidence, "amendment_authorized": False}
    proposal["digest"] = _digest(proposal)
    return proposal


def recheck_amendment(proposal: dict, *, read_event: Callable, read_freebusy: Callable,
                      now: Callable = lambda: datetime.now(UTC)) -> dict:
    """Fresh preparation against the same frozen before/after; no authorization."""
    _validate(proposal)
    existing = {**proposal["before"], **{k: proposal["ownership"][k] for k in ("account_id", "calendar_id")}}
    slot = {k: proposal["after"][k] for k in ("start", "end")} if proposal["operation"] == "reschedule" else None
    checked = prepare_amendment(existing, proposal["operation"], slot, participants=_participants(proposal["participants"]), bindings=proposal["bindings"], read_event=read_event, read_freebusy=read_freebusy, now=now)
    if checked["after"] != proposal["after"]:
        raise ValueError("Amendment target drifted")
    return {"status": "rechecked", "digest": proposal["digest"], "event_evidence": checked["event_evidence"], "calendar_evidence": checked["calendar_evidence"], "amendment_authorized": False}


def verify_amendment(proposal: dict, *, read_event: Callable,
                     now: Callable = lambda: datetime.now(UTC)) -> bool:
    """A missing/404 event is unknown, never proof of cancellation.

    Sparse provider cancellation tombstones lack attendee/time evidence and are
    conservatively rejected; a host adapter needs a fuller authoritative receipt.
    """
    try:
        _validate(proposal)
        actual, _ = _read(proposal["ownership"], read_event, now)
        return all(actual.get(key) == value for key, value in proposal["after"].items())
    except Exception:
        return False
