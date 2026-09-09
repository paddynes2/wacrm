from copy import deepcopy
from datetime import datetime, time, timedelta
import json
import pytest

from concierge_core.calendar import UTC, Participant, WorkingWindow
from concierge_core.amendment import prepare_amendment, recheck_amendment, verify_amendment

NOW = datetime(2026, 9, 8, 8, tzinfo=UTC)


@pytest.fixture
def seam():
    existing = {"account_id": "account", "calendar_id": "calendar", "id": "event", "status": "confirmed", "start": {"dateTime": "2026-09-09T10:00:00+02:00", "timeZone": "Africa/Johannesburg"}, "end": {"dateTime": "2026-09-09T10:30:00+02:00", "timeZone": "Africa/Johannesburg"}, "attendees": [{"email": "patrick@example.com"}, {"email": "bond@example.com"}], "etag": "version-one"}
    people = [Participant(email, "Africa/Johannesburg", tuple(WorkingWindow(d, time(9), time(17)) for d in range(5))) for email in ("patrick@example.com", "bond@example.com")]
    bindings = {p.id: {"account_id": "account", "calendar_ids": ["calendar"]} for p in people}
    state = {"event": {k: deepcopy(v) for k, v in existing.items() if k not in ("account_id", "calendar_id")}, "busy": [], "calls": []}

    def read_event(**kwargs):
        state["calls"].append(kwargs)
        return {"account_id": state.get("account", "account"), "calendar_id": state.get("calendar", "calendar"), "fetched_at": state.get("fetched", NOW.isoformat()), "source_ref": "event-read", "event": deepcopy(state["event"])}

    def read_freebusy(**kwargs):
        return {"account_id": "account", "source_ref": "busy-read", "fetched_at": NOW.isoformat(), "payload": {"timeMin": kwargs["start"], "timeMax": kwargs["end"], "calendars": {"calendar": {"busy": state["busy"]}}}}

    options = dict(participants=people, bindings=bindings, read_event=read_event, read_freebusy=read_freebusy, now=lambda: NOW)
    return existing, state, options


def prepare(seam, operation="reschedule", slot=None):
    existing, _, options = seam
    return prepare_amendment(existing, operation, slot if slot is not None else ({"start": "2026-09-10T08:00:00Z", "end": "2026-09-10T08:30:00Z"} if operation == "reschedule" else None), **options)


def callbacks(options):
    return {k: options[k] for k in ("read_event", "read_freebusy", "now")}


def verify(proposal, options):
    return verify_amendment(proposal, read_event=options["read_event"], now=options["now"])


def test_proposal_json_recheck_and_verify(seam):
    proposal = prepare(seam)
    existing, state, options = seam
    assert json.loads(json.dumps(proposal)) == proposal
    assert proposal["amendment_authorized"] is False
    assert recheck_amendment(proposal, **callbacks(options))["digest"] == proposal["digest"]
    assert not verify(proposal, options)
    state["event"].update(proposal["after"])
    state["event"]["etag"] = "version-two"
    assert verify(proposal, options)
    assert all(set(call) == {"account_id", "calendar_id", "event_id"} for call in state["calls"])
    assert existing["start"]["timeZone"] == "Africa/Johannesburg"


def test_cancel_requires_explicit_complete_receipt(seam):
    proposal = prepare(seam, "cancel")
    _, state, options = seam
    assert not verify(proposal, options)
    state["event"]["status"] = "cancelled"
    assert verify(proposal, options)
    state["event"] = {"id": "event", "status": "cancelled"}
    assert not verify(proposal, options)
    state["event"] = None
    assert not verify(proposal, options)
    assert not verify_amendment(proposal, read_event=lambda **kw: (_ for _ in ()).throw(ValueError("404")), now=options["now"])


