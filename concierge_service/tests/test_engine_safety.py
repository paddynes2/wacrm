from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import copy
import pytest

from concierge_service.engine import Engine
from concierge_service.store import Store

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
BRIEF = dict(principal_name="Patrick", offer="Offer", audience="Owners", geography="ZA",
             exclusions="", claims="", timezone="Africa/Johannesburg", booking_link="", budget_usd=0)


def setup(tmp_path, mode="simulation"):
    e = Engine(Store(tmp_path / "state.db"), mode=mode)
    e.command(A, {"command": "save_brief", "brief": BRIEF})
    with e.store.transaction() as db:
        doc = e.store.load(db, A, mode)
        doc["prospects"].append(dict(id="p", name="Person", fit="Verified fit", source="evidence:1",
            profile_url=None, phone="+27820000002", phone_status="operator_verified", qualification="qualified", status="qualified"))
        e.store.save(db, doc)
    return e


def command(e, name, **kwargs):
    return e.command(A, {"command": name, "prospect_id": "p", **kwargs})


def consent_all(e):
    for party in ("principal", "recipient"):
        for scope in ("contact", "introduction", "group", "scheduling", "booking"):
            command(e, "consent", party=party, scope=scope, source_ref="operator:agreement")


def test_live_initialization_allows_subsequent_eligibility(tmp_path):
    e = setup(tmp_path, "live")
    r = command(e, "start")
    assert r["prospects"][0]["conversation"]["status"] == "proposed"
    assert not r["jobs"]
    command(e, "consent", party="recipient", scope="contact", source_ref="operator:eligibility")
    assert len(command(e, "start")["jobs"]) == 1


def test_approval_rejects_modified_payload_and_recipient(tmp_path):
    e = setup(tmp_path)
    command(e, "start")
    with e.store.transaction() as db:
        d = e.store.load(db, A, e.mode)
        original = e.stage(d, d["prospects"][0], "approach", "Original")
        for key, value in (("text", "Tampered"), ("recipients", ["wrong"]), ("account_id", B)):
            modified = {**original, key: value}
            with pytest.raises(ValueError, match="digest|ownership"):
                e.approve(d, modified)


def test_repeated_start_never_repeats_approach(tmp_path):
    e = setup(tmp_path)
    command(e, "start")
    e.process_one(A)
    first = e.report(A)
    command(e, "start")
    e.process_one(A)
    assert len(e.report(A)["messages"]) == len(first["messages"]) == 1


def test_brief_change_requires_new_reviewed_pursuit_and_preserves_stop(tmp_path):
    e = setup(tmp_path)
    command(e, "start")
    command(e, "reply", text="STOP")
    e.command(A, {"command": "save_brief", "brief": {**BRIEF, "offer": "New offer"}})
    with pytest.raises(ValueError, match="qualification"):
        command(e, "start")
    r = command(e, "new_pursuit")
    new_id = r["prospects"][-1]["id"]
    e.command(A, {"command": "qualify", "prospect_id": new_id, "verdict": "qualified", "reason": "Reviewed"})
    with pytest.raises(ValueError, match="opted_out"):
        e.command(A, {"command": "start", "prospect_id": new_id})
    assert r["prospects"][0]["conversation"]["identity"]["offer"] == "Offer"


def test_crm_link_requires_account_ownership(tmp_path):
    e = setup(tmp_path)
    with pytest.raises(ValueError, match="CRM"):
        command(e, "link_contact", contact={"id": B, "phone": "+27820000002", "account_id": B})
    assert command(e, "link_contact", contact={"id": B, "phone": "+27820000002", "account_id": A})["prospects"][0]["contact_id"] == B


def test_duplicate_provider_inbound_and_equal_timestamp_are_preserved(tmp_path):
    e = setup(tmp_path)
    command(e, "start")
    e.process_one(A)
    stamp = datetime.now(timezone.utc).isoformat()
    args = (A, "p", "Question", "m1", "chat", "27820000002@s.whatsapp.net", stamp, "provider:read")
    e.ingest(*args)
    e.process_one(A)
    count = len(e.report(A)["messages"])
    e.ingest(*args)
    assert len(e.report(A)["messages"]) == count
    e.ingest(A, "p", "Another question", "m2", "chat", "+27820000002", stamp, "provider:read")
    assert e.report(A)["prospects"][0]["conversation"]["reply_required"]
    e.process_one(A)
    assert not e.report(A)["prospects"][0]["conversation"]["reply_required"]


def test_provider_identity_and_media_fail_closed(tmp_path):
    e = setup(tmp_path)
    command(e, "start")
    stamp = datetime.now(timezone.utc).isoformat()
    with pytest.raises(ValueError, match="identity"):
        e.ingest(A, "p", None, "m", "chat", "+27820000099", stamp, "provider:read")
    e.ingest(A, "p", None, "m", "chat", "+27820000002", stamp, "provider:read")
    assert e.report(A)["prospects"][0]["conversation"]["status"] == "human_owned"


