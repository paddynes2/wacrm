import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from concierge_service.legacy_import import inspect, import_workspace
from concierge_service.engine import Engine
from concierge_service.store import Store

A = '11111111-1111-4111-8111-111111111111'
C = '22222222-2222-4222-8222-222222222222'


def fixture(tmp_path):
    source = tmp_path/'old'
    (source/'wacrm-bridge').mkdir(parents=True)
    (source/'bots/b123456').mkdir(parents=True)
    index = {A:{'mode':'simulation','bot_id':'b123456','brief':{'principal_name':'Test','offer':'An offer'}}}
    (source/'wacrm-bridge/workspaces.json').write_text(json.dumps(index))
    e = {'event_id':'one','pursuit_id':'wacrm:'+C,'account_id':'legacy-account','kind':'identified',
         'source_ref':'legacy:test','occurred_at':'2026-09-01T10:00:00+00:00','data':{
             'crm_ref':'wacrm:'+C,'principal_id':'27820000001@s.whatsapp.net','recipient_id':'27820000002@s.whatsapp.net',
             'principal_name':'Test','name':'Person','offer':'An offer','fit':'A fit','profile_url':'https://example.invalid'}}
    (source/'bots/b123456/runs.jsonl').write_text(json.dumps({'kind':'concierge_event','observation':e})+'\n')
    return source


def test_import_preserves_evidence_no_source_writes_and_no_pending_actions(tmp_path):
    source = fixture(tmp_path)
    before = (source/'bots/b123456/runs.jsonl').read_bytes()
    assert len(inspect(source,A)['states']) == 1
    target = tmp_path/'new.sqlite3'
    result = import_workspace(source,target,A)
    assert result['observations'] == 1 and result['paused']
    report = Engine(Store(target)).report(A)
    assert report['prospects'][0]['contact_id'] == C
    assert report['decisions'] == [] and report['jobs'] == []
    store = Store(target)
    with store.transaction() as db:
        document = store.load(db,A,'simulation')
        assert document['observations'][0]['account_id'] == A
        assert document['legacy_imports'][0]['original_observations'][0]['account_id'] == 'legacy-account'
    assert (source/'bots/b123456/runs.jsonl').read_bytes() == before
    with pytest.raises(ValueError,match='overwrite'):
        import_workspace(source,target,A)


def test_invalid_bot_path_and_live_mode_refused(tmp_path):
    source = fixture(tmp_path)
    file = source/'wacrm-bridge/workspaces.json'
    row = json.loads(file.read_text())
    row[A]['bot_id']='../outside'
    file.write_text(json.dumps(row))
    with pytest.raises(ValueError): inspect(source,A)
    row[A]['mode']='live'
    file.write_text(json.dumps(row))
    with pytest.raises(ValueError): inspect(source,A)