@pytest.mark.parametrize("change", [
    {"id": "other"}, {"status": "cancelled"}, {"status": "tentative"},
    {"etag": "changed"}, {"attendees": [{"email": "stranger@example.com"}]},
    {"start": "2026-09-09T08:15:00Z"}, {"attendees": []},
])
def test_authoritative_drift_blocks_prepare_and_recheck(seam, change):
    proposal = prepare(seam)
    _, state, options = seam
    state["event"].update(change)
    with pytest.raises(ValueError): prepare(seam)
    with pytest.raises(ValueError): recheck_amendment(proposal, **callbacks(options))


@pytest.mark.parametrize("key,value", [("account", "foreign"), ("calendar", "foreign"), ("fetched", "2026-09-08T07:00:00Z"), ("fetched", "2026-09-08T09:00:00Z")])
def test_bad_ownership_and_stale_evidence(seam, key, value):
    seam[1][key] = value
    with pytest.raises(ValueError): prepare(seam)


@pytest.mark.parametrize("slot", [
    {"start": "2026-09-09T08:15:00Z", "end": "2026-09-09T08:45:00Z"},
    {"start": "2026-09-07T08:00:00Z", "end": "2026-09-07T08:30:00Z"},
    {"start": "2026-09-10T08:00:00", "end": "2026-09-10T08:30:00"},
    {"start": "2026-09-10T08:00:00Z", "end": "2026-09-10T08:00:00Z"},
    {"start": "2026-09-10T23:00:00Z", "end": "2026-09-10T23:30:00Z"},
])
def test_invalid_or_unavailable_slot(seam, slot):
    with pytest.raises(ValueError): prepare(seam, slot=slot)


def test_busy_not_subtracted_and_incomplete_calendar_refused(seam):
    seam[1]["busy"] = [{"start": "2026-09-10T08:00:00Z", "end": "2026-09-10T08:30:00Z"}]
    with pytest.raises(ValueError): prepare(seam)
    seam[1]["busy"] = []
    seam[2]["bindings"].pop("bond@example.com")
    with pytest.raises(ValueError): prepare(seam)


@pytest.mark.parametrize("field", ["after", "before", "ownership", "participants", "bindings", "amendment_authorized"])
def test_mutation_never_passes_recheck_or_verification(seam, field):
    proposal = prepare(seam)
    proposal[field] = True
    with pytest.raises(ValueError): recheck_amendment(proposal, **callbacks(seam[2]))
    assert not verify(proposal, seam[2])


def test_dst_nonexistent_provider_wall_time_rejected(seam):
    seam[0]["start"] = {"dateTime": "2027-03-14T02:00:00-05:00", "timeZone": "America/New_York"}
    with pytest.raises(ValueError, match="offset"): prepare(seam)


def test_dst_repeated_time_explicit_offset_is_valid(seam):
    for item in (seam[0], seam[1]["event"]):
        item["start"] = {"dateTime": "2026-11-01T01:00:00-05:00", "timeZone": "America/New_York"}
        item["end"] = {"dateTime": "2026-11-01T01:30:00-05:00", "timeZone": "America/New_York"}
    assert prepare(seam, "cancel")["before"]["start"] == "2026-11-01T06:00:00+00:00"


def test_clock_advance_rejects_past_original_event(seam):
    proposal = prepare(seam)
    options = callbacks(seam[2])
    options["now"] = lambda: NOW + timedelta(days=3)
    with pytest.raises(ValueError): recheck_amendment(proposal, **options)


def test_verification_rejects_changed_attendees_or_wrong_after_time(seam):
    proposal = prepare(seam)
    seam[1]["event"].update(deepcopy(proposal["after"]))
    seam[1]["event"]["attendees"][0]["email"] = "wrong@example.com"
    assert not verify(proposal, seam[2])


def test_cancel_never_reads_availability(seam):
    seam[2]["read_freebusy"] = lambda **kw: pytest.fail("Cancellation must not query freebusy")
    assert prepare(seam, "cancel")["after"]["status"] == "cancelled"
