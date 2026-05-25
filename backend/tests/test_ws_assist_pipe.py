"""Integration: /ws/assist wires assist.start → AssistantPipe → outbound (#10)."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi.testclient import TestClient

from app.audit import AuditLogger, NullSink
from app.main import create_app
from app.realtime.assistant import AssistantPipe, AssistantSessionConnection
from app.session_store import SessionStore


class FakeAssistConn(AssistantSessionConnection):
    def __init__(self, scripted: list[dict[str, Any]]) -> None:
        self.opened = False
        self.session_update: dict | None = None
        self.appended: list[str] = []
        self.sent: list[dict] = []
        self._q: asyncio.Queue = asyncio.Queue()
        for ev in scripted:
            self._q.put_nowait(ev)
        self._stop_sentinel: dict[str, Any] = {"__stop__": True}

    async def open(self) -> None:
        self.opened = True

    async def update_session(self, session_config):
        self.session_update = session_config

    async def append_audio(self, audio_b64):
        self.appended.append(audio_b64)

    async def commit(self):
        pass

    async def send_event(self, event):
        self.sent.append(event)

    async def events(self) -> AsyncIterator[Any]:
        while True:
            ev = await self._q.get()
            if ev is self._stop_sentinel:
                return
            yield ev

    async def aclose(self):
        await self._q.put(self._stop_sentinel)


def _make_app(captured: dict):
    audit = AuditLogger(sink=NullSink())
    store = SessionStore(audit=audit)

    def factory(call_id, outbound, next_seq, reasoning_effort, order_id, context_summary):
        conn = FakeAssistConn(scripted=[
            {"type": "response.reasoning.delta", "delta": "先查 A12345"},
            {"type": "response.audio.delta", "delta": "QUJD"},
            {"type": "response.audio.done"},
            {"type": "response.text.delta", "delta": "根据订单"},
            {"type": "response.done", "response": {"usage": {
                "total_tokens": 100, "output_token_details": {"reasoning_tokens": 30}}}},
        ])
        captured["conn"] = conn
        pipe = AssistantPipe(
            call_id=call_id, conn=conn, outbound=outbound, next_seq=next_seq,
            reasoning_effort=reasoning_effort, order_id=order_id,
            context_summary=context_summary,
        )
        captured["pipe"] = pipe
        return pipe

    return create_app(audit=audit, store=store, assistant_factory=factory)


def test_assist_ws_opens_rt2_and_streams_outbound() -> None:
    captured: dict = {}
    app = _make_app(captured)
    client = TestClient(app)
    with client.websocket_connect("/ws/assist") as ws:
        ws.send_text(json.dumps({
            "v": 1, "type": "assist.start", "ts": 0, "call_id": "A-int-1", "seq": 1,
            "payload": {
                "context_summary": "客户要求退税",
                "order_id": "A12345",
                "reasoning_effort": "medium",
            },
        }))
        started = json.loads(ws.receive_text())
        assert started["type"] == "assist.started"

        # Collect outbound rt2.* envelopes; 4 emit (reasoning.delta + audio.delta
        # + audio.done + text.delta); response.done updates usage silently.
        types: list[str] = []
        for _ in range(4):
            msg = json.loads(ws.receive_text())
            types.append(msg["type"])

        ws.send_text(json.dumps({
            "v": 1, "type": "assist.end", "ts": 0, "call_id": "A-int-1", "seq": 2,
            "payload": {"reason": "client"},
        }))

        # Drain rt2.done emitted in the receiver's finally clause.
        for _ in range(3):
            try:
                msg = json.loads(ws.receive_text())
                types.append(msg["type"])
                if msg["type"] == "rt2.done":
                    break
            except Exception:
                break

    conn = captured["conn"]
    assert conn.opened is True
    assert "A12345" in conn.session_update["instructions"]
    assert any(e.get("type") == "response.create" for e in conn.sent)

    assert "rt2.reasoning.delta" in types
    assert "rt2.audio.delta" in types
    assert "rt2.done" in types


def test_assist_ws_forwards_user_text_to_rt2() -> None:
    captured: dict = {}
    app = _make_app(captured)
    client = TestClient(app)
    with client.websocket_connect("/ws/assist") as ws:
        ws.send_text(json.dumps({
            "v": 1, "type": "assist.start", "ts": 0, "call_id": "A-int-2", "seq": 1,
            "payload": {"context_summary": "ctx", "order_id": "A1"},
        }))
        json.loads(ws.receive_text())  # assist.started

        ws.send_text(json.dumps({
            "v": 1, "type": "assist.user_text", "ts": 0, "call_id": "A-int-2", "seq": 2,
            "payload": {"text": "请再确认保险是否覆盖关税"},
        }))

        # Give the server a beat to forward.
        import time as _t
        _t.sleep(0.1)

        ws.send_text(json.dumps({
            "v": 1, "type": "assist.end", "ts": 0, "call_id": "A-int-2", "seq": 3,
            "payload": {"reason": "client"},
        }))

    conn = captured["conn"]
    item_events = [e for e in conn.sent if e.get("type") == "conversation.item.create"]
    assert any("保险" in str(e) for e in item_events)


def test_assist_ws_rejects_no_context() -> None:
    audit = AuditLogger(sink=NullSink())
    store = SessionStore(audit=audit)
    app = create_app(audit=audit, store=store, assistant_factory=None)
    client = TestClient(app)
    with client.websocket_connect("/ws/assist") as ws:
        ws.send_text(json.dumps({
            "v": 1, "type": "assist.start", "ts": 0, "call_id": "A-x", "seq": 1,
            "payload": {},
        }))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error.raised"
        assert msg["payload"]["code"] == "E_ESCALATE_NO_CONTEXT"
