"""Shared WS gateway primitives — envelope routing, heartbeat, audit, errors.

All three WebSocket endpoints (/ws/customer, /ws/agent, /ws/assist) share:
- inbound frame validation (envelope shape + protocol version)
- ``system.ping`` → ``system.pong`` reply with 30s timeout disconnect (docs/11 §11.1.1)
- ``error.raised`` emission with code registry (docs/11 §11.1.2)
- audit-event logging of every inbound and outbound envelope
- 64 KB max audio-frame guard (docs/11 §11.1.3 + §11.8)
- unknown ``type`` ignored with WARN log (docs/11 §11.8)

Endpoint-specific routing is plugged in via the ``handle_frame`` callback.
Foundry session bridging lives in #9 (fork-audio) and #10 (escalate-backend).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.realtime.protocol import (
    ERROR_CODES,
    Envelope,
    ProtocolError,
    dumps,
    loads,
    make_envelope,
    make_error,
)
from app.session_store import Session

log = logging.getLogger(__name__)


# docs/11 §11.1.1 — client sends ping every 15s; server disconnects on 30s of silence
HEARTBEAT_TIMEOUT_SEC = 30.0

# docs/11 §11.1.3 — 64 KB max base64 audio
MAX_AUDIO_BYTES = 64 * 1024


FrameHandler = Callable[[Session, Envelope], Awaitable[None]]


async def send_envelope(ws: WebSocket, sess: Session, env: Envelope) -> None:
    await ws.send_text(dumps(env))
    await sess.audit.log_event(sess.call_id, envelope=env, direction="server_to_client")


async def send_error(
    ws: WebSocket,
    sess: Session,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    env = make_error(
        call_id=sess.call_id, seq=sess.next_seq(),
        code=code, message=message, details=details,
    )
    await send_envelope(ws, sess, env)


async def _recv_with_timeout(ws: WebSocket) -> str:
    """Wait up to HEARTBEAT_TIMEOUT_SEC for the next inbound text frame."""
    return await asyncio.wait_for(ws.receive_text(), timeout=HEARTBEAT_TIMEOUT_SEC)


def _is_audio_too_large(env: Envelope) -> bool:
    """Reject audio frames whose base64 payload exceeds 64 KB."""
    if not env["type"].endswith("audio.frame") and env["type"] != "audio.frame":
        return False
    audio = env.get("payload", {}).get("audio", "")
    return isinstance(audio, str) and len(audio.encode("utf-8")) > MAX_AUDIO_BYTES


async def run_gateway(
    ws: WebSocket,
    sess: Session,
    handle_frame: FrameHandler,
) -> None:
    """Main per-connection loop. Handles ping/pong/error/audit, delegates the rest.

    The connection is expected to be ``accept()``-ed by the caller and the
    Session created beforehand (so the caller can validate ``call.start`` /
    ``assist.start`` before allocating any state).
    """
    try:
        while True:
            if ws.application_state != WebSocketState.CONNECTED:
                return
            try:
                raw = await _recv_with_timeout(ws)
            except TimeoutError:
                log.info("heartbeat timeout call_id=%s", sess.call_id)
                await send_error(
                    ws, sess,
                    code="E_SESSION_EXPIRED",
                    message=f"no inbound frame for {HEARTBEAT_TIMEOUT_SEC:.0f}s",
                )
                await ws.close(code=1001)
                return

            try:
                env = loads(raw)
            except ProtocolError as e:
                log.warning("invalid frame call_id=%s err=%s", sess.call_id, e)
                await send_error(ws, sess, code="E_INTERNAL", message=str(e))
                continue

            await sess.audit.log_event(sess.call_id, envelope=env, direction="client_to_server")

            # Audio frame size guard before any other routing.
            if _is_audio_too_large(env):
                await send_error(
                    ws, sess, code="E_AUDIO_TOO_LARGE",
                    message=f"audio frame exceeds {MAX_AUDIO_BYTES} bytes",
                )
                continue

            t = env["type"]
            if t == "system.ping":
                pong = make_envelope(
                    type="system.pong", call_id=sess.call_id,
                    seq=sess.next_seq(), payload={},
                )
                await send_envelope(ws, sess, pong)
                continue

            try:
                await handle_frame(sess, env)
            except ProtocolError as e:
                await send_error(ws, sess, code="E_INTERNAL", message=str(e))
            except Exception as e:  # pragma: no cover — defensive only
                log.exception("handler crashed call_id=%s", sess.call_id)
                await send_error(ws, sess, code="E_INTERNAL", message=repr(e))

    except WebSocketDisconnect:
        log.info("client disconnected call_id=%s", sess.call_id)


def known_error_code(code: str) -> bool:
    return code in ERROR_CODES
