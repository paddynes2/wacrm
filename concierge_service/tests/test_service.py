"""Service boundary tests use only temporary execution stores and local fixtures."""
from concurrent.futures import ThreadPoolExecutor
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from concierge_service.api import create_app
from concierge_service.engine import Engine
from concierge_service.store import Store

ACCOUNT = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'
TOKEN = 'isolated-test-token-never-a-real-credential'
BRIEF = {'principal_name':'Test operator','offer':'Workflow analysis for independent firms.',
         'audience':'Operations directors','geography':'South Africa','exclusions':'Existing clients',
         'claims':'We provide workflow analysis.','timezone':'Africa/Johannesburg','booking_link':'','budget_usd':0}


@pytest.fixture
def setup(tmp_path):
    engine = Engine(Store(tmp_path/'execution.sqlite3'))
    client = TestClient(create_app(engine, TOKEN))
    client.headers['Authorization'] = 'Bearer ' + TOKEN
    return engine, client


def command(client, name, **kwargs):
    response = client.post(f'/workspace/{ACCOUNT}/dogfood', json={'command':name,**kwargs})
    assert response.status_code == 200, response.text
    return response.json()


def seeded(client):
    command(client,'save_brief',brief=BRIEF)
    command(client,'discover',source='fixture',limit=2)
    report = command(client,'process')
    assert len(report['prospects']) == 2, report
    pid = report['prospects'][0]['id']
    command(client,'qualify',prospect_id=pid,verdict='qualified',reason='Synthetic evaluation only')
    return pid


def test_auth_modes_and_input_limits(setup):
    engine, client = setup
    url = f'/workspace/{ACCOUNT}/dogfood'
    assert client.get(url,headers={'Authorization':'Bearer wrong'}).status_code == 401
    assert client.post(url,json={'command':'unknown'}).status_code == 409
    assert client.post(url,content='bad').status_code == 400
    assert client.post(url,content='x'*65000).status_code == 413
    assert client.get('/workspace/not-a-uuid/dogfood').status_code == 409
    assert client.get('/health').json()['service'] == 'standalone-concierge'
    with pytest.raises(RuntimeError):
        create_app(engine,'short')


def test_standalone_sandbox_uses_durable_worker(setup):
    engine,client = setup
    pid = seeded(client)
    report = command(client,'start',prospect_id=pid)
    assert not report['messages']
    report = command(client,'process')
    assert len(report['messages']) == 1
    assert report['messages'][0]['direction'] == 'outbound'
    command(client,'reply',prospect_id=pid,text='What is the next step?')
    report = command(client,'process')
    assert len(report['messages']) == 3
    assert all(m['simulated'] for m in report['messages'])
    restarted = Engine(Store(engine.store.path))
    assert restarted.report(ACCOUNT)['messages'] == report['messages']
    assert restarted.report(OTHER)['messages'] == []


def test_stop_and_duplicate_replay(setup):
    engine,client = setup
    pid = seeded(client)
    command(client,'start',prospect_id=pid)
    command(client,'process')
    command(client,'reply',prospect_id=pid,text='STOP',message_id='provider-one')
    report = command(client,'reply',prospect_id=pid,text='STOP',message_id='provider-one')
    assert report['prospects'][0]['conversation']['status'] == 'opted_out'
    assert len(report['messages']) == 2
    command(client,'resume',prospect_id=pid)
    assert client.post(f'/workspace/{ACCOUNT}/dogfood',json={'command':'start','prospect_id':pid}).status_code == 409
    assert len(command(client,'process')['messages']) == 2


def test_lease_serializes_concurrent_workers(setup):
    engine,client = setup
    pid = seeded(client)
    command(client,'start',prospect_id=pid)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: engine.process_one(ACCOUNT), range(4)))
    assert len(engine.report(ACCOUNT)['messages']) == 1


def test_brief_edit_cancels_pending_generation(setup):
    _,client = setup
    pid = seeded(client)
    command(client,'start',prospect_id=pid)
    command(client,'save_brief',brief={**BRIEF,'offer':'A newly revised offer.'})
    report = command(client,'process')
    assert report['messages'] == []
    assert report['prospects'][0]['brief_stale'] is True


