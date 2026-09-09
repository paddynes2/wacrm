"""Extracted reducer contract tests; no host or provider dependencies."""
import copy
import pytest
from concierge_core import state as c

A = "27820000001@s.whatsapp.net"


B = "27820000002@s.whatsapp.net"


IDENTITY = {"crm_ref": "rebound:person-1", "principal_id": A, "recipient_id": B,
            "name": "Bond", "principal_name": "Patrick", "offer": "Patrick helps owners improve operations.",
            "fit": "Your profitability work complements his workflow implementation.",
            "profile_url": "https://example.com/bond"}


def event(kind, data, eid=None, **over):
    return {"event_id": eid or kind, "pursuit_id": "rebound:pursuit-1", "account_id": "wa-account",
            "kind": kind, "occurred_at": "2026-09-08T10:00:00Z", "source_ref": "evidence:1",
            "data": data, **over}


def initial():
    return [event("identified", copy.deepcopy(IDENTITY))]


def consent(party, scope):
    return event("consent", {"party_id": party, "scope": scope, "proposal_id": "rebound:pursuit-1"}, party + scope)


def agreed():
    return initial() + [consent(p, s) for p in (A, B) for s in ("contact", "introduction", "group", "scheduling", "booking")]


def test_boardy_approach_is_transparent_grounded_and_asks_permission():
    draft = c.introduction_draft(c.derive(initial()))
    assert "Patrick's AI assistant" in draft
    assert IDENTITY["fit"] in draft
    assert draft.endswith("Would you be open to an introduction?")


def test_no_consent_no_intro_or_cold_approach():
    state = c.derive(initial())
    for purpose in ("approach", "introduction", "reply", "schedule"):
        with pytest.raises(ValueError):
            c.check_action(state, purpose, state["revision"])


def test_intro_yes_does_not_mean_group_or_booking_yes():
    state = c.derive(initial() + [consent(p, "introduction") for p in (A, B)])
    assert state["status"] == "agreed" and not state["group_agreed"]
    with pytest.raises(ValueError, match="group"):
        c.check_action(state, "introduction", state["revision"])


@pytest.mark.parametrize("change", [
    {"party_id": "stranger"}, {"proposal_id": "different-intro"}, {"scope": "admin"}])
def test_unrelated_or_broadened_consent_refuses(change):
    e = consent(B, "introduction")
    e["data"].update(change)
    with pytest.raises(ValueError):
        c.derive(initial() + [e])


@pytest.mark.parametrize("kind", ["opt_out", "declined"])
def test_stop_survives_delayed_yes_and_resume(kind):
    state = c.derive(agreed() + [event(kind, {"party_id": B}),
                               event("resume", {"reason": "operator tried resuming"}),
                               consent(B, "introduction")])
    assert state["status"] in {"opted_out", "declined"}
    with pytest.raises(ValueError):
        c.check_action(state, "introduction", state["revision"])


def test_cross_account_cannot_join_same_pursuit():
    with pytest.raises(ValueError, match="mixed"):
        c.derive(initial() + [{**consent(B, "contact"), "account_id": "another-tenant"}])


def test_attendance_must_match_verified_booking():
    rows = agreed() + [event("dispatch_started", {"action_id": "a", "purpose": "introduction", "revision": "r"}),
                      event("dispatch_verified", {"action_id": "a", "purpose": "introduction", "provider_id": "group"}),
                      event("booking_verified", {"event_id": "calendar-A", "request_sha": "proof"})]
    with pytest.raises(ValueError, match="same verified"):
        c.derive(rows + [event("meeting_attended", {"event_id": "calendar-B"})])


@pytest.mark.parametrize("field,value", [("kind", "owner_approved"), ("occurred_at", "2026-09-08"), ("event_id", "bad\nvalue")])
def test_malformed_evidence_refuses(field, value):
    with pytest.raises(ValueError):
        c.validate({**initial()[0], field: value})


def test_cross_pursuit_optout_changes_revision_but_not_other_account():
    other = event("identified", copy.deepcopy(IDENTITY), "other-identity", pursuit_id="other")
    rows = initial() + [other]
    before = c.scoped_view(rows, "other")
    rows.append(event("opt_out", {"party_id": B}))
    stopped = c.scoped_view(rows, "other")
    assert stopped["status"] == "opted_out"
    assert stopped["revision"] != before["revision"]
    other["account_id"] = "another-account"
    assert c.scoped_view(rows, "other")["status"] == "proposed"


def test_takeover_and_inbound_invalidate_frozen_revision():
    before = c.derive(agreed())
    after = c.derive(agreed() + [event("takeover", {"reason": "human reply"})])
    with pytest.raises(ValueError, match="invalidated"):
        c.check_action(after, "introduction", before["revision"])
    with pytest.raises(ValueError, match="human_owned"):
        c.check_action(after, "introduction", after["revision"])


def test_uncertain_dispatch_requires_reconciliation_and_cannot_repeat():
    started = event("dispatch_started", {"action_id": "a", "purpose": "introduction", "revision": "r"})
    rows = agreed() + [started, event("dispatch_unknown", {"action_id": "a", "purpose": "introduction"})]
    state = c.derive(rows)
    assert state["status"] == "reconcile"
    with pytest.raises(ValueError, match="reconcile"):
        c.check_action(state, "introduction", state["revision"])
    rows.append(event("reconciled_absent", {"action_id": "a"}))
    assert c.derive(rows)["status"] == "agreed"
    with pytest.raises(ValueError, match="duplicate dispatch"):
        c.derive(rows + [{**started, "event_id": "repeated-start"}])


def test_reply_receipt_clears_only_the_observed_inbound_and_older_replay_stays_old():
    inbound = event("inbound", {"message_id": "m1", "chat_id": "chat", "sender_id": B})
    rows = agreed() + [inbound]
    before = c.derive(rows)
    c.check_action(before, "reply", before["revision"])
    rows += [event("dispatch_started", {"action_id": "r1", "purpose": "reply", "revision": before["revision"]}),
             event("dispatch_verified", {"action_id": "r1", "purpose": "reply", "provider_id": "receipt"})]
    assert c.derive(rows)["reply_required"] is False
    rows.append(event("inbound", {"message_id": "older", "chat_id": "chat", "sender_id": B}, "older", occurred_at="2026-09-08T09:00:00Z"))
    assert c.derive(rows)["reply_required"] is False
    rows.append(event("inbound", {"message_id": "m2", "chat_id": "chat", "sender_id": B}, "newer", occurred_at="2026-09-08T11:00:00Z"))
    assert c.derive(rows)["reply_required"] is True


def test_booking_verified_dispatch_requires_request_digest():
    rows = agreed() + [event("dispatch_started", {"action_id": "book", "purpose": "booking", "revision": "r"})]
    receipt = event("dispatch_verified", {"action_id": "book", "purpose": "booking", "provider_id": "meeting"})
    with pytest.raises(ValueError, match="digest"):
        c.derive(rows + [receipt])
    receipt["data"]["request_sha"] = "a" * 64
    assert c.derive(rows + [receipt])["booking_id"] == "meeting"


def test_duplicate_event_is_idempotent_but_changed_payload_collides():
    rows = initial()
    assert c.derive(rows + rows) == c.derive(rows)
    with pytest.raises(ValueError, match="collision"):
        c.derive(rows + [{**rows[0], "source_ref": "changed"}])

