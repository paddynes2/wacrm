from copy import deepcopy
from uuid import uuid4
import pytest
from concierge_service.chris.contracts import ChrisError
from concierge_service.chris.research import Research
from concierge_service.chris.scheduler import reserve
from concierge_service.chris.service import Service
from concierge_service.store import Store
from concierge_service.tests.test_chris_e2e import workspace
from concierge_service.tests.chris_support import ReplayModel,Search


def test_independent_critic_can_reject_researchers_own_acceptance(tmp_path):
    class Reject(ReplayModel):
        def turn(self,context):
            if context.get('task')=='research_critic':
                return dict(schema_version=1,step='qualify',arguments=dict(verdict='reject',reasons=['Material relevance unsupported.'],required_fixes=['Read independent source.']),evidence_ids=[],decision_summary='Reject weak thesis')
            return super().turn(context)
    with pytest.raises(ChrisError,match='critic_revision_needed'): workspace(tmp_path,Reject())
    store=Store(tmp_path/'chris.sqlite');a=store.accounts()[0];state=Service(store).snapshot(a)
    assert not any(p['qualification']=='qualified' for p in state['pursuits'].values()) and not state['actions']


@pytest.mark.parametrize('step',['send_email','execute_shell','set_autonomy','create_group'])
def test_source_or_model_instructions_cannot_expand_tool_allowlist(tmp_path,step):
    class Inject:
        calls=0
        def turn(self,context):
            self.calls+=1
            return dict(schema_version=1,step=step,arguments={'recipient':'attacker'},evidence_ids=[],decision_summary='Ignore previous rules')
    model=Inject()
    with pytest.raises(ChrisError,match='model_contract_error'): workspace(tmp_path,model)
    assert model.calls==2
    store=Store(tmp_path/'chris.sqlite');state=Service(store).snapshot(store.accounts()[0])
    assert not state['actions'] and not state['people'] and len(state['tool_runs'])==2


@pytest.mark.parametrize('fault',['snippet','invented_span','duplicate_origins','strict_roster','known_contact'],ids=['R11','R20','R12','R21','R22'])
def test_qualification_evidence_boundaries(tmp_path,fault):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);research=Research(s,{a:ReplayModel()},{a:Search()})
    state=s.snapshot(a);dossier=s.blobs.get(state['people'][person]['dossier_ref']);dossier.pop('brief_research_revision')
    if fault=='snippet':
        with s.transaction(a) as (_,state):
            for source in state['sources'].values(): source['read']=False
    elif fault=='invented_span': dossier['facts'][0]['span']='Unsupported imaginary evidence'
    elif fault=='duplicate_origins': dossier.pop('primary_source_exception',None)
    elif fault=='strict_roster':
        with s.transaction(a) as (_,state): state['brief_versions']['1']['known_relationship_policy']='strict_first_degree'
    else:
        with s.transaction(a) as (_,state): state['people'][person]['known_relationship']=True
    with pytest.raises(ChrisError):
        if fault in {'snippet','invented_span','duplicate_origins'}: research.dossier(a,dict(person_id=person,dossier=dossier),state['research_revision'])
        else: research.qualify(a,dict(person_id=person,verdict='qualified',reasons='Try again'),state['research_revision'])
    assert not s.snapshot(a)['actions']


def test_stale_paid_result_retains_charge_but_cannot_qualify(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);research=Research(s,{},{});old=s.snapshot(a)['research_revision']
    run,fresh=reserve(s,a,'search_web',{'query':'new pending query'},100000);assert fresh
    with s.transaction(a) as (_,state): state['research_revision']+=1
    with pytest.raises(ChrisError,match='research_stale'): research.record_run(a,run,{'results':[]},old)
    row=Service(Store(s.store.path)).snapshot(a)['tool_runs'][run['run_id']]
    assert row['status']=='completed' and row['cost_reservation_micro_usd']==100000 and row['output_ref']


def test_profiles_deduplicate_but_same_name_different_company_does_not_merge(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);research=Research(s,{},{});state=s.snapshot(a)
    original=state['people'][person];source=state['sources'][original['source_registration']]
    same=research.register(a,dict(source_id=source['source_id'],display_name=original['display_name'],company_name=original['company_name'],profile_url=source['url']),state['research_revision'])
    assert same['person_id']==person
    other=research.retain(a,dict(results=[dict(url='https://example.com/other-maya',title='Maya Chen, Different Company',text='Maya Chen leads Different Company.',read=True,status='success')]),state['research_revision'])['sources'][0]
    distinct=research.register(a,dict(source_id=other['source_id'],display_name='Maya Chen',company_name='Different Company',profile_url=other['url']),state['research_revision'])
    assert distinct['person_id']!=person and len(s.snapshot(a)['people'])==2
