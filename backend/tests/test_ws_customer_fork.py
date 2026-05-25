"""Integration: /ws/customer wires audio.frame → AudioFork → outbound (#9)."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from fastapi.testclient import TestClient

from app.audit import AuditLogger, NullSink
from app.main import create_app
from app.realtime.fork_audio import AudioFork, SessionConnection
from app.session_store import SessionStore


@dataclass
class FakeConn(SessionConnection):
    name: str
    received: list[str] = field(default_factory=list)
    _q: asyncio.Queue | None = None
    _scripted: list[Any] = field(default_factory=list)

    async def append_audio(self, audio_b64: str) -> None:
        self.received.append(audio_b64)

    async def commit(self) -> None:
        pass

    async def events(self) -> AsyncIterator[Any]:
        if self._q is None:
            self._q = asyncio.Queue()
            for ev in self._scripted:
                await self._q.put(ev)
        while True:
            ev = await self._q.get()
            if isinstance(ev, dict) and ev.get("type") == "__stop__":
                return
            yield ev

    async def aclose(self) -> None:
        if self._q is not None:
            await self._q.put({"type": "__stop__"})


def _make_app_with_fake_fork(captured: dict):
    audit = AuditLogger(sink=NullSink())
    store = SessionStore(audit=audit)
    return create_app(
        audit=audit, store=store,
        fork_factory=lambda cid, outbound, next_seq: _build_fake_fork(
            cid, outbound, next_seq, captured),
    )


def _build_fake_fork(call_id: str, outbound: asyncio.Queue, next_seq, captured: dict) -> AudioFork:
    tr = FakeConn(name="translate", _scripted=[
        type("E", (), {"type": "response.audio_transcript.delta", "delta": "hello"})(),
        {"type": "__stop__"},
    ])
    wh = FakeConn(name="whisper", _scripted=[
        type("E", (), {"type": "conversation.item.input_audio_transcription.completed",
                       "transcript": "你好"})(),
        {"type": "__stop__"},
    ])
    captured["translate"] = tr
    captured["whisper"] = wh
    return AudioFork(call_id=call_id, translate=tr, whisper=wh,
                     outbound=outbound, next_seq=next_seq)


def test_customer_ws_pipes_audio_into_fork_and_returns_outbound() -> None:
    captured: dict = {}
    app = _make_app_with_fake_fork(captured)
    client = TestClient(app)
    with client.websocket_connect("/ws/customer") as ws:
        ws.send_text(json.dumps({
            "v": 1, "type": "call.start", "ts": 0, "call_id": "C-int-1", "seq": 1,
            "payload": {"lang": "zh-CN", "target_lang": "en-US"},
        }))
        started = json.loads(ws.receive_text())
        assert started["type"] == "call.started"

        ws.send_text(json.dumps({
            "v": 1, "type": "audio.frame", "ts": 0, "call_id": "C-int-1", "seq": 2,
            "payload": {"audio": "AAAA", "seq": 1, "ts": 0},
        }))

        # Collect a handful of outbound envelopes.
        types: list[str] = []
        for _ in range(4):
            try:
                msg = json.loads(ws.receive_text())
                types.append(msg["type"])
            except Exception:
                break

        ws.send_text(json.dumps({
            "v": 1, "type": "call.end", "ts": 0, "call_id": "C-int-1", "seq": 3,
            "payload": {"reason": "client"},
        }))

    assert captured["translate"].received == ["AAAA"]
    assert captured["whisper"].received == ["AAAA"]
    assert "translate.text.delta" in types
    assert "whisper.transcript.completed" in types
