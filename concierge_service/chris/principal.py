"""Narrow factual principal replies under separately enabled external scope."""
from uuid import uuid4
from .contracts import digest


def eligibility(state):
    a,c,p=state['authority'],state['connection'] or {},state['principal'] or {}
    reasons=[]
    if a['paused'] or a['emergency_stop']: reasons.append('workspace_paused')
    if not a['external_enabled'] or 'principal_reply' not in a['allowed_action_kinds'] or not state['settings']['principal_messages_enabled']: reasons.append('principal_messages_off')
    if not c.get('connected') or not c.get('contract_verified'): reasons.append('connection_unavailable')
    if not p or p.get('provider_id')==c.get('self_provider_id'): reasons.append('principal_identity_needed')
    if state.get('mode')=='live' and p.get('synthetic'): reasons.append('synthetic_live_evidence')
    return reasons


def draft(state,account,thread,content,now):
    a,c,p=state['authority'],state['connection'],state['principal']
    frozen=dict(account_id=account,connection_generation=c['generation'],provider_account_id=c['provider_account_id'],
        self_provider_id=c['self_provider_id'],principal_binding_revision=p['revision'],principal_provider_id=p['provider_id'],
        recipients=[p['provider_id']],chat_id=thread['provider_chat_id'],review_chat_id=thread['provider_chat_id'],group_subject=None,
        text=content,purpose='principal_reply',brief_revision=state['active_brief_revision'],research_revision=state['research_revision'],
        pursuit_revision=None,authority_revision=a['revision'],permission_ids=[],source_claim_ids=[],
        history_watermark=thread['last_observed_seq'],not_before=now,expires_at=now+3600)
    action=dict(action_id=str(uuid4()),kind='principal_reply',pursuit_id=None,intro_id=None,created_at=now,status='queued',
        frozen=frozen,digest=digest(frozen),dispatch_generation=0,attempts=0)
    state['actions'][action['action_id']]=action
    return action
