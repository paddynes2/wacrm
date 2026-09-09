from datetime import datetime, timedelta, timezone
import pytest

from concierge_service.tests.test_engine_safety import A, setup, command, consent_all


def booked(tmp_path):
    engine = setup(tmp_path)
    command(engine, "start")
    consent_all(engine)
    report = command(engine, "introduce")
    engine.command(A, {"command": "approve", "decision_id": report["decisions"][-1]["id"]})
    start = (datetime.now(timezone.utc) + timedelta(days=7)).replace(hour=7, minute=0, second=0, microsecond=0)
    while start.weekday() > 4:
        start += timedelta(days=1)
    report = command(engine, "propose", start=start.isoformat(), end=(start + timedelta(hours=8)).isoformat())
    slot = report["prospects"][0]["calendar"]["slots"][0]
    report = command(engine, "book", start=slot["start"], end=slot["end"])
    engine.command(A, {"command": "approve", "decision_id": report["decisions"][-1]["id"]})
    return engine, start


def prepare(engine, operation="reschedule", start=None):
    values = {"operation": operation, "source_ref": "operator:both-parties-agreed-to-this-change"}
    if start:
        values.update(start=start.isoformat(), end=(start + timedelta(minutes=30)).isoformat())
    return command(engine, "prepare_amendment", **values)


def approve(engine, report):
    return command(engine, "approve_amendment", digest=report["prospects"][0]["amendment"]["digest"])


def test_nonoverlapping_reschedule_verified_without_replacing_original_observations(tmp_path):
    engine, start = booked(tmp_path)
    before = engine.report(A)["prospects"][0]["conversation"]
    report = prepare(engine, start=start + timedelta(hours=2))
    assert report["prospects"][0]["amendment"]["status"] == "pending"
    result = approve(engine, report)
    prospect = result["prospects"][0]
    assert prospect["calendar_status"] == "rescheduled"
    assert datetime.fromisoformat(prospect["booking"]["start"]) == start + timedelta(hours=2)
    assert prospect["conversation"] == before
    assert prospect["amendment"]["status"] == "verified"


def test_cancel_has_verified_receipt_and_duplicate_approval_has_no_effect(tmp_path):
    engine, _ = booked(tmp_path)
    report = prepare(engine, "cancel")
    result = approve(engine, report)
    assert result["prospects"][0]["booking"]["status"] == "cancelled"
    assert result["prospects"][0]["calendar_status"] == "cancelled"
    count = len(result["events"])
    with pytest.raises(ValueError, match="pending"):
        approve(engine, report)
    assert len(engine.report(A)["events"]) == count
    with pytest.raises(ValueError):
        command(engine, "followup", seconds=60)


@pytest.mark.parametrize("minutes", [0, 15])
def test_same_or_overlapping_reschedule_refused(tmp_path, minutes):
    engine, start = booked(tmp_path)
    with pytest.raises(ValueError, match="Overlapping"):
        prepare(engine, start=start + timedelta(minutes=minutes))


def test_no_verified_booking_and_missing_evidence_refused(tmp_path):
    engine = setup(tmp_path)
    command(engine, "start")
    with pytest.raises(ValueError, match="booking"):
        prepare(engine, "cancel")
    engine, _ = booked(tmp_path / "booked")
    with pytest.raises(ValueError, match="evidence"):
        command(engine, "prepare_amendment", operation="cancel")


def test_new_inbound_invalidates_amendment(tmp_path):
    engine, _ = booked(tmp_path)
    report = prepare(engine, "cancel")
    command(engine, "reply", text="Please wait before changing anything")
    with pytest.raises(ValueError):
        approve(engine, report)
    assert engine.report(A)["prospects"][0]["booking"]["status"] == "confirmed"


def test_wrong_digest_and_changed_proposal_refused(tmp_path):
    engine, _ = booked(tmp_path)
    report = prepare(engine, "cancel")
    with pytest.raises(ValueError, match="digest"):
        command(engine, "approve_amendment", digest="wrong")
    with engine.store.transaction() as db:
        doc = engine.store.load(db, A, engine.mode)
        doc["prospects"][0]["amendment"]["proposal"]["after"]["status"] = "confirmed"
        engine.store.save(db, doc)
    with pytest.raises(ValueError, match="digest"):
        approve(engine, report)


def test_changed_calendar_or_busy_slot_fails_recheck(tmp_path):
    engine, start = booked(tmp_path)
    report = prepare(engine, start=start + timedelta(hours=2))
    with engine.store.transaction() as db:
        doc = engine.store.load(db, A, engine.mode)
        doc["prospects"][0]["simulated_busy"] = [{"start": (start + timedelta(hours=2)).isoformat(), "end": (start + timedelta(hours=3)).isoformat()}]
        engine.store.save(db, doc)
    with pytest.raises(ValueError, match="busy"):
        approve(engine, report)


def test_live_mode_cannot_prepare_amendments(tmp_path):
    engine = setup(tmp_path, "live")
    command(engine, "start")
    with pytest.raises(ValueError, match="simulation"):
        prepare(engine, "cancel")
