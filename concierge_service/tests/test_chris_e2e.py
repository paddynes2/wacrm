import json
import datetime as dt
from uuid import uuid4
import pytest
from concierge_service.store import Store
from concierge_service.chris.service import Service
from concierge_service.chris.research import Research
from concierge_service.chris.identity import bind_connection, claim_principal
from concierge_service.chris.dispatch import Dispatcher, freeze, product_authorizer
from concierge_service.chris.ingestion import Ingestion
from concierge_service.chris.introductions import Introductions
from concierge_service.chris.projection import Projection
from concierge_service.chris.contracts import ChrisError
from concierge_service.tests.chris_support import SELF, PRINCIPAL, PROSPECT, Wire, Search, ReplayModel


def workspace(tmp_path, model=None):
    now = [dt.datetime(2026, 9, 10, 12, tzinfo=dt.timezone.utc).timestamp()]
    account = str(uuid4())
    settings = {account: dict(daily_micro_usd=20000000, job_micro_usd=5000000, daily_operations=100)}
    service = Service(Store(tmp_path/'chris.sqlite'), settings=settings, clock=lambda: now[0])
    actor = dict(user_id=str(uuid4()), request_id=str(uuid4()), role='owner')
    def command(name, payload):
        return service.command(account, dict(schema_version=1, command_id=str(uuid4()), expected_revision=service.snapshot(account)['revision'], command=name, payload=payload), actor)
    proposal = command('brief.propose', {'text':'Find distribution partners for a public software offer.'})['proposal_id']
    command('brief.save_proposal', dict(proposal_id=proposal, brief=dict(objective='Find distribution partners for a public software offer.', principal_display_name='Alex', principal_public_context='Alex builds software for distributors.', timezone='Europe/London')))
    command('brief.activate', {'proposal_id':proposal})
    search = Search()
    research = Research(service, {account:model or ReplayModel()}, {account:search}, {account:lambda p:dict(known=False,coverage='Synthetic WACRM roster',fresh=True)})
    research.run(account, {})
    assert [c[0] for c in search.calls] == ['search','read']
    state = service.snapshot(account)
    person_id, pursuit_id = next(iter(state['people'])), next(iter(state['pursuits']))
    with service.transaction(account) as (_,state):
        bind_connection(state, dict(provider_account_id='synthetic-wa',self_provider_id=SELF,type='WHATSAPP',connected=True,contract_verified=True))
    nonce = command('principal.challenge', {})['challenge']
    with service.transaction(account) as (_,state):
        claim_principal(state, nonce=nonce, sender=PRINCIPAL, chat='principal-chat', now=now[0], direct=True)
        state['people'][person_id]['provider_id']=PROSPECT
    command('person.identity_attest',dict(person_id=person_id,phone_e164='+15550001003',evidence_refs=['synthetic-control-proof'],attestation_text='Synthetic test identity proof.'))
    command('permission.record',dict(person_id=person_id,kind='contact',source_ref='synthetic-opt-in',scope_text='Contact about this introduction.',granted_at='2026-09-10T09:00:00+00:00',business_sender_identity=SELF,attestation_text='Synthetic retained opt-in for this business sender.'))
    state=service.snapshot(account)
    command('autonomy.set',dict(enabled=True,scope_kinds=['invite','reply','permission_clarification','followup','group_create','group_introduction'],displayed_authority_revision=state['authority']['revision']))
    return service,account,actor,person_id,pursuit_id,now,settings


def invitation(service, account, pursuit_id):
    with service.transaction(account) as (_,state):
        pursuit=state['pursuits'][pursuit_id]
        action=freeze(state,account,pursuit,'invite',"Hi Maya, I'm Chris, an AI assistant working with Alex. Your distribution work looked relevant. Would you like a WhatsApp introduction in a group with Alex and me? You would both see each other's number.",service.clock(),claim_ids=['role'])
        action['question_scope']=dict(principal_id=PRINCIPAL,group=True,number_visibility=True)
        action['status']='queued'
        return action['action_id']


