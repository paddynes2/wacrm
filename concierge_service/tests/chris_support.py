"""Synthetic provider transports. Every unexpected operation is a test failure."""
from copy import deepcopy
from uuid import uuid4
from concierge_service.chris.contracts import require

SELF = '15550001001@s.whatsapp.net'
PRINCIPAL = '15550001002@s.whatsapp.net'
PROSPECT = '15550001003@s.whatsapp.net'


class Wire:
    def __init__(self, clock):
        self.clock = clock
        self.calls, self.receipts = [], []
        self.participants = [SELF, PRINCIPAL, PROSPECT]
        self.fail_after = False
        self.before_wire = None

    def preflight(self, frozen):
        if self.before_wire: self.before_wire()
        return dict(account_id='synthetic-wa', self_provider_id=SELF, history_ready=True,
                    membership_verified=True, recipients=frozen['recipients'],
                    stop=False, manual=False, pending_inbound=False, message_ids=[r['message_id'] for r in self.receipts])

    def mutate(self, frozen):
        from concierge_service.chris.dispatch import multipart
        fields = [('account_id', frozen['provider_account_id'])] if not frozen['chat_id'] or frozen['purpose'] == 'group_create' else []
        fields += [('attendees_ids', x) for x in frozen['recipients']] if fields else []
        if frozen['group_subject']: fields.append(('subject', frozen['group_subject']))
        fields.append(('text', frozen['text']))
        raw, content_type = multipart(fields)
        self.calls.append(dict(frozen=deepcopy(frozen), raw=raw, content_type=content_type))
        chat = 'synthetic-group' if frozen['purpose'] == 'group_create' else frozen['chat_id'] or 'synthetic-direct'
        mid = 'synthetic-' + str(len(self.receipts) + 1)
        self.receipts.append(dict(account_id='synthetic-wa', self_provider_id=SELF, sender_id=SELF,
            text=frozen['text'], recipients=frozen['recipients'], timestamp=self.clock(), message_id=mid,
            chat_id=chat, membership_verified=True))
        if self.fail_after: raise OSError('synthetic lost response')
        return dict(object='ChatStarted', message_id=mid, chat_id=chat)

    def observe_action(self, action): return deepcopy(self.receipts)
    def membership(self, chat): return dict(participants=self.participants, self_verified=SELF in self.participants, chat_id=chat)


class Search:
    def __init__(self): self.calls = []
    def search(self, query):
        self.calls.append(('search', query))
        return dict(results=[dict(url='https://example.com/maya', title='Maya Chen, Cedar Distribution', text='Maya Chen leads Cedar Distribution.', read=False, status='success')], estimated_cost_micro_usd=1000)
    def read(self, url):
        assert url == 'https://example.com/maya'
        self.calls.append(('read', url))
        return dict(results=[dict(url=url, title='Maya Chen', text='Maya Chen leads Cedar Distribution. Cedar operates regional distribution partnerships.', read=True, status='success')], estimated_cost_micro_usd=1000)


class ReplayModel:
    def __init__(self): self.turns = 0
    def turn(self, context):
        if context.get('task') == 'research_critic':
            return dict(schema_version=1, step='qualify', arguments=dict(verdict='accept', reasons=['Retained company role supports this thesis.'], required_fixes=[]), evidence_ids=[], decision_summary='Independent fixture critique')
        self.turns += 1
        results = context['results']
        def result(step): return next(r['result'] for r in reversed(results) if r['step'] == step)
        if self.turns == 1: name, args = 'search_web', dict(query=context['brief']['objective'] + ' leaders', purpose='discovery')
        elif self.turns == 2: name, args = 'read_url', dict(source_id=result('search_web')['sources'][0]['source_id'], question='Who leads the business?')
        elif self.turns == 3: name, args = 'register_person', dict(source_id=result('read_url')['sources'][0]['source_id'], display_name='Maya Chen', company_name='Cedar Distribution', profile_url='https://example.com/maya')
        elif self.turns == 4: name, args = 'get_known_relationship', dict(person_id=result('register_person')['person_id'])
        elif self.turns == 5:
            name = 'write_dossier'
            args = dict(person_id=result('register_person')['person_id'], dossier=dict(why_this_person='Maya leads a distribution business relevant to the endeavour.', principal_benefit='Explore a distribution partnership.',
                facts=[dict(claim_id='role', text='Maya leads Cedar Distribution.', source_ids=[result('read_url')['sources'][0]['source_id']], span='Maya Chen leads Cedar Distribution.')],
                inferences=['A partnership may be relevant; interest is unknown.'], unknowns=['Reciprocal benefit is not yet established.'], risks=[], approach_thesis='Explore distribution fit without assuming interest.',
                primary_source_exception='The company leadership page proves the identity and role.', critic=dict(verdict='accept', reasons=['Primary identity evidence supports relevance.'], required_fixes=[])))
        elif self.turns == 6: name, args = 'qualify', dict(person_id=result('register_person')['person_id'], verdict='qualified', reasons='Direct relevance to distribution, with recipient benefit still unknown.')
        else: name, args = 'finish', dict(result='One evidenced candidate; contact route needs checking.')
        return dict(schema_version=1, step=name, arguments=args, evidence_ids=[], decision_summary='Progress against the active endeavour.')
