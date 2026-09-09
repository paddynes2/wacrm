"""Launch standalone dogfood against an existing local Supabase, never Fleet.

No seed/reset, credentials file changes, provider purchases or external sends.
The default model/discovery adapters are explicitly synthetic until configured.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
WEB_PORT, BRIDGE_PORT = 8316, 8317


def available(port):
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            raise SystemExit(f"Port {port} is occupied. Stop the identified old concierge launcher before switching; no process was replaced.")


def main():
    for port in (WEB_PORT, BRIDGE_PORT):
        available(port)
    npx = shutil.which("npx.cmd" if os.name == "nt" else "npx")
    node = shutil.which("node")
    if not npx or not node:
        raise SystemExit("Install the locked Node dependencies first.")
    status = subprocess.run([npx, "supabase", "status", "-o", "json"], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8")
    if status.returncode:
        raise SystemExit("Local Supabase is unavailable. Start the existing database; do not reset it.")
    config = json.loads(status.stdout)
    if urlsplit(config["API_URL"]).hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("This launcher only supports local Supabase")
    local = ROOT / ".local"
    local.mkdir(exist_ok=True)
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("FLEET_") or key in {"UNIPILE_API_KEY", "UNIPILE_ACCOUNT_ID", "WHATSAPP_ACCESS_TOKEN", "META_APP_SECRET"}:
            env.pop(key)
    env.update(NEXT_PUBLIC_SUPABASE_URL=config["API_URL"], NEXT_PUBLIC_SUPABASE_ANON_KEY=config["ANON_KEY"],
               SUPABASE_SERVICE_ROLE_KEY=config["SERVICE_ROLE_KEY"], NEXT_PUBLIC_SITE_URL=f"http://127.0.0.1:{WEB_PORT}",
               NEXT_PUBLIC_APP_LOCALE="en", NEXT_TELEMETRY_DISABLED="1", WACRM_STANDALONE="1",
               WACRM_BRIDGE_URL=f"http://127.0.0.1:{BRIDGE_PORT}", WACRM_BRIDGE_TOKEN=secrets.token_urlsafe(48),
               WACRM_BRIDGE_MODE="simulation", CONCIERGE_DB_PATH=str(local / "dogfood.sqlite3"), CONCIERGE_WORKER_ENABLED="1")
    children, logs = [], []
    try:
        for name, command in [
            ("dogfood-engine", [sys.executable, "-m", "uvicorn", "concierge_service.api:application", "--factory", "--host", "127.0.0.1", "--port", str(BRIDGE_PORT)]),
            ("dogfood-web", [node, str(ROOT / "node_modules/next/dist/bin/next"), "dev", "--webpack", "--hostname", "127.0.0.1", "--port", str(WEB_PORT)]),
        ]:
            log = (local / (name + ".log")).open("a", encoding="utf-8")
            logs.append(log)
            children.append(subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
        (local / "dogfood-processes.json").write_text(json.dumps({"launcher": os.getpid(), "children": [p.pid for p in children]}), encoding="utf-8")
        print(f"Standalone dogfood: http://127.0.0.1:{WEB_PORT}/dogfood", flush=True)
        print("Simulation transport. CRM is persistent local Supabase. No Fleet runtime.", flush=True)
        while all(p.poll() is None for p in children):
            time.sleep(1)
        raise SystemExit("A service exited. Inspect .local/dogfood-*.log")
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
