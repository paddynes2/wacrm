"""Transactional account commands and bounded versioned execution documents."""
from contextlib import contextmanager
from copy import deepcopy
import datetime as dt
import time
from uuid import uuid4
from . import contracts as c
from .blobs import Blobs
from .settings import effective, DISCOVERY_STOP, OUTBOUND_STOP, HARD_STOP
from .state import event, cancel_unstarted, pursuit_for, transition
from .identity import challenge, phone

class Service:
    def __init__(self, store, mode="simulation", settings=None, clock=time.time):
        c.require(mode in {"simulation", "live"})
        self.store, self.mode, self.clock = store, mode, clock
        self.host_settings = settings or {}
        self.blobs = Blobs(store.path)

    def new(self, account):
        return dict(schema_version=1, revision=0, event_seq=0, mode=self.mode, created_at=self.clock(),
                    active_brief_revision=None, research_revision=0, brief_versions={}, proposals={}, principal=None,
                    connection=None, authority=dict(revision=0, external_enabled=False, research_enabled=True,
                    paused=False, emergency_stop=False, allowed_action_kinds=[], future_actions_from=None),
                    settings=effective(self.host_settings.get(account)), people={}, pursuits={}, permissions={},
                    suppressions={}, actions={}, introductions={}, commands={}, tool_runs={}, threads={},
                    projection_outbox={}, events=[], sources={}, health={}, storage={}, identity_aliases={},
                    chat=[], budgets={}, research_passes={})

    @contextmanager
    def transaction(self, account, recovery=False):
        with self.store.transaction() as db:
            doc = self.store.load(db, account, self.mode)
            state = doc.setdefault("chris_v1", self.new(account))
            c.require(state.get("schema_version") == 1, "upgrade_required", 409)
            yield db, state
            from .scheduler import CURRENT_JOB
            job = CURRENT_JOB.get()
            if job and not recovery:
                lease = db.execute("SELECT attempts,state,lease_until FROM jobs WHERE id=? AND account=?", (job[0],account)).fetchone()
                c.require(lease and lease['attempts'] == job[1] and lease['state'] == 'running' and lease['lease_until'] > self.clock(), 'stale_worker_generation', 409)
            size = len(c.canonical(doc))
            c.require(size < HARD_STOP, "storage_capacity_exceeded", 503)
            state["storage"] = dict(document_bytes=size, healthy=True, discovery_paused=size >= DISCOVERY_STOP,
                                    research_paused=size >= OUTBOUND_STOP, outbound_paused=size >= OUTBOUND_STOP)
            state["revision"] += 1
            self.store.save(db, doc)

    def snapshot(self, account):
        with self.store.transaction() as db:
            doc = self.store.load(db, account, self.mode)
            state = doc.get("chris_v1", self.new(account))
            c.require(state.get("schema_version") == 1, "upgrade_required", 409)
            return deepcopy(state)

    def enqueue(self, db, account, state, kind, payload=None, due=None, key=None):
        payload = {**(payload or {}), "research_revision": state["research_revision"]}
        job_id = str(uuid4())
        db.execute("INSERT OR IGNORE INTO jobs(id,account,job_key,kind,payload,state,due) VALUES(?,?,?,?,?,'queued',?)",
                   (job_id, account, key or job_id, "chris." + kind, c.canonical(payload).decode(), self.clock() if due is None else due))
        return job_id

    def command(self, account, envelope, actor):
        envelope, actor = c.command(envelope), c.actor(actor)
        c.require(actor["role"] != "viewer" and (envelope["command"] not in c.OWNER or actor["role"] == "owner"), "owner_required", 403)
        identity = envelope["command_id"]
        fingerprint = c.digest(envelope)
        # Replays are reads and do not advance the revision.
        old = self.snapshot(account)["commands"].get(identity)
        if old:
            c.require(old["digest"] == fingerprint, "idempotency_conflict", 409)
            return old["result"]
        with self.transaction(account) as (db, state):
            old = state["commands"].get(identity)
            if old:
                c.require(old["digest"] == fingerprint, "idempotency_conflict", 409)
                return old["result"]
            c.require(state["revision"] == envelope["expected_revision"], "revision_conflict", 409)
            name, p, now = envelope["command"], envelope["payload"], self.clock()
            result = {"command_id": identity, "status": "accepted", "revision": state["revision"] + 1}
            if name == "brief.propose":
                state["chat"].append(dict(role="principal", text=p["text"], created_at=now))
                request = p['text'].strip().lower().rstrip('?.!')
                if request in {'status', 'what is happening', 'what are you doing', 'how is it going'}:
                    completed = sum(i['state'] == 'introduced' for i in state['introductions'].values())
                    reply = f"I have researched {len(state['people'])} people and verified {completed} introductions. Messaging is {'enabled for eligible future actions' if state['authority']['external_enabled'] else 'off'}. See People for evidence and individual gaps."
                elif request in {'pause', 'pause chris', 'stop', 'stop messaging', 'stop research'}:
                    if request == 'stop research': state['settings']['research_enabled'] = False
                    else: state['authority']['paused'] = True
                    cancel_unstarted(state)
                    reply = 'Paused. I will keep observing in-flight outcomes and withdrawals.'
                elif request in {'resume', 'resume work'}:
                    c.require(actor['role'] == 'owner', 'owner_required', 403)
                    state['authority']['paused'] = False
                    reply = 'Resumed within the existing authority. Messaging scope has not expanded.'
                elif any(phrase in request for phrase in ['turn sending on', 'enable messaging', 'turn all sending on']):
                    reply = 'Review the future messaging scope in Settings to enable it.'
                else:
                    proposal_id = str(uuid4())
                    state["proposals"][proposal_id] = dict(text=p["text"], brief=None, created_at=now)
                    result["proposal_id"] = proposal_id
                    if state['health'].get('research_configured') and state['settings']['daily_micro_usd']>0:
                        self.enqueue(db,account,state,'briefing',{'proposal_id':proposal_id})
                    reply = "Review your endeavour, public name and timezone, then start research. Your WhatsApp connection can be completed separately."
                state['chat'].append(dict(role='chris', text=reply, created_at=now))
            elif name == "brief.save_proposal":
                proposal = self.entity(state, "proposals", p["proposal_id"])
                proposal["brief"] = deepcopy(p["brief"])
                proposal['reviewed'] = True
                result["proposal_id"] = p["proposal_id"]
            elif name == "brief.activate":
                proposal = self.entity(state, "proposals", p["proposal_id"])
                c.require(proposal["brief"] is not None, "brief_review_required", 409)
                brief = c.brief(proposal["brief"])
                previous = state["brief_versions"].get(str(state["active_brief_revision"]))
                relevant = lambda b: {k: v for k, v in (b or {}).items() if k not in {"revision", "created_at", "timezone"}}
                changed = relevant(previous) != relevant(brief)
                revision = len(state["brief_versions"]) + 1
                state["brief_versions"][str(revision)] = {**brief, "revision": revision, "created_at": now}
                state["active_brief_revision"] = revision
                if changed:
                    state["research_revision"] += 1
                    cancel_unstarted(state)
                    db.execute("UPDATE jobs SET state='cancelled' WHERE account=? AND kind LIKE 'chris.%' AND state='queued'", (account,))
                    for pursuit in state["pursuits"].values():
                        if pursuit["state"] not in {"declined", "suppressed", "introduced", "excluded"}: pursuit["qualification"] = "pending"
                state["settings"]["timezone"] = brief["timezone"]
                self.enqueue(db, account, state, "research")
            elif name == "research.start":
                c.require(state["active_brief_revision"] is not None, "economic_objective_needed", 409)
                c.require(not state["storage"].get("discovery_paused"), "storage_attention", 409)
                result["job_id"] = self.enqueue(db, account, state, "research")
            elif name in {"workspace.pause", "workspace.resume"}:
                state["authority"]["paused"] = name == "workspace.pause"
                cancel_unstarted(state)
            elif name == "autonomy.set":
                a = state["authority"]
                c.require(p["displayed_authority_revision"] == a["revision"], "authority_changed", 409)
                if p["enabled"]:
                    c.require(state["active_brief_revision"] and state["principal"] and state["connection"], "identity_setup_needed", 409)
                    c.require(state["principal"]["provider_id"] != state["connection"]["self_provider_id"], "principal_not_distinct", 409)
                cancel_unstarted(state)
                a.update(external_enabled=p["enabled"], allowed_action_kinds=p["scope_kinds"], revision=a["revision"] + 1,
                         enabled_by_user_id=actor["user_id"], future_actions_from=now, enabled_at=now)
            elif name == "settings.update":
                maxima = effective(self.host_settings.get(account))
                for key, value in p.items():
                    if key.startswith("daily_") or key == "job_micro_usd": c.require(value <= maxima[key], "host_limit_exceeded", 409)
                state["settings"].update(p)
            elif name == "principal.challenge":
                c.require(state["connection"], "connection_unavailable", 409)
                result["challenge"] = challenge(state, now)
                result["expires_at"] = now + 600
            elif name == "principal.unbind":
                state["principal"] = None
                state["authority"]["external_enabled"] = False
                cancel_unstarted(state)
            elif name.startswith("person."):
                person = self.entity(state, "people", p["person_id"])
                pursuit = pursuit_for(state, p["person_id"])
                if name == "person.identity_attest":
                    phone(p["phone_e164"])
                    c.require(self.mode != "live" or not person.get("synthetic"), "synthetic_live_evidence", 409)
                    collisions = [v for v in state["people"].values() if v["person_id"] != p["person_id"] and v.get("phone_e164") == p["phone_e164"]]
                    c.require(not collisions, "ambiguous_phone", 409)
                    person.update(phone_e164=p["phone_e164"], identity_status="operator_attested", identity_evidence=p, identity_attested_at=now)
                    if pursuit["qualification"] == "qualified":
                        from .projection import stage
                        source = event(state, "contact_identity_attested", now, p["person_id"])
                        stage(state, account, source, "contact", dict(person_id=p["person_id"], display_name=person["display_name"], company_name=person["company_name"], identity_status=person["identity_status"]))
                        if person.get('dossier_ref'):
                            stage(state,account,source,'dossier_note',dict(person_id=p['person_id'],summary=pursuit.get('rank_rationale','Research dossier available in Chris.'),dossier_ref=person['dossier_ref']))
                    # Attestation does not manufacture an observed WhatsApp provider identity.
                    cancel_unstarted(state, p["person_id"])
                elif name == "person.exclude":
                    transition(pursuit, "excluded", now); cancel_unstarted(state, p["person_id"])
                else:
                    pursuit.update(not_before=dt.datetime.fromisoformat(c.stamp(p["not_before"])).timestamp(), paused=True, defer_reason=p["reason"])
                    cancel_unstarted(state, p["person_id"])
            elif name == "permission.record":
                person = self.entity(state, "people", p["person_id"])
                c.require(person.get("provider_id") and state["connection"] and p["business_sender_identity"] == state["connection"]["self_provider_id"], "recipient_identity_unresolved", 409)
                granted = dt.datetime.fromisoformat(c.stamp(p["granted_at"])).timestamp()
                c.require(granted <= now and (self.mode != "live" or not person.get("synthetic")), "invalid_permission_evidence", 409)
                permission_id = str(uuid4())
                state["permissions"][permission_id] = {**p, "permission_id": permission_id, "subject_provider_id": person["provider_id"], "status": "valid", "basis": "operator_attestation", "actor_user_id": actor["user_id"]}
            elif name == "permission.revoke":
                permission = self.entity(state, "permissions", p["permission_id"])
                permission.update(status="revoked", revoked_at=now)
                cancel_unstarted(state)
            elif name.startswith("pursuit."):
                pursuit = self.entity(state, "pursuits", p["pursuit_id"])
                if name == "pursuit.resume":
                    thread = state["threads"].get(pursuit.get("direct_thread_key"), {})
                    c.require(thread.get("last_observed_seq") == p["reviewed_thread_watermark"] and thread.get("history_ready"), "thread_review_stale", 409)
                pursuit["human_takeover"] = name == "pursuit.takeover"
                if name == 'pursuit.resume': pursuit['paused'] = False
                cancel_unstarted(state, pursuit["person_id"])
            elif name == "message.draft":
                from .dispatch import freeze
                pursuit = self.entity(state, "pursuits", p["pursuit_id"])
                action = freeze(state, account, pursuit, "reply", p["text"], now)
                result["action_id"] = action["action_id"]
            elif name == "message.approve":
                action = self.entity(state, "actions", p["action_id"])
                c.require(action["status"] == "draft" and action["digest"] == p["displayed_digest"], "action_changed", 409)
                action.update(status="queued", approved_by=actor["user_id"])
                result["job_id"] = self.enqueue(db, account, state, "dispatch", {"action_id": action["action_id"]})
            elif name in {"action.cancel", "action.reconcile"}:
                action = self.entity(state, "actions", p["action_id"])
                if name == "action.cancel":
                    c.require(action["status"] in {"draft", "queued", "preflight"}, "started_action_cannot_reset", 409)
                    action["status"] = "cancelled"
                else: self.enqueue(db, account, state, "reconcile", {"action_id": action["action_id"]})
            elif name == "projection.retry":
                projection = self.entity(state, "projection_outbox", p["projection_id"])
                projection["next_attempt_at"] = now
                self.enqueue(db, account, state, "projection")
            elif name == "connection.refresh": self.enqueue(db, account, state, "sync")
            event(state, name, now, actor_id=actor["user_id"], command_id=identity)
            stored_result = {k: v for k, v in result.items() if k != "challenge"}
            state["commands"][identity] = dict(digest=fingerprint, result=stored_result)
            return result

    @staticmethod
    def entity(state, collection, identity):
        value = state[collection].get(identity)
        c.require(value is not None, "not_found", 404)
        return value

    def overview(self, account):
        s = self.snapshot(account)
        connection, principal = s["connection"] or {}, s["principal"] or {}
        configured = bool(s["health"].get("research_configured"))
        from zoneinfo import ZoneInfo
        today = dt.datetime.fromtimestamp(self.clock(), ZoneInfo(s['settings']['timezone'])).date().isoformat()
        reserved = s['budgets'].get(max(today, s['budgets'].get('latest_day', today)), {}).get('reserved', 0)
        return dict(schema_version=1, revision=s["revision"], mode=self.mode,
                    brief=s["brief_versions"].get(str(s["active_brief_revision"])), proposals=s["proposals"],
                    counts={"researching": sum(p["state"] in {"discovered", "researching"} for p in s["pursuits"].values()),
                            "approached": sum(bool(p.get("last_verified_outbound_at")) for p in s["pursuits"].values()),
                            "awaiting_reply": sum(p["state"] == "awaiting_reply" for p in s["pursuits"].values()),
                            "introduced": sum(p["state"] == "introduced" for p in s["pursuits"].values())},
                    authority=s["authority"], settings=s["settings"], chat=s["chat"][-30:],
                    activity=s["events"][-30:], readiness=dict(mode=self.mode, schema_supported=True,
                    research=dict(configured=configured, enabled=s["settings"]["research_enabled"], budget_remaining=max(0,s["settings"]["daily_micro_usd"]-reserved), reason_codes=[s["health"].get("research_error","research_not_configured")] if not configured else ["budget_exhausted"] if reserved >= s['settings']['daily_micro_usd'] else []),
                    whatsapp=dict(configured=bool(connection), connected=connection.get("connected", False), account_bound=bool(connection.get("provider_account_id")), self_verified=bool(connection.get("self_provider_id")), history_ready=bool(s["threads"]) and all(t.get("history_ready") for t in s["threads"].values()), contract_verified=connection.get("contract_verified", False), reason_codes=[s["health"].get("sync_error", "connection_unavailable")] if not connection.get("connected") else []),
                    principal=dict(named=bool(s["active_brief_revision"]), number_bound=bool(principal), distinct_from_chris=bool(principal) and principal.get("provider_id") != connection.get("self_provider_id"), reason_codes=[] if principal else ["principal_identity_needed"]),
                    authority=s["authority"], worker=dict(running=self.clock()-s["health"].get("heartbeat", 0)<30, last_heartbeat_at=s["health"].get("heartbeat")),
                    projection=dict(configured=bool(s["health"].get("projection_configured")), prerequisites_verified=False, pending=sum(p["status"] != "acknowledged" for p in s["projection_outbox"].values())),
                    storage=s["storage"] or dict(document_bytes=0, healthy=True, research_paused=False, outbound_paused=False), live_acceptance=dict(verified=False, evidence_ref=None)))
