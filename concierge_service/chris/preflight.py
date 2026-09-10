"""Read-only local preflight and explicit offline backup/restore utilities."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4
from .contracts import require


def inspect(database):
    path = Path(database)
    require(path.is_absolute() and path.is_file(), 'database_missing', 503)
    problems, accounts = [], []
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        integrity = db.execute('PRAGMA quick_check').fetchone()[0]
        if integrity != 'ok': problems.append('database_corrupt')
        for account, raw in db.execute('SELECT account,document FROM workspaces'):
            doc = json.loads(raw)
            state = doc.get('chris_v1', {})
            if not state: continue
            if state.get('schema_version') != 1: problems.append('upgrade_required')
            refs = set()
            def visit(v):
                if isinstance(v, dict):
                    for key, value in v.items():
                        if key.endswith('_ref') and isinstance(value, str) and len(value) == 64: refs.add(value)
                        visit(value)
                elif isinstance(v, list):
                    for x in v: visit(x)
            visit(state)
            for ref in refs:
                target = path.parent / 'chris-blobs' / ref
                if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != ref: problems.append('blob_corrupt')
            accounts.append(dict(account_id=account, schema_version=state.get('schema_version'), document_bytes=len(raw.encode()),
                mode=doc['mode'], external_enabled=state.get('authority', {}).get('external_enabled', False),
                worker_heartbeat=state.get('health', {}).get('heartbeat'),
                unresolved_actions=sum(a.get('status') in {'started', 'unknown', 'provider_accepted', 'needs_attention'} for a in state.get('actions', {}).values()),
                pending_projections=sum(p.get('status') != 'acknowledged' for p in state.get('projection_outbox', {}).values()),
                principal_bound=bool(state.get('principal')), whatsapp_bound=bool(state.get('connection'))))
    finally:
        db.close()
    return dict(database_integrity=integrity, path_writable=os.access(path, os.W_OK), accounts=accounts,
                reason_codes=sorted(set(problems)), live_acceptance_verified=False)


def backup(database, destination):
    source, target = Path(database).resolve(), Path(destination).resolve()
    require(source.is_file(),'database_missing',503)
    require(source != target and not target.exists(), 'backup_target_must_be_new')
    target.mkdir(parents=True)
    with sqlite3.connect(source) as original, sqlite3.connect(target / 'execution.sqlite') as copy:
        original.backup(copy)
    blobs = source.parent / 'chris-blobs'
    if blobs.exists(): shutil.copytree(blobs, target / 'chris-blobs')
    manifest = {str(p.relative_to(target)): hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file()}
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def restore(backup_path, destination):
    source, target = Path(backup_path).resolve(), Path(destination).resolve()
    require(source != target and not target.exists(), 'restore_target_must_be_new')
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    for relative, expected in manifest.items():
        p = (source / relative).resolve()
        require(p.is_relative_to(source) and hashlib.sha256(p.read_bytes()).hexdigest() == expected, 'backup_corrupt')
    with sqlite3.connect((source/'execution.sqlite').as_uri()+'?mode=ro',uri=True) as original:
        require(all(json.loads(raw)['mode']=='simulation' for (raw,) in original.execute('SELECT document FROM workspaces')),
                'live_restore_requires_host_procedure')
    shutil.copytree(source, target)
    with sqlite3.connect(target / 'execution.sqlite') as db:
        for account, raw in db.execute('SELECT account,document FROM workspaces').fetchall():
            doc = json.loads(raw)
            require(doc['mode'] == 'simulation', 'live_restore_requires_host_procedure')
            state = doc.get('chris_v1')
            if state:
                state['authority'].update(external_enabled=False, paused=True)
                state['authority']['revision'] += 1
                state['restoration_generation'] = str(uuid4())
                from .state import cancel_unstarted
                cancel_unstarted(state)
                db.execute('UPDATE workspaces SET document=? WHERE account=?', (json.dumps(doc), account))
        db.execute("UPDATE jobs SET state='cancelled' WHERE kind='chris.dispatch' AND state='queued'")
    return target / 'execution.sqlite'


def main():
    parser = argparse.ArgumentParser(description='Read-only Chris execution-store preflight; no provider or paid calls.')
    parser.add_argument('--db', required=True)
    args = parser.parse_args()
    try:
        report = inspect(args.db)
        print(json.dumps(report, indent=2))
        return 3 if report['reason_codes'] else 2 if not report['accounts'] else 0
    except (ValueError, OSError, sqlite3.Error):
        print(json.dumps({'reason_codes': ['local_storage_unavailable'], 'live_acceptance_verified': False}))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
