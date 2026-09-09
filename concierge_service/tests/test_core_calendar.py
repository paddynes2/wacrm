"""Scheduling boundary and adversarial provider tests; no live calendar writes."""
from copy import deepcopy
from datetime import datetime, time, timedelta

import pytest

from concierge_core.calendar import (
    Interval, Participant, WorkingWindow, aware_datetime, local_datetime,
    parse_freebusy, propose_slots, stage_booking, verify_booking,
    read_and_propose, recheck_booking,
)

START = "2026-09-15T07:00:00Z"
END = "2026-09-15T16:00:00Z"
READ_NOW = aware_datetime("2026-09-14T12:00:00Z")


def calendar_reader(**kwargs):
    return {"account_id": kwargs["account_id"], "fetched_at": READ_NOW.isoformat(),
            "source_ref": "fleet:calendar:read-1", "payload": response()}


def binding():
    return {"patrick": {"account_id": "owner-calendar", "calendar_ids": ["primary"]}}


def test_operational_calendar_read_binds_horizon_and_ignores_caller_busy():
    result = read_and_propose(START, END, [person(busy=None)], binding(), calendar_reader,
                               now=lambda: READ_NOW)
    assert result["status"] == "proposed"
    assert result["calendar_evidence"]["patrick"]["account_id"] == "owner-calendar"
    with pytest.raises(ValueError, match="coverage"):
        read_and_propose("2026-09-16T07:00:00Z", "2026-09-16T16:00:00Z",
                         [person()], binding(), calendar_reader, now=lambda: READ_NOW)


@pytest.mark.parametrize("change", [
    {"account_id": "other-customer"}, {"fetched_at": "2026-09-14T11:57:59Z"},
    {"fetched_at": "2026-09-14T12:00:01Z"}, {"source_ref": ""},
    {"payload": {"successful": False, "data": {}}},
])
def test_operational_calendar_bad_evidence_refused(change):
    def read(**kwargs):
        return {**calendar_reader(**kwargs), **change}
    with pytest.raises(ValueError):
        read_and_propose(START, END, [person()], binding(), read, now=lambda: READ_NOW)


def test_operational_partial_access_stays_tentative():
    result = read_and_propose(START, END, [person(), person("bond")], binding(),
                               calendar_reader, now=lambda: READ_NOW)
    assert result["status"] == "tentative"
    assert result["unverified_participants"] == ["bond"]


def test_operational_read_expiring_during_other_reads_refused():
    moments = iter([READ_NOW, READ_NOW, READ_NOW + timedelta(minutes=3)])
    with pytest.raises(ValueError, match="expired"):
        read_and_propose(START, END, [person()], binding(), calendar_reader,
                         now=lambda: next(moments))


def test_booking_recheck_reads_again_and_refuses_race():
    slot = {"start": START, "end": "2026-09-15T07:30:00Z"}
    checked = recheck_booking(slot, [person()], binding(), calendar_reader, now=lambda: READ_NOW)
    assert checked["status"] == "rechecked" and checked["booking_authorized"] is False
    def taken(**kwargs):
        result = calendar_reader(**kwargs)
        result["payload"]["calendars"]["primary"]["busy"] = [slot]
        return result
    with pytest.raises(ValueError, match="busy"):
        recheck_booking(slot, [person()], binding(), taken, now=lambda: READ_NOW)
    with pytest.raises(ValueError, match="confirmation"):
        recheck_booking(slot, [person(), person("bond")], binding(), calendar_reader,
                        now=lambda: READ_NOW)


def test_operational_read_refuses_past_and_wrong_participant_before_read():
    def no_read(**kwargs):
        pytest.fail("Invalid request must not spend a read")
    with pytest.raises(ValueError):
        read_and_propose(START, END, [person()], {"other": binding()["patrick"]}, no_read,
                         now=lambda: READ_NOW)
    with pytest.raises(ValueError):
        read_and_propose(START, END, [person()], binding(), no_read,
                         now=lambda: aware_datetime(END))


def person(name="patrick", timezone="Africa/Johannesburg", busy=(), hours=(9, 17)):
    return Participant(name, timezone, tuple(WorkingWindow(d, time(hours[0]), time(hours[1]))
                                          for d in range(5)), busy)


def response():
    return {"timeMin": START, "timeMax": END,
            "calendars": {"primary": {"busy": []}}}


@pytest.mark.parametrize("value", ["2026-09-15", "2026-09-15T10:00:00", None, 3, "invalid"])
def test_requires_aware_timestamp(value):
    with pytest.raises(ValueError):
        aware_datetime(value)


def test_offset_normalization():
    assert aware_datetime("2026-09-15T09:00:00+02:00") == aware_datetime(START)


