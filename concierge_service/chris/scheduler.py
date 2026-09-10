"""Leased Chris jobs share SQLite, never legacy job handlers."""
import json
import time
import threading
from contextvars import ContextVar
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from .contracts import require

LEASE_SECONDS = 120
CURRENT_JOB = ContextVar('chris_job', default=None)
BUDGET_JOB = ContextVar('chris_budget_job', default=None)


def bounded_job(method):
    @wraps(method)
    def run(self, account, payload):
        job = CURRENT_JOB.get()
        token = BUDGET_JOB.set(job[0] if job else payload.get('pass_id') or payload.get('_job_id') or str(uuid4()))
        try: return method(self,account,payload)
        finally: BUDGET_JOB.reset(token)
    return run
class Scheduler:
    def __init__(self, service, handlers):
        self.service, self.handlers = service, handlers
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix='chris')
        self.futures = {}
        self.rotation = 0

    def process_one(self, account):
        service = self.service
        now = service.clock()
        with service.transaction(account) as (db, state):
            state['health']['heartbeat'] = now
            allowed = set(self.handlers)
            running = db.execute("SELECT kind FROM jobs WHERE account=? AND kind LIKE 'chris.%' AND state='running' AND lease_until>?", (account,now)).fetchall()
            writes = {'dispatch','introduction'}
            if sum(r['kind'].removeprefix('chris.') in writes for r in running) >= 1: allowed -= writes
            if sum(r['kind'].removeprefix('chris.') not in writes for r in running) >= 2: allowed &= writes
            if state['authority']['paused']: allowed &= {'sync','reconcile','projection'}
            if state['storage'].get('discovery_paused') or state['storage'].get('research_paused'): allowed.discard('research')
            candidates = db.execute("SELECT * FROM jobs WHERE account=? AND kind LIKE 'chris.%' AND ((state='queued' AND due<=?) OR (state='running' AND lease_until<=?)) ORDER BY CASE WHEN kind IN ('chris.sync','chris.reconcile','chris.interpret') THEN 0 WHEN kind='chris.research' THEN 2 ELSE 1 END,due", (account,now,now)).fetchall()
            priority = {'sync':0,'reconcile':1,'interpret':2,'conversation':3,'introduction':4,'dispatch':4,'research':6,'projection':7}
            ready = sorted((r for r in candidates if r['kind'].removeprefix('chris.') in allowed),
                key=lambda r:(priority.get(r['kind'].removeprefix('chris.'),5),r['due']))
            row = ready[0] if ready else None
            if state['health'].get('nonresearch_jobs',0) >= 10:
                row = next((r for r in ready if r['kind']=='chris.research'),row)
            if row is None: return False
            job = dict(row); kind = job['kind'].removeprefix('chris.')
            state['health']['nonresearch_jobs'] = 0 if kind=='research' else state['health'].get('nonresearch_jobs',0)+1
            payload = json.loads(job['payload'])
            if kind == 'research' and payload['research_revision'] != state['research_revision']:
                db.execute("UPDATE jobs SET state='cancelled' WHERE id=?", (job['id'],)); return True
            if job['state'] == 'running' and kind == 'dispatch': kind = 'reconcile'
            generation = job['attempts'] + 1
            payload['_job_id'], payload['_generation'] = job['id'], generation
            db.execute("UPDATE jobs SET state='running',attempts=?,lease_until=? WHERE id=?", (generation,now+LEASE_SECONDS,job['id']))
        # Every handler performs its own state fence before a material commit.
        stopped = threading.Event()
        def heartbeat():
            while not stopped.wait(20):
                with service.store.transaction() as db:
                    db.execute("UPDATE jobs SET lease_until=? WHERE id=? AND attempts=? AND state='running'", (service.clock()+LEASE_SECONDS,job['id'],generation))
        keeper = threading.Thread(target=heartbeat, daemon=True, name='chris-lease')
        keeper.start()
        context = CURRENT_JOB.set((job['id'], generation))
        try:
            handler = self.handlers.get(kind)
            require(handler is not None, kind + '_not_configured', 503)
            handler(account, payload)
            status, error = 'completed', None
        except Exception as exc:
            status, error = 'failed', getattr(exc, 'code', 'provider_unavailable')
        finally:
            CURRENT_JOB.reset(context)
            stopped.set()
        with service.transaction(account) as (db,state):
            db.execute("UPDATE jobs SET state=?,error=?,lease_until=NULL WHERE id=? AND attempts=? AND state='running'", (status,error,job['id'],generation))
            if error:
                state['health'][kind + '_error'] = error
                if kind == 'sync' and state.get('connection'):
                    state['connection']['connected'] = False
        return True

    def tick(self):
        accounts = self.service.store.accounts()
        if not accounts: return
        start = self.rotation % len(accounts)
        self.rotation += 1
        for slot in range(3):
            for account in accounts[start:] + accounts[:start]:
                key = (account,slot)
                pending = self.futures.get(key)
                if pending and not pending.done(): continue
                if sum(not f.done() for f in self.futures.values()) >= 4: return
                self.futures[key] = self.pool.submit(self.process_one, account)

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)


def reserve(service, account, tool, arguments, maximum):
    from .contracts import digest, integer
    integer(maximum)
    key = digest({'tool':tool, 'arguments':arguments})
    with service.transaction(account) as (_,state):
        old = next((r for r in state['tool_runs'].values() if r['input_digest']==key and r['research_revision']==state['research_revision']),None)
        if old: return old, False
        settings = state['settings']
        require(maximum > 0 and maximum <= settings['job_micro_usd'], 'budget_exhausted', 409)
        job_id = BUDGET_JOB.get() or (CURRENT_JOB.get() or (None,))[0]
        if job_id:
            committed = sum(r['cost_reservation_micro_usd'] for r in state['tool_runs'].values() if r.get('job_id')==job_id)
            require(committed+maximum <= settings['job_micro_usd'],'job_budget_exhausted',409)
            model_tools = {'model','model_repair','research_critic'}
            if tool in model_tools:
                require(sum(r.get('job_id')==job_id and r['tool_name'] in model_tools for r in state['tool_runs'].values())<20,'model_turn_limit',409)
        import datetime as dt
        from zoneinfo import ZoneInfo
        day = dt.datetime.fromtimestamp(service.clock(), ZoneInfo(settings['timezone'])).date().isoformat()
        day = max(day, state['budgets'].get('latest_day', day))
        budget = state['budgets'].setdefault(str(day),dict(reserved=0,operations=0))
        require(budget['reserved']+maximum <= settings['daily_micro_usd'] and budget['operations'] < settings['daily_operations'], 'budget_exhausted',409)
        budget['reserved'] += maximum; budget['operations'] += 1; state['budgets']['latest_day']=day
        run = dict(run_id=str(uuid4()), tool_name=tool, input_digest=key, normalized_input=arguments, status='started',
                   job_id=job_id,
                   research_revision=state['research_revision'], cost_reservation_micro_usd=maximum, reported_cost_micro_usd=None, estimated_cost_micro_usd=None, started_at=service.clock())
        state['tool_runs'][run['run_id']]=run
        return run, True
