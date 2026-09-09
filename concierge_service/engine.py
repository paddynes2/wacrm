"""Account-scoped outbound orchestration over extracted, tested concierge rules."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta, time as wall_time
import hashlib
import json
import math
import re
import time
from uuid import uuid4

from .store import Store, account_id, encode
from .concierge_core import state as core
from .concierge_core import calendar as calendar_core
from .concierge_core import amendment as amendment_core
from . import providers, research, enrichment

MAX_ATTEMPTS = 3
LEASE_SECONDS = 180
STOP_WORDS = {"stop", "unsubscribe", "do not contact me", "don't contact me", "remove me"}


def text(value, name, limit=4000, optional=False):
    if optional and value in (None, ""):
        return ""
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} requires text of at most {limit} characters")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise ValueError(f"{name} contains invalid characters")
    return value.strip()


def number(value, name, maximum=10000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= maximum:
        raise ValueError(f"{name} requires a number between zero and {maximum}")
    return value


def digest(value):
    return core._digest(value)


class Engine:
    def __init__(self, store: Store, *, mode="simulation", model_config=None, discovery_config=None, unipile=None):
        if mode not in {"simulation", "live"}:
            raise ValueError("Explicit simulation or live mode required")
        self.store, self.mode = store, mode
        # Configs are keyed by verified account UUID; a tenant never supplies credentials.
        self.models = model_config or {}
        self.discovery = discovery_config or {}
        self.unipile = unipile or {}

    def now(self, doc):
        return time.time() + doc["clock_offset"]

    def stamp(self, doc):
        return datetime.fromtimestamp(self.now(doc), timezone.utc).isoformat()

    def event(self, doc, kind, **data):
        doc["events"].append({"id": str(uuid4()), "kind": kind, "created_at": self.stamp(doc), **data})

    def prospect(self, doc, pid):
        value = next((p for p in doc["prospects"] if p["id"] == pid), None)
        if value is None:
            raise ValueError("Prospect not found in this account")
        return value

    def state(self, doc, pid):
        return core.scoped_view(doc["observations"], pid)

    def observe(self, doc, pid, kind, data, *, event_id=None, source="operator:dogfood", occurred_at=None):
        event = {"event_id": event_id or str(uuid4()), "pursuit_id": pid, "account_id": doc["account_id"],
                 "kind": kind, "data": data, "source_ref": source,
                 "occurred_at": occurred_at or self.stamp(doc)}
        core.validate(event)
        old = next((e for e in doc["observations"] if e["event_id"] == event["event_id"]), None)
        if old:
            if old != event:
                raise ValueError("Provider event identity collision")
            return
        core.derive([e for e in doc["observations"] if e["pursuit_id"] == pid] + [event])
        doc["observations"].append(event)

    def enqueue(self, db, doc, kind, payload, key, delay=0):
        jid = str(uuid4())
        db.execute("INSERT OR IGNORE INTO jobs(id,account,job_key,kind,payload,state,due) VALUES(?,?,?,?,?,'queued',?)",
                   (jid, doc["account_id"], key, kind, encode(payload), self.now(doc) + delay))

    def cancel(self, db, doc, pid=None):
        rows = db.execute("SELECT id,payload FROM jobs WHERE account=? AND state IN ('queued','running')", (doc["account_id"],)).fetchall()
        for row in rows:
            if pid is None or json.loads(row["payload"]).get("prospect_id") == pid:
                db.execute("UPDATE jobs SET state='cancelled',lease_until=NULL WHERE id=?", (row["id"],))
        for decision in doc["decisions"]:
            if decision["status"] == "pending" and (pid is None or decision["prospect_id"] == pid):
                decision["status"] = "stale"

    def report(self, account):
        with self.store.transaction() as db:
            doc = self.store.load(db, account, self.mode)
            jobs = [dict(r) for r in db.execute("SELECT id,kind,state,due,attempts,error FROM jobs WHERE account=? ORDER BY due DESC LIMIT 100", (account,))]
            return self.present(doc, jobs)

    def present(self, doc, jobs):
        ps = []
        for p in doc["prospects"]:
            state = self.state(doc, p["id"])
            ps.append({**p, "conversation": state,
                       "status": state["status"] if state["status"] != "unconfigured" else p["status"]})
        spent = sum(e["charged_usd"] for e in doc["expenses"])
        model = self.models.get(doc["account_id"], {"provider": "fixture"} if self.mode == "simulation" else {})
        readiness = {"number_provider": "Wabi", "transport": "Unipile", "mode": self.mode,
                     "model": model.get("provider", "unconfigured"), "model_configured": bool(model),
                     "fixture_model": model.get("provider") == "fixture",
                     "unipile_configured": doc["account_id"] in self.unipile,
                     "connection_verified": doc["connections"].get("verified_at"),
                     "live_delivery_verified": False, "live_execution_enabled": False,
                     "reason": "Live execution requires a separately authorized exact action. No live sends occur in this build.",
                     "remaining_setup": ["Fresh Wabi account registration and recovery", "Unipile account identity verification",
                                         "Controlled live delivery and calendar acceptance"]}
        return {"account_id": doc["account_id"], "mode": self.mode, "brief": doc["brief"],
                "brief_revision": doc["brief_revision"], "calendar_preferences": doc.get("calendar_preferences", {}), "prospects": ps, "messages": doc["messages"],
                "decisions": doc["decisions"], "jobs": jobs, "timeline": doc["observations"],
                "amendment_outcomes": [e for e in doc["events"] if e["kind"] == "calendar_amendment_verified"], "events": doc["events"][-200:],
                "paused": doc["paused"], "readiness": readiness,
                "metrics": {"discovered": len(ps), "qualified": sum(p.get("qualification") == "qualified" for p in ps),
                            "reachable": sum(p.get("phone_status") == "operator_verified" for p in ps),
                            "approached": len({m["prospect_id"] for m in doc["messages"] if m.get("purpose") == "approach"}),
                            "introduced": sum(p["conversation"].get("introduced", False) for p in ps),
                            "booked": sum(bool(p["conversation"].get("booking_id")) and p.get("calendar_status") != "cancelled" for p in ps),
                            "bookings_created": sum(bool(p["conversation"].get("booking_id")) for p in ps),
                            "bookings_cancelled": sum(p.get("calendar_status") == "cancelled" for p in ps),
                            "attended": sum(p["conversation"].get("status") == "attended" for p in ps),
                            "useful_introductions": sum(r["useful"] for r in doc["reviews"]),
                            "customer_minutes": sum(r["minutes"] for r in doc["reviews"]),
                            "cost_usd": round(spent, 6), "budget_usd": (doc["brief"] or {}).get("budget_usd", 0),
                            "cost_basis": "Unknown provider charges retain the reserved maximum; not a settled invoice",
                            "simulated": self.mode == "simulation"}}

    def command(self, account, body):
        account = account_id(account)
        if not isinstance(body, dict):
            raise ValueError("Command object required")
        name = body.get("command")
        fields = {"calendar_preferences": {"prospect_id", "party", "timezone", "windows", "calendar_access", "simulated_busy", "source_ref"},
                  "request_calendar_exception": {"prospect_id", "party", "start", "end", "source_ref"}, "booking_link": {"prospect_id"}, "sync": set(), "research": {"prospect_id"}, "research_phone": {"prospect_id"}, "save_brief": {"brief"}, "discover": {"source", "limit"},
                  "qualify": {"prospect_id", "verdict", "reason"}, "enrich": {"prospect_id", "phone", "source_ref"},
                  "start": {"prospect_id"}, "reply": {"prospect_id", "text", "message_id"},
                  "prepare_amendment": {"prospect_id", "operation", "start", "end", "source_ref"},
                  "approve_amendment": {"prospect_id", "digest"}, "retry_job": {"job_id"}, "new_pursuit": {"prospect_id"}, "process": set(), "approve": {"decision_id"}, "discard": {"decision_id"},
                  "takeover": {"prospect_id"}, "resume": {"prospect_id"},
                  "consent": {"prospect_id", "party", "scope", "source_ref"},
                  "introduce": {"prospect_id"}, "propose": {"prospect_id", "start", "end", "timezone"},
                  "book": {"prospect_id", "start", "end"}, "review": {"prospect_id", "useful", "minutes", "note"},
                  "readiness": set(), "pause": set(), "unpause": set(), "advance": {"seconds"},
                  "followup": {"prospect_id", "seconds"}, "link_contact": {"prospect_id", "contact"},
                  "attended": {"prospect_id", "source_ref"}, "manual_reply": {"prospect_id", "text"}}
        if name not in fields or set(body) - fields[name] - {"command", "attested_by"}:
            raise ValueError("Unknown command or fields")
        if name == "sync":
            from .ingestion import sync_account
            sync_account(self, account)
            return self.report(account)
        if name == "process":
            self.process_one(account)
            return self.report(account)
        if name == "readiness":
            client = self.unipile.get(account)
            if client:
                result = client.verify_account()
                with self.store.transaction() as db:
                    doc = self.store.load(db, account, self.mode)
                    if result.get("id") != client.account_id or result.get("identity_verified") is not True:
                        raise ValueError("Provider account identity verification failed")
                    doc["connections"].update(verified_at=self.stamp(doc), account_id=client.account_id)
                    self.event(doc, "connection_checked", verified=True)
                    self.store.save(db, doc)
            return self.report(account)
        with self.store.transaction() as db:
            doc = self.store.load(db, account, self.mode)
            if name == "save_brief":
                self.save_brief(db, doc, body.get("brief"))
            elif name == "retry_job":
                row = db.execute("SELECT * FROM jobs WHERE id=? AND account=?", (body.get("job_id"), account)).fetchone()
                if not row or row["state"] not in {"failed", "cancelled"} or doc["paused"]:
                    raise ValueError("Retry requires a failed/cancelled job and active workspace")
                payload = json.loads(row["payload"])
                if payload["brief_revision"] != doc["brief_revision"]:
                    raise ValueError("Changed brief requires new work")
                if row["kind"] in {"research", "research_phone"}:
                    p = self.prospect(doc, payload["prospect_id"])
                    if digest(p) != payload["prospect_digest"]:
                        raise ValueError("Research evidence changed; request fresh research")
                if row["kind"] == "turn":
                    p = self.prospect(doc, payload["prospect_id"])
                    self.eligible(doc, p)
                    core.check_action(self.state(doc, p["id"]), payload["purpose"], payload["revision"])
                # Attempt numbers never reset: a late worker cannot acquire a new attempt's authority.
                replacement = {**payload, "retry_of": row["id"]}
                self.enqueue(db, doc, row["kind"], replacement, "retry:" + row["id"])
            elif name in {"pause", "unpause"}:
                doc["paused"] = name == "pause"
                if doc["paused"]:
                    self.cancel(db, doc)
            elif name == "advance":
                if self.mode != "simulation":
                    raise ValueError("Clock controls are simulation only")
                doc["clock_offset"] += number(body.get("seconds"), "seconds", 30 * 86400)
            elif name == "discover":
                if not doc["brief"]:
                    raise ValueError("Save a brief first")
                source = body.get("source", "fixture")
                if source not in {"fixture", "treg"} or (source == "fixture" and self.mode != "simulation"):
                    raise ValueError("Invalid discovery source for this mode")
                limit = body.get("limit", 10)
                if type(limit) is not int or not 1 <= limit <= 20:
                    raise ValueError("Dogfood discovery supports 1 to 20 candidates")
                self.enqueue(db, doc, "discover", {"source": source, "limit": limit, "brief_revision": doc["brief_revision"]},
                             f"discovery:{doc['brief_revision']}:{source}:{limit}")
            elif name in {"approve", "discard"}:
                decision = next((d for d in doc["decisions"] if d["id"] == body.get("decision_id")), None)
                if not decision or decision["status"] != "pending":
                    raise ValueError("Pending decision not found")
                if name == "discard":
                    decision["status"] = "discarded"
                else:
                    self.approve(doc, decision)
            else:
                pid = body.get("prospect_id")
                p = self.prospect(doc, pid)
                state = self.state(doc, pid)
                if name in {"research", "research_phone"}:
                    if not doc["brief"] or doc["paused"] or p.get("archived"):
                        raise ValueError("Research requires an active brief and candidate")
                    if name == "research_phone" and p.get("qualification") != "qualified":
                        raise ValueError("Qualify the candidate before spending on phone research")
                    snapshot = digest(p)
                    self.enqueue(db, doc, name, {"prospect_id": pid, "revision": state["revision"],
                                 "brief_revision": doc["brief_revision"], "prospect_digest": snapshot},
                                 name + ":" + pid + ":" + str(doc["brief_revision"]) + ":" + snapshot)
                elif name == "new_pursuit":
                    self.cancel(db, doc, pid)
                    replacement = {k: v for k, v in p.items() if k not in {"calendar", "booking", "chat_id"}}
                    replacement.update(id=str(uuid4()), previous_pursuit=pid, qualification="pending", status="discovered", brief_stale=False)
                    doc["prospects"].append(replacement)
                    p["archived"] = True
                elif name == "qualify":
                    if body.get("verdict") not in {"qualified", "rejected"}:
                        raise ValueError("Qualification verdict required")
                    p["qualification"] = body["verdict"]
                    p["status"] = body["verdict"]
                    p["qualified_brief_revision"] = doc["brief_revision"]
                    if state["status"] == "unconfigured":
                        p["brief_stale"] = False
                    p["qualification_reason"] = text(body.get("reason"), "Qualification reason")
                    if body["verdict"] == "rejected":
                        self.cancel(db, doc, pid)
                elif name == "enrich":
                    phone = text(body.get("phone"), "Phone", 20)
                    if not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
                        raise ValueError("International phone with country code required")
                    if state["status"] != "unconfigured" and p.get("phone") != phone:
                        raise ValueError("Cannot redirect an existing conversation to another phone")
                    p.update(phone=phone, phone_status="operator_verified", phone_source=text(body.get("source_ref"), "Phone evidence"))
                elif name == "link_contact":
                    contact = body.get("contact")
                    if (not isinstance(contact, dict) or contact.get("account_id") != doc["account_id"]
                            or contact.get("phone") != p.get("phone") or not p.get("phone")):
                        raise ValueError("CRM contact must match the verified prospect phone")
                    p["contact_id"] = account_id(contact.get("id"))
                elif name == "start":
                    self.start(db, doc, p, state)
                elif name == "reply":
                    if self.mode != "simulation":
                        raise ValueError("Typed recipient replies are simulation only")
                    self.inbound(db, doc, p, text(body.get("text"), "Reply"), body.get("message_id"))
                elif name in {"takeover", "resume"}:
                    if state["status"] == "unconfigured":
                        raise ValueError("Start the conversation first")
                    self.observe(doc, pid, name, {"reason": "Operator " + name})
                    self.cancel(db, doc, pid)
                elif name == "consent":
                    if state["status"] == "unconfigured" or body.get("party") not in {"principal", "recipient"}:
                        raise ValueError("Choose a conversation and party")
                    self.observe(doc, pid, "consent", {"party_id": state["identity"][body["party"] + "_id"],
                                 "scope": body.get("scope"), "proposal_id": pid}, source=text(body.get("source_ref"), "Permission evidence", 500))
                    self.cancel(db, doc, pid)
                elif name == "introduce":
                    self.stage(doc, p, "introduction", f"{doc['brief']['principal_name']}, meet {p['name']}. {p['fit']}")
                elif name == "calendar_preferences":
                    self.set_calendar_preferences(db, doc, p, body)
                elif name == "request_calendar_exception":
                    self.request_calendar_exception(doc, p, body)
                elif name == "booking_link":
                    link = doc["brief"].get("booking_link")
                    if not link:
                        raise ValueError("Configure the preferred booking link first")
                    self.stage(doc, p, "booking_link", "Please choose a suitable time here: " + link)
                elif name == "propose":
                    self.propose(doc, p, body)
                elif name == "book":
                    self.book(doc, p, body)
                elif name == "prepare_amendment":
                    self.prepare_amendment(doc, p, body)
                elif name == "approve_amendment":
                    self.approve_amendment(db, doc, p, body.get("digest"))
                elif name == "review":
                    if type(body.get("useful")) is not bool:
                        raise ValueError("Usefulness must be true or false")
                    review = {"prospect_id": pid, "useful": body["useful"], "minutes": number(body.get("minutes"), "Minutes"),
                              "note": text(body.get("note"), "Review note", optional=True)}
                    doc["reviews"] = [r for r in doc["reviews"] if r["prospect_id"] != pid] + [review]
                elif name == "attended":
                    if not state.get("booking_id") or p.get("calendar_status") == "cancelled" or p.get("booking", {}).get("status") == "cancelled":
                        raise ValueError("Attendance requires a verified booking that has not been cancelled")
                    self.observe(doc, pid, "meeting_attended", {"event_id": state["booking_id"]}, source=text(body.get("source_ref"), "Attendance evidence", 500))
                elif name == "followup":
                    if p.get("calendar_status") == "cancelled" or state["status"] in {"unconfigured", "human_owned", "opted_out", "declined", "reconcile"} or state.get("latest_inbound"):
                        raise ValueError("Follow-up requires an active unanswered approach")
                    receipts = [m for m in doc["messages"] if m["prospect_id"] == pid and m.get("purpose") == "approach"]
                    if not receipts:
                        raise ValueError("Follow-up requires the preceding verified receipt")
                    delay = number(body.get("seconds"), "Follow-up delay", 30 * 86400)
                    self.queue_turn(db, doc, p, "approach", delay=delay)
                elif name == "manual_reply":
                    if state["status"] != "human_owned":
                        raise ValueError("Take over this conversation before a human reply")
                    if self.mode != "simulation":
                        raise ValueError("Live human reply requires exact action authorization")
                    self.message(doc, p, text(body.get("text"), "Reply"), "outbound", "manual")
                else:
                    raise ValueError("Unsupported command")
            self.event(doc, name, actor=body.get("attested_by", "local-operator"))
            self.store.save(db, doc)
        return self.report(account)

    def save_brief(self, db, doc, brief):
        allowed = {"principal_name", "offer", "audience", "geography", "exclusions", "claims", "timezone", "booking_link", "budget_usd"}
        if not isinstance(brief, dict) or set(brief) - allowed:
            raise ValueError("Invalid brief fields")
        clean = {k: text(brief.get(k), k, 2000 if k == "offer" else 4000, optional=k in {"exclusions", "claims", "booking_link"})
                 for k in allowed - {"budget_usd"}}
        calendar_core.zone(clean["timezone"])
        if clean["booking_link"]:
            from urllib.parse import urlsplit
            url = urlsplit(clean["booking_link"])
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("Booking link requires HTTPS without credentials")
        clean["budget_usd"] = number(brief.get("budget_usd", 0), "Budget")
        if doc["brief"] == clean:
            return
        self.cancel(db, doc)
        doc["brief"] = clean
        doc["brief_revision"] += 1
        for p in doc["prospects"]:
            p["brief_stale"] = True

    def eligible(self, doc, p):
        if p.get("qualification") != "qualified" or p.get("brief_stale") or p.get("archived"):
            raise ValueError("Current qualification required; a changed configured brief needs a new pursuit")

    def start(self, db, doc, p, state):
        if doc["paused"] or not doc["brief"]:
            raise ValueError("Save a brief and resume the workspace first")
        self.eligible(doc, p)
        if state["status"] == "unconfigured":
            if self.mode == "live" and p.get("phone_status") != "operator_verified":
                raise ValueError("Live approach requires attributable phone evidence")
            identity = {"crm_ref": p.get("contact_id", "prospect:" + p["id"]), "principal_id": "principal:" + doc["account_id"],
                        "recipient_id": p.get("phone") or "prospect:" + p["id"], "principal_name": doc["brief"]["principal_name"],
                        "name": p["name"], "offer": doc["brief"]["offer"], "fit": p["fit"][:2000],
                        "profile_url": p.get("profile_url") or p["source"][:500]}
            self.observe(doc, p["id"], "identified", identity)
            if self.mode == "simulation":
                self.observe(doc, p["id"], "consent", {"party_id": identity["recipient_id"], "scope": "contact", "proposal_id": p["id"]},
                             source="simulation:operator-started-test")
        state = self.state(doc, p["id"])
        if self.mode == "live" and [state["identity"]["recipient_id"], "contact"] not in state["consents"]:
            return
        if any(m["prospect_id"] == p["id"] and m.get("purpose") == "approach" and m["direction"] == "outbound" for m in doc["messages"]) and not state.get("reply_required"):
            return
        self.queue_turn(db, doc, p, "reply" if self.state(doc, p["id"]).get("reply_required") else "approach")

    def queue_turn(self, db, doc, p, purpose, delay=0):
        self.eligible(doc, p)
        state = self.state(doc, p["id"])
        core.check_action(state, purpose, state["revision"])
        self.enqueue(db, doc, "turn", {"prospect_id": p["id"], "revision": state["revision"],
                     "brief_revision": doc["brief_revision"], "purpose": purpose},
                     f"turn:{p['id']}:{state['revision']}:{doc['brief_revision']}:{purpose}", delay)

    def ingest(self, account, prospect_id, text, message_id, chat_id, sender_id, occurred_at, source_ref):
        """Trusted provider-reader seam; never exposed as arbitrary observations."""
        with self.store.transaction() as db:
            doc = self.store.load(db, account, self.mode)
            p = self.prospect(doc, prospect_id)
            bound = self.state(doc, prospect_id)
            canonical = ("+" + sender_id.removesuffix("@s.whatsapp.net")) if isinstance(sender_id, str) and sender_id.endswith("@s.whatsapp.net") else sender_id
            if bound["status"] == "unconfigured" or canonical != bound["identity"]["recipient_id"] or not isinstance(chat_id, str) or not chat_id or (p.get("chat_id") and p["chat_id"] != chat_id):
                raise ValueError("Provider conversation identity mismatch")
            if text is None:
                self.observe(doc, prospect_id, "takeover", {"reason": "[Media requires human review]"},
                             event_id="media:" + digest([chat_id, message_id]), source=source_ref, occurred_at=occurred_at)
                self.cancel(db, doc, prospect_id)
                self.store.save(db, doc)
                return self.present(doc, [])
            self.inbound(db, doc, p, text, message_id, chat_id=chat_id, sender_id=sender_id,
                         occurred_at=occurred_at, source_ref=source_ref)
            self.store.save(db, doc)
        return self.report(account)

    def manual_outbound(self, account, prospect_id, text, message_id, chat_id, sender_id, occurred_at, source_ref):
        """Provider-verified human outbound; pause independently of model inference."""
        with self.store.transaction() as db:
            doc = self.store.load(db, account, self.mode)
            p = self.prospect(doc, prospect_id)
            state = self.state(doc, prospect_id)
            if state["status"] == "unconfigured" or not isinstance(chat_id, str) or not chat_id:
                raise ValueError("Configured provider conversation required")
            if p.get("chat_id") and p["chat_id"] != chat_id:
                raise ValueError("Provider chat differs from bound conversation")
            known = {e["data"]["provider_id"] for e in doc["observations"] if e["pursuit_id"] == prospect_id and e["kind"] == "dispatch_verified"}
            if message_id in known:
                return self.present(doc, [])
            prior = next((m for m in doc["messages"] if m["id"] == message_id), None)
            value = text if isinstance(text, str) and text.strip() else "[Media requires human review]"
            if prior:
                if prior["prospect_id"] != prospect_id or prior["text"] != value or prior["direction"] != "outbound" or prior.get("chat_id") != chat_id or prior.get("provider_timestamp") != occurred_at:
                    raise ValueError("Provider message identity collision")
                return self.present(doc, [])
            self.observe(doc, prospect_id, "manual_outbound", {"message_id": message_id, "chat_id": chat_id},
                         event_id="manual:" + digest([chat_id, message_id]), occurred_at=occurred_at, source=source_ref)
            p["chat_id"] = chat_id
            self.cancel(db, doc, prospect_id)
            self.message(doc, p, value, "outbound", "manual", message_id)
            doc["messages"][-1].update(chat_id=chat_id, provider_timestamp=occurred_at, source_ref=source_ref)
            self.store.save(db, doc)
        return self.report(account)

    def inbound(self, db, doc, p, value, message_id=None, *, chat_id=None, sender_id=None, occurred_at=None, source_ref=None):
        state = self.state(doc, p["id"])
        if state["status"] == "unconfigured":
            raise ValueError("Start the conversation first")
        value = text(value, "Reply")
        sender = sender_id or state["identity"]["recipient_id"]
        canonical_sender = ("+" + sender.removesuffix("@s.whatsapp.net")) if sender.endswith("@s.whatsapp.net") else sender
        if canonical_sender != state["identity"]["recipient_id"]:
            raise ValueError("Provider sender differs from bound recipient")
        chat = text(chat_id or "chat:" + p["id"], "Chat ID", 200)
        if p.get("chat_id") and p["chat_id"] != chat:
            raise ValueError("Provider chat differs from bound conversation")
        timestamp = occurred_at or self.stamp(doc)
        calendar_core.aware_datetime(timestamp)
        source = text(source_ref or "simulation:typed-reply", "Source", 500)
        mid = text(message_id, "Message ID", 150, optional=True) or str(uuid4())
        old = next((m for m in doc["messages"] if m["id"] == mid), None)
        if old:
            if old["text"] != value or old["prospect_id"] != p["id"] or old["direction"] != "inbound" or old.get("chat_id") != chat or (occurred_at and old.get("provider_timestamp") != occurred_at):
                raise ValueError("Message ID collision")
            return
        p["chat_id"] = chat
        self.cancel(db, doc, p["id"])
        # Keep raw provider time on the message. Equal-resolution deliveries still
        # need distinct reducer instants so a second reply cannot disappear.
        effective_timestamp = timestamp
        matching = [e for e in doc["observations"] if e["pursuit_id"] == p["id"] and e["kind"] == "inbound"]
        raw_matches = [m for m in doc["messages"] if m["prospect_id"] == p["id"] and m.get("provider_timestamp") == timestamp]
        if raw_matches and matching:
            latest = max(calendar_core.aware_datetime(e["occurred_at"]) for e in matching)
            effective_timestamp = (max(latest, calendar_core.aware_datetime(timestamp)) + timedelta(microseconds=1)).isoformat()
        self.observe(doc, p["id"], "inbound", {"message_id": mid, "chat_id": chat,
                     "sender_id": state["identity"]["recipient_id"]}, event_id="inbound:" + digest([chat, mid]), occurred_at=effective_timestamp, source=source)
        self.message(doc, p, value, "inbound", "reply", mid)
        doc["messages"][-1].update(chat_id=chat, provider_timestamp=timestamp, source_ref=source)
        normalized = re.sub(r"[.!\s]+$", "", value.strip().lower())
        if normalized in STOP_WORDS:
            self.observe(doc, p["id"], "opt_out", {"party_id": state["identity"]["recipient_id"]})
        elif normalized in {"no thanks", "not interested", "no thank you"}:
            self.observe(doc, p["id"], "declined", {"party_id": state["identity"]["recipient_id"]})
        elif self.state(doc, p["id"]).get("reply_required") and not p.get("archived") and not p.get("brief_stale") and p.get("qualification") == "qualified" and self.state(doc, p["id"])["status"] not in {"human_owned", "opted_out", "declined", "reconcile", "attended"}:
            self.queue_turn(db, doc, p, "reply")

    def message(self, doc, p, value, direction, purpose, mid=None):
        doc["messages"].append({"id": mid or str(uuid4()), "prospect_id": p["id"], "direction": direction,
                               "text": value, "purpose": purpose, "simulated": self.mode == "simulation", "created_at": self.stamp(doc)})

    def stage(self, doc, p, purpose, value, extra=None):
        self.eligible(doc, p)
        state = self.state(doc, p["id"])
        core.check_action(state, purpose, state["revision"])
        value = text(value, "Draft")
        payload = {"prospect_id": p["id"], "purpose": purpose, "text": value, "revision": state["revision"],
                   "brief_revision": doc["brief_revision"], "account_id": doc["account_id"], "mode": self.mode, "recipients": ([state["identity"]["principal_id"], state["identity"]["recipient_id"]] if purpose == "introduction" else [state["identity"]["recipient_id"]]), **(extra or {})}
        did = digest(payload)
        old = next((d for d in doc["decisions"] if d["id"] == did), None)
        if old:
            return old
        decision = {**payload, "id": did, "status": "pending", "created_at": self.stamp(doc)}
        doc["decisions"].append(decision)
        return decision

    def approve(self, doc, decision):
        if self.mode != "simulation":
            raise ValueError("Live sending is not authorized by simulation approval")
        if doc["paused"] or decision["brief_revision"] != doc["brief_revision"]:
            raise ValueError("Paused or changed brief invalidated this decision")
        frozen = {k: v for k, v in decision.items() if k not in {"id", "status", "created_at"}}
        if digest(frozen) != decision["id"] or decision["account_id"] != doc["account_id"] or decision["mode"] != self.mode:
            raise ValueError("Decision payload digest or ownership mismatch")
        p = self.prospect(doc, decision["prospect_id"])
        self.eligible(doc, p)
        state = self.state(doc, p["id"])
        core.check_action(state, decision["purpose"], decision["revision"])
        expected = ([state["identity"]["principal_id"], state["identity"]["recipient_id"]] if decision["purpose"] == "introduction" else [state["identity"]["recipient_id"]])
        if decision["recipients"] != expected:
            raise ValueError("Simulated membership or recipient mismatch")
        action = {"action_id": decision["id"], "purpose": decision["purpose"]}
        if decision["purpose"] == "booking":
            if self.now(doc) > decision["valid_until"]:
                raise ValueError("Calendar proposal expired; find times again")
            people, bindings, read = self.calendar_reader(doc, p)
            calendar_core.recheck_booking(decision["slot"], people, bindings, read, now=lambda: datetime.fromtimestamp(self.now(doc), timezone.utc))
            request = decision["request"]
            proposal = request["proposal"]
            receipt = {"id": "sim:" + decision["id"], "status": "confirmed", "summary": proposal["summary"],
                       "start": {"dateTime": proposal["start"]}, "end": {"dateTime": proposal["end"]},
                       "attendees": [{"email": a} for a in proposal["attendees"]]}
            if decision["request_sha"] != digest(proposal) or not calendar_core.verify_booking(request, receipt):
                raise ValueError("Simulated booking read-back differs from proposal")
            p["booking"] = receipt
        self.observe(doc, p["id"], "dispatch_started", {**action, "revision": decision["revision"]})
        self.observe(doc, p["id"], "dispatch_verified", {**action, "provider_id": "sim:" + decision["id"],
                     **({"request_sha": decision["request_sha"]} if decision["purpose"] == "booking" else {})}, source="simulation:verified-local-effect")
        self.message(doc, p, decision["text"], "outbound", decision["purpose"])
        decision["status"] = "simulated"

    def calendar_settings(self, doc, p, party, timezone_name=None):
        saved = doc.get("calendar_preferences", {}) if party == "principal" else p.get("calendar_preferences", {})
        defaults = {"timezone": timezone_name or (p.get("calendar", {}).get("timezone") if party == "recipient" else None) or doc["brief"]["timezone"],
                    "windows": [{"weekday": day, "start": "09:00", "end": "17:00"} for day in range(5)],
                    "calendar_access": self.mode == "simulation", "simulated_busy": [], "source_ref": "simulation:default-working-hours"}
        return {**defaults, **saved}

    def set_calendar_preferences(self, db, doc, p, body):
        if self.mode != "simulation":
            raise ValueError("Calendar access/busy scenario controls are simulation only")
        party = body.get("party")
        if party not in {"principal", "recipient"}:
            raise ValueError("Choose principal or recipient calendar preferences")
        tz = text(body.get("timezone"), "Timezone", 100)
        calendar_core.zone(tz)
        rows = body.get("windows")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 28:
            raise ValueError("Explicit bounded working windows required")
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"weekday", "start", "end"}:
                raise ValueError("Invalid working window")
            calendar_core.WorkingWindow(row["weekday"], wall_time.fromisoformat(row["start"]), wall_time.fromisoformat(row["end"]))
        if type(body.get("calendar_access")) is not bool:
            raise ValueError("Explicit simulated calendar access required")
        busy = body.get("simulated_busy", [])
        if not isinstance(busy, list) or len(busy) > 500:
            raise ValueError("Bounded simulated busy intervals required")
        for interval in busy:
            if not isinstance(interval, dict) or set(interval) != {"start", "end"}:
                raise ValueError("Invalid busy interval")
            calendar_core.Interval(interval["start"], interval["end"])
        settings = {"timezone": tz, "windows": json.loads(encode(rows)), "calendar_access": body["calendar_access"],
                    "simulated_busy": json.loads(encode(busy)), "source_ref": text(body.get("source_ref"), "Calendar preferences evidence", 500)}
        if party == "principal":
            doc["calendar_preferences"] = settings
            affected = doc["prospects"]
            self.cancel(db, doc)
        else:
            p["calendar_preferences"] = settings
            affected = [p]
            self.cancel(db, doc, p["id"])
        for prospect in affected:
            prospect.pop("calendar", None)
            if prospect.get("amendment", {}).get("status") == "pending":
                prospect["amendment"]["status"] = "stale"

    def request_calendar_exception(self, doc, p, body):
        state = self.state(doc, p["id"])
        core.check_action(state, "schedule", state["revision"])
        party = body.get("party")
        if party not in {"principal", "recipient"}:
            raise ValueError("Specify whose working hours require an exception")
        interval = calendar_core.Interval(body.get("start"), body.get("end"))
        if interval.start.timestamp() <= self.now(doc):
            raise ValueError("Exception must concern a future interval")
        proposal = {"party": party, "start": interval.start.isoformat(), "end": interval.end.isoformat(),
                    "source_ref": text(body.get("source_ref"), "Exception request evidence", 500),
                    "revision": state["revision"], "status": "needs_owner_agreement", "availability_verified": False}
        p["calendar_exception"] = proposal
        # Requesting an exception never widens working hours or authorizes booking.
        self.event(doc, "calendar_exception_requested", prospect_id=p["id"], **proposal)

    def calendar_reader(self, doc, p, timezone_name=None):
        state = self.state(doc, p["id"])
        people, bindings, busy_by_id = [], {}, {}
        for party in ("principal", "recipient"):
            settings = self.calendar_settings(doc, p, party, timezone_name if party == "recipient" else None)
            windows = tuple(calendar_core.WorkingWindow(w["weekday"], wall_time.fromisoformat(w["start"]), wall_time.fromisoformat(w["end"])) for w in settings["windows"])
            person = calendar_core.Participant(state["identity"][party + "_id"], settings["timezone"], windows)
            people.append(person)
            if settings["calendar_access"]:
                bindings[person.id] = {"account_id": "sim:" + doc["account_id"], "calendar_ids": [person.id]}
                busy_by_id[person.id] = settings["simulated_busy"] + p.get("simulated_busy", [])
        def read(**kwargs):
            return {"account_id": kwargs["account_id"], "fetched_at": self.stamp(doc),
                    "source_ref": "simulation:calendar-read", "payload": {"timeMin": kwargs["start"], "timeMax": kwargs["end"],
                    "calendars": {cid: {"busy": busy_by_id[cid]} for cid in kwargs["calendar_ids"]}}}
        return people, bindings, read

    def propose(self, doc, p, body):
        state = self.state(doc, p["id"])
        self.eligible(doc, p)
        core.check_action(state, "schedule", state["revision"])
        if self.mode != "simulation":
            raise ValueError("Live calendar binding and read-back have not been configured")
        tz = body.get("timezone", doc["brief"]["timezone"])
        people, bindings, read = self.calendar_reader(doc, p, tz)
        result = calendar_core.read_and_propose(body.get("start"), body.get("end"), people, bindings, read,
                 now=lambda: datetime.fromtimestamp(self.now(doc), timezone.utc), limit=8, booking_link=doc["brief"].get("booking_link") or None)
        if result["status"] == "needs_exception":
            p["calendar_exception"] = {"status": "needs_owner_agreement", "availability_verified": False,
                                       "start": body.get("start"), "end": body.get("end"), "revision": state["revision"],
                                       "reason": "No overlap within configured working hours and known availability"}
        p["calendar"] = {**result, "timezone": tz, "simulated": True,
                         "valid_until": self.now(doc) + 120, "revision": state["revision"]}

    def book(self, doc, p, body):
        proposal = p.get("calendar", {})
        slot = next((s for s in proposal.get("slots", []) if s["start"] == body.get("start") and s["end"] == body.get("end")), None)
        if not slot or self.now(doc) > proposal.get("valid_until", 0):
            raise ValueError("Select a fresh proposed slot")
        if self.state(doc, p["id"])["revision"] != proposal["revision"]:
            raise ValueError("New conversation evidence invalidated the calendar proposal")
        people, bindings, read = self.calendar_reader(doc, p)
        calendar_core.recheck_booking(slot, people, bindings, read, now=lambda: datetime.fromtimestamp(self.now(doc), timezone.utc))
        request = calendar_core.stage_booking(slot, ["principal@simulation.invalid", "recipient@simulation.invalid"],
                                              doc["brief"]["principal_name"] + " + " + p["name"])
        self.stage(doc, p, "booking", f"Meeting: {slot['start']} to {slot['end']}",
                   {"slot": slot, "request": request, "request_sha": digest(request["proposal"]), "valid_until": proposal["valid_until"]})

    def amendment_context(self, doc, p):
        if self.mode != "simulation":
            raise ValueError("Calendar amendments are simulation only")
        self.eligible(doc, p)
        state = self.state(doc, p["id"])
        if doc["paused"] or state["status"] in {"unconfigured", "human_owned", "opted_out", "declined", "reconcile", "attended"}:
            raise ValueError("Conversation cannot amend a meeting in its current state")
        if (not state.get("booking_id") or not p.get("booking")
                or p["booking"].get("id") != state["booking_id"]
                or p["booking"].get("status") != "confirmed"):
            raise ValueError("A verified confirmed booking is required")
        if state.get("reply_required") or not state.get("scheduling_agreed") or not state.get("booking_agreed"):
            raise ValueError("Acknowledge replies and verify both parties' scheduling and booking agreement")
        return state

    def amendment_readers(self, doc, p, event=None):
        booking = p["booking"] if event is None else event
        account = "sim:" + doc["account_id"]
        calendar = "sim-calendar:" + p["id"]
        emails = [a["email"] for a in booking["attendees"]]
        people, bindings, busy_rows = [], {}, []
        roles = {"principal@simulation.invalid": "principal", "recipient@simulation.invalid": "recipient"}
        for email in emails:
            settings = self.calendar_settings(doc, p, roles[email])
            windows = tuple(calendar_core.WorkingWindow(w["weekday"], wall_time.fromisoformat(w["start"]), wall_time.fromisoformat(w["end"])) for w in settings["windows"])
            people.append(calendar_core.Participant(email, settings["timezone"], windows))
            if settings["calendar_access"]:
                bindings[email] = {"account_id": account, "calendar_ids": [calendar]}
            busy_rows.extend(settings["simulated_busy"])
        busy_rows.extend(p.get("simulated_busy", []))
        def read_event(**kwargs):
            return {"account_id": account, "calendar_id": calendar, "fetched_at": self.stamp(doc),
                    "source_ref": "simulation:calendar-event-read", "event": json.loads(encode(booking))}
        def read_busy(**kwargs):
            return {"account_id": account, "fetched_at": self.stamp(doc), "source_ref": "simulation:calendar-busy-read",
                    "payload": {"timeMin": kwargs["start"], "timeMax": kwargs["end"],
                                "calendars": {calendar: {"busy": busy_rows}}}}
        return account, calendar, people, bindings, read_event, read_busy

    def prepare_amendment(self, doc, p, body):
        state = self.amendment_context(doc, p)
        source = text(body.get("source_ref"), "Amendment agreement evidence", 500)
        operation = body.get("operation")
        if operation == "cancel" and (body.get("start") is not None or body.get("end") is not None):
            raise ValueError("Cancellation cannot select another time")
        slot = {"start": body.get("start"), "end": body.get("end")} if operation == "reschedule" else None
        account, calendar, people, bindings, read_event, read_busy = self.amendment_readers(doc, p)
        proposal = amendment_core.prepare_amendment({**p["booking"], "account_id": account, "calendar_id": calendar},
            operation, slot, participants=people, bindings=bindings, read_event=read_event, read_freebusy=read_busy,
            now=lambda: datetime.fromtimestamp(self.now(doc), timezone.utc))
        # The reviewed card binds the evidence and conversation as well as provider payload.
        card = {"proposal": proposal, "revision": state["revision"], "brief_revision": doc["brief_revision"],
                "source_ref": source, "account_id": doc["account_id"], "prospect_id": p["id"]}
        p["amendment"] = {**card, "digest": digest(card), "status": "pending"}

    def approve_amendment(self, db, doc, p, supplied_digest):
        amendment = p.get("amendment")
        if not amendment or amendment.get("status") != "pending":
            raise ValueError("No pending amendment; an approved card cannot execute twice")
        card = {k: v for k, v in amendment.items() if k not in {"digest", "status"}}
        if (supplied_digest != amendment.get("digest") or digest(card) != supplied_digest
                or card["account_id"] != doc["account_id"] or card["prospect_id"] != p["id"]):
            raise ValueError("Amendment digest or ownership mismatch")
        state = self.amendment_context(doc, p)
        if card["revision"] != state["revision"] or card["brief_revision"] != doc["brief_revision"]:
            raise ValueError("New evidence invalidated this amendment")
        _, _, _, _, read_event, read_busy = self.amendment_readers(doc, p)
        now = lambda: datetime.fromtimestamp(self.now(doc), timezone.utc)
        proposal = card["proposal"]
        amendment_core.recheck_amendment(proposal, read_event=read_event, read_freebusy=read_busy, now=now)
        # A simulated provider result is verified through the same callback contract.
        # Preserve event metadata; only the frozen approved fields may change.
        candidate = {**p["booking"], **proposal["after"]}
        _, _, _, _, read_after, _ = self.amendment_readers(doc, p, candidate)
        if not amendment_core.verify_amendment(proposal, read_event=read_after, now=now):
            raise ValueError("Calendar amendment read-back differs from approved request")
        p["booking"] = candidate
        p["calendar_status"] = "cancelled" if proposal["operation"] == "cancel" else "rescheduled"
        amendment["status"] = "verified"
        self.cancel(db, doc, p["id"])
        self.event(doc, "calendar_amendment_verified", prospect_id=p["id"], operation=proposal["operation"],
                   digest=supplied_digest, booking_id=candidate["id"], source_ref=card["source_ref"], simulated=True)

    def process_one(self, account):
        account = account_id(account)
        with self.store.transaction() as db:
            doc = self.store.load(db, account, self.mode)
            if doc["paused"]:
                return
            now = self.now(doc)
            row = db.execute("SELECT * FROM jobs WHERE account=? AND ((state='queued' AND due<=?) OR (state='running' AND lease_until<=?)) ORDER BY due LIMIT 1", (account, now, time.time())).fetchone()
            if row is None:
                return
            job = dict(row)
            payload = json.loads(job["payload"])
            if job["attempts"] >= MAX_ATTEMPTS:
                db.execute("UPDATE jobs SET state='failed',error='Retry limit reached' WHERE id=?", (job["id"],))
                return
            if payload["brief_revision"] != doc["brief_revision"]:
                db.execute("UPDATE jobs SET state='cancelled' WHERE id=?", (job["id"],))
                return
            if job["kind"] in {"turn", "research", "research_phone"}:
                p = self.prospect(doc, payload["prospect_id"])
                state = self.state(doc, p["id"])
                if state["revision"] != payload["revision"]:
                    db.execute("UPDATE jobs SET state='cancelled' WHERE id=?", (job["id"],))
                    return
                if job["kind"] in {"research", "research_phone"} and digest(p) != payload["prospect_digest"]:
                    db.execute("UPDATE jobs SET state='cancelled' WHERE id=?", (job["id"],))
                    return
                config = (self.discovery if job["kind"] == "research_phone" else self.models).get(account, {"provider": "fixture"} if self.mode == "simulation" else {})
            else:
                p = None
                config = {"provider": "fixture"} if payload["source"] == "fixture" else self.discovery.get(account, {})
            if not config or (self.mode == "live" and config.get("provider") == "fixture"):
                db.execute("UPDATE jobs SET state='failed',error='Account provider is not configured' WHERE id=?", (job["id"],))
                return
            reserve = 0 if config.get("provider") == "fixture" else number(config.get("max_cost_usd"), "Per-call maximum")
            if config.get("provider") != "fixture" and reserve <= 0:
                raise ValueError("Paid providers require a positive per-call maximum")
            spent = sum(e["charged_usd"] for e in doc["expenses"])
            if spent + reserve > doc["brief"]["budget_usd"]:
                db.execute("UPDATE jobs SET state='failed',error='Budget exhausted; review spend before retry' WHERE id=?", (job["id"],))
                return
            attempt = job["attempts"] + 1
            lease = time.time() + LEASE_SECONDS
            db.execute("UPDATE jobs SET state='running',lease_until=?,attempts=?,error=NULL WHERE id=?", (lease, attempt, job["id"]))
            charge_id = f"{job['id']}:{attempt}"
            doc["expenses"].append({"id": charge_id, "charged_usd": reserve, "settled": False, "provider": config.get("provider")})
            self.store.save(db, doc)
            brief = doc["brief"]
            messages = [m for m in doc["messages"] if p and m["prospect_id"] == p["id"]][-30:]
        try:
            result = (providers.discover(brief, payload["limit"], config) if job["kind"] == "discover"
                      else research.assess(brief, p, config) if job["kind"] == "research"
                      else enrichment.enrich(p, config) if job["kind"] == "research_phone"
                      else providers.generate(brief, p, messages, config))
            with self.store.transaction() as db:
                doc = self.store.load(db, account, self.mode)
                latest = db.execute("SELECT state,attempts FROM jobs WHERE id=?", (job["id"],)).fetchone()
                expense = next(e for e in doc["expenses"] if e["id"] == charge_id)
                actual = result.get("cost_usd")
                if actual is not None:
                    expense.update(charged_usd=number(actual, "Provider cost"), settled=True)
                stale = (latest["state"] != "running" or latest["attempts"] != attempt or doc["brief_revision"] != payload["brief_revision"] or doc["paused"])
                if p:
                    stale |= self.state(doc, p["id"])["revision"] != payload["revision"]
                    if "prospect_digest" in payload:
                        stale |= digest(self.prospect(doc, p["id"])) != payload["prospect_digest"]
                if stale:
                    if latest["attempts"] == attempt:
                        db.execute("UPDATE jobs SET state='cancelled',lease_until=NULL WHERE id=?", (job["id"],))
                    self.event(doc, "stale_generation_discarded", job_id=job["id"])
                elif job["kind"] in {"research", "research_phone"}:
                    p = self.prospect(doc, p["id"])
                    errors = result.get("errors", [])
                    if not isinstance(errors, list) or any(not isinstance(error, str) for error in errors):
                        raise ValueError("Malformed research errors")
                    if job["kind"] == "research":
                        p["research"] = {**result, "evidence": research.evidence_for(p), "brief_revision": doc["brief_revision"], "observed_at": self.stamp(doc)}
                        verdict = result["verdict"]
                        if verdict not in {"qualified", "rejected", "needs_review"}:
                            raise ValueError("Unknown research verdict")
                        p["qualification"] = verdict if verdict != "needs_review" else "pending"
                        p["qualification_reason"] = result["rationale"]
                        p["status"] = verdict
                        p["qualified_brief_revision"] = doc["brief_revision"]
                        if self.state(doc, p["id"])["status"] == "unconfigured":
                            p["brief_stale"] = False
                        if verdict == "rejected":
                            self.cancel(db, doc, p["id"])
                    else:
                        p["phone_research"] = {**result, "observed_at": self.stamp(doc)}
                        # Provider phone is a candidate route. Only the existing human
                        # enrichment command can attest attribution and change identity.
                        p["candidate_phone"] = result.get("phone")
                        if p.get("phone_status") != "operator_verified":
                            p["phone_status"] = result["phone_status"]
                    self.event(doc, "research_completed", prospect_id=p["id"], kind_of_research=job["kind"], errors=errors)
                    db.execute("UPDATE jobs SET state=?,lease_until=NULL,error=? WHERE id=?", ("needs_review" if errors else "completed", " | ".join(errors)[:1000] or None, job["id"]))
                    if errors:
                        doc["paused"] = True
                        self.cancel(db, doc)
                elif job["kind"] == "discover":
                    self.add_prospects(doc, result, payload)
                    errors = result.get("errors", [])
                    db.execute("UPDATE jobs SET state=?,lease_until=NULL,error=? WHERE id=?", ("needs_review" if errors else "completed", " | ".join(errors)[:1000] or None, job["id"]))
                    if errors:
                        doc["paused"] = True
                        self.cancel(db, doc)
                else:
                    p = self.prospect(doc, p["id"])
                    intent = result.get("intent", "review")
                    if intent in {"optout", "decline"}:
                        state = self.state(doc, p["id"])
                        self.observe(doc, p["id"], "opt_out" if intent == "optout" else "declined", {"party_id": state["identity"]["recipient_id"]}, source="model:conservative-stop")
                        self.cancel(db, doc, p["id"])
                    else:
                        decision = self.stage(doc, p, payload["purpose"], result["text"])
                        if self.mode == "simulation" and decision["status"] == "pending":
                            self.approve(doc, decision)
                        self.event(doc, "agent_turn", prospect_id=p["id"], intent=intent, provider=result.get("provider"),
                                   evidence=[p["source"]], needs_review=intent in {"review", "interest", "scheduling"})
                    db.execute("UPDATE jobs SET state='completed',lease_until=NULL WHERE id=? AND attempts=?", (job["id"], attempt))
                if sum(e["charged_usd"] for e in doc["expenses"]) > doc["brief"]["budget_usd"]:
                    doc["paused"] = True
                    self.cancel(db, doc)
                    self.event(doc, "budget_exceeded", job_id=job["id"])
                self.store.save(db, doc)
        except Exception:
            with self.store.transaction() as db:
                db.execute("UPDATE jobs SET state=?,due=?,lease_until=NULL,error=? WHERE id=? AND state='running' AND attempts=?",
                           ("failed" if attempt >= MAX_ATTEMPTS else "queued", self.now(doc) + min(60 * attempt, 180),
                            "Provider or validation failed; inspect configuration/evidence. Reserved cost retained.", job["id"], attempt))

    def add_prospects(self, doc, result, payload):
        errors = result.get("errors", [])
        if not isinstance(errors, list) or any(not isinstance(error, str) for error in errors):
            raise ValueError("Malformed discovery errors")
        rows = result.get("prospects")
        if not isinstance(rows, list) or len(rows) > payload["limit"]:
            raise ValueError("Discovery returned an invalid page")
        for row in rows:
            name = text(row.get("name"), "Name", 200)
            company = text(row.get("company"), "Company", 300, optional=True)
            source = text(row.get("source"), "Source", 1000)
            profile = row.get("profile_url") or None
            if profile is not None:
                from urllib.parse import urlsplit
                profile = text(profile, "Profile URL", 500)
                parsed = urlsplit(profile)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("Profile URL must be public HTTP(S)")
            key = digest([profile or name.casefold(), company.casefold()])
            if any(p["identity_key"] == key for p in doc["prospects"]):
                continue
            doc["prospects"].append({"id": str(uuid4()), "identity_key": key, "name": name, "company": company,
                                     "role": text(row.get("role"), "Role", optional=True), "domain": text(row.get("domain"), "Domain", 253, optional=True), "phone": None,
                                     "source": source, "profile_url": profile,
                                     "fit": text(row.get("fit"), "Fit", 2000, optional=True) or "Research and qualification review required.",
                                     "status": "discovered", "qualification": "pending", "phone_status": "unresolved",
                                     "fixture": payload["source"] == "fixture", "brief_stale": False,
                                     "discovery_errors": list(errors), "created_at": self.stamp(doc)})
        self.event(doc, "discovery_completed", provider=result.get("provider"), count=len(rows), errors=errors, partial=bool(errors), simulated=payload["source"] == "fixture")
