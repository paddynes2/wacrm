from copy import deepcopy
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import pytest

from concierge_service.calendar_provider import GoogleCalendar
from concierge_service.concierge_core.calendar import stage_booking
from concierge_service.tests.test_engine_safety import A, setup, command, consent_all


class GoogleRig:
    def __init__(self):
        self.calls, self.events = [], {}
        self.primary, self.sparse, self.wrong, self.timeout = "owner@example.com", False, False, False
        self.client = GoogleCalendar("owner@example.com", lambda: "test-token", ["primary"], http=self.http)

    def http(self, method, url, headers, body):
        self.calls.append((method, url, deepcopy(body), dict(headers)))
        if url.endswith("/users/me/calendarList/primary"):
            return 200, {}, {"id": self.primary, "primary": True}
        if url.endswith("/freeBusy"):
            return 200, {}, {"timeMin": body["timeMin"], "timeMax": body["timeMax"], "calendars": {row["id"]: {"busy": []} for row in body["items"]}}
        if method == "POST":
            if self.timeout:
                raise TimeoutError("Uncertain provider mutation")
            self.events[body["id"]] = {**deepcopy(body), "status": "confirmed", "etag": "etag1"}
            return 200, {}, deepcopy(self.events[body["id"]])
        eid = url.split("/events/")[-1].split("?")[0]
        if method == "PATCH":
            assert headers["If-Match"] == self.events[eid]["etag"]
            self.events[eid].update(deepcopy(body), etag="etag2")
            return 200, {}, deepcopy(self.events[eid])
        value = deepcopy(self.events[eid])
        if self.wrong:
            value["attendees"] = []
        if self.sparse and value["status"] == "cancelled":
            value = {"id": eid, "status": "cancelled"}
        return 200, {}, value


def request():
    start = (datetime.now(timezone.utc) + timedelta(days=7)).replace(hour=8, minute=0, second=0, microsecond=0)
    while start.weekday() > 4:
        start += timedelta(days=1)
    return stage_booking({"start": start.isoformat(), "end": (start + timedelta(minutes=30)).isoformat()},
                         ["owner@example.com", "recipient@example.com"], "Introduction")


def callbacks():
    log = []
    return log, dict(authorize=lambda plan: log.append("authorized") or True,
                     claim=lambda plan: log.append("claimed") or True,
                     complete=lambda plan, result: log.append("verified"),
                     failed=lambda plan, result: log.append(result), preflight=lambda: None, mutation_guard=nullcontext)


def test_freebusy_bound_account_and_complete_coverage():
    rig = GoogleRig()
    proposal = request()["proposal"]
    result = rig.client.read_freebusy(participant_id="owner", account_id=rig.primary, calendar_ids=["primary"], start=proposal["start"], end=proposal["end"])
    assert result["account_id"] == rig.primary and result["payload"]["calendars"]["primary"]["busy"] == []
    rig.primary = "wrong@example.com"
    with pytest.raises(ValueError, match="identity"):
        rig.client.read_freebusy(participant_id="owner", account_id="owner@example.com", calendar_ids=["primary"], start=proposal["start"], end=proposal["end"])


def test_exact_create_requires_gate_and_durable_claim_before_provider():
    rig = GoogleRig()
    plan = rig.client.prepare_create("primary", request())
    log, cb = callbacks()
    cb["authorize"] = lambda _: False
    with pytest.raises(ValueError, match="authorized"):
        rig.client.execute(plan, **cb)
    assert not rig.calls
    log, cb = callbacks()
    result = rig.client.execute(plan, **cb)
    assert log == ["authorized", "claimed", "verified"]
    assert result["event_verified"]
    assert next(call for call in rig.calls if call[0] == "POST")[1].endswith("sendUpdates=all")


def test_tamper_duplicate_claim_and_wrong_readback_fail_closed():
    rig = GoogleRig()
    plan = rig.client.prepare_create("primary", request())
    changed = deepcopy(plan)
    changed["body"]["summary"] = "Tampered"
    _, cb = callbacks()
    with pytest.raises(ValueError, match="digest"):
        rig.client.execute(changed, **cb)
    cb["claim"] = lambda _: False
    with pytest.raises(ValueError, match="attempted"):
        rig.client.execute(plan, **cb)
    assert not rig.events
    log, cb = callbacks()
    rig.wrong = True
    with pytest.raises(ValueError, match="read-back"):
        rig.client.execute(plan, **cb)
    assert log[-1] == "unknown" and "verified" not in log


