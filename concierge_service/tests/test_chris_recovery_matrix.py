"""Faults at real host boundaries; every wire assertion uses the recorder."""
from copy import deepcopy
from uuid import uuid4
import pytest
from concierge_service.chris.contracts import ChrisError, digest
from concierge_service.chris.dispatch import Dispatcher, product_authorizer
from concierge_service.chris.ingestion import Ingestion
from concierge_service.chris.permissions import eligibility
from concierge_service.chris.interpreter import Interpreter
from concierge_service.chris.service import Service
from concierge_service.store import Store
from concierge_service.tests.test_chris_e2e import workspace, invitation
from concierge_service.tests.chris_support import Wire, PROSPECT


def receive(s,a,person,now,text='Yes',**extra):
    batch=dict(account_id='synthetic-wa',chat_id='synthetic-direct',recipients=[PROSPECT],complete=True,truncated=False,
        messages=[dict(message_id='reply',sender_id=PROSPECT,timestamp=now[0],text=text,kind='text',outbound=False,**extra)])
    Ingestion(s,{}).ingest(a,('prospect_direct',person),batch)
    return batch


@pytest.mark.parametrize('field,value',[('text','changed'),('recipients',['stranger']),('group_subject','changed')],ids=['D02-text','D02-recipient','D02-subject'])
def test_frozen_mutation_denied_before_wire(tmp_path,field,value):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    action=invitation(s,a,pursuit);wire=Wire(s.clock)
    with s.transaction(a) as (_,state): state['actions'][action]['frozen'][field]=value
    with pytest.raises(ChrisError,match='action_changed'): Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':action})
    assert not wire.calls and Service(Store(s.store.path)).snapshot(a)['actions'][action]['status']=='queued'


@pytest.mark.parametrize('fault',['old','duplicate','foreign_sender','foreign_group','missing'],ids=['D14','D15','D10-sender','D10-group','D16'])
def test_uncertain_receipts_never_retry_mutation(tmp_path,fault):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    wire=Wire(s.clock);wire.fail_after=True;action=invitation(s,a,pursuit)
    dispatcher=Dispatcher(s,{a:wire},product_authorizer);dispatcher.execute(a,{'action_id':action})
    observations=wire.observe_action(s.snapshot(a)['actions'][action])
    if fault=='old': observations[0]['timestamp']-=86400
    elif fault=='duplicate': observations.append({**observations[0],'message_id':'second'})
    elif fault=='foreign_sender': observations[0]['sender_id']='stranger'
    elif fault=='foreign_group': observations[0]['recipients']=['stranger']
    else: observations=[]
    wire.observe_action=lambda action:observations
    for _ in range(6):
        restored=Service(Store(s.store.path),settings=settings,clock=lambda:now[0])
        Dispatcher(restored,{a:wire},product_authorizer).reconcile(a,{'action_id':action})
    assert len(wire.calls)==1 and restored.snapshot(a)['actions'][action]['status']=='needs_attention'


@pytest.mark.parametrize('flag',['forwarded','quoted','truncated'],ids=['C14-forward','C14-quote','R19'])
def test_incomplete_or_quoted_affirmative_has_no_scope(tmp_path,flag):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock)
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':invitation(s,a,pursuit)})
    now[0]+=1;receive(s,a,person,now,**{flag:True})
    assert not any(p['kind']=='group' for p in s.snapshot(a)['permissions'].values()) and len(wire.calls)==1


def test_edit_revokes_consent_and_duplicate_is_inert(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock)
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':invitation(s,a,pursuit)})
    now[0]+=1;batch=receive(s,a,person,now)
    first=s.snapshot(a);receive(s,a,person,now)
    assert s.snapshot(a)['event_seq']==first['event_seq']
    batch['messages'][0]['text']='[deleted]';batch['messages'][0]['kind']='deleted'
    Ingestion(s,{}).ingest(a,('prospect_direct',person),batch)
    state=Service(Store(s.store.path)).snapshot(a)
    assert any(e['kind']=='message_edit' for e in state['events'])
    assert not any(p['kind']=='group' and p['status']=='valid' for p in state['permissions'].values())
    assert 'group_permission_missing' in eligibility(state,state['pursuits'][pursuit],now[0],'group_create')


def test_future_skew_retains_original_but_blocks_progress(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock)
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':invitation(s,a,pursuit)})
    future=[now[0]+1000];receive(s,a,person,future)
    state=s.snapshot(a);thread=next(iter(state['threads'].values()))
    assert not thread['history_ready'] and next(iter(thread['messages'].values()))['provider_original_timestamp']==future[0]
    assert not any(p['kind']=='group' for p in state['permissions'].values())


@pytest.mark.parametrize('mutation,reason',[('contact','contact_permission_missing'),('synthetic','synthetic_live_evidence'),('expired','group_permission_missing'),('principal','introduction_permission_missing'),('takeover','manual_takeover')],ids=['C01','A20','C25','C24','I15'])
def test_current_evidence_is_revalidated(tmp_path,mutation,reason):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock)
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':invitation(s,a,pursuit)})
    now[0]+=1;receive(s,a,person,now)
    with s.transaction(a) as (_,state):
        if mutation=='contact':
            for p in state['permissions'].values():
                if p['kind']=='contact': p['status']='revoked'
        elif mutation=='synthetic': state['mode']='live'
        elif mutation=='expired': now[0]+=31*86400
        elif mutation=='principal': state['principal']['provider_id']='another-principal'
        else: state['pursuits'][pursuit]['human_takeover']=True
    state=s.snapshot(a)
    assert reason in eligibility(state,state['pursuits'][pursuit],now[0],'group_create') and len(wire.calls)==1


@pytest.mark.parametrize('intent,text',[('question','What is the price?'),('conditional','Yes if it is free'),('defer','Ask me later'),('referral','Speak with my colleague'),('unclear','Perhaps')],ids=['C23','C12','C11','C22','C06'])
def test_semantic_interpreter_retains_owned_evidence_without_granting_permission(tmp_path,intent,text):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock)
    action=invitation(s,a,pursuit);Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':action})
    now[0]+=1;receive(s,a,person,now,text)
    class Classifier:
        def turn(self,context):
            row=context['messages'][-1]
            return dict(schema_version=1,step='classify_reply',evidence_ids=[row['event_id']],decision_summary='Fixture interpretation',arguments=dict(intent=intent,question_event_id=action,evidence_event_ids=[row['event_id']],exact_spans=[text],target_principal_id=context['target_principal_id'],group_agreement='absent',number_visibility_agreement='absent',condition_text=text if intent in {'conditional','defer'} else None,suggested_public_answer=None))
    Interpreter(s,{a:Classifier()}).run(a,{'pursuit_id':pursuit})
    state=Service(Store(s.store.path)).snapshot(a)
    assert state['pursuits'][pursuit]['interpretation_ref'] and not any(p['kind']=='group' for p in state['permissions'].values())
    assert len(wire.calls)==1
