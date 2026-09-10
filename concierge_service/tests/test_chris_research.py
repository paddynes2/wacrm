import json
from pathlib import Path
from uuid import uuid4
import pytest
from concierge_service.chris.service import Service
from concierge_service.chris.research import Research
from concierge_service.chris.contracts import ChrisError
from concierge_service.store import Store

SCENARIOS=json.loads((Path(__file__).parent/'fixtures/chris/research-scenarios.json').read_text(encoding='utf-8'))


class ScenarioSearch:
    def __init__(self, scenario): self.scenario=scenario;self.calls=[]
    def source(self, read):
        s=self.scenario
        return dict(results=[dict(url='https://example.com/'+s['kind'],title=s['name']+' at '+s['company'],text=s['fact'],read=read,status='success')])
    def search(self, query): self.calls.append(('search',query));return self.source(False)
    def read(self, url): self.calls.append(('read',url));return self.source(True)


class Replay:
    def __init__(self, scenario): self.s=scenario;self.index=0
    def turn(self, context):
        if context.get('task') == 'research_critic':
            return dict(schema_version=1,step='qualify',arguments=dict(verdict='accept',reasons=['Retained role supports thesis.'],required_fixes=[]),evidence_ids=[],decision_summary='Independent fixture critique')
        self.index+=1;s=self.s
        latest=lambda step:next(r['result'] for r in reversed(context['results']) if r['step']==step)
        if self.index==1: step,args='search_web',dict(query=s['objective']+' public leaders',purpose='discovery')
        elif self.index==2: step,args='read_url',dict(source_id=latest('search_web')['sources'][0]['source_id'],question='Verify the identity and present role')
        elif self.index==3: step,args='register_person',dict(source_id=latest('read_url')['sources'][0]['source_id'],display_name=s['name'],company_name=s['company'],profile_url='https://example.com/'+s['kind'])
        elif self.index==4: step,args='get_known_relationship',dict(person_id=latest('register_person')['person_id'])
        elif self.index==5:
            step='write_dossier';args=dict(person_id=latest('register_person')['person_id'],dossier=dict(why_this_person=s['thesis'],principal_benefit=s['thesis'],
                facts=[dict(claim_id='identity',text=s['fact'],source_ids=[latest('read_url')['sources'][0]['source_id']],span=s['fact'])],
                inferences=[s['thesis']],unknowns=[s['gap']],risks=[],approach_thesis=s['thesis'],primary_source_exception='The authoritative company role page supports the material identity and expertise.',critic=dict(verdict='accept',reasons=['The retained role directly supports this endeavour.'],required_fixes=[])))
        elif self.index==6: step,args='qualify',dict(person_id=latest('register_person')['person_id'],verdict='qualified',reasons=s['thesis'])
        else: step,args='finish',dict(result=s['gap'])
        return dict(schema_version=1,step=step,arguments=args,evidence_ids=[],decision_summary=s['thesis'])


@pytest.mark.parametrize('scenario',SCENARIOS,ids=lambda x:x['id']+'-'+x['kind'])
def test_six_endeavours_real_search_read_registration_dossier_loop(tmp_path,scenario):
    account=str(uuid4());actor=dict(user_id=str(uuid4()),request_id=str(uuid4()),role='owner')
    service=Service(Store(tmp_path/'execution.sqlite'),settings={account:dict(daily_micro_usd=20000000,job_micro_usd=5000000,daily_operations=100)})
    def command(name,payload):
        return service.command(account,dict(schema_version=1,command_id=str(uuid4()),expected_revision=service.snapshot(account)['revision'],command=name,payload=payload),actor)
    proposal=command('brief.propose',{'text':scenario['objective']})['proposal_id']
    command('brief.save_proposal',dict(proposal_id=proposal,brief=dict(objective=scenario['objective'],principal_display_name='Alex',principal_public_context='Approved public offer.',timezone='UTC')))
    command('brief.activate',dict(proposal_id=proposal))
    search=ScenarioSearch(scenario)
    Research(service,{account:Replay(scenario)},{account:search},{account:lambda p:dict(known=False,coverage='Synthetic WACRM roster',fresh=True)}).run(account,{})
    state=Service(Store(service.store.path)).snapshot(account)
    assert [x[0] for x in search.calls]==['search','read']
    assert all(p['qualification']=='qualified' for p in state['pursuits'].values())
    person=next(iter(state['people'].values()));dossier=service.blobs.get(person['dossier_ref'])
    assert dossier['facts'][0]['text']==scenario['fact'] and scenario['gap'] in dossier['unknowns']
    assert not state['actions'] and not state['permissions'] and not state['introductions']
    assert 'geography_include' not in state['brief_versions']['1']


def test_offline_suite_rejects_unexpected_external_network():
    import urllib.request
    with pytest.raises(AssertionError,match='Unexpected network access'):
        urllib.request.urlopen('https://example.com')
