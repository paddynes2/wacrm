import pytest
from concierge_service.chris.dispatch import Dispatcher,product_authorizer
from concierge_service.chris.service import Service
from concierge_service.store import Store
from concierge_service.tests.test_chris_e2e import workspace,invitation
from concierge_service.tests.test_chris_recovery_matrix import receive
from concierge_service.tests.chris_support import Wire


@pytest.mark.parametrize('boundary',['started','provider_accepted'],ids=['D08','D10'])
def test_restart_at_external_boundary_reconciles_without_new_mutation(tmp_path,boundary):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);action=invitation(s,a,pursuit);wire=Wire(s.clock)
    with s.transaction(a) as (_,state): state['actions'][action].update(status=boundary,started_at=now[0])
    restored=Service(Store(s.store.path),settings=settings,clock=lambda:now[0])
    Dispatcher(restored,{a:wire},product_authorizer).execute(a,{'action_id':action})
    assert not wire.calls and restored.snapshot(a)['actions'][action]['status']=='unknown'


@pytest.mark.parametrize('fault',['missing_ids','http429','http500','receipt_blob','accepted_write'],ids=['D13','D12-429','D12-500','P11','D11'])
def test_failures_after_start_are_not_safe_retries(tmp_path,fault,monkeypatch):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path);action=invitation(s,a,pursuit)
    class Broken(Wire):
        def mutate(self,frozen):
            response=super().mutate(frozen)
            if fault=='missing_ids': return {'chat_id':response['chat_id']}
            if fault.startswith('http'): raise OSError(fault)
            return response
    wire=Broken(s.clock)
    if fault=='receipt_blob':
        original=s.blobs.put;failed=[False]
        def put(value):
            if value.get('object')=='ChatStarted' and not failed[0]: failed[0]=True;raise OSError('synthetic disk full')
            return original(value)
        monkeypatch.setattr(s.blobs,'put',put)
    if fault=='accepted_write':
        original=s.store.save;failed=[False]
        def save(db,doc):
            if doc.get('chris_v1',{}).get('actions',{}).get(action,{}).get('status')=='provider_accepted' and not failed[0]:
                failed[0]=True;raise OSError('synthetic SQLite write failure')
            return original(db,doc)
        monkeypatch.setattr(s.store,'save',save)
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':action})
    state=s.snapshot(a);assert state['actions'][action]['status']=='unknown' and len(wire.calls)==1
    restored=Service(Store(s.store.path),settings=settings,clock=lambda:now[0])
    Dispatcher(restored,{a:wire},product_authorizer).execute(a,{'action_id':action})
    assert restored.snapshot(a)['actions'][action]['status']=='verified' and len(wire.calls)==1


def test_stop_after_remote_mutation_preserves_truthful_receipt_and_stops_future_actions(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    class LateStop(Wire):
        def mutate(self,frozen):
            response=super().mutate(frozen)
            now[0]+=1;receive(s,a,person,now,'STOP')
            return response
    wire=LateStop(s.clock);action=invitation(s,a,pursuit)
    Dispatcher(s,{a:wire},product_authorizer).execute(a,{'action_id':action})
    state=Service(Store(s.store.path)).snapshot(a)
    assert len(wire.calls)==1 and state['actions'][action]['status']=='verified'
    assert state['pursuits'][pursuit]['state']=='suppressed' and s.overview(a)['counts']['approached']==1
