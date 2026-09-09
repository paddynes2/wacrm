"""Private standalone service. The authenticated WACRM server supplies tenant identity."""
from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import json
import logging
import os
from pathlib import Path
import threading

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


def create_app(engine=None, token=None, worker=False):
    secret = token if token is not None else os.environ.get("WACRM_BRIDGE_TOKEN", "")
    if len(secret) < 32:
        raise RuntimeError("A private bridge token of at least 32 characters is required")
    runtime = engine or configured_engine()
    stop = threading.Event()

    def work():
        while not stop.is_set():
            try:
                for account in runtime.store.accounts():
                    if stop.is_set():
                        break
                    runtime.process_one(account)
            except Exception:
                # Details may contain provider credentials; jobs carry safe failure states.
                log.error("Concierge worker sweep failed; inspect job state and configuration")
            stop.wait(2)

    @asynccontextmanager
    async def lifespan(app):
        thread = threading.Thread(target=work, name="concierge-worker", daemon=True) if worker else None
        if thread:
            thread.start()
        yield
        stop.set()
        if thread:
            thread.join(timeout=5)

    app = FastAPI(title="Standalone concierge", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def auth(authorization: str = Header(default="")):
        if not hmac.compare_digest(authorization, "Bearer " + secret):
            raise HTTPException(401, "Private service authentication required")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "standalone-concierge", "mode": runtime.mode, "worker": worker}

    @app.get("/workspace/{account}/dogfood", dependencies=[Depends(auth)])
    def report(account: str):
        try:
            return runtime.report(account_id(account))
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
            return await run_in_threadpool(runtime.command, account_id(account), body)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(409, str(exc) if isinstance(exc, ValueError) else "Invalid command fields") from exc
        except Exception as exc:
            raise HTTPException(503, "Provider unavailable; inspect readiness and retry-safe job state") from exc

    app.state.engine = runtime
    return app


def application():
    return create_app(worker=os.environ.get("CONCIERGE_WORKER_ENABLED") == "1")
