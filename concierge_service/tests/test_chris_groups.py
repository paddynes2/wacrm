import pytest
from concierge_service.chris.dispatch import Dispatcher, product_authorizer
from concierge_service.chris.ingestion import Ingestion
from concierge_service.chris.introductions import Introductions
from concierge_service.chris.conversation import Conversation
from concierge_service.tests.test_chris_e2e import workspace, invitation
from concierge_service.tests.test_chris_recovery_matrix import receive
from concierge_service.tests.chris_support import Wire, SELF, PRINCIPAL, PROSPECT


def ready(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock)
    dispatch=Dispatcher(s,{a:wire},product_authorizer)
    dispatch.execute(a,{'action_id':invitation(s,a,pursuit)})
    now[0]+=1;receive(s,a,person,now)
    saga=Introductions(s,dispatch)
    intro=saga.start(a,pursuit,'Alex, meet Maya of Cedar Distribution. Maya, Alex builds software for distributors. You both agreed to connect.')
    return s,a,person,pursuit,now,wire,dispatch,saga,intro


def test_group_only_is_partial_then_delayed_membership_completes_once(tmp_path):
    s,a,person,pursuit,now,wire,dispatch,saga,intro=ready(tmp_path)
    wire.participants=[SELF,PROSPECT];saga.advance(a,{'intro_id':intro})
    state=s.snapshot(a);assert state['introductions'][intro]['state']=='membership_pending'
    assert s.overview(a)['counts']['introduced']==0 and len(wire.calls)==2
    wire.participants=[SELF,PRINCIPAL,PROSPECT];saga.advance(a,{'intro_id':intro})
    assert len(wire.calls)==2
    now[0]+=60;saga.advance(a,{'intro_id':intro});saga.advance(a,{'intro_id':intro})
    assert len(wire.calls)==3 and s.overview(a)['counts']['introduced']==1


@pytest.mark.parametrize('cessation',['No','Do not add me','Wrong number'])
def test_withdrawal_between_group_and_substantive_message(tmp_path,cessation):
    s,a,person,pursuit,now,wire,dispatch,saga,intro=ready(tmp_path)
    wire.participants=[SELF,PROSPECT];saga.advance(a,{'intro_id':intro})
    now[0]+=1;receive(s,a,person,now,cessation)
    wire.participants=[SELF,PRINCIPAL,PROSPECT];now[0]+=60;saga.advance(a,{'intro_id':intro})
    assert len(wire.calls)==2 and s.snapshot(a)['introductions'][intro]['state']=='cancelled_after_create'


@pytest.mark.parametrize('members',[[PRINCIPAL,PROSPECT],[SELF,PROSPECT],[SELF,PRINCIPAL,PROSPECT,'stranger']])
def test_later_membership_change_retains_history_and_disables_reactive_disclosure(tmp_path,members):
    s,a,person,pursuit,now,wire,dispatch,saga,intro=ready(tmp_path);saga.advance(a,{'intro_id':intro})
    Ingestion(s,{}).ingest(a,('introduction_group',intro),dict(account_id='synthetic-wa',chat_id='synthetic-group',recipients=[x for x in members if x!=SELF],complete=True,truncated=False,messages=[]))
    state=s.snapshot(a);assert state['introductions'][intro]['state']=='introduced'
    # Self membership is checked afresh at dispatch even if the external list is unchanged.
    if members!=[PRINCIPAL,PROSPECT]: assert state['introductions'][intro]['membership_changed']
    assert len(wire.calls)==3 and s.overview(a)['counts']['introduced']==1


def test_owned_addressed_group_question_uses_group_not_direct_projection(tmp_path):
    s,a,person,pursuit,now,wire,dispatch,saga,intro=ready(tmp_path);saga.advance(a,{'intro_id':intro});now[0]+=1
    Ingestion(s,{}).ingest(a,('introduction_group',intro),dict(account_id='synthetic-wa',chat_id='synthetic-group',recipients=[PRINCIPAL,PROSPECT],complete=True,truncated=False,messages=[dict(message_id='group-question',sender_id=PRINCIPAL,timestamp=now[0],text='Chris, what does Maya do?',kind='text',outbound=False)]))
    class Model:
        def turn(self,context):
            if 'proposed_text' in context:
                return dict(schema_version=1,step='qualify',arguments=dict(verdict='qualified',reasons=['Supported role.'],required_fixes=[]),evidence_ids=[],decision_summary='Public fact only')
            return dict(schema_version=1,step='propose_message',arguments=dict(purpose='reply',pursuit_id=pursuit,text='Maya leads Cedar Distribution.',claim_ids=['role'],answered_event_ids=[context['messages'][0]['event_id']]),evidence_ids=[],decision_summary='Answer the addressed factual question')
    Conversation(s,{a:Model()},saga).run(a,dict(pursuit_id=pursuit,purpose='reply',intro_id=intro))
    action=next(v for v in s.snapshot(a)['actions'].values() if v['kind']=='reply')
    before=len(s.snapshot(a)['projection_outbox']);dispatch.execute(a,{'action_id':action['action_id']})
    state=s.snapshot(a)
    assert len(wire.calls)==4 and wire.calls[-1]['frozen']['chat_id']=='synthetic-group'
    assert set(wire.calls[-1]['frozen']['recipients'])=={PRINCIPAL,PROSPECT}
    assert len(state['projection_outbox'])==before and state['pursuits'][pursuit]['state']=='introduced'
