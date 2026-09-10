import pytest
from concierge_service.chris.research import Research
from concierge_service.chris.contracts import ChrisError
from concierge_service.tests.test_chris_continuations import blank
from concierge_service.tests.chris_support import Search,ReplayModel


@pytest.mark.parametrize('fault',['contradiction','old_announcement','truncated'],ids=['R14','R15','R19'])
def test_critic_sees_retained_conflicts_dates_and_truncation_before_qualification(tmp_path,fault):
    s,a=blank(tmp_path)
    class Sources(Search):
        def read(self,url):
            result=super().read(url)
            if fault=='old_announcement': result['results'][0]['published_at']='2012-01-01T00:00:00Z'
            elif fault=='truncated': result['results'][0]['truncated']=True
            else: result['results'].append(dict(url=url,title='Maya Chen, Cedar Distribution',text='Correction: Maya Chen left Cedar Distribution. Current role is unresolved.',read=True,status='success'))
            return result
    class Critic(ReplayModel):
        def turn(self,context):
            if context.get('task')=='research_critic':
                evidence=context['evidence']
                if fault=='contradiction': assert any('Correction:' in x['text'] for x in evidence)
                elif fault=='old_announcement': assert any(x.get('published_at','').startswith('2012') for x in evidence)
                else: assert any(x.get('truncated') for x in evidence)
                return dict(schema_version=1,step='qualify',arguments=dict(verdict='revise',reasons=['Current role is not established by this evidence.'],required_fixes=['Read a current authoritative role source.']),evidence_ids=[],decision_summary='Preserve the source gap')
            return super().turn(context)
    with pytest.raises(ChrisError,match='critic_revision_needed'):
        Research(s,{a:Critic()},{a:Sources()},{a:lambda p:dict(known=False,fresh=True,coverage='Synthetic roster')}).run(a,{})
    state=s.snapshot(a)
    assert not state['actions'] and all(p['qualification']!='qualified' for p in state['pursuits'].values())
    assert any(r['tool_name']=='research_critic' and r['status']=='completed' for r in state['tool_runs'].values())
