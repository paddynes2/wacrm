"""Evidence applicability and future-only authority are host-owned."""
import datetime as dt
from .contracts import require

CONSENT_SECONDS = 30 * 86400

def applicable(state, pursuit, kind, now):
    connection, principal = state["connection"] or {}, state["principal"] or {}
    person = state["people"][pursuit["person_id"]]
    matches = []
    for row in state["permissions"].values():
        if row["kind"] != kind or row["status"] != "valid" or row.get("revoked_at"):
            continue
        if row["subject_provider_id"] != person.get("provider_id") or row["business_sender_identity"] != connection.get("self_provider_id"):
            continue
        if row.get("expires_at") and row["expires_at"] <= now:
            continue
        if kind != "contact" and (row.get("principal_id") != principal.get("provider_id") or row.get("research_revision") != state["research_revision"] or row.get("pursuit_id") != pursuit["pursuit_id"]):
            continue
        matches.append(row["permission_id"])
    return matches

def eligibility(state, pursuit, now, kind="invite"):
    reasons = []
    a, c, principal = state["authority"], state["connection"] or {}, state["principal"] or {}
    person = state["people"][pursuit["person_id"]]
    if state.get('mode') == 'live' and person.get('synthetic'): reasons.append('synthetic_live_evidence')
    if a["paused"] or a["emergency_stop"]: reasons.append("workspace_paused")
    if not a["external_enabled"]: reasons.append("external_autonomy_off")
    if kind not in a["allowed_action_kinds"]: reasons.append("action_scope_missing")
    if not c.get("connected") or not c.get("contract_verified"): reasons.append("connection_unavailable")
    if not principal or principal.get("provider_id") == c.get("self_provider_id"): reasons.append("principal_identity_needed")
    if not person.get("provider_id") or person.get("identity_status") not in {"corroborated", "operator_attested"}: reasons.append("recipient_identity_unresolved")
    if person.get('provider_id') and person['provider_id'] in {c.get('self_provider_id'),principal.get('provider_id')}: reasons.append('recipient_not_distinct')
    if person.get("provider_id") in state["suppressions"] or pursuit["state"] in {"declined", "suppressed", "excluded", "closed_no_response"}: reasons.append("recipient_suppressed")
    if pursuit.get("human_takeover") or pursuit.get("paused"): reasons.append("manual_takeover")
    if pursuit["current_research_revision"] != state["research_revision"] or pursuit["qualification"] != "qualified": reasons.append("research_stale")
    if not person.get("relationship_checked") or person.get("known_relationship"): reasons.append("relationship_unresolved")
    if not applicable(state, pursuit, "contact", now): reasons.append("contact_permission_missing")
    if kind in {"group_create", "group_introduction"}:
        for scope in ("introduction", "group"):
            if not applicable(state, pursuit, scope, now): reasons.append(scope + "_permission_missing")
    if kind in {"invite", "followup"} and pursuit.get("reply_required"): reasons.append("pending_reply")
    if kind in {'reply','permission_clarification'}:
        thread = state['threads'].get(pursuit.get('group_reply_thread_key') or pursuit.get('direct_thread_key'),{})
        if not thread.get('history_ready'): reasons.append('owned_thread_needed')
        if kind=='reply' and not pursuit.get('reply_required'): reasons.append('no_pending_reply')
    if kind == "followup":
        if pursuit.get("followup_count_verified", 0) >= 2: reasons.append("followup_limit")
        if not person.get("timezone"): reasons.append("recipient_timezone_unknown")
        if not pursuit.get("useful_followup_reason") or not pursuit.get("not_before") or now < pursuit["not_before"]: reasons.append("followup_not_due")
    if pursuit["state"] == "introduced" and kind not in {"reply"}: reasons.append("already_introduced")
    return reasons