def test_proposed_alternatives_do_not_overlap_each_other():
    result = propose_slots(START, END, [person()], duration_minutes=30, step_minutes=15)
    assert len(result["slots"]) == 3
    for left, right in zip(result["slots"], result["slots"][1:]):
        assert aware_datetime(left["end"]) <= aware_datetime(right["start"])


def test_dst_ambiguous_requires_explicit_choice():
    with pytest.raises(ValueError, match="Ambiguous"):
        local_datetime("2026-11-01T01:30:00", "America/Los_Angeles")
    first = local_datetime("2026-11-01T01:30:00", "America/Los_Angeles", fold=0)
    second = local_datetime("2026-11-01T01:30:00", "America/Los_Angeles", fold=1)
    assert second - first == timedelta(hours=1)


def test_dst_nonexistent_and_invalid_zone():
    for zone, wall in [("America/Los_Angeles", "2026-03-08T02:30:00"),
                       ("Mars/City", "2026-03-08T02:30:00")]:
        with pytest.raises(ValueError):
            local_datetime(wall, zone)


def test_aware_nonexistent_zoneinfo_rejected():
    from zoneinfo import ZoneInfo
    with pytest.raises(ValueError, match="Nonexistent"):
        aware_datetime(datetime(2026, 3, 8, 2, 30, tzinfo=ZoneInfo("America/Los_Angeles")))


@pytest.mark.parametrize("start,end", [(END, START), (START, START)])
def test_invalid_intervals(start, end):
    with pytest.raises(ValueError):
        Interval(start, end)


def test_busy_overlap_and_touching_boundary():
    p = person(busy=(Interval("2026-09-15T09:00:00+02:00", "2026-09-15T10:00:00+02:00"),))
    result = propose_slots(START, END, [p])
    assert result["slots"][0]["start"] == "2026-09-15T08:00:00+00:00"
    assert result["status"] == "proposed"
    assert result["booking_authorized"] is False


def test_busy_start_at_slot_end_is_free():
    p = person(busy=(Interval("2026-09-15T07:30:00Z", "2026-09-15T08:00:00Z"),))
    assert propose_slots(START, END, [p])["slots"][0]["start"] == aware_datetime(START).isoformat()


def test_no_overlap_matches_boardy_exception():
    result = propose_slots(START, "2026-09-22T22:00:00Z",
                           [person(), person("bond", "America/Los_Angeles")])
    assert result["status"] == "needs_exception"
    assert result["slots"] == []


def test_partial_access_is_tentative_and_link_available():
    result = propose_slots(START, END, [person(), person("bond", busy=None)],
                           booking_link="https://hey.example.com/book")
    assert result["status"] == "tentative"
    assert result["unverified_participants"] == ["bond"]
    assert result["fallback"]["url"] == "https://hey.example.com/book"


def test_no_calendar_access_never_claims_free():
    assert propose_slots(START, END, [person(busy=None)])["status"] == "needs_calendar_access"


@pytest.mark.parametrize("link", ["http://example.com", "https://a:b@example.com", "https://", "https://example.com/\n"])
def test_unsafe_booking_link(link):
    with pytest.raises(ValueError):
        propose_slots(START, END, [person()], booking_link=link)


@pytest.mark.parametrize("kwargs", [{"duration_minutes": 0}, {"duration_minutes": True},
                                    {"step_minutes": 0}, {"limit": 1000}, {"limit": 1.5}])
def test_limits(kwargs):
    with pytest.raises(ValueError):
        propose_slots(START, END, [person()], **kwargs)


def test_duplicate_empty_and_long_horizon():
    for participants in ([], [person(), person()]):
        with pytest.raises(ValueError):
            propose_slots(START, END, participants)
    with pytest.raises(ValueError):
        propose_slots(START, "2027-01-01T00:00:00Z", [person()])


def test_windows_and_weekend():
    with pytest.raises(ValueError):
        WorkingWindow(8, time(9), time(17))
    with pytest.raises(ValueError):
        WorkingWindow(0, time(22), time(6))
    assert propose_slots("2026-09-19T07:00:00Z", "2026-09-19T16:00:00Z", [person()])["slots"] == []


@pytest.mark.parametrize("date,expected", [("2026-10-30", "16:00"), ("2026-11-02", "17:00")])
def test_date_specific_dst_offsets(date, expected):
    result = propose_slots(f"{date}T00:00:00Z", f"{date}T23:59:00Z",
                           [person("bond", "America/Los_Angeles")], limit=1)
    assert result["slots"][0]["start"][11:16] == expected


