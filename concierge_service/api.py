"""Private standalone service. The authenticated WACRM server supplies tenant identity."""
from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import json
import logging
import os
from pathlib import Path
import threading
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from .engine import Engine
from .store import Store, account_id
from .providers import UnipileClient

log = logging.getLogger("concierge")
MAX_REQUEST_BYTES = 64000


def mapping(name):
    raw = os.environ.get(name, "{}")
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
        for key, item in value.items():
            account_id(key)
            if not isinstance(item, dict):
                raise ValueError()
        return value
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"{name} requires an account-keyed JSON object") from exc


def configured_engine():
    path = os.environ.get("CONCIERGE_DB_PATH")
    if not path or not Path(path).is_absolute():
        raise RuntimeError("CONCIERGE_DB_PATH must be an explicit absolute path")
    mode = os.environ.get("WACRM_BRIDGE_MODE", "simulation")
    clients = {account: UnipileClient(**config) for account, config in mapping("CONCIERGE_UNIPILE_JSON").items()}
    return Engine(Store(path), mode=mode, model_config=mapping("CONCIERGE_MODELS_JSON"),
                  discovery_config=mapping("CONCIERGE_DISCOVERY_JSON"), unipile=clients)


def create_app(engine=None, token=None, worker=False, sync_interval=0,
               live_executor=None, live_amendment_executor=None, chris_authorizer=None):
    secret = token if token is not None else os.environ.get("WACRM_BRIDGE_TOKEN", "")
    if len(secret) < 32:
        raise RuntimeError("A private bridge token of at least 32 characters is required")
    runtime = engine or configured_engine()
    from .chris.runtime import Runtime
    chris = Runtime(runtime, mapping('CONCIERGE_CHRIS_SETTINGS_JSON'), chris_authorizer,
                    os.environ.get('CONCIERGE_WACRM_INTERNAL_URL'), secret)
    if any(value is not None and not callable(value) for value in (live_executor, live_amendment_executor)):
        raise RuntimeError("Live execution requires explicit host callbacks")
    if type(sync_interval) is not int or (sync_interval != 0 and not 60 <= sync_interval <= 3600):
        raise RuntimeError("Account polling interval must be zero or 60 to 3600 seconds")
    stop = threading.Event()
    next_sync = {}

    def work():
        while not stop.is_set():
            try:
                chris.tick()
            except Exception:
                log.error('Chris worker tick failed; legacy processing continues')
            for account in runtime.store.accounts():
                if stop.is_set():
                    break
                try:
                    runtime.process_one(account)
                    if sync_interval and runtime.mode == "live" and account in runtime.unipile and time.monotonic() >= next_sync.get(account, 0):
                        # Advance before IO so a failed provider cannot create a tight retry loop.
                        next_sync[account] = time.monotonic() + sync_interval
                        from .ingestion import sync_account
                        sync_account(runtime, account)
                except Exception:
                    # One tenant's provider failure must not starve other workspaces.
                    log.error("Concierge account work failed; inspect job state and configuration")
            stop.wait(2)

    @asynccontextmanager
    async def lifespan(app):
        thread = threading.Thread(target=work, name="concierge-worker", daemon=True) if worker else None
        if thread:
            thread.start()
        yield
        stop.set()
        chris.scheduler.close()
        if thread:
            thread.join(timeout=5)

    app = FastAPI(title="Standalone concierge", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def auth(authorization: str = Header(default="")):
        if not hmac.compare_digest(authorization, "Bearer " + secret):
            raise HTTPException(401, "Private service authentication required")

    def present(account):
        result = runtime.report(account)
        ready = result["readiness"]
        ready["live_execution_enabled"] = runtime.mode == "live" and callable(live_executor)
        ready["live_amendments_enabled"] = runtime.mode == "live" and callable(live_amendment_executor)
        if ready["live_execution_enabled"] or ready["live_amendments_enabled"]:
            ready["reason"] = "Host authorization integration installed; every exact action still requires its gate. Delivery is unverified."
        return result

    def dispatch(account, body):
        name = body.get("command") if isinstance(body, dict) else None
        if runtime.mode == "live" and name in {"approve", "approve_amendment"}:
            fields = {"decision_id"} if name == "approve" else {"prospect_id", "digest"}
            if set(body) - fields - {"command", "attested_by"} or not fields.issubset(body):
                raise ValueError("Invalid exact approval fields")
            executor = live_executor if name == "approve" else live_amendment_executor
            if not callable(executor):
                raise ValueError("Live execution has no installed host authorization integration")
            # The host callback must invoke the tested exact-action executor through
            # its real human authorization gate. Neither env nor browser arms it.
            if name == "approve":
                executor(runtime, account, body["decision_id"])
            else:
                executor(runtime, account, body["prospect_id"], body["digest"])
            return present(account)
        runtime.command(account, body)
        return present(account)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "standalone-concierge", "mode": runtime.mode, "worker": worker}

    @app.get("/workspace/{account}/dogfood", dependencies=[Depends(auth)])
    def report(account: str):
        try:
            return present(account_id(account))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/workspace/{account}/dogfood", dependencies=[Depends(auth)])
    async def command(account: str, request: Request):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_REQUEST_BYTES:
                raise HTTPException(413, "Request too large")
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(400, "Invalid JSON") from exc
        try:
            # Process/model calls can block; keep them off the async request loop.
            from starlette.concurrency import run_in_threadpool
            return await run_in_threadpool(dispatch, account_id(account), body)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(409, str(exc) if isinstance(exc, ValueError) else "Invalid command fields") from exc
        except Exception as exc:
            raise HTTPException(503, "Provider unavailable; inspect readiness and retry-safe job state") from exc

    app.state.engine = runtime
    from .chris.api import install
    install(app, chris.service, auth, chris.projection)
    app.state.chris = chris
    return app


def application():
    from .chris.dispatch import product_authorizer
    return create_app(worker=os.environ.get("CONCIERGE_WORKER_ENABLED") == "1",
                      sync_interval=int(os.environ.get("CONCIERGE_SYNC_INTERVAL_SECONDS", "0")),
                      chris_authorizer=product_authorizer)
