"""Real local acceptance for prospect imports, draft operations and role boundaries.

Requires scripts/local-concierge.py running with the current bridge. Creates only
unique local test fixtures. Reuses the loopback-only, redirect-refusing HTTP helper.
Never approves any decision, sends a message or exposes credentials.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import secrets

HELPER = Path(__file__).with_name("test-local-concierge.py")
SPEC = importlib.util.spec_from_file_location("local_concierge_acceptance", HELPER)
assert SPEC and SPEC.loader
local = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(local)


def request(user, path, *, body=None, expected=200, method=None, **kwargs):
    return local.checked(local.local_request(user.web, method or ("POST" if body is not None else "GET"),
                         local.WEB + "/api/concierge" + path,
                         **({"json": body} if body is not None else {}), **kwargs), expected)


def operation(user, command, expected=200, **fields):
    return request(user, "/operations", body={"command": command, **fields}, expected=expected)


def main():
    config = local.local_config()
    owner = local.User(config, "operations-owner")
    assert owner.get()["mode"] == "simulation", "Acceptance refuses a live workspace"
    owner.action("setup", principal_name="Operations Test Principal",
                 principal_phone="+2781" + str(secrets.randbelow(10_000_000)).zfill(7),
                 offer="We implement practical workflow improvements.", timezone="Africa/Johannesburg")
    readiness = request(owner, "/readiness")
    assert readiness["mode"] == "simulation" and readiness["live_ready"] is False
    assert readiness["service"]["status"] == "available" and readiness["brief"]["configured"]
    assert "apiKey" not in readiness and "token" not in readiness

    phone = "+2782" + str(secrets.randbelow(10_000_000)).zfill(7)
    csv = ("name,phone,email,company,source,profile_url,fit\n"
           f"Operations Prospect,{phone},prospect@simulation.invalid,Test Co,operator research,https://example.invalid/profile,Complementary workflow expertise\n")
    preview = request(owner, "/prospects", body={"action": "preview", "csv": csv})
    assert len(preview["rows"]) == 1 and not preview["rows"][0]["errors"]
    row = preview["rows"][0]["row"]
    imported = request(owner, "/prospects", body={"action": "import", "csv": csv, "selected_rows": [row]})
    assert imported["results"][0]["status"] == "imported"
    contact_id = imported["results"][0]["contact_id"]
    retried = request(owner, "/prospects", body={"action": "import", "csv": csv, "selected_rows": [row]})
    assert retried["results"][0]["status"] == "already_imported"
    assert retried["results"][0]["contact_id"] == contact_id
    preview_again = request(owner, "/prospects", body={"action": "preview", "csv": csv})
    assert preview_again["rows"][0]["duplicate"] and preview_again["rows"][0]["retryable"]
    contacts = local.checked(local.local_request(owner.rest, "GET", owner.base + f"/rest/v1/contacts?id=eq.{contact_id}&select=*"))
    assert len(contacts) == 1 and contacts[0]["account_id"] == owner.account_id
    contact = contacts[0]
    notes = local.checked(local.local_request(owner.rest, "GET", owner.base + f"/rest/v1/contact_notes?contact_id=eq.{contact_id}&select=id,note_text"))
    assert len(notes) == 1 and "does not establish permission" in notes[0]["note_text"]
    print("PASS: readiness is truthful; prospect preview/import/retry persists exactly one contact and source note", flush=True)

    report = owner.action("start", contact, fit="Complementary workflow expertise", source_ref="integration:operator-research")
    report = owner.action("consent", contact, report, scope="contact", party="recipient", source_ref="integration:explicit-simulation-consent")
    campaign = operation(owner, "create_campaign", name="Operations acceptance", steps=[
        {"delay_seconds": 0, "text": "Hi {{name}}, Chris here on behalf of {{principal_name}}. {{fit}} Open to an introduction?"},
        {"delay_seconds": 300, "text": "Following up on the introduction request."}], pace_seconds=300, daily_cap=10)["result"]
    enrollment = operation(owner, "enroll", campaign_id=campaign["id"], contact_ids=[contact_id])
    assert any(e["contact"] == contact_id and e["state"] == "active" for e in enrollment["enrollments"])
    tick = operation(owner, "tick")
    assert any(j["state"] == "done" for j in tick["jobs"]), "Worker did not stage a draft"
    report = owner.get()["report"]
    pending = [d for d in report["pending_decisions"] if d["action"].get("frozen", {}).get("text", "").startswith("Hi Operations Prospect")]
    assert len(pending) == 1, "Expected exactly one campaign draft for review"
    assert report["direct_messages"] == [], "Staged campaign draft was sent"
    operation(owner, "tick")
    assert len(owner.get()["report"]["pending_decisions"]) == len(report["pending_decisions"])
    report = owner.action("simulate_reply", contact, report, text="STOP")
    stopped = operation(owner, "tick")
    assert not any(j["state"] in {"queued", "leased"} for j in stopped["jobs"])
    assert all(e["state"] == "stopped" for e in stopped["enrollments"])
    assert all(m["direction"] == "inbound" for m in report["direct_messages"]), "An outgoing provider action occurred"
    print("PASS: campaign stages one reviewable draft, repeated tick does not duplicate it, STOP cancels future work", flush=True)

    foreign = local.User(config, "operations-foreign")
    foreign_contact = foreign.contact("Foreign operations prospect")
    operation(owner, "enroll", campaign_id=campaign["id"], contact_ids=[foreign_contact["id"]], expected=404)
    operation(owner, "watch", contact_id=foreign_contact["id"], enabled=True, chat_id="test-only", expected=404)
    request(owner, "/operations", body={"command": "tick"}, expected=403, headers={"Origin": "http://foreign.invalid"})
    viewer = local.User(config, "operations-viewer")
    local.checked(local.local_request(viewer.admin, "PATCH", viewer.base + f"/rest/v1/profiles?user_id=eq.{viewer.id}",
                  headers={"Prefer": "return=representation"}, json={"account_id": owner.account_id, "account_role": "viewer"}))
    assert request(viewer, "/operations")["draft_only"] is True
    operation(viewer, "tick", expected=403)
    request(viewer, "/prospects", body={"action": "preview", "csv": csv}, expected=403)
    print("PASS: foreign contacts refused, CSRF blocked, viewer can inspect but cannot mutate operations/imports", flush=True)
    print(f"PASS: {local.COUNT} loopback HTTP requests; unique fixtures retained; no live sends or secret output", flush=True)


if __name__ == "__main__":
    main()
