"""One durable group saga per pursuit and principal, completion by observation."""
from uuid import uuid4
from .contracts import require
from .dispatch import freeze
from .permissions import eligibility
from .state import event, transition

SETUP = "I've created this group for the introduction you agreed to. I'll add the introduction shortly."


class Introductions:
    def __init__(self, service, dispatcher):
        self.service, self.dispatcher = service, dispatcher

    def start(self, account, pursuit_id, content):
        with self.service.transaction(account) as (_, state):
            pursuit = self.service.entity(state, 'pursuits', pursuit_id)
            existing = next((i for i in state['introductions'].values() if i['pursuit_id'] == pursuit_id and i['principal_id'] == (state['principal'] or {}).get('provider_id')), None)
            if existing: return existing['intro_id']
            reasons = eligibility(state, pursuit, self.service.clock(), 'group_create')
            require(not reasons and pursuit['state'] == 'ready_to_introduce', reasons[0] if reasons else 'consent_needed', 409)
            person = state['people'][pursuit['person_id']]
            principal = state['principal']; connection = state['connection']
            participants = [connection['self_provider_id'], principal['provider_id'], person['provider_id']]
            require(len(set(participants)) == 3, 'three_distinct_identities_required', 409)
            brief = state['brief_versions'][str(state['active_brief_revision'])]
            intro = dict(intro_id=str(uuid4()), pursuit_id=pursuit_id, principal_id=principal['provider_id'],
                         principal_display_name=brief['principal_display_name'], prospect_display_name=person['display_name'],
                         expected_participants=participants, external_participants=participants[1:], state='planned',
                         group_chat_id=None, content=content, subject=(brief['principal_display_name'].split()[0] + ', ' + person['display_name'].split()[0] + ' - Introduction')[:80])
            state['introductions'][intro['intro_id']] = intro
            transition(pursuit, 'introducing', self.service.clock())
            action = freeze(state, account, pursuit, 'group_create', SETUP, self.service.clock(), intro=intro)
            action['status'] = 'queued'
            intro.update(group_create_action_id=action['action_id'], state='creating_group')
            pursuit['introduction_id'] = intro['intro_id']
            return intro['intro_id']

    def advance(self, account, payload):
        current = self.service.snapshot(account)
        intro = self.service.entity(current, 'introductions', payload['intro_id'])
        if intro['state'] in {'introduced', 'membership_failed', 'cancelled_after_create'}: return
        if self.service.clock() < intro.get('next_membership_at', 0): return
        creation = current['actions'][intro['group_create_action_id']]
        if creation['status'] != 'verified':
            self.dispatcher.execute(account, {'action_id': creation['action_id']})
            current = self.service.snapshot(account); creation = current['actions'][creation['action_id']]
        if creation['status'] != 'verified': return
        provider = self.dispatcher.providers[account]
        membership = provider.membership(creation['provider_chat_id'])
        with self.service.transaction(account) as (_, state):
            intro = state['introductions'][intro['intro_id']]
            intro['group_chat_id'] = creation['provider_chat_id']
            observed = set(membership.get('participants', []))
            expected = set(intro['expected_participants'])
            if observed - expected:
                intro['state'] = 'membership_failed'; intro['last_failure'] = 'membership_mismatch'; return
            if observed != expected or not membership.get('self_verified'):
                intro['membership_attempts'] = intro.get('membership_attempts', 0) + 1
                intro.update(state='membership_pending' if intro['membership_attempts'] <= 5 else 'membership_failed', last_failure='membership_unverified')
                delays = [60,180,600,1800,3600]
                intro['next_membership_at'] = creation['verified_at'] + delays[min(intro['membership_attempts']-1,4)]
                return
            pursuit = state['pursuits'][intro['pursuit_id']]
            reasons = eligibility(state, pursuit, self.service.clock(), 'group_introduction')
            if reasons:
                intro.update(state='cancelled_after_create', last_failure=reasons[0]); return
            intro['membership_receipt'] = membership
            intro['previous_failure'] = intro.get('last_failure')
            intro['last_failure'] = None
            if not intro.get('substantive_action_id'):
                action = freeze(state, account, pursuit, 'group_introduction', intro['content'], self.service.clock(), intro=intro)
                action['status'] = 'queued'
                intro.update(substantive_action_id=action['action_id'], state='introducing')
            action_id = intro['substantive_action_id']
        self.dispatcher.execute(account, {'action_id': action_id})
        with self.service.transaction(account, recovery=True) as (_, state):
            intro = state['introductions'][payload['intro_id']]
            action = state['actions'][action_id]
            if action['status'] == 'verified' and intro['state'] != 'introduced':
                intro.update(state='introduced', verified_at=self.service.clock())
                pursuit = state['pursuits'][intro['pursuit_id']]
                transition(pursuit, 'introduced', self.service.clock())
                pursuit.pop('attention',None)
                completion = event(state, 'introduction_completed', self.service.clock(), intro['intro_id'], action_id=action_id)
                intro['completion_event_id'] = completion['event_id']
                from .projection import stage
                stage(state, account, completion, 'introduction_note', dict(person_id=pursuit['person_id'], introduction_id=intro['intro_id'], observed_at=intro['verified_at']))
