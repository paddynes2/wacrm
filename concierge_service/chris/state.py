"""Pure pursuit changes, with cessation stronger than relevance updates."""
from uuid import uuid4
from .contracts import require

TERMINAL = {"declined", "suppressed", "excluded", "introduced", "closed_no_response"}
TRANSITIONS = {
 "discovered": {"researching", "excluded"}, "researching": {"qualified", "rejected", "research_blocked"},
 "qualified": {"contact_unresolved", "ready_to_invite", "excluded"},
 "contact_unresolved": {"researching", "ready_to_invite"}, "ready_to_invite": {"awaiting_reply"},
 "awaiting_reply": {"conversing", "closed_no_response", "deferred"},
 "conversing": {"awaiting_group_permission", "ready_to_introduce", "deferred", "awaiting_reply"},
 "awaiting_group_permission": {"conversing", "ready_to_introduce"}, "ready_to_introduce": {"introducing", "conversing"},
 "introducing": {"introduced", "recovery_needed"}, "research_blocked": {"researching"},
 "rejected": {"researching"}, "deferred": {"researching", "conversing"}, "recovery_needed": {"introducing"}}

def transition(pursuit, target, now):
    if pursuit["state"] == target:
        return
    require(target in TRANSITIONS.get(pursuit["state"], set()) or
            (target in {"declined", "suppressed", "excluded", "human_takeover"} and pursuit["state"] != "introduced"), "illegal_transition", 409)
    pursuit.update(state=target, state_revision=pursuit["state_revision"] + 1, updated_at=now)

def cancel_unstarted(state, person_id=None):
    for action in state["actions"].values():
        pursuit = state["pursuits"].get(action.get("pursuit_id"), {})
        if (person_id is None or pursuit.get("person_id") == person_id) and action["status"] in {"draft", "queued", "preflight"}:
            action["status"] = "cancelled"

def event(state, kind, now, entity_id=None, **payload):
    state["event_seq"] += 1
    row = dict(event_id=str(uuid4()), kind=kind, entity_id=entity_id, observed_seq=state["event_seq"], occurred_at=now, payload=payload)
    state["events"].append(row)
    return row

def pursuit_for(state, person_id):
    return next((p for p in state["pursuits"].values() if p["person_id"] == person_id), None)
