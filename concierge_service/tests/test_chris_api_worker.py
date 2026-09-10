import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from concierge_service.api import create_app
from concierge_service.engine import Engine
from concierge_service.store import Store
from concierge_service.chris.contracts import ChrisError
from concierge_service.chris.scheduler import Scheduler
from concierge_service.chris.service import Service

TOKEN='synthetic-private-bridge-token-for-offline-tests'


def test_private_api_auth_idor_commands_and_lost_post(tmp_path):
    app=create_app(Engine(Store(tmp_path/'api.sqlite')),TOKEN)
    client=TestClient(app);a,b=str(uuid4()),str(uuid4())
    path=f'/workspace/{a}/chris';headers={'Authorization':'Bearer '+TOKEN}
    assert client.get(path).status_code==401
    assert client.get(path,headers=headers).json()['counts']['introduced']==0
    actor=dict(user_id=str(uuid4()),request_id=str(uuid4()),role='owner')
    envelope=dict(schema_version=1,command_id=str(uuid4()),expected_revision=0,command='brief.propose',payload={'text':'Find specialist expertise.'})
    first=client.post(path+'/commands',headers=headers,json=dict(actor=actor,envelope=envelope))
    assert first.status_code==202 and first.headers['cache-control']=='private, no-store'
    replay=client.post(path+'/commands',headers=headers,json=dict(actor=actor,envelope=envelope))
    assert replay.json()==first.json()
    assert client.get(path+'/commands/'+envelope['command_id'],headers=headers).json()['item']['result']==first.json()
    assert client.get(f'/workspace/{b}/chris/commands/'+envelope['command_id'],headers=headers).status_code==404
    envelope['payload']['text']='Different intent'
    assert client.post(path+'/commands',headers=headers,json=dict(actor=actor,envelope=envelope)).status_code==409
    assert client.post(path+'/commands',headers=headers,content=b'x'*32769).status_code==413
    app.state.chris.scheduler.close()


@pytest.mark.parametrize('role',['viewer','agent','admin'])
def test_nonowner_cannot_expand_private_authority(tmp_path,role):
    app=create_app(Engine(Store(tmp_path/'api.sqlite')),TOKEN);a=str(uuid4())
    result=TestClient(app).post(f'/workspace/{a}/chris/commands',headers={'Authorization':'Bearer '+TOKEN},json=dict(
        actor=dict(user_id=str(uuid4()),request_id=str(uuid4()),role=role),envelope=dict(schema_version=1,command_id=str(uuid4()),expected_revision=0,command='autonomy.set',payload=dict(enabled=True,scope_kinds=['invite'],displayed_authority_revision=0))))
    assert result.status_code==403
    app.state.chris.scheduler.close()


def test_stale_worker_generation_cannot_commit_after_new_claim(tmp_path):
    s=Service(Store(tmp_path/'jobs.sqlite'));a=str(uuid4())
    with s.transaction(a) as (db,state): s.enqueue(db,a,state,'research')
    def delayed(account,payload):
        with s.store.transaction() as db: db.execute('UPDATE jobs SET attempts=attempts+1 WHERE id=?',(payload['_job_id'],))
        with s.transaction(account) as (_,state): state['health']['invalid_late_result']=True
    worker=Scheduler(s,{'research':delayed});worker.process_one(a);worker.close()
    assert 'invalid_late_result' not in s.snapshot(a)['health']


def test_two_account_hang_does_not_starve_other_tenant(tmp_path):
    s=Service(Store(tmp_path/'jobs.sqlite'));a,b=str(uuid4()),str(uuid4())
    for account in [a,b]:
        with s.transaction(account) as (db,state): s.enqueue(db,account,state,'sync')
    entered=threading.Event();release=threading.Event();finished=threading.Event()
    def handler(account,payload):
        if account==a: entered.set();assert release.wait(5)
        else: finished.set()
    worker=Scheduler(s,{'sync':handler})
    with ThreadPoolExecutor(2) as pool:
        first=pool.submit(worker.process_one,a);assert entered.wait(2)
        second=pool.submit(worker.process_one,b);assert finished.wait(2)
        release.set();assert first.result() and second.result()
    worker.close()


def test_pause_does_not_starve_reconciliation_behind_queued_research(tmp_path):
    s=Service(Store(tmp_path/'jobs.sqlite'));a=str(uuid4());calls=[]
    with s.transaction(a) as (db,state):
        s.enqueue(db,a,state,'research');s.enqueue(db,a,state,'projection');state['authority']['paused']=True
    worker=Scheduler(s,{'research':lambda *x:calls.append('research'),'projection':lambda *x:calls.append('projection')})
    assert worker.process_one(a);worker.close();assert calls==['projection']
