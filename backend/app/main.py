"""FastAPI app entrypoint. Mounts the three WS gateways and /health.

Spec: docs/04 (app structure), docs/11 (WS contract).
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from app.audit import AuditLogger, JsonlFileSink, NullSink
from app.session_store import SessionStore
from app.ws import agent as ws_agent
from app.ws import assist as ws_assist
from app.ws import customer as ws_customer


def _build_audit() -> AuditLogger:
    sink_kind = os.getenv("AUDIT_SINK", "local")
    if sink_kind == "local":
        audit_dir = Path(os.getenv("AUDIT_DIR", "./audit"))
        return AuditLogger(sink=JsonlFileSink(audit_dir))
    if sink_kind == "null":
        return AuditLogger(sink=NullSink())
    # "blob" sink is planned for #15 — fall back to local until then.
    audit_dir = Path(os.getenv("AUDIT_DIR", "./audit"))
    return AuditLogger(sink=JsonlFileSink(audit_dir))


def create_app(
    *,
    audit: AuditLogger | None = None,
    store: SessionStore | None = None,
) -> FastAPI:
    """App factory. Tests inject NullSink + a fresh SessionStore."""
    audit = audit or _build_audit()
    store = store or SessionStore(audit=audit)

    app = FastAPI(title="contact-center-on-gpt-realtime")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(ws_customer.make_router(store, audit))
    app.include_router(ws_agent.make_router(store, audit))
    app.include_router(ws_assist.make_router(store, audit))

    # Expose for tests / introspection.
    app.state.audit = audit
    app.state.store = store
    return app


app = create_app()
