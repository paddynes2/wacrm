from contextlib import contextmanager
from uuid import uuid4
import pytest
from concierge_service.chris.service import Service
from concierge_service.chris.research import Research
from concierge_service.chris.conversation import Conversation
from concierge_service.chris.dispatch import Dispatcher,product_authorizer,freeze
from concierge_service.chris.scheduler import reserve,BUDGET_JOB
from concierge_service.chris.ingestion import Ingestion
from concierge_service.chris.contracts import ChrisError
from concierge_service.store import Store
from concierge_service.tests.test_chris_e2e import workspace,invitation
from concierge_service.tests.test_chris_recovery_matrix import receive
from concierge_service.tests.chris_support import Wire,ReplayModel,Search,PROSPECT


def blank(tmp_path):
    a=str(uuid4());s=Service(Store(tmp_path/'continuation.sqlite'),settings={a:dict(daily_micro_usd=20000000,job_micro_usd=5000000,daily_operations=100)})
    with s.transaction(a) as (_,state):
        state['active_brief_revision']=1;state['research_revision']=1
        state['brief_versions']['1']=dict(objective='Find distribution partners.',principal_display_name='Alex',principal_public_context='Software for distributors.',timezone='UTC')
    return s,a


def test_research_checkpoint_survives_process_boundary_without_repaying_completed_search(tmp_path):
    s,a=blank(tmp_path);first_search=Search();original=s.transaction;crashed=[False];pass_id=str(uuid4())
    class Crash(BaseException): pass
    @contextmanager
    def transaction(account,recovery=False):
        with original(account,recovery) as pair:
            yield pair
            checkpoint=pair[1]['research_passes'].get(pass_id,{}).get('next_turn')==1
        if checkpoint and not crashed[0]: crashed[0]=True;raise Crash()
    s.transaction=transaction
    relationship={a:lambda p:dict(known=False,fresh=True,coverage='Synthetic roster')}
    with pytest.raises(Crash): Research(s,{a:ReplayModel()},{a:first_search},relationship).run(a,{'pass_id':pass_id})
    restored=Service(Store(s.store.path));second_search=Search();model=ReplayModel();model.turns=1
    Research(restored,{a:model},{a:second_search},relationship).run(a,{'pass_id':pass_id})
    assert [c[0] for c in first_search.calls]==['search'] and [c[0] for c in second_search.calls]==['read']
    assert any(p['qualification']=='qualified' for p in restored.snapshot(a)['pursuits'].values())


def test_irrelevant_first_queries_use_alternative_strategy(tmp_path):
    s,a=blank(tmp_path)
    class AlternativeSearch(Search):
        def search(self,query):
            if query.startswith('alternative'):
                self.calls.append(('search',query));return {'results':[]}
            return super().search(query)
    class Model:
        calls=0
        delegate=ReplayModel()
        def turn(self,context):
            self.calls+=1
            if self.calls<=2:
                return dict(schema_version=1,step='search_web',arguments=dict(query='alternative '+str(self.calls),purpose='discovery'),evidence_ids=[],decision_summary='Try another route after empty results')
            return self.delegate.turn(context)
    search=AlternativeSearch()
    Research(s,{a:Model()},{a:search},{a:lambda p:dict(known=False,fresh=True,coverage='Synthetic roster')}).run(a,{})
    assert [c[0] for c in search.calls]==['search','search','search','read']
    assert len(s.snapshot(a)['people'])==1


def test_job_budget_is_cumulative_and_unknown_charge_is_not_refunded(tmp_path):
    s,a=blank(tmp_path)
    with s.transaction(a) as (_,state): state['settings']['job_micro_usd']=100000
    token=BUDGET_JOB.set('synthetic-job')
    try:
        reserve(s,a,'model',{'turn':0},100000)
        with pytest.raises(ChrisError,match='job_budget_exhausted'): reserve(s,a,'model',{'turn':1},100000)
    finally: BUDGET_JOB.reset(token)
    assert len(s.snapshot(a)['tool_runs'])==1


def test_generic_yes_requires_one_verified_group_clarification(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock)
    with s.transaction(a) as (_,state):
        action=freeze(state,a,state['pursuits'][pursuit],'invite',"I'm Chris, an AI assistant working with Alex. Would you like an introduction to Alex?",now[0]);action['status']='queued';action_id=action['action_id']
    dispatch=Dispatcher(s,{a:wire},product_authorizer);dispatch.execute(a,{'action_id':action_id});now[0]+=1;receive(s,a,person,now)
    assert s.snapshot(a)['pursuits'][pursuit]['state']=='awaiting_group_permission'
    class Model:
        def turn(self,context):
            if 'proposed_text' in context: args=dict(verdict='qualified',reasons=['Exact scope.'],required_fixes=[]);step='qualify'
            else: args=dict(purpose='permission_clarification',pursuit_id=pursuit,text='Would you like the introduction in a WhatsApp group with Alex and me, Chris, where you would both see each other’s number?',claim_ids=[],answered_event_ids=[]);step='propose_message'
            return dict(schema_version=1,step=step,arguments=args,evidence_ids=[],decision_summary='Clarify exact group scope')
    Conversation(s,{a:Model()},None).run(a,dict(pursuit_id=pursuit,purpose='permission_clarification'))
    clarification=next(r for r in s.snapshot(a)['actions'].values() if r['kind']=='permission_clarification')
    dispatch.execute(a,{'action_id':clarification['action_id']});now[0]+=1
    batch=dict(account_id='synthetic-wa',chat_id='synthetic-direct',recipients=[PROSPECT],complete=True,truncated=False,messages=[dict(message_id='clarified',sender_id=PROSPECT,timestamp=now[0],text='Yes please',kind='text',outbound=False)])
    Ingestion(s,{}).ingest(a,('prospect_direct',person),batch)
    assert s.snapshot(a)['pursuits'][pursuit]['state']=='ready_to_introduce' and len(wire.calls)==2


def test_two_clarifications_stop_only_the_affected_pursuit(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock)
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':invitation(s,a,pursuit)});now[0]+=1;receive(s,a,person,now,'Who is Alex?')
    with s.transaction(a) as (_,state): state['pursuits'][pursuit]['clarification_count']=2
    class NoModel:
        def turn(self,context): raise AssertionError('No third clarification model call')
    Conversation(s,{a:NoModel()},None).run(a,dict(pursuit_id=pursuit,purpose='permission_clarification'))
    state=s.snapshot(a);assert state['pursuits'][pursuit]['attention']=='clarification_limit' and not state['authority']['paused'] and len(wire.calls)==1