def test_timeout_is_unknown_never_retried():
    rig = GoogleRig()
    rig.timeout = True
    log, cb = callbacks()
    with pytest.raises(ValueError):
        rig.client.execute(rig.client.prepare_create("primary", request()), **cb)
    assert log[-1] == "unknown"
    assert len([call for call in rig.calls if call[0] == "POST"]) == 1


def live_engine(tmp_path):
    engine = setup(tmp_path, "live")
    rig = GoogleRig()
    windows = [{"weekday": d, "start": "09:00", "end": "17:00"} for d in range(5)]
    engine.calendars[A] = {"participants": {"principal:" + A: {"client": rig.client, "email": "owner@example.com", "calendar_ids": ["primary"], "timezone": "Africa/Johannesburg", "windows": windows},
        "+27820000002": {"client": rig.client, "email": "recipient@example.com", "calendar_ids": ["primary"], "timezone": "Africa/Johannesburg", "windows": windows}}}
    command(engine, "start")
    consent_all(engine)
    with engine.store.transaction() as db:
        doc = engine.store.load(db, A, "live")
        state = engine.state(doc, "p")
        engine.observe(doc, "p", "dispatch_started", {"action_id": "intro", "purpose": "introduction", "revision": state["revision"]}, source="test:verified-introduction")
        engine.observe(doc, "p", "dispatch_verified", {"action_id": "intro", "purpose": "introduction", "provider_id": "group"}, source="test:verified-introduction")
        engine.store.save(db, doc)
    proposal = request()["proposal"]
    result = command(engine, "propose", start=proposal["start"], end=(datetime.fromisoformat(proposal["end"]) + timedelta(hours=2)).isoformat())
    slot = result["prospects"][0]["calendar"]["slots"][0]
    result = command(engine, "book", start=slot["start"], end=slot["end"])
    return engine, rig, result["decisions"][-1]["id"]


def test_engine_live_read_stage_and_host_authorized_booking(tmp_path):
    engine, rig, did = live_engine(tmp_path)
    assert not rig.events
    with pytest.raises(ValueError, match="simulation"):
        engine.command(A, {"command": "approve", "decision_id": did})
    result = engine.execute_calendar(A, did, authorize=lambda _: True)
    assert result["prospects"][0]["booking"]["status"] == "confirmed"
    assert result["prospects"][0]["calendar_owner"]["account_id"] == rig.primary
    with pytest.raises(ValueError, match="Pending"):
        engine.execute_calendar(A, did, authorize=lambda _: True)


def test_engine_uncertain_booking_keeps_durable_reconciliation(tmp_path):
    engine, rig, did = live_engine(tmp_path)
    rig.timeout = True
    with pytest.raises(ValueError):
        engine.execute_calendar(A, did, authorize=lambda _: True)
    assert engine.report(A)["prospects"][0]["conversation"]["status"] == "reconcile"


def test_engine_live_reschedule_then_cancel_uses_readback(tmp_path):
    engine, rig, did = live_engine(tmp_path)
    result = engine.execute_calendar(A, did, authorize=lambda _: True)
    start = datetime.fromisoformat(result["prospects"][0]["booking"]["start"]["dateTime"]) + timedelta(hours=1)
    result = command(engine, "prepare_amendment", operation="reschedule", start=start.isoformat(), end=(start + timedelta(minutes=30)).isoformat(), source_ref="operator:both-agree")
    result = engine.execute_calendar_amendment(A, "p", result["prospects"][0]["amendment"]["digest"], authorize=lambda _: True)
    assert result["prospects"][0]["calendar_status"] == "rescheduled"
    result = command(engine, "prepare_amendment", operation="cancel", source_ref="operator:both-agree")
    result = engine.execute_calendar_amendment(A, "p", result["prospects"][0]["amendment"]["digest"], authorize=lambda _: True)
    assert result["prospects"][0]["booking"]["status"] == "cancelled"
    assert result["amendment_outcomes"][-1]["simulated"] is False


def test_sparse_cancellation_receipt_remains_unknown(tmp_path):
    engine, rig, did = live_engine(tmp_path)
    engine.execute_calendar(A, did, authorize=lambda _: True)
    result = command(engine, "prepare_amendment", operation="cancel", source_ref="operator:both-agree")
    rig.sparse = True
    with pytest.raises(ValueError, match="read-back"):
        engine.execute_calendar_amendment(A, "p", result["prospects"][0]["amendment"]["digest"], authorize=lambda _: True)
    prospect = engine.report(A)["prospects"][0]
    assert prospect["amendment"]["status"] == "reconcile"
    assert prospect["calendar_mutation_pending"]
