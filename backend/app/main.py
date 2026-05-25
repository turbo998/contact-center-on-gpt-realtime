"""FastAPI app entrypoint. Mounts the three WS gateways and /health.

Spec: docs/04 (app structure), docs/11 (WS contract).
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from app.audit import AuditLogger, JsonlFileSink, NullSink
from app.realtime.assistant import AssistantConnection, AssistantPipe
from app.realtime.fork_audio import AudioFork, FoundryConnection
from app.realtime.sessions import TRANSLATE_SESSION, WHISPER_SESSION
from app.session_store import SessionStore
from app.ws import agent as ws_agent
from app.ws import assist as ws_assist
from app.ws import customer as ws_customer


def _default_fork_factory():  # pragma: no cover — requires Azure creds at runtime
    """Build an AudioFork using real Foundry connections (translate + whisper).

    Returns None when DEPLOYMENT_TRANSLATE / DEPLOYMENT_WHISPER aren't set so
    tests and dev runs without Azure creds still boot cleanly (#9).
    """
    tr_dep = os.getenv("DEPLOYMENT_TRANSLATE")
    wh_dep = os.getenv("DEPLOYMENT_WHISPER")
    if not tr_dep or not wh_dep:
        return None

    def factory(call_id, outbound, next_seq):
        tr = FoundryConnection(deployment=tr_dep, session_config=TRANSLATE_SESSION)
        wh = FoundryConnection(deployment=wh_dep, session_config=WHISPER_SESSION)
        import asyncio
        asyncio.create_task(tr.open())
        asyncio.create_task(wh.open())
        return AudioFork(
            call_id=call_id, translate=tr, whisper=wh,
            outbound=outbound, next_seq=next_seq,
        )

    return factory


def _default_assistant_factory():  # pragma: no cover — requires Azure creds
    """Build an AssistantPipe wired to real Foundry rt-2 (#10).

    Returns None when DEPLOYMENT_RT2 isn't set so dev / CI without Azure creds
    still boot cleanly. /ws/assist will then operate in handshake-only mode.
    """
    rt2_dep = os.getenv("DEPLOYMENT_RT2")
    if not rt2_dep:
        return None

    def factory(call_id, outbound, next_seq, reasoning_effort, order_id, context_summary):
        conn = AssistantConnection(deployment=rt2_dep)
        return AssistantPipe(
            call_id=call_id, conn=conn, outbound=outbound, next_seq=next_seq,
            reasoning_effort=reasoning_effort,
            order_id=order_id, context_summary=context_summary,
        )

    return factory


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
    fork_factory=None,
    assistant_factory=None,
) -> FastAPI:
    """App factory. Tests inject NullSink + a fresh SessionStore + fake fork/assistant."""
    audit = audit or _build_audit()
    store = store or SessionStore(audit=audit)
    if fork_factory is None:
        fork_factory = _default_fork_factory()
    if assistant_factory is None:
        assistant_factory = _default_assistant_factory()

    app = FastAPI(title="contact-center-on-gpt-realtime")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(ws_customer.make_router(store, audit, fork_factory=fork_factory))
    app.include_router(ws_agent.make_router(store, audit))
    app.include_router(ws_assist.make_router(store, audit, assistant_factory=assistant_factory))

    # Expose for tests / introspection.
    app.state.audit = audit
    app.state.store = store
    return app


app = create_app()