def test_manual_outbound_pauses_and_is_idempotent(tmp_path):
    e = setup(tmp_path)
    command(e, "start")
    args = (A, "p", None, "manual1", "chat", None, datetime.now(timezone.utc).isoformat(), "provider:read")
    e.manual_outbound(*args)
    e.manual_outbound(*args)
    r = e.report(A)
    assert r["prospects"][0]["conversation"]["status"] == "human_owned"
    assert len(r["messages"]) == 1


def test_explicit_retry_preserves_original_attempt_and_adds_new_job(tmp_path):
    e = setup(tmp_path)
    command(e, "start")
    with e.store.transaction() as db:
        db.execute("UPDATE jobs SET state='failed', attempts=3")
    job = e.report(A)["jobs"][0]
    e.command(A, {"command": "retry_job", "job_id": job["id"]})
    assert len(e.report(A)["jobs"]) == 2
    e.process_one(A)
    assert len(e.report(A)["messages"]) == 1


def test_concurrent_workers_publish_one_response(tmp_path):
    e = setup(tmp_path)
    command(e, "start")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: e.process_one(A), range(4)))
    assert len(e.report(A)["messages"]) == 1


def test_calendar_uses_exact_future_horizon_and_rechecks_busy(tmp_path):
    e = setup(tmp_path)
    command(e, "start")
    consent_all(e)
    r = command(e, "introduce")
    e.command(A, {"command": "approve", "decision_id": r["decisions"][-1]["id"]})
    start = (datetime.now(timezone.utc) + timedelta(days=7)).replace(hour=7, minute=0, second=1, microsecond=0)
    while start.weekday() > 4:
        start += timedelta(days=1)
    r = command(e, "propose", start=start.isoformat(), end=(start + timedelta(hours=8)).isoformat())
    slot = r["prospects"][0]["calendar"]["slots"][0]
    assert datetime.fromisoformat(slot["start"]) >= start
    r = command(e, "book", start=slot["start"], end=slot["end"])
    did = r["decisions"][-1]["id"]
    with e.store.transaction() as db:
        d = e.store.load(db, A, e.mode)
        d["prospects"][0]["simulated_busy"] = [{"start": slot["start"], "end": slot["end"]}]
        e.store.save(db, d)
    with pytest.raises(ValueError, match="busy"):
        e.command(A, {"command": "approve", "decision_id": did})


def test_store_closes_all_connections(tmp_path):
    e = setup(tmp_path)
    assert e.store.accounts() == [A]
    e.store.path.unlink()


def test_discovery_profile_scheme_rejected(tmp_path):
    e = setup(tmp_path)
    with e.store.transaction() as db:
        d = e.store.load(db, A, e.mode)
        with pytest.raises(ValueError, match="HTTP"):
            e.add_prospects(d, {"prospects": [{"name": "P", "source": "s", "profile_url": "javascript:alert(1)"}]}, {"limit": 1, "source": "fixture"})


def test_stale_model_completion_cannot_reply_after_optout(tmp_path, monkeypatch):
    from concierge_service import providers
    e = setup(tmp_path)
    command(e, "start")
    def delayed(*args):
        command(e, "reply", text="STOP")
        return {"text": "Late draft", "intent": "reply", "provider": "fixture", "cost_usd": 0}
    monkeypatch.setattr(providers, "generate", delayed)
    e.process_one(A)
    r = e.report(A)
    assert all(m["direction"] == "inbound" for m in r["messages"])
    assert r["prospects"][0]["conversation"]["status"] == "opted_out"


def test_failed_provider_keeps_reservation_and_logical_retry_delay(tmp_path, monkeypatch):
    from concierge_service import providers
    e = setup(tmp_path)
    e.command(A, {"command": "save_brief", "brief": {**BRIEF, "budget_usd": 1}})
    command(e, "qualify", verdict="qualified", reason="Reviewed updated brief")
    e.models[A] = {"provider": "paid", "max_cost_usd": 0.5}
    e.command(A, {"command": "advance", "seconds": 86400})
    command(e, "start")
    calls = []
    def fail(*args):
        calls.append(1)
        raise ValueError("Uncertain charge")
    monkeypatch.setattr(providers, "generate", fail)
    e.process_one(A)
    e.process_one(A)
    assert calls == [1]
    assert e.report(A)["metrics"]["cost_usd"] == 0.5


def test_complete_booking_uses_verified_calendar_receipt(tmp_path):
    e = setup(tmp_path)
    command(e, "start")
    consent_all(e)
    r = command(e, "introduce")
    e.command(A, {"command": "approve", "decision_id": r["decisions"][-1]["id"]})
    start = (datetime.now(timezone.utc) + timedelta(days=7)).replace(hour=7, minute=0, second=0, microsecond=0)
    while start.weekday() > 4:
        start += timedelta(days=1)
    r = command(e, "propose", start=start.isoformat(), end=(start + timedelta(hours=8)).isoformat())
    slot = r["prospects"][0]["calendar"]["slots"][0]
    r = command(e, "book", start=slot["start"], end=slot["end"])
    r = e.command(A, {"command": "approve", "decision_id": r["decisions"][-1]["id"]})
    assert r["prospects"][0]["booking"]["status"] == "confirmed"
    assert r["prospects"][0]["conversation"]["booking_id"] == r["prospects"][0]["booking"]["id"]
