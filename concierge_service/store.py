"""Transactional execution state; WACRM remains the canonical contact store.

SQLite is deliberate for the single-host dogfood. BEGIN IMMEDIATE serializes writers;
jobs lease work outside the transaction, then compare the conversation revision.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from uuid import UUID


def account_id(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Account UUID required") from exc


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS workspaces (
                  account TEXT PRIMARY KEY, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY, account TEXT NOT NULL, job_key TEXT NOT NULL,
                  kind TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL,
                  due REAL NOT NULL, lease_until REAL, attempts INTEGER NOT NULL DEFAULT 0,
                  error TEXT, UNIQUE(account, job_key));
                CREATE INDEX IF NOT EXISTS jobs_due ON jobs(state,due);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def load(self, db, account, mode):
        account = account_id(account)
        row = db.execute("SELECT document FROM workspaces WHERE account=?", (account,)).fetchone()
        if row:
            value = json.loads(row[0])
            if value["mode"] != mode:
                raise ValueError("Workspace mode is immutable; use a separate execution database")
            return value
        return {"account_id": account, "mode": mode, "brief": None, "brief_revision": 0,
                "prospects": [], "observations": [], "messages": [], "decisions": [],
                "events": [], "reviews": [], "expenses": [], "clock_offset": 0,
                "paused": False, "connections": {}, "legacy_imports": []}

    def save(self, db, value):
        db.execute("INSERT INTO workspaces VALUES (?,?) ON CONFLICT(account) DO UPDATE SET document=excluded.document",
                   (value["account_id"], encode(value)))

    def accounts(self):
        with self.connect() as db:
            return [row[0] for row in db.execute("SELECT account FROM workspaces")]
