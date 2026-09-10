"""Atomic complete-chat replay, conservative cessation and scoped consent."""
import datetime as dt
import re
from uuid import uuid4
from .contracts import require, digest
from .identity import claim_principal
from .state import event, cancel_unstarted, pursuit_for, transition
from .permissions import CONSENT_SECONDS

STOP = re.compile(r'\b(stop|unsubscribe|wrong (number|person)|do not contact|don.t contact|never contact)\b', re.I)
DECLINE = re.compile(r'\b(no thanks|not interested|not for me|please don.t|no thank you|changed my mind|withdraw my permission|don.t add me)\b|^\s*no[.! ]*$', re.I)
AFFIRM = re.compile(r'^(yes|yes please|sure|absolutely|sounds good|i agree|please do)[.! ]*$', re.I)


class Ingestion:
    def __init__(self, service, providers):
        self.service, self.providers = service, providers

    def sync(self, account, payload=None):
        provider = self.providers.get(account)
        require(provider is not None, 'connection_unavailable', 503)
        observation = provider.connection()
        from .identity import bind_connection
        with self.service.transaction(account) as (_, state):
            bind_connection(state, observation)
        current = self.service.snapshot(account)
        for person in current['people'].values():
            if person.get('identity_status') == 'operator_attested' and person.get('phone_e164') and not person.get('provider_id') and hasattr(provider, 'resolve_identity'):
                try:
                    receipt = provider.resolve_identity(person['phone_e164'])
                    with self.service.transaction(account) as (_, state):
                        target = state['people'][person['person_id']]
                        require(target.get('phone_e164') == receipt['phone_e164'] and state['connection']['provider_account_id'] == receipt['provider_account_id'], 'identity_changed')
                        require(not any(p.get('provider_id') == receipt['provider_id'] for p in state['people'].values()), 'ambiguous_identity')
                        target.update(provider_id=receipt['provider_id'], provider_identity_receipt=receipt)
                except ValueError:
                    continue
        current = self.service.snapshot(account)
        for chat in provider.chats():
            try:
                owner = self.owner(current, chat)
                if not owner: continue
                batch = provider.read_chat(chat['chat_id'])
                self.ingest(account, owner, batch)
            except Exception as exc:
                with self.service.transaction(account) as (_, state):
                    state['health']['chat:' + str(chat.get('chat_id', 'unknown'))] = getattr(exc, 'code', 'chat_quarantined')
                    for thread in state['threads'].values():
                        if thread['provider_chat_id']==chat.get('chat_id'):
                            thread.update(history_ready=False,quarantined=True)

    @staticmethod
    def owner(state, chat):
        connection = state['connection'] or {}
        if chat.get('account_id') != connection.get('provider_account_id'): return None
        principal = state['principal'] or {}
        if not chat.get('is_group') and len(chat.get('recipients', [])) == 1:
            party = chat['recipients'][0]
            if principal.get('provider_id') == party: return ('principal_direct', party)
            person = next((p for p in state['people'].values() if p.get('provider_id') == party), None)
            if person: return ('prospect_direct', person['person_id'])
            if state.get('challenge'): return ('challenge', party)
        for intro in state['introductions'].values():
            if intro.get('group_chat_id') == chat['chat_id']: return ('introduction_group', intro['intro_id'])
        return None

    def ingest(self, account, owner, batch):
        require(batch.get('complete') is True and not batch.get('truncated'), 'history_incomplete', 409)
        require(isinstance(batch.get('messages'), list) and len(batch['messages']) <= 20000, 'message_capacity')
        now = self.service.clock()
        with self.service.transaction(account, recovery=True) as (db, state):
            connection = state['connection'] or {}
            require(batch['account_id'] == connection.get('provider_account_id'), 'foreign_chat')
            thread_key = f"unipile:{connection['generation']}:{batch['account_id']}:{batch['chat_id']}"
            thread = state['threads'].setdefault(thread_key, dict(thread_key=thread_key, kind=owner[0], owner_entity_id=owner[1], provider_chat_id=batch['chat_id'], messages={}, last_observed_seq=0))
            thread.update(history_ready=True, last_complete_sync_at=now, coverage=batch.get('coverage', 'provider pagination only'), participants=batch.get('recipients', []))
            fresh = []
            for message in batch['messages']:
                require(message.get('message_id') and message.get('sender_id') and isinstance(message.get('timestamp'), (int, float)), 'provider_schema_changed')
                mid = message['message_id']
                old = thread['messages'].get(mid)
                if old and old['digest'] == digest(message): continue
                row = event(state, 'message_edit' if old else 'message_observed', now, owner[1], message_id=mid, thread_key=thread_key)
                row.update(provider_timestamp=message['timestamp'], message=message, digest=digest(message))
                row['provider_original_timestamp'] = message.get('original_timestamp', message['timestamp'])
                thread['messages'][mid] = row
                thread['last_observed_seq'] = row['observed_seq']
                fresh.append(row)
                if old:
                    for permission in state['permissions'].values():
                        if old['event_id'] in permission.get('evidence_event_ids', []): permission['status'] = 'revoked'
                if message['timestamp'] > now + 60: thread['history_ready'] = False
            # All pages are persisted before any semantic progression is considered.
            if owner[0] == 'challenge':
                for row in fresh:
                    m = row['message']
                    if not m.get('outbound') and m.get('kind') == 'text':
                        try:
                            claim_principal(state, nonce=m.get('text', ''), sender=m['sender_id'], chat=batch['chat_id'], now=now, direct=True, forwarded=m.get('forwarded', False))
                            # Nonce never enters retained messages or model context.
                            row['message'] = {**m, 'text': '[principal control proof]'}
                            thread['kind'] = 'principal_direct'
                        except ValueError:
                            row['message'] = {**m, 'text': '[unsuccessful control proof]'}
                return
            if owner[0] == 'principal_direct':
                for row in fresh:
                    m = row['message']
                    if m.get('outbound') or m.get('forwarded') or m.get('quoted') or m.get('kind') != 'text': continue
                    if m['sender_id'] != (state['principal'] or {}).get('provider_id'): continue
                    value = m.get('text', '').strip().lower()
                    if value in {'pause', 'stop', 'stop messaging', 'stop research'}:
                        if value == 'stop research': state['settings']['research_enabled'] = False
                        else: state['authority']['paused'] = True
                        cancel_unstarted(state)
                    elif value == 'resume':
                        state['authority']['paused'] = False
                    else:
                        state['chat'].append(dict(role='principal', text=m.get('text', '')[:8000], created_at=now))
                        if value.rstrip('?.!') in {'status','what is happening','what are you doing'}:
                            content=f"I have researched {len(state['people'])} people and verified {sum(i['state']=='introduced' for i in state['introductions'].values())} introductions. The console shows the current evidence and gaps."
                        else: content='Use the console to review a changed brief or enable messaging. Existing authority has not been expanded.'
                        state['chat'].append(dict(role='chris', text=content, created_at=now))
                        from .principal import eligibility as principal_eligibility,draft
                        if not principal_eligibility(state):
                            action=draft(state,account,thread,content,now)
                            self.service.enqueue(db,account,state,'dispatch',{'action_id':action['action_id']})
                return
            if owner[0] == 'introduction_group':
                intro = state['introductions'][owner[1]]
                if set(batch.get('recipients', [])) != set(intro['external_participants']):
                    intro['membership_changed'] = True
                    event(state, 'group_membership_changed', now, intro['intro_id'])
                    if intro['state'] != 'introduced': intro['state'] = 'cancelled_after_create'
                    return
                if intro['state'] == 'introduced' and not intro.get('membership_changed'):
                    for row in fresh:
                        m = row['message']
                        if (m['sender_id'] in intro['external_participants'] and m.get('kind') == 'text'
                            and not m.get('outbound') and not any(m.get(k) for k in ['quoted','forwarded','truncated'])
                            and re.search(r'\bchris\b',m.get('text',''),re.I) and '?' in m.get('text','')):
                            pursuit = state['pursuits'][intro['pursuit_id']]
                            pursuit.update(reply_required=True, group_reply_thread_key=thread_key, group_reply_intro_id=intro['intro_id'])
                return
            person = state['people'][owner[1]]
            pursuit = pursuit_for(state, owner[1])
            pursuit['direct_thread_key'] = thread_key
            relevant = [r for r in fresh if r['message']['sender_id'] == person.get('provider_id') and not r['message'].get('outbound')]
            # Cessation wins even if a later page or delayed message says yes.
            for row in relevant:
                m = row['message']; value = m.get('text', '')
                if STOP.search(value) or DECLINE.search(value):
                    broad = bool(STOP.search(value))
                    if broad: state['suppressions'][person['provider_id']] = dict(event_id=row['event_id'], created_at=now)
                    if re.search('wrong (number|person)', value, re.I): person['identity_status'] = 'invalid'
                    if pursuit['state'] != 'introduced': transition(pursuit, 'suppressed' if broad else 'declined', now)
                    for permission in state['permissions'].values():
                        if permission['subject_provider_id'] == person.get('provider_id'): permission['status'] = 'revoked'
                    cancel_unstarted(state, owner[1])
                    return
            for row in fresh:
                m = row['message']
                if m.get('outbound'):
                    echo = [a for a in state['actions'].values() if a['frozen']['text'] == m.get('text') and a.get('started_at')
                            and a['started_at'] - 60 <= m['timestamp'] <= a['started_at'] + 300
                            and (a.get('provider_chat_id') or a['frozen']['chat_id']) == batch['chat_id']]
                    if not echo:
                        possible = [a for a in state['actions'].values() if a['pursuit_id']==pursuit['pursuit_id']
                            and a['status'] in {'started','unknown','provider_accepted','needs_attention'}
                            and a['frozen']['text']==m.get('text') and a.get('started_at')
                            and a['started_at']-60<=m['timestamp']<=a['started_at']+300]
                        if possible:
                            pursuit['attention']='possible_assistant_echo'
                            for action in possible: self.service.enqueue(db,account,state,'reconcile',{'action_id':action['action_id']})
                        else:
                            pursuit['human_takeover'] = True
                            cancel_unstarted(state, owner[1])
            if pursuit['state'] in {'declined', 'suppressed', 'excluded', 'introduced'} or not thread['history_ready']: return
            ambiguous_order = any(a['message']['timestamp']==b['message']['timestamp']
                and a['message'].get('text')!=b['message'].get('text') for i,a in enumerate(relevant) for b in relevant[i+1:])
            for row in relevant:
                message = row['message']
                timezone = re.fullmatch(r'my timezone is ([A-Za-z_+-]+/[A-Za-z_+/-]+)[.! ]*',message.get('text','').strip(),re.I)
                if timezone and message.get('kind') == 'text' and not any(message.get(k) for k in ['quoted','forwarded','truncated']):
                    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
                    try:
                        ZoneInfo(timezone[1])
                        person.update(timezone=timezone[1], timezone_evidence_event_id=row['event_id'])
                    except ZoneInfoNotFoundError:
                        pursuit['attention'] = 'recipient_timezone_unknown'
                if (message.get('kind') == 'text' and not any(message.get(k) for k in ['quoted','forwarded','truncated'])
                    and re.fullmatch(r'please contact me (here|on whatsapp) about this introduction[.! ]*',message.get('text','').strip(),re.I)):
                    permission_id = str(uuid4())
                    state['permissions'][permission_id] = dict(permission_id=permission_id,kind='contact',status='valid',
                        subject_provider_id=person['provider_id'],business_sender_identity=connection['self_provider_id'],
                        basis='verified_inbound_opt_in',scope_text=message['text'],source_ref=row['event_id'],
                        evidence_event_ids=[row['event_id']],evidence_spans=[message['text']],granted_at=now)
                for permission in state['permissions'].values():
                    if permission['kind'] != 'contact' and permission.get('pursuit_id') == pursuit['pursuit_id']:
                        permission['status'] = 'revoked'
                pursuit['reply_required'] = True
                pursuit.pop('group_reply_thread_key', None)
                pursuit.pop('group_reply_intro_id', None)
                pursuit['not_before'] = None
                cancel_unstarted(state, owner[1])
                if pursuit['state'] == 'awaiting_reply': transition(pursuit, 'conversing', now)
                if ambiguous_order: pursuit['attention']='ambiguous_message_order'
                else: self.interpret(state, pursuit, row, thread, now)
                if pursuit['state'] == 'ready_to_introduce' and pursuit['reply_required']:
                    transition(pursuit, 'conversing', now)
                from .projection import stage
                stamp = dt.datetime.fromtimestamp(row['message']['timestamp'], dt.timezone.utc).isoformat()
                if row['message'].get('text'):
                    stage(state, account, row, 'direct_messages', dict(person_id=owner[1], messages=[dict(id=row['message']['message_id'], text=row['message']['text'], direction='inbound', occurred_at=stamp, chat_id=batch['chat_id'])]))

    @staticmethod
    def interpret(state, pursuit, row, thread, now, semantic_accept=False):
        message = row['message']; value = message.get('text', '').strip()
        if message.get('kind') != 'text' or message.get('forwarded') or message.get('quoted') or message.get('truncated'):
            pursuit['attention'] = 'interpretation_needed'; return
        if re.search(r'\b(email|if|but|only after|pricing|tell me more|not now|november|colleague)\b', value, re.I):
            pursuit['attention'] = 'conditional_or_question'
            if re.search(r'\b(email|if|but|only after|not now|november|colleague)\b',value,re.I): pursuit['condition_text'] = value
            return
        question = state['actions'].get(pursuit.get('active_invitation_action_id'))
        if not question or question['status'] != 'verified' or message['timestamp'] < question['verified_at'] - 60: return
        if question.get('provider_chat_id') != thread.get('provider_chat_id'): return
        if message.get('reply_to') and message['reply_to'] != question.get('provider_message_id'): return
        if not AFFIRM.fullmatch(value) and not semantic_accept:
            pursuit['attention'] = 'interpretation_needed'; return
        resolves_condition = semantic_accept and bool(re.fullmatch(r'Yes[, ]+I agree unconditionally[.!]?', value, re.I))
        if pursuit.get('condition_text') and not resolves_condition:
            pursuit['attention'] = 'unresolved_condition'; return
        scope = question['frozen'].get('question_scope', {})
        principal = state['principal'] or {}
        if scope.get('principal_id') != principal.get('provider_id') or not scope.get('introduction'): return
        if scope.get('pending_question_count', 1) != 1: return
        if pursuit.get('condition_text') and resolves_condition:
            pursuit.setdefault('resolved_conditions', []).append(dict(text=pursuit.pop('condition_text'), evidence_event_id=row['event_id']))
        for kind in ['introduction', 'group']:
            if kind == 'group' and not (scope.get('group') and scope.get('number_visibility')): continue
            permission_id = str(uuid4())
            state['permissions'][permission_id] = dict(permission_id=permission_id, kind=kind, status='valid',
                subject_provider_id=message['sender_id'], business_sender_identity=state['connection']['self_provider_id'],
                principal_id=principal['provider_id'], pursuit_id=pursuit['pursuit_id'], invitation_action_id=question['action_id'],
                evidence_event_ids=[row['event_id']], evidence_spans=[value], granted_at=now, expires_at=now + CONSENT_SECONDS,
                basis='verified_inbound', research_revision=state['research_revision'])
        full = scope.get('group') and scope.get('number_visibility')
        transition(pursuit, 'ready_to_introduce' if full else 'awaiting_group_permission', now)
        pursuit['reply_required'] = False
        pursuit.pop('attention',None)