def test_parse_real_google_shape_and_success_envelope():
    payload = response()
    payload["calendars"]["primary"]["busy"] = [{"start": "2026-09-15T10:00:00+02:00",
                                                 "end": "2026-09-15T11:00:00+02:00"}]
    parsed = parse_freebusy({"successful": True, "data": payload}, ["primary"], START, END)
    assert parsed["primary"][0].start.hour == 8


@pytest.mark.parametrize("mutation", [
    lambda p: p.pop("timeMin"),
    lambda p: p.update(timeMin="2026-09-15T08:00:00Z"),
    lambda p: p.update(timeMax="2026-09-15T15:00:00Z"),
    lambda p: p.update(calendars={}),
    lambda p: p["calendars"]["primary"].update(errors=[{"reason": "forbidden"}]),
    lambda p: p["calendars"]["primary"].pop("busy"),
    lambda p: p["calendars"]["primary"].update(busy=None),
    lambda p: p["calendars"]["primary"].update(busy=[{}]),
    lambda p: p["calendars"]["primary"].update(busy=[{"start": START, "end": START}]),
    lambda p: p["calendars"]["primary"].update(busy=[{"start": "2026-09-15T09:00", "end": END}]),
])
def test_provider_fail_closed(mutation):
    payload = response()
    mutation(payload)
    with pytest.raises(ValueError):
        parse_freebusy(payload, ["primary"], START, END)


@pytest.mark.parametrize("payload", [None, [], {"successful": False, "data": {}},
                                     {"data": response()}, {"error": "denied"}])
def test_provider_envelope_errors(payload):
    with pytest.raises(ValueError):
        parse_freebusy(payload, ["primary"], START, END)


def booking():
    request = stage_booking({"start": START, "end": "2026-09-15T07:30:00Z"},
                            ["a@example.com", "b@example.com"], "Introduction")
    event = {"id": "event-1", "status": "confirmed", "summary": "Introduction",
             "start": {"dateTime": START}, "end": {"dateTime": "2026-09-15T09:30:00+02:00"},
             "attendees": [{"email": "B@example.com"}, {"email": "a@example.com"}]}
    return request, event


def test_booking_is_only_proposal_and_verification_checks_actual_response():
    request, event = booking()
    assert request["status"] == "needs_approval" and request["booking_authorized"] is False
    assert verify_booking(request, event)
    for key, value in [("id", ""), ("status", "cancelled"), ("attendees", []),
                       ("summary", "Wrong meeting"), ("start", {"dateTime": END}),
                       ("end", {"date": "2026-09-15"})]:
        changed = deepcopy(event)
        changed[key] = value
        assert not verify_booking(request, changed)


@pytest.mark.parametrize("attendees", [[], ["invalid"], ["a@"], ["a@b", "A@B"], ["a b@example.com"]])
def test_invalid_booking_attendees(attendees):
    with pytest.raises(ValueError):
        stage_booking({"start": START, "end": END}, attendees, "Intro")


def test_dst_repeated_window_cannot_escape_working_hours():
    p = Participant("p", "America/Los_Angeles", (WorkingWindow(6, time(1, 30), time(2, 30)),), ())
    result = propose_slots("2026-11-01T08:30:00Z", "2026-11-01T11:00:00Z", [p], limit=1)
    assert result["slots"][0]["start"] == "2026-11-01T09:30:00+00:00"


def test_dst_skipped_working_boundary_fails_closed():
    p = Participant("p", "America/Los_Angeles", (WorkingWindow(6, time(2, 30), time(4)),), ())
    assert propose_slots("2026-03-08T09:00:00Z", "2026-03-08T12:00:00Z", [p])["slots"] == []


def test_long_meeting_spanning_dst_uses_elapsed_duration():
    p = Participant("p", "America/Los_Angeles", (WorkingWindow(6, time(0), time(4)),), ())
    result = propose_slots("2026-11-01T07:00:00Z", "2026-11-01T12:00:00Z", [p],
                           duration_minutes=240, limit=1)
    slot = result["slots"][0]
    assert aware_datetime(slot["end"]) - aware_datetime(slot["start"]) == timedelta(hours=4)
    assert slot["local"]["p"]["end"].startswith("2026-11-01T03:00:00")


def test_working_hour_end_rejects_one_second_overrun():
    assert propose_slots("2026-09-15T14:30:01Z", END, [person()], limit=1)["slots"] == []


def test_unknown_calendars_and_malformed_busy_rows():
    for ids in ([], ["primary", "primary"], ["other"]):
        with pytest.raises(ValueError):
            parse_freebusy(response(), ids, START, END)
    for row in (None, [], 4, "not an interval"):
        payload = response()
        payload["calendars"]["primary"]["busy"] = [row]
        with pytest.raises(ValueError):
            parse_freebusy(payload, ["primary"], START, END)
