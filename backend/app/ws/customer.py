"""/ws/customer endpoint. Spec: docs/11 §11.2, docs/05 §5.2 (#9 fork-audio).

#8 ws-gateway: envelope routing, audit, call.started, audio.flush ack, call.end → call.ended.
#9 fork-audio: when a ``fork_factory`` is provided, lazily start an :class:`AudioFork`
on the first ``audio.frame`` and pump its outbound queue back to the client.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable

from fastapi import APIRouter, Query, WebSocket

from app.audit import AuditLogger
from app.realtime.fork_audio import AudioFork
from app.realtime.protocol import Envelope, ProtocolError, dumps, loads, make_envelope
from app.session_store import Session, SessionStore
from app.ws.gateway_base import run_gateway, send_envelope

router = APIRouter()  # legacy, unused after make_router-local refactor


ForkFactory = Callable[[str, asyncio.Queue, Callable[[], int]], AudioFork]


def make_router(
    store: SessionStore,
    audit: AuditLogger,
    fork_factory: ForkFactory | None = None,
) -> APIRouter:
    router = APIRouter()

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

        # --- fork-audio state (#9) ---
        outbound: asyncio.Queue = asyncio.Queue()
        fork: AudioFork | None = None
        pump_task: asyncio.Task | None = None

        async def _pump_outbound(s: Session) -> None:
            while True:
                envelope = await outbound.get()
                try:
                    await send_envelope(ws, s, envelope)
                except Exception:  # pragma: no cover — ws closed mid-pump
                    return

        async def handle(s: Session, e: Envelope) -> None:
            nonlocal fork, pump_task
            t = e["type"]
            if t == "audio.frame":
                if fork_factory is None:
                    return
                if fork is None:
                    fork = fork_factory(cid, outbound, s.next_seq)
                    await fork.start()
                    pump_task = asyncio.create_task(_pump_outbound(s), name=f"pump-{cid}")
                audio_b64 = e.get("payload", {}).get("audio", "")
                await fork.feed(audio_b64)
                return
            if t == "audio.flush":
                if fork is not None:
                    await fork.commit()
                return
            if t == "call.end":
                if fork is not None:
                    await fork.aclose()
                if pump_task is not None:
                    pump_task.cancel()
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
        if fork is not None:
            await fork.aclose()
        if pump_task is not None:
            pump_task.cancel()
        if store.get(cid) is not None:
            await store.end(cid)
            await store.remove(cid)
            await sess.audit.close(cid)

    return router
