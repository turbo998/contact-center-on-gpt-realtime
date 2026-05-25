"""/ws/customer endpoint. Spec: docs/11 §11.2.

For #8 ws-gateway: implements envelope routing, audit, ack-style
``call.started``, ``audio.flush`` ack, and ``call.end`` → ``call.ended``.
Actual Foundry translate + whisper bridging is wired in #9 (fork-audio).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, WebSocket

from app.audit import AuditLogger
from app.realtime.protocol import Envelope, ProtocolError, dumps, loads, make_envelope
from app.session_store import SessionStore
from app.ws.gateway_base import run_gateway, send_envelope

router = APIRouter()


def make_router(store: SessionStore, audit: AuditLogger) -> APIRouter:
    @router.websocket("/ws/customer")
    async def ws_customer(ws: WebSocket, call_id: str | None = Query(default=None)) -> None:
        await ws.accept()

        # First frame must be call.start (docs/11 §11.2.3).
        try:
            raw = await ws.receive_text()
            env = loads(raw)
        except ProtocolError as e:
            await ws.send_text(dumps(make_envelope(
                type="error.raised", call_id=call_id or "unknown", seq=1,
                payload={"code": "E_INTERNAL", "message": str(e), "retriable": False},
            )))
            await ws.close(code=1003)
            return

        if env["type"] != "call.start":
            await ws.close(code=1003)
            return

        cid = call_id or env["call_id"] or f"C-{uuid.uuid4().hex[:12]}"
        payload = env.get("payload", {})
        sess = await store.create(
            call_id=cid,
            role="customer",
            lang=payload.get("lang", "zh-CN"),
            target_lang=payload.get("target_lang", "en-US"),
        )

        await send_envelope(ws, sess, make_envelope(
            type="call.started", call_id=cid, seq=sess.next_seq(),
            payload={"call_id": cid, "voice": "alloy", "started_at": sess.started_at_ms},
        ))

        async def handle(s, e: Envelope) -> None:  # noqa: ANN001
            t = e["type"]
            if t == "audio.frame":
                # #9 fork-audio will pipe this into translate + whisper Foundry sessions.
                return
            if t == "audio.flush":
                return
            if t == "call.end":
                ended = await store.end(cid)
                await send_envelope(ws, s, make_envelope(
                    type="call.ended", call_id=cid, seq=s.next_seq(),
                    payload={
                        "duration_ms": ended.duration_ms() if ended else 0,
                        "audit_url": f"/audit/audit-{cid}.jsonl",
                    },
                ))
                await s.audit.close(cid)
                await store.remove(cid)
                await ws.close(code=1000)
                return
            # Unknown types: ignored per docs/11 §11.7 / §11.8.

        await run_gateway(ws, sess, handle)
        if store.get(cid) is not None:
            await store.end(cid)
            await store.remove(cid)
            await sess.audit.close(cid)

    return router
