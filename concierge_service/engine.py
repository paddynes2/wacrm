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
from . import providers

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
                "brief_revision": doc["brief_revision"], "prospects": ps, "messages": doc["messages"],
                "decisions": doc["decisions"], "jobs": jobs, "events": doc["events"][-200:],
                "paused": doc["paused"], "readiness": readiness,
                "metrics": {"discovered": len(ps), "qualified": sum(p.get("qualification") == "qualified" for p in ps),
                            "reachable": sum(p.get("phone_status") == "operator_verified" for p in ps),
                            "approached": len({m["prospect_id"] for m in doc["messages"] if m.get("purpose") == "approach"}),
                            "introduced": sum(p["conversation"].get("introduced", False) for p in ps),
                            "booked": sum(bool(p["conversation"].get("booking_id")) for p in ps),
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
        fields = {"save_brief": {"brief"}, "discover": {"source", "limit"},
                  "qualify": {"prospect_id", "verdict", "reason"}, "enrich": {"prospect_id", "phone", "source_ref"},
                  "start": {"prospect_id"}, "reply": {"prospect_id", "text", "message_id"},
                  "retry_job": {"job_id"}, "new_pursuit": {"prospect_id"}, "process": set(), "approve": {"decision_id"}, "discard": {"decision_id"},
                  "takeover": {"prospect_id"}, "resume": {"prospect_id"},
                  "consent": {"prospect_id", "party", "scope", "source_ref"},
                  "introduce": {"prospect_id"}, "propose": {"prospect_id", "start", "end", "timezone"},
                  "book": {"prospect_id", "start", "end"}, "review": {"prospect_id", "useful", "minutes", "note"},
                  "readiness": set(), "pause": set(), "unpause": set(), "advance": {"seconds"},
                  "followup": {"prospect_id", "seconds"}, "link_contact": {"prospect_id", "contact"},
                  "attended": {"prospect_id", "source_ref"}, "manual_reply": {"prospect_id", "text"}}
        if name not in fields or set(body) - fields[name] - {"command", "attested_by"}:
            raise ValueError("Unknown command or fields")
        if name == "process":
            self.process_one(account)
            return self.report(account)
        if name == "readiness":
            client = self.unipile.get(account)
            if client:
                result = client.verify_account()
                with self.store.transaction() as db:
                    doc = self.store.load(db, account, self.mode)
                    doc["connections"] = {"verified_at": self.stamp(doc), "account_id": client.account_id}
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
                if name == "new_pursuit":
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
                elif name == "propose":
                    self.propose(doc, p, body)
                elif name == "book":
                    self.book(doc, p, body)
                elif name == "review":
                    if type(body.get("useful")) is not bool:
                        raise ValueError("Usefulness must be true or false")
                    review = {"prospect_id": pid, "useful": body["useful"], "minutes": number(body.get("minutes"), "Minutes"),
                              "note": text(body.get("note"), "Review note", optional=True)}
                    doc["reviews"] = [r for r in doc["reviews"] if r["prospect_id"] != pid] + [review]
                elif name == "attended":
                    if not state.get("booking_id"):
                        raise ValueError("Attendance requires a verified booking")
                    self.observe(doc, pid, "meeting_attended", {"event_id": state["booking_id"]}, source=text(body.get("source_ref"), "Attendance evidence", 500))
                elif name == "followup":
                    if state["status"] in {"unconfigured", "human_owned", "opted_out", "declined", "reconcile"} or state.get("latest_inbound"):
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

    def calendar_reader(self, doc, p, timezone_name=None):
        tz = timezone_name or p.get("calendar", {}).get("timezone", doc["brief"]["timezone"])
        state = self.state(doc, p["id"])
        windows = tuple(calendar_core.WorkingWindow(d, wall_time(9), wall_time(17)) for d in range(5))
        people = [calendar_core.Participant(state["identity"][party + "_id"], zone, windows)
                  for party, zone in [("principal", doc["brief"]["timezone"]), ("recipient", tz)]]
        bindings = {person.id: {"account_id": "sim:" + doc["account_id"], "calendar_ids": [person.id]} for person in people}
        def read(**kwargs):
            return {"account_id": kwargs["account_id"], "fetched_at": self.stamp(doc),
                    "source_ref": "simulation:calendar-read", "payload": {"timeMin": kwargs["start"], "timeMax": kwargs["end"],
                    "calendars": {cid: {"busy": p.get("simulated_busy", [])} for cid in kwargs["calendar_ids"]}}}
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
                 now=lambda: datetime.fromtimestamp(self.now(doc), timezone.utc), limit=8)
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
            if job["kind"] == "turn":
                p = self.prospect(doc, payload["prospect_id"])
                state = self.state(doc, p["id"])
                if state["revision"] != payload["revision"]:
                    db.execute("UPDATE jobs SET state='cancelled' WHERE id=?", (job["id"],))
                    return
                config = self.models.get(account, {"provider": "fixture"} if self.mode == "simulation" else {})
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
                if stale:
                    if latest["attempts"] == attempt:
                        db.execute("UPDATE jobs SET state='cancelled',lease_until=NULL WHERE id=?", (job["id"],))
                    self.event(doc, "stale_generation_discarded", job_id=job["id"])
                elif job["kind"] == "discover":
                    self.add_prospects(doc, result, payload)
                    db.execute("UPDATE jobs SET state='completed',lease_until=NULL WHERE id=?", (job["id"],))
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
        rows = result.get("prospects")
        if not isinstance(rows, list) or len(rows) > payload["limit"]:
            raise ValueError("Discovery returned an invalid page")
        for row in rows:
            name = text(row.get("name"), "Name", 200)
            company = text(row.get("company"), "Company", 300, optional=True)
            source = text(row.get("source"), "Source", 1000)
            profile = row.get("profile_url")
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
                                     "role": text(row.get("role"), "Role", optional=True), "phone": None,
                                     "source": source, "profile_url": profile,
                                     "fit": text(row.get("fit"), "Fit", 2000, optional=True) or "Research and qualification review required.",
                                     "status": "discovered", "qualification": "pending", "phone_status": "unresolved",
                                     "fixture": payload["source"] == "fixture", "brief_stale": False,
                                     "created_at": self.stamp(doc)})
        self.event(doc, "discovery_completed", provider=result.get("provider"), count=len(rows), simulated=payload["source"] == "fixture")
