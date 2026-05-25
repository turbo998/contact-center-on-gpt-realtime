"""/ws/assist endpoint. Spec: docs/11 §11.4.

#8 ws-gateway laid the envelope handshake (``assist.start`` → ``assist.started``)
and routing. #10 (escalate-backend) wires the actual rt-2 turn execution:
when an ``assistant_factory`` is provided, the gateway lazily opens an
:class:`AssistantPipe`, pumps its outbound queue back to the client, and
forwards ``assist.user_text`` / ``assist.audio.frame`` into the rt-2 session.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable

from fastapi import APIRouter, Query, WebSocket

from app.audit import AuditLogger
from app.realtime.assistant import AssistantPipe
from app.realtime.protocol import Envelope, ProtocolError, dumps, loads, make_envelope
from app.session_store import Session, SessionStore
from app.ws.gateway_base import run_gateway, send_envelope, send_error

router = APIRouter()  # legacy, unused after make_router-local refactor


AssistantFactory = Callable[
    [str, asyncio.Queue, Callable[[], int], str, str | None, str],
    AssistantPipe,
]


def make_router(
    store: SessionStore,
    audit: AuditLogger,
    assistant_factory: AssistantFactory | None = None,
) -> APIRouter:
    router = APIRouter()

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

        # Reuse the agent session if it exists; else create a fresh assist session.
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

        # --- rt-2 pipe state (#10) ---
        outbound: asyncio.Queue = asyncio.Queue()
        pipe: AssistantPipe | None = None
        pump_task: asyncio.Task | None = None
        receiver_task: asyncio.Task | None = None

        async def _pump_outbound(s: Session) -> None:
            while True:
                envelope = await outbound.get()
                if envelope is None:  # sentinel — drain done
                    return
                try:
                    await send_envelope(ws, s, envelope)
                except Exception:  # pragma: no cover — ws closed mid-pump
                    return

        if assistant_factory is not None:
            pipe = assistant_factory(cid, outbound, sess.next_seq, effort, order_id, context_summary)
            await pipe.open()
            pump_task = asyncio.create_task(_pump_outbound(sess), name=f"assist-pump-{cid}")
            receiver_task = asyncio.create_task(pipe.run_receiver(), name=f"assist-recv-{cid}")

        async def handle(s: Session, e: Envelope) -> None:
            t = e["type"]
            if t == "assist.user_text":
                if pipe is not None:
                    text = e.get("payload", {}).get("text", "")
                    if text:
                        await pipe.send_user_text(text)
                return
            if t == "assist.audio.frame":
                if pipe is not None:
                    audio_b64 = e.get("payload", {}).get("audio", "")
                    if audio_b64:
                        await pipe.send_audio_frame(audio_b64)
                return
            if t == "assist.end":
                if pipe is not None:
                    await pipe.aclose()
                # Wait for receiver to flush rt2.done into outbound, then post a
                # sentinel so the pump drains it before we close the WebSocket.
                if receiver_task is not None:
                    try:
                        await asyncio.wait_for(receiver_task, timeout=2.0)
                    except TimeoutError:
                        receiver_task.cancel()
                await outbound.put(None)
                if pump_task is not None:
                    try:
                        await asyncio.wait_for(pump_task, timeout=2.0)
                    except TimeoutError:
                        pump_task.cancel()
                await s.audit.close(cid)
                await store.remove(cid)
                await ws.close(code=1000)
                return

        await run_gateway(ws, sess, handle)
        if pipe is not None:
            await pipe.aclose()
        if receiver_task is not None:
            receiver_task.cancel()
        if pump_task is not None:
            pump_task.cancel()
        if store.get(cid) is not None:
            await sess.audit.close(cid)
            await store.remove(cid)

    return router
