import pytest
from concierge_service.chris.ingestion import Ingestion
from concierge_service.chris.dispatch import Dispatcher,product_authorizer,freeze
from concierge_service.chris.contracts import digest
from concierge_service.chris.scheduler import Scheduler
from concierge_service.tests.test_chris_e2e import workspace,invitation
from concierge_service.tests.chris_support import Wire,SELF,PRINCIPAL,PROSPECT


@pytest.mark.parametrize('fault',['other_chat','reply_to','media','two_questions','equal_time'],ids=['I02','C17','C15','C16','I10'])
def test_scope_requires_exact_owned_question_and_unambiguous_text(tmp_path,fault):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock);action=invitation(s,a,pursuit)
    if fault=='two_questions':
        with s.transaction(a) as (_,state):
            row=state['actions'][action];row['frozen']['text']+=' Are you the right person?';row['frozen']['question_scope']['pending_question_count']=2;row['digest']=digest(row['frozen'])
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':action});now[0]+=1
    message=dict(message_id='reply',sender_id=PROSPECT,timestamp=now[0],kind='media' if fault=='media' else 'text',text='Yes',outbound=False)
    if fault=='reply_to': message['reply_to']='a-different-question'
    messages=[message]
    if fault=='equal_time': messages.insert(0,{**message,'message_id':'question','text':'What is the price?'})
    Ingestion(s,{}).ingest(a,('prospect_direct',person),dict(account_id='synthetic-wa',chat_id='different-direct' if fault=='other_chat' else 'synthetic-direct',recipients=[PROSPECT],complete=True,truncated=False,messages=messages))
    assert not any(p['kind']=='group' and p['status']=='valid' for p in s.snapshot(a)['permissions'].values()) and len(wire.calls)==1


def test_possible_lost_send_echo_reconciles_before_manual_takeover(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock);wire.fail_after=True;action=invitation(s,a,pursuit)
    dispatch=Dispatcher(s,{a:wire},product_authorizer);dispatch.execute(a,{'action_id':action})
    row=wire.receipts[0]
    Ingestion(s,{}).ingest(a,('prospect_direct',person),dict(account_id='synthetic-wa',chat_id=row['chat_id'],recipients=[PROSPECT],complete=True,truncated=False,messages=[dict(message_id=row['message_id'],sender_id=SELF,timestamp=row['timestamp'],kind='text',text=row['text'],outbound=True)]))
    assert not s.snapshot(a)['pursuits'][pursuit]['human_takeover']
    dispatch.reconcile(a,{'action_id':action})
    assert s.snapshot(a)['actions'][action]['status']=='verified' and len(wire.calls)==1


def test_unowned_and_malformed_chat_do_not_block_owned_stop_with_browser_closed(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);calls=[]
    class Provider:
        def connection(self): return dict(provider_account_id='synthetic-wa',self_provider_id=SELF,type='WHATSAPP',connected=True,contract_verified=True)
        def chats(self): return [dict(account_id='synthetic-wa',chat_id='unowned',is_group=True,recipients=['stranger']),dict(account_id='synthetic-wa',chat_id='malformed',is_group=False,recipients=[PROSPECT]),dict(account_id='synthetic-wa',chat_id='valid',is_group=False,recipients=[PROSPECT])]
        def read_chat(self,chat):
            calls.append(chat)
            if chat=='malformed': raise ValueError('synthetic bad schema')
            assert chat=='valid'
            return dict(account_id='synthetic-wa',chat_id=chat,recipients=[PROSPECT],complete=True,truncated=False,messages=[dict(message_id='stop',sender_id=PROSPECT,timestamp=now[0],text='STOP',kind='text',outbound=False)])
    ingress=Ingestion(s,{a:Provider()})
    with s.transaction(a) as (db,state): s.enqueue(db,a,state,'sync')
    worker=Scheduler(s,{'sync':ingress.sync});worker.process_one(a);worker.close()
    state=s.snapshot(a)
    assert calls==['malformed','valid'] and state['pursuits'][pursuit]['state']=='suppressed'
    assert state['health']['chat:malformed']=='chat_quarantined'


def test_verified_manual_message_cancels_queued_bot_action(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);action=invitation(s,a,pursuit)
    Ingestion(s,{}).ingest(a,('prospect_direct',person),dict(account_id='synthetic-wa',chat_id='synthetic-direct',recipients=[PROSPECT],complete=True,truncated=False,messages=[dict(message_id='manual',sender_id=SELF,timestamp=now[0],text='I will handle this personally.',kind='text',outbound=True)]))
    state=s.snapshot(a);assert state['pursuits'][pursuit]['human_takeover'] and state['actions'][action]['status']=='cancelled'
