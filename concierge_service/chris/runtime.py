"""Host composition and durable wakeups; no browser-dependent execution."""
from .service import Service
from .scheduler import Scheduler
from .research import Research
from .agent import Model
from .search_provider import Exa
from .provider import Provider
from .dispatch import Dispatcher
from .ingestion import Ingestion
from .introductions import Introductions
from .projection import Projection
from .conversation import Conversation
from .interpreter import Interpreter
from .briefing import Briefing


class Runtime:
    def __init__(self, engine, settings=None, authorizer=None, projection_base=None, token=None):
        self.service = Service(engine.store, engine.mode, settings)
        providers = {a: Provider(client) for a, client in engine.unipile.items()} if engine.mode == 'live' else {}
        provider_accounts = [client.account_id for client in engine.unipile.values()]
        self.binding_conflicts = {a for a, client in engine.unipile.items() if provider_accounts.count(client.account_id) > 1}
        providers = {a: p for a, p in providers.items() if a not in self.binding_conflicts}
        priced = lambda cfg: type(cfg.get('max_operation_micro_usd')) is int and cfg['max_operation_micro_usd']>0
        models = {a: Model(cfg) for a, cfg in engine.models.items() if cfg.get('provider') in {'openai', 'anthropic'} and cfg.get('model') and cfg.get('api_key') and priced(cfg)}
        searches = {a: Exa(cfg) for a, cfg in engine.discovery.items() if cfg.get('provider') == 'exa' and cfg.get('api_key') and priced(cfg)}
        self.pricing_unverified = {a for a,cfg in list(engine.models.items())+list(engine.discovery.items()) if not priced(cfg)}
        self.research = Research(self.service, models, searches)
        self.dispatcher = Dispatcher(self.service, providers, authorizer)
        self.ingestion = Ingestion(self.service, providers)
        self.introductions = Introductions(self.service, self.dispatcher)
        self.conversation = Conversation(self.service, models, self.introductions)
        self.interpreter = Interpreter(self.service, models)
        self.briefing = Briefing(self.service,models)
        self.projection = Projection(self.service, projection_base, token)
        from .relationships import Relationships
        relationships = Relationships(self.projection)
        self.research.relationships = {a: (lambda person, account=a: relationships.lookup(account, person)) for a in models}
        self.scheduler = Scheduler(self.service, dict(research=self.research.run, sync=self.ingestion.sync,
            dispatch=self.dispatcher.execute, reconcile=self.dispatcher.reconcile,
            introduction=self.introductions.advance, projection=self.projection.run, conversation=self.conversation.run,
            interpret=self.interpreter.run, briefing=self.briefing.run))

    def tick(self):
        for account in self.service.store.accounts():
            try:
                self.schedule_account(account)
            except Exception:
                # A damaged tenant document must not starve healthy tenants.
                # Its own reads expose the concrete storage/schema failure.
                continue
        self.scheduler.tick()

    def schedule_account(self, account):
        with self.service.transaction(account) as (db, state):
            now = self.service.clock()
            state['health']['research_configured'] = account in self.research.models and account in self.research.searches
            if account in self.pricing_unverified: state['health']['research_error']='provider_price_ceiling_unverified'
            state['health']['projection_configured'] = bool(self.projection.base)
            if account in self.binding_conflicts:
                state['health']['connection_error'] = 'provider_account_shared'
                state['authority']['external_enabled'] = False
            from .permissions import eligibility
            if (state['active_brief_revision'] and state['settings']['research_enabled']
                and not state['authority']['paused'] and not state['storage'].get('discovery_paused')
                and state['health']['research_configured'] and now >= state['health'].get('next_research', 0)):
                pending = db.execute("SELECT 1 FROM jobs WHERE account=? AND kind='chris.research' AND state IN ('queued','running')", (account,)).fetchone()
                if not pending:
                    self.service.enqueue(db, account, state, 'research')
                state['health']['next_research'] = now + 3600
            for pursuit in state['pursuits'].values():
                if pursuit['state']=='awaiting_reply' and not pursuit.get('reply_required') and pursuit.get('no_response_after') and now>=pursuit['no_response_after']:
                    from .state import transition
                    transition(pursuit,'closed_no_response',now)
                if pursuit.get('reply_required') and pursuit.get('attention') and account in self.interpreter.models:
                    thread = state['threads'].get(pursuit.get('direct_thread_key'), {})
                    self.service.enqueue(db, account, state, 'interpret', {'pursuit_id': pursuit['pursuit_id']},
                        key='interpret:'+pursuit['pursuit_id']+':'+str(thread.get('last_observed_seq',0)))
                purpose = ('group_introduction' if pursuit['state'] == 'ready_to_introduce' else
                           'permission_clarification' if pursuit['state'] == 'awaiting_group_permission' else
                           'reply' if pursuit.get('reply_required') else
                           'invite' if pursuit['state'] in {'qualified', 'contact_unresolved', 'ready_to_invite'} else
                           'followup' if pursuit['state'] == 'awaiting_reply' else None)
                if purpose:
                    reasons = eligibility(state, pursuit, now, 'group_create' if purpose == 'group_introduction' else purpose)
                    pursuit['reason_codes'] = reasons
                    if not reasons and account in self.conversation.models:
                        thread = state['threads'].get(pursuit.get('group_reply_thread_key') or pursuit.get('direct_thread_key'), {})
                        key = ':'.join(['conversation', pursuit['pursuit_id'], purpose, str(pursuit['state_revision']), str(thread.get('last_observed_seq', 0)), str(state['authority']['revision'])])
                        self.service.enqueue(db, account, state, 'conversation', {'pursuit_id': pursuit['pursuit_id'], 'purpose': purpose, 'intro_id': pursuit.get('group_reply_intro_id')}, key=key)
            if account in self.ingestion.providers and now >= state['health'].get('next_sync', 0):
                self.service.enqueue(db, account, state, 'sync')
                state['health']['next_sync'] = now + 60
            for action in state['actions'].values():
                if action['status'] in {'unknown', 'provider_accepted', 'started','needs_attention'} and now >= action.get('next_reconcile_at', 0):
                    self.service.enqueue(db, account, state, 'reconcile', {'action_id': action['action_id']}, key='reconcile:' + action['action_id'] + ':' + str(action.get('reconcile_attempts', 0)))
            for intro in state['introductions'].values():
                if intro['state'] not in {'introduced', 'membership_failed', 'cancelled_after_create'} and now >= intro.get('next_membership_at',0):
                    self.service.enqueue(db, account, state, 'introduction', {'intro_id': intro['intro_id']}, key='intro:' + intro['intro_id'] + ':' + str(int(now // 30)))
            if self.projection.base and now >= state['health'].get('next_projection', 0):
                self.service.enqueue(db, account, state, 'projection')
                state['health']['next_projection'] = now + 30
