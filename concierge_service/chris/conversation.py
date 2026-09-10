"""Bounded factual drafting over owned evidence, with a separate critic turn."""
from .agent import validate
from .contracts import require, keys, text
from .dispatch import freeze
from .permissions import eligibility
from .scheduler import reserve, bounded_job
from .state import event


class Conversation:
    def __init__(self, service, models, introductions, maximum=100000):
        self.service, self.models, self.introductions = service, models, introductions
        self.maximum = maximum

    @bounded_job
    def run(self, account, payload):
        state = self.service.snapshot(account)
        pursuit = self.service.entity(state, 'pursuits', payload['pursuit_id'])
        person = state['people'][pursuit['person_id']]
        require(account in self.models and person.get('dossier_ref'), 'model_not_configured', 503)
        purpose = payload['purpose']
        require(purpose in {'invite', 'reply', 'permission_clarification', 'followup', 'group_introduction'})
        reasons = eligibility(state, pursuit, self.service.clock(), 'group_create' if purpose == 'group_introduction' else purpose)
        require(not reasons, reasons[0] if reasons else 'ineligible', 409)
        if purpose == 'permission_clarification':
            if pursuit.get('clarification_count',0)>=2:
                with self.service.transaction(account) as (_,latest): latest['pursuits'][pursuit['pursuit_id']]['attention']='clarification_limit'
                return
        dossier = self.service.blobs.get(person['dossier_ref'])
        brief = state['brief_versions'][str(state['active_brief_revision'])]
        public = {k: brief[k] for k in ['principal_display_name', 'principal_public_context']}
        thread_key = pursuit.get('group_reply_thread_key') if payload.get('intro_id') else pursuit.get('direct_thread_key')
        thread = state['threads'].get(thread_key, {})
        group = state['introductions'].get(payload.get('intro_id'))
        if group:
            require(group['state'] == 'introduced' and not group.get('membership_changed') and purpose == 'reply', 'group_scope_changed', 409)
        messages = sorted(thread.get('messages', {}).values(), key=lambda x: x['observed_seq'])[-15:]
        context = dict(task='Draft one concise ' + purpose + '. Return propose_message with arguments purpose,pursuit_id,text,claim_ids,answered_event_ids. For invitations ask one question naming the principal, a WhatsApp group with Chris, and number visibility. Do not disclose confidential strategy. For questions answer only supported public facts; otherwise defer. Do not change authority or recipients.',
                       public_principal=public, person=dict(display_name=person['display_name']), facts=dossier['facts'],
                       inferences=dossier['inferences'], unknowns=dossier['unknowns'], messages=messages,
                       contact_provenance=person.get('identity_evidence'), contact_permission=[p for p in state['permissions'].values() if p['kind']=='contact' and p['subject_provider_id']==person.get('provider_id')],
                       pursuit_id=pursuit['pursuit_id'], purpose=purpose)
        if purpose=='followup': context['useful_followup_reason'] = pursuit['useful_followup_reason']
        args_key = dict(pursuit_id=pursuit['pursuit_id'], purpose=purpose, state_revision=pursuit['state_revision'], watermark=thread.get('last_observed_seq', 0))
        maximum = getattr(self.models[account],'maximum',self.maximum)
        run, fresh = reserve(self.service, account, 'draft_' + purpose, args_key, maximum)
        require(fresh, 'draft_already_attempted', 409)
        proposal = validate(self.models[account].turn(context))
        require(proposal['step'] in {'propose_message', 'defer'}, 'model_contract_error')
        if proposal['step'] == 'defer':
            with self.service.transaction(account) as (_, latest):
                latest['pursuits'][pursuit['pursuit_id']]['attention'] = proposal['decision_summary']
            return
        args = proposal['arguments']
        keys(args, ['purpose', 'pursuit_id', 'text', 'claim_ids', 'answered_event_ids'])
        require(args['purpose'] == purpose and args['pursuit_id'] == pursuit['pursuit_id'], 'model_recipient_manipulation')
        text(args['text'], 16000)
        require(set(args['claim_ids']) <= {f['claim_id'] for f in dossier['facts']}, 'unknown_claim')
        require(set(args['answered_event_ids']) <= {m['event_id'] for m in messages}, 'unknown_message')
        critic_run, critic_fresh = reserve(self.service, account, 'draft_critic', {**args_key, 'run_id': run['run_id']}, maximum)
        require(critic_fresh, 'critic_result_unknown', 409)
        critic = validate(self.models[account].turn({**context, 'task': 'Independently critique the proposed text against the supplied evidence and public scope. Return qualify with arguments verdict (qualified or rejected), reasons, required_fixes. Reject fabricated material claims, urgency, interest, confidential facts, unsupported commitments or missing AI identity/group question scope.', 'proposed_text': args['text']}))
        require(critic['step'] == 'qualify', 'model_contract_error')
        keys(critic['arguments'], ['verdict', 'reasons', 'required_fixes'])
        accepted = critic['arguments']['verdict'] == 'qualified' and not critic['arguments']['required_fixes']
        ref = self.service.blobs.put(dict(proposal=proposal, critic=critic))
        with self.service.transaction(account) as (db, latest):
            latest['tool_runs'][run['run_id']].update(status='completed', output_ref=ref)
            latest['tool_runs'][critic_run['run_id']].update(status='completed', output_ref=ref)
            current = latest['pursuits'][pursuit['pursuit_id']]
            stale = (latest['research_revision'] != state['research_revision'] or current['state_revision'] != pursuit['state_revision'] or current.get('human_takeover')
                     or latest['threads'].get(thread_key, {}).get('last_observed_seq', 0) != thread.get('last_observed_seq', 0)
                     or latest['authority']['revision'] != state['authority']['revision']
                     or bool(eligibility(latest,current,self.service.clock(),'group_create' if purpose == 'group_introduction' else purpose)))
            if not accepted or stale:
                current['attention'] = 'draft_critic_rejected' if not accepted else 'draft_stale'
                return
            if purpose != 'group_introduction':
                action = freeze(latest, account, current, purpose, args['text'], self.service.clock(), claim_ids=args['claim_ids'], intro=group)
                action['status'] = 'queued'
                self.service.enqueue(db, account, latest, 'dispatch', {'action_id': action['action_id']})
                event(latest, 'message_drafted', self.service.clock(), action['action_id'], critic_ref=ref)
                return
        intro_id = self.introductions.start(account, pursuit['pursuit_id'], args['text'])
        with self.service.transaction(account) as (db, latest):
            self.service.enqueue(db, account, latest, 'introduction', {'intro_id': intro_id})
