import datetime as dt
import json
from pathlib import Path
from uuid import uuid4
import pytest
from concierge_service.store import Store
from concierge_service.chris.service import Service
from concierge_service.chris.preflight import backup, restore, inspect
from concierge_service.chris.contracts import ChrisError
from concierge_service.chris.settings import DISCOVERY_STOP, OUTBOUND_STOP, HARD_STOP
from concierge_service.chris.timing import next_followup
from concierge_service.tests.test_chris_e2e import workspace, invitation


def test_backup_restore_preserves_claims_and_disables_authority(tmp_path):
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    action=invitation(s,a,pursuit)
    with s.transaction(a) as (_,state): state['actions'][action].update(status='unknown',started_at=now[0])
    backup(s.store.path,tmp_path/'backup')
    restored=restore(tmp_path/'backup',tmp_path/'restored')
    state=Service(Store(restored),settings=settings,clock=lambda:now[0]).snapshot(a)
    assert state['authority']['external_enabled'] is False and state['authority']['paused'] is True
    assert state['actions'][action]['status']=='unknown'
    assert not inspect(restored)['reason_codes']
    with pytest.raises(ChrisError): restore(tmp_path/'backup',tmp_path/'restored')

@pytest.mark.parametrize('size,research,outbound',[(DISCOVERY_STOP,False,False),(OUTBOUND_STOP,True,True)])
def test_capacity_thresholds_are_durable(tmp_path,size,research,outbound):
    s=Service(Store(tmp_path/'execution.sqlite'));a=str(uuid4())
    with s.transaction(a) as (_,state): state['capacity_test']='x'*size
    storage=Service(Store(s.store.path)).snapshot(a)['storage']
    assert storage['research_paused'] is research and storage['outbound_paused'] is outbound
    assert storage['discovery_paused'] is True
    with pytest.raises(ChrisError,match='storage_capacity_exceeded'):
        with s.transaction(a) as (_,state): state['capacity_test']='x'*HARD_STOP
    assert len(s.snapshot(a)['capacity_test'])==size

def test_business_day_followup_has_no_unknown_timezone_fallback():
    friday=dt.datetime(2026,9,11,10,tzinfo=dt.timezone.utc).timestamp()
    assert next_followup(friday,None,0) is None
    assert next_followup(friday,'Europe/London',2) is None
    due=dt.datetime.fromtimestamp(next_followup(friday,'Europe/London',0),dt.timezone.utc)
    assert due.day==16 and due.hour==10

def test_unknown_provider_charge_cannot_be_replayed(tmp_path):
    from concierge_service.chris.scheduler import reserve
    s,a,actor,person,pursuit,now,settings=workspace(tmp_path)
    run,fresh=reserve(s,a,'search_web',{'query':'unanswered lookup'},100000)
    assert fresh and run['reported_cost_micro_usd'] is None
    reopened=Service(Store(s.store.path),settings=settings,clock=lambda:now[0])
    again,fresh=reserve(reopened,a,'search_web',{'query':'unanswered lookup'},100000)
    assert not fresh and again['run_id']==run['run_id'] and again['cost_reservation_micro_usd']==100000
