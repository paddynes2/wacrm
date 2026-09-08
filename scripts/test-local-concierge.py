"""Exercise real local WACRM -> private Fleet bridge -> Supabase with fresh fixtures.

Requires the local launcher already running. Creates uniquely named test users,
accounts and contacts; never deletes existing data. Every HTTP destination is
loopback and redirects are disabled. Credentials stay in process memory.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import uuid

import requests

ROOT = Path(__file__).resolve().parents[1]
WEB = "http://127.0.0.1:8316"
TIMEOUT = 60
COUNT = 0


def local_request(session, method, url, **kwargs):
    global COUNT
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise AssertionError("Integration test refuses every non-loopback HTTP destination")
    if parsed.username or parsed.password or parsed.port not in {54321, 8316}:
        raise AssertionError("Unexpected local service destination")
    COUNT += 1
    return session.request(method, url, timeout=TIMEOUT, allow_redirects=False, **kwargs)


def checked(response, expected=200):
    if response.status_code != expected:
        # Never print raw authentication responses or headers (they contain tokens).
        try:
            value = response.json()
            reason = value.get("error") or value.get("detail") or "response rejected"
            reason = str(reason)[:350]
        except (ValueError, AttributeError):
            reason = "non-JSON response"
        raise AssertionError(f"{response.request.method} {urlparse(response.url).path}: "
                             f"expected {expected}, received {response.status_code}: {reason}")
    return response.json() if response.content else None


def local_config():
    npx = shutil.which("npx.cmd" if os.name == "nt" else "npx")
    if not npx:
        raise AssertionError("npm/npx is required")
    result = subprocess.run([npx, "supabase", "status", "-o", "json"], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise AssertionError("Local Supabase status failed; start the local services first")
    config = json.loads(result.stdout)
    parsed = urlparse(config["API_URL"])
    if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port != 54321:
        raise AssertionError("Supabase must be the local instance on 54321")
    return config


class User:
    def __init__(self, config, label):
        self.config = config
        self.base = config["API_URL"].rstrip("/")
        self.admin = requests.Session()
        self.admin.headers.update({"apikey": config["SERVICE_ROLE_KEY"],
                                   "Authorization": "Bearer " + config["SERVICE_ROLE_KEY"]})
        email = f"test-{label}-{uuid.uuid4().hex}@concierge.integration.invalid"
        password = secrets.token_urlsafe(32)
        created = checked(local_request(self.admin, "POST", self.base + "/auth/v1/admin/users", json={
            "email": email, "password": password, "email_confirm": True,
            "user_metadata": {"full_name": "Concierge integration " + label}}))
        self.id = created["id"]
        anon = requests.Session()
        anon.headers.update({"apikey": config["ANON_KEY"]})
        session = checked(local_request(anon, "POST", self.base + "/auth/v1/token?grant_type=password",
                                        json={"email": email, "password": password}))
        self.rest = requests.Session()
        self.rest.headers.update({"apikey": config["ANON_KEY"], "Authorization": "Bearer " + session["access_token"],
                                  "Prefer": "return=representation"})
        profile = checked(local_request(self.rest, "GET", self.base + f"/rest/v1/profiles?user_id=eq.{self.id}&select=account_id,account_role"))
        assert len(profile) == 1 and profile[0]["account_role"] == "owner", "Signup did not create canonical owner profile"
        self.account_id = profile[0]["account_id"]
        self.web = requests.Session()
        self.web.headers.update({"Origin": WEB, "Referer": WEB + "/concierge"})
        # This is the real @supabase/ssr cookie format, not a route/auth bypass.
        if "expires_at" not in session:
            session["expires_at"] = int(datetime.now(timezone.utc).timestamp()) + session["expires_in"]
        encoded = "base64-" + base64.urlsafe_b64encode(json.dumps(session, separators=(",", ":")).encode()).decode().rstrip("=")
        name = "sb-" + urlparse(self.base).hostname.split(".")[0] + "-auth-token"
        chunks = [encoded[i:i + 3180] for i in range(0, len(encoded), 3180)]
        for index, chunk in enumerate(chunks):
            self.web.cookies.set(name if len(chunks) == 1 else name + f".{index}", chunk, domain="127.0.0.1", path="/")

    def contact(self, label="Bond"):
        # Valid E164 test data, no provider is ever contacted in simulation.
        phone = "+2782" + str(secrets.randbelow(10_000_000)).zfill(7)
        return checked(local_request(self.rest, "POST", self.base + "/rest/v1/contacts", json={
            "user_id": self.id, "account_id": self.account_id, "name": label,
            "phone": phone, "email": "recipient@simulation.invalid", "company": "Integration Test Co"}), 201)[0]

    def get(self):
        return checked(local_request(self.web, "GET", WEB + "/api/concierge"))

    def action(self, action, contact=None, report=None, expected=200, **extra):
        body = {"action": action, **extra}
        if contact:
            body["contact_id"] = contact["id"]
        if report and contact:
            state = next(p for p in report["pursuits"] if p["pursuit_id"] == "wacrm:" + contact["id"])
            body.setdefault("revision", state["revision"])
            body.setdefault("pursuit_id", state["pursuit_id"])
        value = checked(local_request(self.web, "POST", WEB + "/api/concierge", json=body), expected)
        if expected == 200:
            assert value.get("mode") == "simulation" and value.get("simulated") is True, "Real WACRM route is not in simulation mode"
            assert "crm_warning" not in value, "CRM mirror failed: " + str(value.get("crm_warning"))
        return value

    def approve(self, contact, staged):
        return self.action("approve", contact, staged, decision_id=staged["result"]["decision"]["id"])

    def inbox(self, contact):
        conversations = checked(local_request(self.rest, "GET", self.base +
            f"/rest/v1/conversations?contact_id=eq.{contact['id']}&select=id,account_id"))
        assert len(conversations) == 1 and conversations[0]["account_id"] == self.account_id
        return checked(local_request(self.rest, "GET", self.base +
            f"/rest/v1/messages?conversation_id=eq.{conversations[0]['id']}&select=message_id,content_text,sender_type,status"))


def main():
    config = local_config()
    owner = User(config, "owner")
    initial = owner.get()
    assert initial["mode"] == "simulation" and initial["report"] is None
    contact = owner.contact()
    principal_phone = "+2781" + str(secrets.randbelow(10_000_000)).zfill(7)
    owner.action("setup", principal_name="Integration Principal", principal_phone=principal_phone,
                 offer="We implement practical AI workflows.", timezone="Africa/Johannesburg")
    report = owner.action("start", contact, fit="Your owner-independence focus complements our workflow implementation.",
                          source_ref="integration:operator-verified", profile_url="https://example.invalid/contact")
    assert "AI assistant" in report["result"]["draft"]
    report = owner.action("consent", contact, report, party="recipient", scope="contact", source_ref="integration:explicit-contact-consent")
    staged = owner.action("draft", contact, report)
    assert not staged["direct_messages"], "Draft was treated as sent"
    report = owner.approve(contact, staged)
    assert len(owner.inbox(contact)) == 1
    owner.action("approve", contact, report, decision_id=staged["result"]["decision"]["id"], expected=409)
    assert len(owner.inbox(contact)) == 1, "Duplicate approval mirrored a second message"
    report = owner.action("simulate_reply", contact, report, text="Yes please introduce us")
    assert len(owner.inbox(contact)) == 2
    for scope in ("introduction", "group", "scheduling", "booking"):
        for party in ("principal", "recipient"):
            report = owner.action("consent", contact, report, scope=scope, party=party, source_ref="integration:explicit-party-agreement")
    owner.action("introduce", contact, report, expected=409)
    report = owner.approve(contact, owner.action("draft", contact, report))
    report = owner.approve(contact, owner.action("introduce", contact, report))
    state = next(p for p in report["pursuits"] if p["pursuit_id"] == "wacrm:" + contact["id"])
    assert state["introduced"] and not state["reply_required"]
    messages = owner.inbox(contact)
    assert len(messages) == 3, "Group introduction leaked into native direct inbox"
    assert all(m["content_text"].startswith("[Simulation] ") and m["status"] == "sent" for m in messages)
    assert sorted(m["sender_type"] for m in messages) == ["bot", "bot", "customer"]
    horizon = datetime.now(timezone.utc) + timedelta(days=1)
    report = owner.action("propose", contact, report, start=horizon.isoformat(), end=(horizon + timedelta(days=7)).isoformat())
    assert report["result"]["status"] == "proposed"
    selected = report["result"]["slots"][0]
    slot = {"start": selected["start"], "end": selected["end"]}
    staged = owner.action("book", contact, report, slot=slot)
    report = owner.approve(contact, staged)
    state = next(p for p in report["pursuits"] if p["pursuit_id"] == "wacrm:" + contact["id"])
    assert state["status"] == "booked" and state["booking_id"].startswith("sim-event-")
    assert len(owner.inbox(contact)) == 3
    print("PASS: real authenticated API Boardy journey, calendar verification, three native direct messages; group excluded", flush=True)

    stopped = owner.contact("STOP test")
    report = owner.action("start", stopped)
    report = owner.action("consent", stopped, report, scope="contact", party="recipient", source_ref="integration:contact-agreement")
    staged = owner.action("draft", stopped, report)
    report = owner.action("simulate_reply", stopped, staged, text="STOP")
    owner.action("approve", stopped, report, decision_id=staged["result"]["decision"]["id"], expected=409)
    assert len(owner.inbox(stopped)) == 1 and owner.inbox(stopped)[0]["sender_type"] == "customer"

    foreign = User(config, "foreign")
    foreign_contact = foreign.contact()
    owner.action("start", foreign_contact, expected=404)
    assert checked(local_request(owner.rest, "GET", owner.base + f"/rest/v1/contacts?id=eq.{foreign_contact['id']}&select=id")) == []
    cross = local_request(owner.web, "POST", WEB + "/api/concierge", headers={"Origin": "http://foreign.invalid"},
                          json={"action": "start", "contact_id": contact["id"]})
    assert cross.status_code == 403, "Cross-origin mutation was accepted"

    viewer = User(config, "viewer")
    # Fixture-only local profile membership. No policies, auth configuration or
    # production accounts are modified; the actual RLS rules enforce this role.
    checked(local_request(viewer.admin, "PATCH", viewer.base + f"/rest/v1/profiles?user_id=eq.{viewer.id}",
                          headers={"Prefer": "return=representation"},
                          json={"account_id": owner.account_id, "account_role": "viewer"}))
    view = viewer.get()
    assert view["report"]["workspace"]["account_id"] == owner.account_id
    viewer.action("start", contact, expected=403)
    print("PASS: STOP cancellation, foreign-account RLS isolation, CSRF refusal, viewer read-only access", flush=True)
    print(f"PASS: {COUNT} loopback HTTP requests; unique test fixtures retained; no live sends or secret output", flush=True)


if __name__ == "__main__":
    main()
