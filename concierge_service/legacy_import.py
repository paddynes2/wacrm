"""Read-only import of a legacy simulation ledger into a NEW product workspace.

Existing source files are never changed. Pending decisions are archived as evidence,
never copied into an executable queue. Inspection is the CLI default.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID

from .store import Store, account_id
from .concierge_core import state

MAX_FILE_BYTES = 20_000_000


def read(path):
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Legacy file exceeds import bound")
    return path.read_text(encoding="utf-8-sig")


def inspect(source, account):
    source = Path(source).resolve()
    account = account_id(account)
    index = json.loads(read(source / "wacrm-bridge" / "workspaces.json"))
    item = index.get(account)
    if not isinstance(item, dict) or item.get("mode") != "simulation":
        raise ValueError("Only an existing explicit simulation workspace can be imported")
    bot = item.get("bot_id", "")
    if not isinstance(bot, str) or not re.fullmatch(r"b[0-9a-z]{6,24}", bot):
        raise ValueError("Invalid legacy bot identity")
    path = source / "bots" / bot / "runs.jsonl"
    raw = read(path) if path.exists() else ""
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    observations = [state.validate(row["observation"]) for row in rows if row.get("kind") == "concierge_event"]
    if len(observations) > state.MAX_EVENTS:
        raise ValueError("Legacy ledger requires a separately reviewed large-history import")
    messages = [row["message"] for row in rows if row.get("kind") == "wacrm_message" and row.get("wacrm_account_id") == account]
    pursuits = sorted({e["pursuit_id"] for e in observations})
    states = [state.scoped_view(observations, pid) for pid in pursuits]
    for row in states:
        if not row["pursuit_id"].startswith("wacrm:"):
            raise ValueError("Legacy pursuit lacks a canonical WACRM contact reference")
        UUID(row["pursuit_id"][6:])
    return {"account": account, "item": item, "observations": observations, "messages": messages,
            "states": states, "source_sha256": hashlib.sha256(raw.encode()).hexdigest(), "source": str(source)}


def import_workspace(source, target, account):
    snapshot = inspect(source, account)
    store = Store(target)
    with store.transaction() as db:
        if db.execute("SELECT 1 FROM workspaces WHERE account=?", (account,)).fetchone():
            raise ValueError("Target already contains this account; refusing to overwrite")
        doc = store.load(db, account, "simulation")
        old = snapshot["item"]["brief"]
        doc["brief"] = {"principal_name": old["principal_name"], "offer": old["offer"],
                        "audience": "", "geography": "", "exclusions": "", "claims": "",
                        "timezone": old.get("timezone", "UTC"), "booking_link": old.get("booking_link") or "", "budget_usd": 0}
        doc["brief_revision"] = 1
        # The bridge used a transport account as reducer ownership. The standalone
        # reducer uses the CRM tenant; retain originals below for lossless audit.
        doc["observations"] = [{**event, "account_id": account} for event in snapshot["observations"]]
        for pid in {event["pursuit_id"] for event in doc["observations"]}:
            state.scoped_view(doc["observations"], pid)
        for row in snapshot["states"]:
            i = row["identity"]
            phone = "+" + i["recipient_id"].split("@")[0] if i["recipient_id"].endswith("@s.whatsapp.net") else None
            doc["prospects"].append({"id": row["pursuit_id"], "identity_key": "legacy:" + row["pursuit_id"],
                "contact_id": row["pursuit_id"][6:], "name": i["name"], "company": "", "role": "", "phone": phone,
                "source": "legacy:" + snapshot["source_sha256"], "profile_url": i["profile_url"], "fit": i["fit"],
                "status": "imported", "qualification": "pending", "phone_status": "unresolved", "fixture": True,
                "brief_stale": True, "created_at": snapshot["observations"][0]["occurred_at"]})
        for message in snapshot["messages"]:
            if message.get("simulated") is not True:
                raise ValueError("Simulation import contains an unlabelled/live message")
            pid = "wacrm:" + message["contact_id"]
            if not any(p["id"] == pid for p in doc["prospects"]):
                raise ValueError("Legacy message has no matching pursuit")
            doc["messages"].append({"id": message["id"], "prospect_id": pid, "direction": message["direction"],
                "text": message.get("text") or "[Legacy media: human review required]", "purpose": "legacy",
                "simulated": True, "created_at": message["occurred_at"]})
        doc["paused"] = True
        doc["legacy_imports"].append({"source_sha256": snapshot["source_sha256"], "source": snapshot["source"],
            "original_observations": snapshot["observations"], "account_mapping": "legacy transport ownership to this canonical CRM account",
            "observations": len(doc["observations"]), "messages": len(doc["messages"]), "pending_decisions": "not executable; retained in original source",
            "requires": "Complete and review the outbound brief and candidate qualification before starting new work"})
        store.save(db, doc)
    return {"account": account, "prospects": len(doc["prospects"]), "observations": len(doc["observations"]),
            "messages": len(doc["messages"]), "source_sha256": snapshot["source_sha256"], "paused": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--target")
    parser.add_argument("--import-workspace", action="store_true")
    args = parser.parse_args()
    if args.import_workspace:
        if not args.target:
            parser.error("--target required for import")
        result = import_workspace(args.source, args.target, args.account)
    else:
        item = inspect(args.source, args.account)
        result = {"account": item["account"], "prospects": len(item["states"]), "messages": len(item["messages"]),
                  "observations": len(item["observations"]), "source_sha256": item["source_sha256"], "read_only": True}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
