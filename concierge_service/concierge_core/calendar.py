"""B-2580 calendar proposals. No calendar writes or invitation transport lives here.

Provider reads are supplied by a trusted host calendar adapter. Feed its raw
free/busy data into parse_freebusy; an error or incomplete coverage is never free time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
MAX_HORIZON = timedelta(days=93)
MAX_READ_AGE = timedelta(minutes=2)


def zone(name: str) -> ZoneInfo:
    if not isinstance(name, str) or not name:
        raise ValueError("An IANA timezone is required")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Unknown IANA timezone") from exc


def aware_datetime(value: str | datetime) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if not isinstance(result, datetime) or result.utcoffset() is None:
            raise ValueError("Timestamp must include an offset")
        utc = result.astimezone(UTC)
        if utc.astimezone(result.tzinfo).replace(tzinfo=None) != result.replace(tzinfo=None):
            raise ValueError("Nonexistent local timestamp")
        return utc
    except (TypeError, OverflowError) as exc:
        raise ValueError("Invalid timestamp") from exc


def local_datetime(value: str | datetime, timezone_name: str, *, fold: int | None = None) -> datetime:
    """Resolve wall time explicitly; ambiguous DST times require a fold selection."""
    wall = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(wall, datetime) or wall.tzinfo is not None or fold not in (None, 0, 1):
        raise ValueError("Expected naive wall time and optional fold 0 or 1")
    tz = zone(timezone_name)
    candidates = [wall.replace(tzinfo=tz, fold=f) for f in (0, 1)]
    valid = [c for c in candidates if c.astimezone(UTC).astimezone(tz).replace(tzinfo=None) == wall]
    if not valid:
        raise ValueError("Nonexistent local time")
    if candidates[0].utcoffset() != candidates[1].utcoffset() and fold is None:
        raise ValueError("Ambiguous local time requires fold")
    return candidates[fold or 0].astimezone(UTC)


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime

    def __post_init__(self):
        object.__setattr__(self, "start", aware_datetime(self.start))
        object.__setattr__(self, "end", aware_datetime(self.end))
        if self.end <= self.start:
            raise ValueError("Interval must have positive duration")


@dataclass(frozen=True)
class WorkingWindow:
    weekday: int
    start: time
    end: time

    def __post_init__(self):
        if type(self.weekday) is not int or self.weekday not in range(7):
            raise ValueError("Weekday must be 0..6")
        if not isinstance(self.start, time) or not isinstance(self.end, time):
            raise ValueError("Working hours require time values")
        if self.start.tzinfo or self.end.tzinfo or self.end <= self.start:
            raise ValueError("Working windows must be naive, same-day, increasing")


@dataclass(frozen=True)
class Participant:
    id: str
    timezone: str
    windows: tuple[WorkingWindow, ...]
    busy: tuple[Interval, ...] | None = None

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Participant id required")
        zone(self.timezone)
        if not self.windows or not all(isinstance(w, WorkingWindow) for w in self.windows):
            raise ValueError("Explicit working windows required")
        if self.busy is not None and not all(isinstance(b, Interval) for b in self.busy):
            raise ValueError("Invalid busy intervals")
        object.__setattr__(self, "windows", tuple(self.windows))
        if self.busy is not None:
            object.__setattr__(self, "busy", tuple(self.busy))


def parse_freebusy(payload: dict, calendar_ids: list[str], start: str | datetime,
                   end: str | datetime) -> dict[str, tuple[Interval, ...]]:
    """Parse Google freeBusy response, optionally inside a successful Composio envelope."""
    requested = Interval(start, end)
    if not calendar_ids or len(set(calendar_ids)) != len(calendar_ids) or not all(
            isinstance(i, str) and i.strip() for i in calendar_ids):
        raise ValueError("Distinct calendar ids required")
    if not isinstance(payload, dict):
        raise ValueError("Invalid provider response")
    if "data" in payload:
        if payload.get("successful") is not True or payload.get("error"):
            raise ValueError("Calendar provider failed")
        payload = payload["data"]
    if not isinstance(payload, dict) or payload.get("error") or payload.get("errors"):
        raise ValueError("Calendar provider failed")
    try:
        coverage = Interval(payload["timeMin"], payload["timeMax"])
        calendars = payload["calendars"]
        if coverage.start > requested.start or coverage.end < requested.end or not isinstance(calendars, dict):
            raise ValueError("Incomplete calendar coverage")
        result = {}
        for key in calendar_ids:
            item = calendars[key]
            if not isinstance(item, dict) or item.get("errors") or not isinstance(item.get("busy"), list):
                raise ValueError("Calendar unavailable")
            result[key] = tuple(Interval(b["start"], b["end"]) for b in item["busy"])
        return result
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed or missing calendar data") from exc


def _within_hours(slot: Interval, person: Participant) -> bool:
    local = slot.start.astimezone(zone(person.timezone))
    for window in person.windows:
        if window.weekday != local.weekday():
            continue
        try:
            # The later start and earlier end conservatively bound repeated DST hours.
            # A skipped boundary is unavailable, rather than silently shifted an hour.
            lower = local_datetime(datetime.combine(local.date(), window.start), person.timezone, fold=1)
            upper = local_datetime(datetime.combine(local.date(), window.end), person.timezone, fold=0)
        except ValueError:
            continue
        if lower <= slot.start and slot.end <= upper:
            return True
    return False


def propose_slots(start: str | datetime, end: str | datetime, participants: list[Participant],
                  *, duration_minutes: int = 30, step_minutes: int = 15, limit: int = 3,
                  booking_link: str | None = None) -> dict[str, Any]:
    horizon = Interval(start, end)
    if horizon.end - horizon.start > MAX_HORIZON:
        raise ValueError("Scheduling horizon exceeds 93 days")
    if any(type(v) is not int for v in (duration_minutes, step_minutes, limit)) or not (
            1 <= duration_minutes <= 480 and 1 <= step_minutes <= 1440 and 1 <= limit <= 50):
        raise ValueError("Invalid scheduling limits")
    if not participants or not all(isinstance(p, Participant) for p in participants) or len(
            {p.id for p in participants}) != len(participants):
        raise ValueError("Distinct participants required")
    if booking_link is not None:
        parsed = urlsplit(booking_link)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or any(
                ord(c) < 33 for c in booking_link):
            raise ValueError("Booking link must be an HTTPS URL without credentials")
    unknown = [p.id for p in participants if p.busy is None]
    slots = []
    cursor = horizon.start
    duration = timedelta(minutes=duration_minutes)
    while cursor + duration <= horizon.end and len(slots) < limit:
        candidate = Interval(cursor, cursor + duration)
        if all(_within_hours(candidate, p) and not any(
                b.start < candidate.end and b.end > candidate.start for b in (p.busy or ()))
               for p in participants):
            slots.append({"start": candidate.start.isoformat(), "end": candidate.end.isoformat(),
                          "local": {p.id: {"start": candidate.start.astimezone(zone(p.timezone)).isoformat(),
                                            "end": candidate.end.astimezone(zone(p.timezone)).isoformat(),
                                            "timezone": p.timezone} for p in participants}})
            # Distinct options should not compete for overlapping minutes of the same
            # meeting; preserve the search grid while skipping the offered interval.
            skip_steps = (duration_minutes + step_minutes - 1) // step_minutes
            cursor += timedelta(minutes=skip_steps * step_minutes)
            continue
        cursor += timedelta(minutes=step_minutes)
    return {"status": ("needs_calendar_access" if len(unknown) == len(participants) else
                       "tentative" if unknown else "proposed") if slots else "needs_exception",
            "slots": slots, "unverified_participants": unknown,
            "fallback": {"kind": "booking_link", "url": booking_link} if booking_link else None,
            "booking_authorized": False}


def stage_booking(slot: dict, attendees: list[str], summary: str) -> dict:
    """Build a proposal only. Host approval must authorize execution."""
    interval = Interval(slot["start"], slot["end"])
    if not attendees or not all(isinstance(a, str) and a.count("@") == 1 and
                               not any(c.isspace() for c in a) and all(a.split("@")) for a in attendees):
        raise ValueError("Attendee email addresses required")
    normalized = sorted(set(a.casefold() for a in attendees))
    if len(normalized) != len(attendees):
        raise ValueError("Duplicate attendees")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 500:
        raise ValueError("Meeting summary required, at most 500 characters")
    return {"status": "needs_approval", "toolkit": "googlecalendar",
            "slug": "GOOGLECALENDAR_CREATE_EVENT", "booking_authorized": False,
            "proposal": {"start": interval.start.isoformat(), "end": interval.end.isoformat(),
                         "attendees": normalized, "summary": summary}}


def verify_booking(request: dict, event: dict) -> bool:
    """Verify provider evidence; a response id alone never proves correct booking."""
    try:
        expected = request["proposal"]
        attendees = event["attendees"]
        return bool(event.get("id") and event.get("status") == "confirmed" and
                    event.get("summary") == expected["summary"] and
                    aware_datetime(event["start"]["dateTime"]) == aware_datetime(expected["start"]) and
                    aware_datetime(event["end"]["dateTime"]) == aware_datetime(expected["end"]) and
                    isinstance(attendees, list) and
                    sorted(a["email"].casefold() for a in attendees) == expected["attendees"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def read_and_propose(start: str | datetime, end: str | datetime,
                     participants: list[Participant], bindings: dict[str, dict],
                     read: Callable[..., dict], *,
                     now: Callable[[], datetime] = lambda: datetime.now(UTC),
                     **options) -> dict:
    """Operational boundary: read the requested horizon and immediately propose.

    ``bindings`` is host configuration, never prospect/model input. Each participant
    maps to account_id/calendar_ids. The injected reader MUST use the existing gated
    calendar read seam and return host-captured account_id, fetched_at, source_ref and
    raw payload. Do not parse the model-visible/truncated text fence as calendar data.
    Pure propose_slots remains useful for simulations, not evidence of availability.
    """
    horizon = Interval(start, end)
    if not isinstance(participants, list) or not participants or not all(
            isinstance(p, Participant) for p in participants):
        raise ValueError("Calendar participants required")
    # Validate limits/participants before spending a provider read. Ignore caller busy
    # data: only the reads below can establish operational calendar availability.
    provisional = [Participant(p.id, p.timezone, p.windows, None) for p in participants]
    propose_slots(horizon.start, horizon.end, provisional, **options)
    if not isinstance(bindings, dict) or set(bindings) - {p.id for p in participants}:
        raise ValueError("Calendar binding names an unrelated participant")
    if horizon.start <= aware_datetime(now()):
        raise ValueError("Scheduling horizon must be in the future")
    resolved, evidence = [], {}
    for person in provisional:
        binding = bindings.get(person.id)
        if binding is None:
            resolved.append(person)
            continue
        if not isinstance(binding, dict) or set(binding) != {"account_id", "calendar_ids"}:
            raise ValueError("Explicit calendar account and ids required")
        account, ids = binding["account_id"], binding["calendar_ids"]
        if not isinstance(account, str) or not account.strip() or not isinstance(ids, list) or not ids or any(
                not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("Invalid calendar account or ids")
        received = read(participant_id=person.id, account_id=account, calendar_ids=list(ids),
                        start=horizon.start.isoformat(), end=horizon.end.isoformat())
        if not isinstance(received, dict) or received.get("account_id") != account:
            raise ValueError("Calendar read account mismatch")
        source = received.get("source_ref")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("Calendar read evidence reference required")
        fetched = aware_datetime(received.get("fetched_at"))
        age = aware_datetime(now()) - fetched
        if not timedelta(0) <= age <= MAX_READ_AGE:
            raise ValueError("Calendar read is stale or future-dated")
        busy = parse_freebusy(received.get("payload"), ids, horizon.start, horizon.end)
        resolved.append(Participant(person.id, person.timezone, person.windows,
                                    tuple(interval for key in ids for interval in busy[key])))
        evidence[person.id] = {"account_id": account, "calendar_ids": list(ids),
                               "fetched_at": fetched.isoformat(), "source_ref": source,
                               "start": horizon.start.isoformat(), "end": horizon.end.isoformat()}
    final_now = aware_datetime(now())
    if horizon.start <= final_now or any(not timedelta(0) <= final_now - aware_datetime(e["fetched_at"]) <= MAX_READ_AGE
                                       for e in evidence.values()):
        raise ValueError("Calendar evidence expired during reads")
    result = propose_slots(horizon.start, horizon.end, resolved, **options)
    result["calendar_evidence"] = evidence
    return result


def recheck_booking(slot: dict, participants: list[Participant], bindings: dict[str, dict],
                    read: Callable[..., dict], *,
                    now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> dict:
    """Fresh read of exactly the chosen slot; this neither books nor authorizes writes.

    Missing participant calendars require human coordination rather than treating an
    earlier tentative proposal as proof that all attendees are free.
    """
    interval = Interval(slot["start"], slot["end"])
    seconds = (interval.end - interval.start).total_seconds()
    if seconds % 60:
        raise ValueError("Booking duration must be whole minutes")
    result = read_and_propose(interval.start, interval.end, participants, bindings, read,
                              now=now, duration_minutes=int(seconds // 60), limit=1)
    if result["status"] != "proposed" or not result["slots"]:
        raise ValueError("Booking slot is busy, outside hours, or requires calendar confirmation")
    return {"status": "rechecked", "slot": result["slots"][0],
            "calendar_evidence": result["calendar_evidence"], "booking_authorized": False}