def test_fresh_journey_restart_receipts_and_browser_closed_projection(tmp_path):
    service,account,actor,person,pursuit,now,settings=workspace(tmp_path)
    wire=Wire(service.clock)
    dispatcher=Dispatcher(service,{account:wire},product_authorizer)
    action=invitation(service,account,pursuit)
    dispatcher.execute(account,{'action_id':action})
    assert service.snapshot(account)['actions'][action]['status']=='verified'
    service=Service(Store(service.store.path),settings=settings,clock=lambda:now[0])
    now[0]+=1
    ingest=Ingestion(service,{})
    batch=dict(account_id='synthetic-wa',chat_id='synthetic-direct',recipients=[PROSPECT],complete=True,truncated=False,messages=[dict(message_id='reply-1',sender_id=PROSPECT,timestamp=now[0],kind='text',text='Yes please',outbound=False)])
    ingest.ingest(account,('prospect_direct',person),batch)
    assert service.snapshot(account)['pursuits'][pursuit]['state']=='ready_to_introduce'
    dispatcher=Dispatcher(service,{account:wire},product_authorizer)
    saga=Introductions(service,dispatcher)
    intro=saga.start(account,pursuit,'Alex, meet Maya, who leads Cedar Distribution. Maya, Alex builds software for distributors. A distribution partnership may be worth exploring. You both agreed to this introduction, so I will leave you to take it from here.')
    saga.advance(account,{'intro_id':intro})
    state=service.snapshot(account)
    assert state['introductions'][intro]['state']=='introduced'
    assert len(wire.calls)==3
    assert wire.calls[1]['raw'].count(b'name="attendees_ids"')==2
    assert state['pursuits'][pursuit]['state']=='introduced'
    projection=Projection(service,'http://127.0.0.1','synthetic-token',transport=lambda body: [Projection(service).acknowledge(account,identity,service.snapshot(account)['projection_outbox'][identity]['payload_digest'],'written') for identity in body['projection_ids']])
    projection.run(account)
    saga.advance(account,{'intro_id':intro})
    restored=Service(Store(service.store.path),settings=settings,clock=lambda:now[0]).snapshot(account)
    assert len(wire.calls)==3 and len(restored['projection_outbox'])==5
    assert all(p['status']=='acknowledged' for p in restored['projection_outbox'].values())
    assert len([e for e in restored['events'] if e['kind']=='introduction_completed'])==1
    trace=[dict(kind=e['kind'],entity_id=e['entity_id'],event_id=e['event_id']) for e in restored['events']]
    assert any(e['kind']=='discovery_search' for e in trace)
    (tmp_path/'completion-trace.json').write_text(json.dumps(dict(events=restored['events'],
        actions=restored['actions'],tool_runs=restored['tool_runs'],projections=restored['projection_outbox'],
        wire_calls=len(wire.calls),introduced=service.overview(account)['counts']['introduced']),indent=2),encoding='utf-8')


def test_response_lost_restart_never_resends(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    wire=Wire(s.clock);wire.fail_after=True
    action=invitation(s,a,pursuit)
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':action})
    assert s.snapshot(a)['actions'][action]['status']=='unknown'
    s=Service(Store(s.store.path),settings=settings,clock=lambda:now[0])
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':action})
    assert len(wire.calls)==1 and s.snapshot(a)['actions'][action]['status']=='verified'


def test_stop_during_preflight_holds_writer_free(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    wire=Wire(s.clock);action=invitation(s,a,pursuit)
    def stop():
        other=Service(Store(s.store.path),settings=settings,clock=lambda:now[0])
        with other.transaction(a) as (_,state): state['suppressions'][PROSPECT]={'reason':'STOP'}
    wire.before_wire=stop
    with pytest.raises(ChrisError,match='recipient_suppressed'): Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':action})
    assert not wire.calls
