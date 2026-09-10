"""Advance the loopback QA workspace using real host operations and fake wire."""
import argparse
import datetime as dt
import json
from pathlib import Path
import time
from uuid import uuid4
from concierge_service.store import Store
from concierge_service.chris.service import Service
from concierge_service.chris.research import Research
from concierge_service.chris.identity import bind_connection, claim_principal
from concierge_service.chris.dispatch import Dispatcher, product_authorizer
from concierge_service.chris.ingestion import Ingestion
from concierge_service.chris.introductions import Introductions
from concierge_service.tests.chris_support import Search, ReplayModel, Wire, SELF, PRINCIPAL, PROSPECT
from concierge_service.tests.chris_qa_host import ACCOUNT, USER
from concierge_service.tests.test_chris_e2e import invitation


def run(database, stage):
    path = Path(database).resolve()
    assert path.is_relative_to(Path(__file__).resolve().parents[2] / '.local')
    service = Service(Store(path), settings={ACCOUNT:dict(daily_micro_usd=20000000, job_micro_usd=5000000, daily_operations=100)})
    actor = dict(user_id=USER, role='owner', request_id=str(uuid4()))
    def command(name, payload):
        return service.command(ACCOUNT, dict(schema_version=1,command_id=str(uuid4()),expected_revision=service.snapshot(ACCOUNT)['revision'],command=name,payload=payload), actor)
    wire = Wire(service.clock)
    recorder = path.with_suffix('.wire.json')
    if recorder.exists(): wire.receipts = json.loads(recorder.read_text(encoding='utf-8'))
    if stage == 'research':
        with service.transaction(ACCOUNT) as (_,state):
            state['settings'].update(daily_micro_usd=20000000,job_micro_usd=5000000,daily_operations=100)
            state['health'].update(research_configured=True,heartbeat=service.clock())
        Research(service,{ACCOUNT:ReplayModel()},{ACCOUNT:Search()},{ACCOUNT:lambda p:dict(known=False,coverage='Synthetic WACRM roster',fresh=True)}).run(ACCOUNT,{})
    state = service.snapshot(ACCOUNT)
    if stage=='many':
        research=Research(service,{},{});revision=state['research_revision']
        for index in range(49):
            name=f'Synthetic prospect {index+1:02d} - José 東京 '+('Long-name ' * 8)
            company='Synthetic international specialist collective'
            url=f'https://example.com/qa-person-{index+1}'
            source=research.retain(ACCOUNT,dict(results=[dict(url=url,title=name,text=name+' works at '+company,read=True,status='success')]),revision)['sources'][0]
            research.register(ACCOUNT,dict(source_id=source['source_id'],display_name=name,company_name=company,profile_url=url),revision)
        state=service.snapshot(ACCOUNT)
    person = next(iter(state['people'])) if state['people'] else None
    pursuit = next(iter(state['pursuits'])) if state['pursuits'] else None
    if stage == 'invite':
        with service.transaction(ACCOUNT) as (_,state):
            bind_connection(state,dict(provider_account_id='synthetic-wa',self_provider_id=SELF,type='WHATSAPP',connected=True,contract_verified=True))
        nonce = command('principal.challenge', {})['challenge']
        with service.transaction(ACCOUNT) as (_,state):
            claim_principal(state,nonce=nonce,sender=PRINCIPAL,chat='principal-chat',now=time.time(),direct=True)
            state['people'][person]['provider_id']=PROSPECT
        command('person.identity_attest',dict(person_id=person,phone_e164='+15550001003',evidence_refs=['synthetic-control-proof'],attestation_text='Synthetic QA control proof.'))
        command('permission.record',dict(person_id=person,kind='contact',source_ref='synthetic-opt-in',scope_text='Introduction to Alex.',granted_at=dt.datetime.now(dt.timezone.utc).isoformat(),business_sender_identity=SELF,attestation_text='Synthetic QA opt-in.'))
        state=service.snapshot(ACCOUNT)
        command('autonomy.set',dict(enabled=True,scope_kinds=['invite','reply','permission_clarification','followup','group_create','group_introduction'],displayed_authority_revision=state['authority']['revision']))
        action=invitation(service,ACCOUNT,pursuit)
        Dispatcher(service,{ACCOUNT:wire},product_authorizer).execute(ACCOUNT,{'action_id':action})
    if stage in {'ambiguous','consent'}:
        Ingestion(service,{}).ingest(ACCOUNT,('prospect_direct',person),dict(account_id='synthetic-wa',chat_id='synthetic-direct',recipients=[PROSPECT],complete=True,truncated=False,
            messages=[dict(message_id='qa-'+stage,sender_id=PROSPECT,timestamp=time.time(),kind='text',text='Sure, tell me more' if stage=='ambiguous' else 'Yes please',outbound=False)]))
    if stage in {'partial','complete'}:
        saga=Introductions(service,Dispatcher(service,{ACCOUNT:wire},product_authorizer))
        intro=saga.start(ACCOUNT,pursuit,'Alex, meet Maya, who leads Cedar Distribution. Maya, Alex builds software for distributors. A distribution partnership may be worth exploring. You both agreed to this introduction, so I will leave you to take it from here.')
        if stage=='partial': wire.participants=[SELF,PROSPECT]
        saga.advance(ACCOUNT,{'intro_id':intro})
    if stage=='pause': command('workspace.pause', {'reason':'QA pause verification'})
    if stage=='projection':
        from concierge_service.chris.projection import Projection
        from concierge_service.tests.chris_qa_host import TOKEN
        Projection(service,'http://127.0.0.1:18762',TOKEN).run(ACCOUNT)
    recorder.write_text(json.dumps(wire.receipts),encoding='utf-8')
    state=service.snapshot(ACCOUNT)
    (path.parent/('trace-'+stage+'.json')).write_text(json.dumps(state['events'],indent=2),encoding='utf-8')
    if stage=='projection':
        assert len(wire.receipts)==3
        assert len(state['projection_outbox'])==5 and all(p['status']=='acknowledged' for p in state['projection_outbox'].values())
        assert sum(e['kind']=='introduction_completed' for e in state['events'])==1
        path.with_suffix('.completion.json').write_text(json.dumps(dict(events=state['events'],actions=state['actions'],projections=state['projection_outbox'],tool_runs=state['tool_runs'],wire_receipts=wire.receipts),indent=2),encoding='utf-8')
    print(json.dumps(dict(stage=stage,person=person,pursuit=pursuit,overview=service.overview(ACCOUNT))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--db',required=True);parser.add_argument('stage',choices=['research','invite','ambiguous','consent','partial','complete','pause','many','projection'])
    args=parser.parse_args();run(args.db,args.stage)
