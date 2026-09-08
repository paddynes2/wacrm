"""Run the actual WACRM app with local Supabase and an isolated simulation engine.

Uses local Supabase-generated credentials only in child process environments, never .env.
First run: npm ci; npx supabase start. Then python scripts/local-concierge.py.
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
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
WEB_PORT = 8316
BRIDGE_PORT = 8317

def available(port: int) -> None:
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', port)) == 0:
            raise SystemExit(f'Port {port} already has a listener. Inspect its identity; this launcher will not replace it.')

def main() -> None:
    available(WEB_PORT)
    available(BRIDGE_PORT)
    npx = shutil.which('npx.cmd' if os.name == 'nt' else 'npx')
    node = shutil.which('node')
    if not npx or not node: raise SystemExit('Node.js and npm are required.')
    status = subprocess.run([npx, 'supabase', 'status', '-o', 'json'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    if status.returncode: raise SystemExit('Local Supabase is not ready. Run npx supabase start first.')
    config = json.loads(status.stdout)
    api_url = config['API_URL']
    if urlparse(api_url).hostname not in ('127.0.0.1', 'localhost'):
        raise SystemExit('This launcher only connects to a local Supabase instance.')
    engine = Path(os.environ.get('WACRM_FLEET_SOURCE', 'C:/wacwt/apps/internal/agent-fleet')).resolve()
    if not (engine/'fleet/wacrm_bridge.py').exists(): raise SystemExit('Set WACRM_FLEET_SOURCE to the checked-out concierge engine.')
    local = ROOT/'.local'
    local.mkdir(exist_ok=True)
    environment = dict(os.environ)
    environment.update({
        'NEXT_PUBLIC_SUPABASE_URL': api_url,
        'NEXT_PUBLIC_SUPABASE_ANON_KEY': config['ANON_KEY'],
        'SUPABASE_SERVICE_ROLE_KEY': config['SERVICE_ROLE_KEY'],
        'NEXT_PUBLIC_SITE_URL': f'http://127.0.0.1:{WEB_PORT}',
        'NEXT_PUBLIC_APP_LOCALE': 'en',
        'WACRM_BRIDGE_URL': f'http://127.0.0.1:{BRIDGE_PORT}',
        'WACRM_BRIDGE_TOKEN': secrets.token_urlsafe(48),
        'WACRM_BRIDGE_MODE': 'simulation',
        'FLEET_HOME': str(local/'fleet'),
        'FLEET_PEOPLE_CRM': 'off',
        'FLEET_ESTATE_OUTCOMES': '0',
        'NEXT_TELEMETRY_DISABLED': '1',
    })
    # No real Meta configuration is loaded by this local simulation launcher.
    for key in ('META_APP_SECRET', 'WHATSAPP_ACCESS_TOKEN', 'UNIPILE_API_KEY'):
        environment.pop(key, None)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    children = []
    logs = []
    try:
        for name, command, cwd in [
            ('engine', [sys.executable, '-m', 'uvicorn', 'fleet.wacrm_bridge:app', '--host', '127.0.0.1', '--port', str(BRIDGE_PORT)], engine),
            ('web', [node, str(ROOT/'node_modules/next/dist/bin/next'), 'dev', '--webpack', '--hostname', '127.0.0.1', '--port', str(WEB_PORT)], ROOT),
        ]:
            log = (local/f'{name}.log').open('a', encoding='utf-8'); logs.append(log)
            child = subprocess.Popen(command, cwd=cwd, env=environment, stdout=log, stderr=log, creationflags=flags)
            children.append(child)
        (local/'processes.json').write_text(json.dumps({'launcher': os.getpid(), 'children': [p.pid for p in children]}))
        print(f'WACRM: http://127.0.0.1:{WEB_PORT}/concierge', flush=True)
        print('Local persistent CRM; WhatsApp and calendars are explicitly simulated. Logs: .local/', flush=True)
        while all(p.poll() is None for p in children): time.sleep(1)
        raise SystemExit('A service exited. Inspect .local/engine.log and .local/web.log.')
    finally:
        for child in children:
            if child.poll() is None: child.terminate()
        for log in logs: log.close()

if __name__ == '__main__': main()
