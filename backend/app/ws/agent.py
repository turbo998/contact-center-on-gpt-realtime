"""/ws/agent endpoint. Spec: docs/11 §11.3.

Symmetric to /ws/customer plus ``escalate.request`` / ``escalate.acked``.
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
    @router.websocket("/ws/agent")
    async def ws_agent(ws: WebSocket, call_id: str | None = Query(default=None)) -> None:
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

        if env["type"] != "call.start":
            await ws.close(code=1003)
            return

        cid = call_id or env["call_id"] or f"C-{uuid.uuid4().hex[:12]}"
        payload = env.get("payload", {})
        sess = await store.create(
            call_id=cid,
            role="agent",
            lang=payload.get("lang", "en-US"),
            target_lang=payload.get("target_lang", "zh-CN"),
        )

        await send_envelope(ws, sess, make_envelope(
            type="call.started", call_id=cid, seq=sess.next_seq(),
            payload={"call_id": cid, "voice": "alloy", "started_at": sess.started_at_ms},
        ))

        async def handle(s, e: Envelope) -> None:  # noqa: ANN001
            t = e["type"]
            if t in ("audio.frame", "audio.flush"):
                return
            if t == "escalate.request":
                # Stash context for /ws/assist to pick up (consumed in #10).
                p = e.get("payload", {})
                order_id = p.get("order_id")
                if not order_id:
                    await send_error(
                        ws, s, code="E_ESCALATE_NO_CONTEXT",
                        message="escalate.request missing order_id",
                    )
                    return
                s.escalate_context = {
                    "order_id": order_id,
                    "note": p.get("note", ""),
                }
                await send_envelope(ws, s, make_envelope(
                    type="escalate.acked", call_id=cid, seq=s.next_seq(),
                    payload={
                        "assist_ws_url": f"/ws/assist?call_id={cid}",
                        "context_summary": p.get("note", "") or f"order {order_id}",
                    },
                ))
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

        await run_gateway(ws, sess, handle)
        if store.get(cid) is not None:
            await store.end(cid)
            await store.remove(cid)
            await sess.audit.close(cid)

    return router
