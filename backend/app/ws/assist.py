"""/ws/assist endpoint. Spec: docs/11 §11.4.

Implements the handshake (``assist.start`` → ``assist.started``) and
envelope routing. Actual rt-2 turn execution (reasoning deltas, tool calls,
audio) is wired in #10 (escalate-backend).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, WebSocket

from app.audit import AuditLogger
from app.realtime.protocol import Envelope, ProtocolError, dumps, loads, make_envelope
from app.session_store import SessionStore
from app.ws.gateway_base import run_gateway, send_envelope, send_error

router = APIRouter()


def make_router(store: SessionStore, audit: AuditLogger) -> APIRouter:
    @router.websocket("/ws/assist")
    async def ws_assist(ws: WebSocket, call_id: str | None = Query(default=None)) -> None:
        await ws.accept()
        try:
            env = loads(await ws.receive_text())
        except ProtocolError as e:
            await ws.send_text(dumps(make_envelope(
                type="error.raised", call_id=call_id or "unknown", seq=1,
                payload={"code": "E_INTERNAL", "message": str(e), "retriable": False},
            )))
            await ws.close(code=1003)
            return

        if env["type"] != "assist.start":
            await ws.close(code=1003)
            return

        cid = call_id or env["call_id"] or f"A-{uuid.uuid4().hex[:12]}"
        payload = env.get("payload", {})
        order_id = payload.get("order_id")
        context_summary = payload.get("context_summary", "")
        if not order_id and not context_summary:
            # Cannot proceed without any context.
            tmp = await store.create(
                call_id=cid, role="agent", lang="en-US", target_lang="zh-CN",
            )
            await send_error(
                ws, tmp,
                code="E_ESCALATE_NO_CONTEXT",
                message="assist.start requires order_id or context_summary",
            )
            await store.remove(cid)
            await ws.close(code=1003)
            return

        # Reuse the agent session if it exists (same call_id, agent escalated
        # from the same call), else create a fresh assist session.
        sess = store.get(cid) or await store.create(
            call_id=cid, role="agent", lang="en-US", target_lang="zh-CN",
        )

        effort = payload.get("reasoning_effort", "high")
        session_id = f"sess-{uuid.uuid4().hex[:10]}"
        await send_envelope(ws, sess, make_envelope(
            type="assist.started", call_id=cid, seq=sess.next_seq(),
            payload={
                "session_id": session_id,
                "model": "gpt-realtime-2",
                "reasoning_effort": effort,
            },
        ))

        async def handle(s, e: Envelope) -> None:  # noqa: ANN001
            t = e["type"]
            if t in ("assist.user_text", "assist.audio.frame"):
                # #10 escalate-backend will forward these into the rt-2 session.
                return
            if t == "assist.end":
                await s.audit.close(cid)
                await store.remove(cid)
                await ws.close(code=1000)
                return

        await run_gateway(ws, sess, handle)
        if store.get(cid) is not None:
            await sess.audit.close(cid)
            await store.remove(cid)

    return router
