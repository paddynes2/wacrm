from types import SimpleNamespace
from uuid import uuid4
import pytest
from concierge_service.store import Store
from concierge_service.chris.service import Service
from concierge_service.chris.runtime import Runtime
from concierge_service.chris.contracts import ChrisError
from concierge_service.chris.dispatch import Dispatcher, product_authorizer, freeze
from concierge_service.chris.permissions import eligibility
from concierge_service.chris.conversation import Conversation
from concierge_service.chris.research import Research
from concierge_service.chris.introductions import Introductions
from concierge_service.tests.test_chris_e2e import workspace, invitation
from concierge_service.tests.test_chris_groups import ready
from concierge_service.tests.test_chris_recovery_matrix import receive
from concierge_service.tests.test_chris_authority import command
from concierge_service.tests.test_chris_continuations import blank
from concierge_service.tests.chris_support import Wire, Search, SELF, PROSPECT


def test_missing_objective_and_name_preserve_draft_without_research(tmp_path):
    s=Service(Store(tmp_path/'blank.sqlite'));a=str(uuid4());actor=dict(user_id=str(uuid4()),request_id=str(uuid4()),role='owner')
    proposal=command(s,a,actor,'brief.propose',{'text':'Help me'})['proposal_id']
    with pytest.raises(ChrisError,match='economic_objective_needed'): command(s,a,actor,'research.start',{})
    for field in ['objective','principal_display_name']:
        brief=dict(objective='Find distribution partners.',principal_display_name='Alex',principal_public_context='Public offer.',timezone='UTC');brief[field]=''
        with pytest.raises(ChrisError): command(s,a,actor,'brief.save_proposal',dict(proposal_id=proposal,brief=brief))
    assert s.snapshot(a)['proposals'][proposal]['text']=='Help me' and not s.snapshot(a)['people']
    with s.store.transaction() as db: assert db.execute('SELECT count(*) FROM jobs').fetchone()[0]==0


def test_corrupt_tenant_does_not_starve_healthy_runtime(tmp_path):
    store=Store(tmp_path/'tenants.sqlite');a,b=str(uuid4()),str(uuid4());s=Service(store)
    with s.transaction(a): pass
    with s.transaction(b): pass
    with store.transaction() as db:
        doc=store.load(db,a,'simulation');doc['chris_v1']['schema_version']=999;store.save(db,doc)
    runtime=Runtime(SimpleNamespace(store=store,mode='simulation',models={},discovery={},unipile={}))
    runtime.tick();runtime.scheduler.close()
    assert s.snapshot(b)['health']['research_configured'] is False
    with pytest.raises(ChrisError,match='upgrade_required'): s.snapshot(a)


def test_invalid_model_repairs_once_and_never_calls_search(tmp_path):
    s,a=blank(tmp_path);search=Search()
    class Invalid:
        calls=0
        def turn(self,context): self.calls+=1;return {'text':'not a typed action'}
    model=Invalid()
    with pytest.raises(ChrisError,match='model_contract_error'): Research(s,{a:model},{a:search}).run(a,{})
    assert model.calls==2 and not search.calls and not s.snapshot(a)['actions']


def test_followup_reason_timezone_inbound_and_lifetime_limit(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock);dispatch=Dispatcher(s,{a:wire},product_authorizer)
    dispatch.execute(a,{'action_id':invitation(s,a,pursuit)})
    state=s.snapshot(a);reasons=eligibility(state,state['pursuits'][pursuit],now[0]+1000000,'followup')
    assert 'recipient_timezone_unknown' in reasons and 'followup_not_due' in reasons
    for index in range(2):
        now[0]+=86400*8
        with s.transaction(a) as (_,state):
            state['people'][person]['timezone']='Europe/London';p=state['pursuits'][pursuit]
            p.update(not_before=now[0],useful_followup_reason='New retained public detail '+str(index))
            action=freeze(state,a,p,'followup','A new public distribution detail may be relevant.',now[0]);action['status']='queued';identity=action['action_id']
        dispatch.execute(a,{'action_id':identity})
    restored=Service(Store(s.store.path),clock=s.clock).snapshot(a)
    assert restored['pursuits'][pursuit]['followup_count_verified']==2 and len(wire.calls)==3
    assert 'followup_limit' in eligibility(restored,restored['pursuits'][pursuit],now[0]+1000000,'followup')
    now[0]+=1;receive(s,a,person,now,'How did you get my number?')
    state=s.snapshot(a);assert 'pending_reply' in eligibility(state,state['pursuits'][pursuit],now[0],'followup')
    proposal=command(s,a,actor,'brief.propose',{'text':'Find new distribution experts'})['proposal_id']
    command(s,a,actor,'brief.save_proposal',dict(proposal_id=proposal,brief=dict(objective='Find new distribution experts',principal_display_name='Alex',principal_public_context='Public software.',timezone='UTC')))
    command(s,a,actor,'brief.activate',{'proposal_id':proposal})
    assert s.snapshot(a)['pursuits'][pursuit]['followup_count_verified']==2 and len(wire.calls)==3


