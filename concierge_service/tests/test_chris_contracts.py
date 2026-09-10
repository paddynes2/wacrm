import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from concierge_service.store import Store
from concierge_service.chris.service import Service
from concierge_service.chris.contracts import ChrisError, parse, command

def setup(tmp_path):
    s = Service(Store(tmp_path / 'execution.sqlite'))
    return s, str(uuid4()), dict(user_id=str(uuid4()), request_id=str(uuid4()), role='owner')

def cmd(s, a, actor, name, payload):
    body = dict(schema_version=1, command_id=str(uuid4()), expected_revision=s.snapshot(a)['revision'], command=name, payload=payload)
    return body, s.command(a, body, actor)

def test_blank_restart_idempotency_revision_tenants(tmp_path):
    s, a, actor = setup(tmp_path)
    assert s.overview(a)['counts']['introduced'] == 0
    body, result = cmd(s, a, actor, 'brief.propose', {'text':'Find distribution partners'})
    restarted = Service(Store(s.store.path))
    assert restarted.command(a, body, actor) == result
    changed = {**body, 'payload': {'text':'Something else'}}
    with pytest.raises(ChrisError, match='idempotency_conflict'): restarted.command(a, changed, actor)
    with pytest.raises(ChrisError, match='revision_conflict'): restarted.command(a, {**body, 'command_id':str(uuid4())}, actor)
    assert restarted.snapshot(str(uuid4()))['proposals'] == {}

def test_unknown_schema_and_blob_corruption(tmp_path):
    s, a, actor = setup(tmp_path)
    key = s.blobs.put({'text':'Evidence'})
    assert s.blobs.get(key)['text'] == 'Evidence'
    (s.blobs.root/key).write_text('corrupt')
    with pytest.raises(ChrisError, match='blob_corrupt'): s.blobs.get(key)
    with s.store.transaction() as db:
        d = s.store.load(db,a,s.mode); d['chris_v1']={'schema_version':2}; s.store.save(db,d)
    with pytest.raises(ChrisError, match='upgrade_required'): s.snapshot(a)

def test_rollback_and_roles(tmp_path):
    s,a,actor=setup(tmp_path)
    with pytest.raises(RuntimeError):
        with s.transaction(a) as (_,state):
            state['revision']=999
            raise RuntimeError('disk failure')
    assert s.snapshot(a)['revision']==0
    for role in ['viewer','admin','agent']:
        with pytest.raises(ChrisError, match='owner_required'):
            cmd(s,a,{**actor,'role':role},'autonomy.set',dict(enabled=True,scope_kinds=[],displayed_authority_revision=0))

@pytest.mark.parametrize('raw', ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '[] trailing'])
def test_strict_json(raw):
    with pytest.raises(ChrisError): parse(raw)

def test_unicode_byte_bound():
    with pytest.raises(ChrisError, match='body_too_large'): parse(json.dumps({'a':'😀'*9000}, ensure_ascii=False))