def test_live_workspace_never_uses_simulation_approval(tmp_path):
    engine = Engine(Store(tmp_path/'live.sqlite3'),mode='live')
    client = TestClient(create_app(engine,TOKEN),headers={'Authorization':'Bearer '+TOKEN})
    command(client,'save_brief',brief=BRIEF)
    assert client.post(f'/workspace/{ACCOUNT}/dogfood',json={'command':'discover','source':'fixture','limit':2}).status_code == 409
    report = client.get(f'/workspace/{ACCOUNT}/dogfood').json()
    assert report['readiness']['live_execution_enabled'] is False
    assert report['readiness']['fixture_model'] is False


def test_runtime_has_no_fleet_imports():
    import ast
    root = Path(__file__).resolve().parents[1]
    for path in root.rglob('*.py'):
        if 'tests' in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                assert all(not n.name.startswith('fleet') for n in node.names),path
            if isinstance(node,ast.ImportFrom):
                assert not (node.module or '').startswith('fleet'),path


def test_worker_keeps_serving_other_accounts_after_one_provider_fails(setup):
    import threading
    engine, _ = setup
    engine.command(ACCOUNT, {'command':'save_brief','brief':BRIEF})
    engine.command(OTHER, {'command':'save_brief','brief':BRIEF})
    processed = threading.Event()
    def process(account):
        if account == ACCOUNT:
            raise RuntimeError('private-provider-error-must-not-be-logged')
        processed.set()
    engine.process_one = process
    with TestClient(create_app(engine,TOKEN,worker=True)) as client:
        assert processed.wait(3), 'First account failure starved a different tenant'
        assert client.get('/health').json()['worker'] is True


def test_polling_requires_explicit_bounded_interval(setup):
    engine, _ = setup
    for invalid in (-1,1,59,3601,True,60.0):
        with pytest.raises(RuntimeError,match='polling interval'):
            create_app(engine,TOKEN,sync_interval=invalid)


def test_live_api_requires_installed_authorizer_and_exact_ledger_decision():
    from concierge_service.tests.test_live_execution import LiveExecutionTest
    from concierge_service.live_execution import execute_decision
    case = LiveExecutionTest('test_verified_dispatch_persists_provider_receipt_and_cannot_repeat')
    case.setUp()
    try:
        from concierge_service.tests.test_engine_safety import A
        url = f'/workspace/{A}/dogfood'
        headers = {'Authorization':'Bearer '+TOKEN}
        disabled = TestClient(create_app(case.engine,TOKEN),headers=headers)
        assert disabled.post(url,json={'command':'approve','decision_id':case.decision}).status_code == 409
        assert not case.client.writes
        waiting = lambda runtime, account, did: execute_decision(runtime,account,did,lambda action,invoke: False)
        configured = TestClient(create_app(case.engine,TOKEN,live_executor=waiting),headers=headers)
        assert configured.get(url).json()['readiness']['live_execution_enabled'] is True
        assert configured.post(url,json={'command':'approve','decision_id':case.decision}).status_code == 200
        assert not case.client.writes, 'Installing authorization must not grant an action'
        approved = lambda runtime, account, did: execute_decision(runtime,account,did,case.gate)
        client = TestClient(create_app(case.engine,TOKEN,live_executor=approved),headers=headers)
        assert client.post(url,json={'command':'approve','decision_id':case.decision,'text':'tamper'}).status_code == 409
        assert not case.client.writes
        report = client.post(url,json={'command':'approve','decision_id':case.decision}).json()
        assert report['decisions'][-1]['status'] == 'executed'
        assert report['readiness']['live_delivery_verified'] is False
        assert len(case.client.writes) == 1  # Fake HTTP only; never a real provider call.
        assert client.post(url,json={'command':'approve','decision_id':case.decision}).status_code == 409
        assert len(case.client.writes) == 1
    finally:
        case.doCleanups()