def test_public_reply_context_contains_provenance_and_omits_private_objective(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock);dispatch=Dispatcher(s,{a:wire},product_authorizer)
    dispatch.execute(a,{'action_id':invitation(s,a,pursuit)});now[0]+=1;receive(s,a,person,now,'How did you get my number?')
    with s.transaction(a) as (_,state): state['brief_versions']['1']['objective']='CONFIDENTIAL acquisition price 123'
    class Model:
        def turn(self,context):
            assert 'CONFIDENTIAL' not in str(context) and context['contact_permission'][0]['source_ref']=='synthetic-opt-in'
            if 'proposed_text' in context: step,args='qualify',dict(verdict='qualified',reasons=['Truthful provenance.'],required_fixes=[])
            else: step,args='propose_message',dict(purpose='reply',pursuit_id=pursuit,text='The account owner recorded your opt-in for this introduction. I can pause contact if that is incorrect.',claim_ids=[],answered_event_ids=[context['messages'][-1]['event_id']])
            return dict(schema_version=1,step=step,arguments=args,evidence_ids=[],decision_summary='Use retained provenance only')
    Conversation(s,{a:Model()},None).run(a,dict(purpose='reply',pursuit_id=pursuit))
    action=next(r for r in s.snapshot(a)['actions'].values() if r['kind']=='reply');dispatch.execute(a,{'action_id':action['action_id']})
    assert len(wire.calls)==2 and 'CONFIDENTIAL' not in wire.calls[-1]['frozen']['text']


@pytest.mark.parametrize('fault',['privacy','crash','changed_intro','post_intro_reply'])
def test_group_recovery_and_completion_boundaries(tmp_path,fault):
    s,a,person,pursuit,now,wire,dispatch,saga,intro=ready(tmp_path)
    if fault=='privacy':
        wire.participants=[SELF,PROSPECT]
        for _ in range(7): saga.advance(a,{'intro_id':intro});now[0]+=3601
        assert s.snapshot(a)['introductions'][intro]['state']=='membership_failed' and len(wire.calls)==2
    elif fault=='crash':
        wire.fail_after=True;saga.advance(a,{'intro_id':intro});assert len(wire.calls)==2
        wire.fail_after=False
        restored=Service(Store(s.store.path),clock=s.clock)
        saga=Introductions(restored,Dispatcher(restored,{a:wire},product_authorizer));saga.advance(a,{'intro_id':intro})
        assert len(wire.calls)==3 and restored.overview(a)['counts']['introduced']==1
    elif fault=='changed_intro':
        original=wire.observe_action
        def observe(action):
            rows=original(action)
            if action['kind']=='group_introduction':
                for row in rows: row['text']='unexpected altered content'
            return rows
        wire.observe_action=observe;saga.advance(a,{'intro_id':intro})
        assert len(wire.calls)==3 and s.overview(a)['counts']['introduced']==0
    else:
        saga.advance(a,{'intro_id':intro});now[0]+=1;receive(s,a,person,now,'Thanks, what next?')
        state=Service(Store(s.store.path)).snapshot(a)
        assert state['pursuits'][pursuit]['state']=='introduced' and not state['pursuits'][pursuit].get('reply_required') and len(wire.calls)==3


def test_unknown_action_command_cannot_reset_and_stale_heartbeat_is_unready(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock);wire.fail_after=True;identity=invitation(s,a,pursuit)
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':identity})
    with pytest.raises(ChrisError,match='started_action_cannot_reset'): command(s,a,actor,'action.cancel',{'action_id':identity,'reason':'Operator retry attempt'})
    command(s,a,actor,'action.reconcile',{'action_id':identity})
    assert s.snapshot(a)['actions'][identity]['status']=='unknown' and len(wire.calls)==1
    with s.transaction(a) as (_,state): state['health']['heartbeat']=now[0]-31
    readiness=s.overview(a)['readiness']
    assert not readiness['worker']['running'] and not readiness['live_acceptance']['verified'] and not readiness['projection']['prerequisites_verified']


