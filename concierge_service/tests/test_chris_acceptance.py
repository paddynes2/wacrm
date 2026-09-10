import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
import pytest
from concierge_service.chris.contracts import parse, command, ChrisError
from concierge_service.chris.identity import challenge, claim_principal
from concierge_service.chris.dispatch import Dispatcher, product_authorizer, multipart
from concierge_service.chris.ingestion import Ingestion
from concierge_service.chris.introductions import Introductions
from concierge_service.chris.scheduler import reserve
from concierge_service.chris.search_provider import public_url, Exa
from concierge_service.tests.test_chris_e2e import workspace, invitation
from concierge_service.tests.chris_support import Wire, PROSPECT, PRINCIPAL, SELF

CORPUS = json.loads((Path(__file__).parent/'fixtures/chris/contracts/corpus.json').read_text(encoding='utf-8'))

@pytest.mark.parametrize('fixture', CORPUS, ids=lambda f:f['name'])
def test_shared_contract_corpus(fixture):
    if fixture['accept']: command(parse(fixture['raw']))
    else:
        with pytest.raises(ChrisError): command(parse(fixture['raw']))

@pytest.mark.parametrize('reply', ['Sure, tell me more', 'Yes, but email me', 'Yes, if pricing is below X', '👍', 'sí', '"yes"', 'Who is Alex?', 'Talk to my colleague', 'Not now, ask in November'])
def test_ambiguous_replies_never_create_group_permission(tmp_path, reply):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    wire=Wire(s.clock);action=invitation(s,a,pursuit)
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':action})
    now[0]+=1
    Ingestion(s,{}).ingest(a,('prospect_direct',person),dict(account_id='synthetic-wa',chat_id='synthetic-direct',recipients=[PROSPECT],complete=True,truncated=False,messages=[dict(message_id='reply',sender_id=PROSPECT,timestamp=now[0],text=reply,kind='text',outbound=False)]))
    state=s.snapshot(a)
    assert not any(p['kind']=='group' for p in state['permissions'].values())
    assert len(wire.calls)==1 and not state['introductions']

@pytest.mark.parametrize('reply', ['STOP', "Don't contact me again", 'Wrong number', 'No thanks', 'Not interested'])
def test_cessation_wins_over_same_batch_and_delayed_yes(tmp_path,reply):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    wire=Wire(s.clock);action=invitation(s,a,pursuit)
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':action})
    now[0]+=1
    batch=dict(account_id='synthetic-wa',chat_id='synthetic-direct',recipients=[PROSPECT],complete=True,truncated=False,messages=[dict(message_id='yes',sender_id=PROSPECT,timestamp=now[0],text='Yes please',kind='text',outbound=False),dict(message_id='stop',sender_id=PROSPECT,timestamp=now[0],text=reply,kind='text',outbound=False)])
    ingress=Ingestion(s,{})
    ingress.ingest(a,('prospect_direct',person),batch)
    batch['messages']=[dict(message_id='late',sender_id=PROSPECT,timestamp=now[0]-1,text='Yes please',kind='text',outbound=False)]
    ingress.ingest(a,('prospect_direct',person),batch)
    state=s.snapshot(a)
    assert state['pursuits'][pursuit]['state'] in {'declined','suppressed'}
    assert not any(p['kind']=='group' and p['status']=='valid' for p in state['permissions'].values())
    assert len(wire.calls)==1

@pytest.mark.parametrize('members', [[SELF,PROSPECT],[PRINCIPAL,PROSPECT],[SELF,PRINCIPAL,PROSPECT,'stranger']])
def test_wrong_missing_self_or_extra_group_member_prevents_intro(tmp_path,members):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    wire=Wire(s.clock);action=invitation(s,a,pursuit);dispatch=Dispatcher(s,{a:wire},product_authorizer)
    dispatch.execute(a,{'action_id':action});now[0]+=1
    Ingestion(s,{}).ingest(a,('prospect_direct',person),dict(account_id='synthetic-wa',chat_id='synthetic-direct',recipients=[PROSPECT],complete=True,truncated=False,messages=[dict(message_id='yes',sender_id=PROSPECT,timestamp=now[0],text='Yes',kind='text',outbound=False)]))
    saga=Introductions(s,dispatch);intro=saga.start(a,pursuit,'Alex, meet Maya. Please take it from here.')
    wire.participants=members;saga.advance(a,{'intro_id':intro})
    assert len(wire.calls)==2 and s.overview(a)['counts']['introduced']==0

def test_two_workers_last_allowance_and_same_action(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    with s.transaction(a) as (_,state):
        state['budgets']={};state['settings'].update(daily_micro_usd=100,job_micro_usd=100,daily_operations=1)
    def reserve_one(i):
        try: return reserve(s,a,'search',{'query':str(i)},100)[1]
        except ChrisError: return False
    with ThreadPoolExecutor(max_workers=2) as pool: assert sum(pool.map(reserve_one,[1,2]))==1
    wire=Wire(s.clock);action=invitation(s,a,pursuit);dispatch=Dispatcher(s,{a:wire},product_authorizer)
    def send(_):
        try: dispatch.execute(a,{'action_id':action})
        except ChrisError: return
    with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(send,[1,2]))
    assert len(wire.calls)==1

def test_modified_frozen_content_denies_wire(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);wire=Wire(s.clock);action=invitation(s,a,pursuit)
    with s.transaction(a) as (_,state): state['actions'][action]['frozen']['text']='tampered'
    with pytest.raises(ChrisError,match='action_changed'): Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':action})
    assert not wire.calls

@pytest.mark.parametrize('url',['http://example.com','https://127.0.0.1','https://[::1]','https://localhost','https://a.local','https://user:secret@example.com','https://169.254.169.254','file:///etc/passwd','https://2130706433'])
def test_unsafe_url_refused_before_transport(url):
    with pytest.raises((ChrisError,ValueError)): public_url(url)

def test_exa_exact_request_and_blocked_content():
    calls=[]
    def http(method,url,headers,body):
        calls.append((method,url,body))
        return 200,{},dict(results=[dict(url='https://example.com/person',title='Person',text='Sign in to continue')],costDollars={'total':0.001})
    exa=Exa(dict(provider='exa',api_key='synthetic',http=http))
    result=exa.read('https://example.com/person')
    assert calls==[('POST','https://api.exa.ai/contents',dict(urls=['https://example.com/person'],text=True,maxAgeHours=24))]
    assert result['results'][0]['status']=='inaccessible' and result['estimated_cost_micro_usd']==1000

def test_nonce_expiry_forward_replay_and_distinctness(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    with s.transaction(a) as (_,state):
        nonce=challenge(state,now[0])
        with pytest.raises(ChrisError): claim_principal(state,nonce=nonce,sender=SELF,chat='direct',now=now[0],direct=True)
        with pytest.raises(ChrisError): claim_principal(state,nonce=nonce,sender=PRINCIPAL,chat='direct',now=now[0],direct=True,forwarded=True)
        with pytest.raises(ChrisError): claim_principal(state,nonce=nonce,sender=PRINCIPAL,chat='direct',now=now[0]+601,direct=True)

def test_multipart_preserves_unicode_newlines_and_repeated_fields():
    raw,header=multipart([('attendees_ids',PRINCIPAL),('attendees_ids',PROSPECT),('text','Hello Maya\nCafé 🌍')])
    assert raw.count(b'name="attendees_ids"')==2 and 'Café 🌍'.encode() in raw and b'Hello Maya\n' in raw
    assert header.split('boundary=')[1].encode() in raw
