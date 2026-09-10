from uuid import uuid4
from concierge_service.store import Store
from concierge_service.chris.service import Service
from concierge_service.chris.briefing import Briefing


def test_structured_brief_is_only_a_reviewable_proposal(tmp_path):
    a=str(uuid4());s=Service(Store(tmp_path/'brief.sqlite'),settings={a:dict(daily_micro_usd=1000000,job_micro_usd=100000,daily_operations=10)})
    actor=dict(user_id=str(uuid4()),request_id=str(uuid4()),role='owner')
    result=s.command(a,dict(schema_version=1,command_id=str(uuid4()),expected_revision=0,command='brief.propose',payload={'text':'I need distribution specialists.'}),actor)
    class Model:
        def turn(self,context):
            assert context['task']=='propose_structured_brief'
            return dict(schema_version=1,step='finish',arguments={'brief':dict(objective='Find distribution specialists.',principal_display_name='',principal_public_context='',timezone='',candidate_archetypes=['Distribution specialists'],geography_include=[])},evidence_ids=[],decision_summary='Name and timezone require review.')
    Briefing(s,{a:Model()}).run(a,{'proposal_id':result['proposal_id']})
    state=Service(Store(s.store.path)).snapshot(a)
    assert state['active_brief_revision'] is None and not state['authority']['external_enabled']
    proposal=state['proposals'][result['proposal_id']]['suggested_brief']
    assert proposal['principal_display_name']=='' and proposal['geography_include']==[] and not state['people']


def test_console_status_and_pause_do_not_replace_endeavour(tmp_path):
    a=str(uuid4());s=Service(Store(tmp_path/'brief.sqlite'));actor=dict(user_id=str(uuid4()),request_id=str(uuid4()),role='owner')
    for text in ['status','pause','turn all sending on']:
        result=s.command(a,dict(schema_version=1,command_id=str(uuid4()),expected_revision=s.snapshot(a)['revision'],command='brief.propose',payload={'text':text}),actor)
        assert 'proposal_id' not in result
    state=s.snapshot(a)
    assert state['authority']['paused'] and not state['authority']['external_enabled'] and not state['proposals']