def test_requalification_preserves_followthrough_and_independent_research(tmp_path):
    from concierge_service.tests.chris_support import ReplayModel
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock)
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':invitation(s,a,pursuit)})
    research=Research(s,{a:ReplayModel()},{a:Search()},{a:lambda p:dict(known=False,fresh=True,coverage='Synthetic roster')})
    revision=s.snapshot(a)['research_revision']
    research.qualify(a,dict(person_id=person,verdict='qualified',reasons='Continuing current research.'),revision)
    assert s.snapshot(a)['pursuits'][pursuit]['state']=='awaiting_reply'
    research.run(a,{})
    state=Service(Store(s.store.path)).snapshot(a)
    assert len(state['people'])==1 and len(state['pursuits'])==1 and state['pursuits'][pursuit]['state']=='awaiting_reply'
    assert any(p['status']=='finish' for p in state['research_passes'].values()) and len(wire.calls)==1


def test_final_paginated_stop_prevents_any_early_reply(tmp_path):
    import urllib.parse
    from concierge_service.providers import UnipileClient
    from concierge_service.chris.provider import Provider
    from concierge_service.chris.ingestion import Ingestion
    from concierge_service.tests.test_chris_provider_contract import Client
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock);identity=invitation(s,a,pursuit)
    fixture=Client();pages=[]
    def http(method,url,headers,body=None):
        parsed=urllib.parse.urlsplit(url);path=parsed.path;query=urllib.parse.parse_qs(parsed.query)
        if '/accounts/' in path: return 200,{},fixture.account
        if path.endswith('/messages'):
            cursor=query.get('cursor',[''])[0];pages.append(cursor)
            message={**fixture.messages[0],'id':'stop' if cursor else 'yes','timestamp':'2026-09-10T12:00:00Z','text':'STOP' if cursor else 'Yes'}
            return 200,{},dict(items=[message],**({} if cursor else {'cursor':'final'}))
        if path.endswith('/attendees'): return 200,{},dict(items=fixture.attendees)
        return 200,{},dict(id='direct',account_id='synthetic-wa')
    provider=Provider(UnipileClient(base_url='https://api.unipile.com/api/v1',api_key='synthetic-key',account_id='synthetic-wa',http=http))
    batch=provider.read_chat('direct');assert pages==['','final']
    Ingestion(s,{}).ingest(a,('prospect_direct',person),batch)
    with pytest.raises(ChrisError): Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':identity})
    assert not wire.calls and Service(Store(s.store.path)).snapshot(a)['pursuits'][pursuit]['state']=='suppressed'


def test_condition_requires_explicit_evidenced_resolution_and_reviewed_resume(tmp_path):
    from concierge_service.chris.interpreter import Interpreter
    from concierge_service.chris.ingestion import Ingestion
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock);identity=invitation(s,a,pursuit)
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':identity});now[0]+=1;receive(s,a,person,now,'Yes if the price is suitable')
    now[0]+=1;receive(s,a,person,now,'Yes')
    assert s.snapshot(a)['pursuits'][pursuit].get('condition_text')
    now[0]+=1
    text='Yes, I agree unconditionally'
    Ingestion(s,{}).ingest(a,('prospect_direct',person),dict(account_id='synthetic-wa',chat_id='synthetic-direct',recipients=[PROSPECT],complete=True,truncated=False,messages=[dict(message_id='resolved',sender_id=PROSPECT,timestamp=now[0],kind='text',text=text,outbound=False)]))
    class Model:
        def turn(self,context):
            row=context['messages'][-1]
            return dict(schema_version=1,step='classify_reply',arguments=dict(intent='accept_group',question_event_id=identity,evidence_event_ids=[row['event_id']],exact_spans=[text],target_principal_id=context['target_principal_id'],group_agreement='explicit',number_visibility_agreement='covered_by_question',condition_text=None,suggested_public_answer=None),evidence_ids=[],decision_summary='Explicit current unconditional agreement')
    Interpreter(s,{a:Model()}).run(a,{'pursuit_id':pursuit})
    state=s.snapshot(a);p=state['pursuits'][pursuit]
    assert p['state']=='ready_to_introduce' and not p.get('condition_text') and p['resolved_conditions'][0]['evidence_event_id']
    command(s,a,actor,'person.defer',dict(person_id=person,not_before='2026-11-01T12:00:00Z',reason='Operator deferral'))
    state=s.snapshot(a);watermark=state['threads'][state['pursuits'][pursuit]['direct_thread_key']]['last_observed_seq']
    command(s,a,actor,'pursuit.resume',dict(pursuit_id=pursuit,reviewed_thread_watermark=watermark))
    assert not s.snapshot(a)['pursuits'][pursuit]['paused'] and len(wire.calls)==1
