"""Unit tests for AssistantPipe — rt-2 session manager (#10 escalate-backend).

Covers:
1. Context injection — escalate context (order_id, summary) appended to system prompt.
2. Event translation — Foundry rt-2 events → rt2.* outbound envelopes.
3. Tool dispatch — function_call_arguments.done triggers ToolDispatcher and emits
   rt2.tool_call + rt2.tool_result envelopes.
4. assist.user_text → conversation.item.create on rt-2 + response.create.
5. aclose cleans up the underlying session.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.realtime.assistant import AssistantPipe, build_assistant_session


class FakeConnection:
    """In-memory SessionConnection — replays scripted events, records sends."""

    def __init__(self, scripted_events: list[dict[str, Any]] | None = None) -> None:
        self.opened = False
        self.closed = False
        self.session_update: dict[str, Any] | None = None
        self.appended_audio: list[str] = []
        self.committed = 0
        self.sent_items: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = list(scripted_events or [])
        self._event_queue: asyncio.Queue = asyncio.Queue()
        for ev in self._events:
            self._event_queue.put_nowait(ev)
        self._stop = object()

    async def open(self) -> None:
        self.opened = True

    async def update_session(self, session_config: dict[str, Any]) -> None:
        self.session_update = session_config

    async def append_audio(self, audio_b64: str) -> None:
        self.appended_audio.append(audio_b64)

    async def commit(self) -> None:
        self.committed += 1

    async def send_event(self, event: dict[str, Any]) -> None:
        self.sent_items.append(event)

    async def push_event(self, ev: dict[str, Any]) -> None:
        await self._event_queue.put(ev)

    async def finish(self) -> None:
        await self._event_queue.put(self._stop)

    async def events(self) -> AsyncIterator[Any]:
        while True:
            ev = await self._event_queue.get()
            if ev is self._stop:
                return
            yield ev

    async def aclose(self) -> None:
        self.closed = True


def _drain(q: asyncio.Queue) -> list[dict[str, Any]]:
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def test_build_assistant_session_injects_context():
    s = build_assistant_session(
        reasoning_effort="medium",
        order_id="A12345",
        context_summary="客户要求退税和免运费",
    )
    assert s["reasoning"] == {"effort": "medium"}
    instr = s["instructions"]
    assert "A12345" in instr
    assert "客户要求退税和免运费" in instr
    # Original prompt must still be present
    assert "跨境电商客服" in instr
    # Tools must be preserved
    names = [t["name"] for t in s["tools"]]
    assert names == ["get_order", "check_tariff", "check_insurance"]


def test_build_assistant_session_requires_some_context():
    with pytest.raises(ValueError):
        build_assistant_session(reasoning_effort="high", order_id=None, context_summary="")


async def test_open_sends_session_update_and_response_create():
    conn = FakeConnection()
    outbound: asyncio.Queue = asyncio.Queue()
    seq = iter(range(1, 999))
    pipe = AssistantPipe(
        call_id="C-1",
        conn=conn,
        outbound=outbound,
        next_seq=lambda: next(seq),
        reasoning_effort="high",
        order_id="A12345",
        context_summary="退换 + 关税豁免",
    )
    await pipe.open()
    assert conn.opened is True
    assert conn.session_update is not None
    assert "A12345" in conn.session_update["instructions"]
    # An initial response.create must be sent so rt-2 starts reasoning.
    assert any(e.get("type") == "response.create" for e in conn.sent_items)
    await pipe.aclose()
    assert conn.closed is True


async def test_event_translation_reasoning_audio_text_done():
    conn = FakeConnection(scripted_events=[
        {"type": "response.reasoning.delta", "delta": "思考: 先查订单"},
        {"type": "response.audio.delta", "delta": "QUJD"},
        {"type": "response.audio.done"},
        {"type": "response.text.delta", "delta": "根据订单"},
        {"type": "response.done", "response": {"usage": {
            "total_tokens": 500, "output_token_details": {"reasoning_tokens": 120}}}},
    ])
    outbound: asyncio.Queue = asyncio.Queue()
    seq = iter(range(1, 999))
    pipe = AssistantPipe(
        call_id="C-2", conn=conn, outbound=outbound,
        next_seq=lambda: next(seq), reasoning_effort="medium",
        order_id="A12345", context_summary="x",
    )
    await pipe.open()
    receiver = asyncio.create_task(pipe.run_receiver())
    await conn.finish()
    await asyncio.wait_for(receiver, timeout=2)

    types = [e["type"] for e in _drain(outbound)]
    assert "rt2.reasoning.delta" in types
    assert "rt2.audio.delta" in types
    assert "rt2.audio.done" in types
    assert "rt2.text.delta" in types
    assert "rt2.done" in types


async def test_tool_call_dispatch_emits_tool_call_and_result():
    """get_order(A12345) → rt2.tool_call + dispatcher runs → rt2.tool_result."""
    conn = FakeConnection(scripted_events=[
        {"type": "response.function_call_arguments.delta",
         "call_id": "tc-1", "name": "get_order", "delta": '{"order_id":'},
        {"type": "response.function_call_arguments.delta",
         "call_id": "tc-1", "name": "get_order", "delta": '"A12345"}'},
        {"type": "response.function_call_arguments.done",
         "call_id": "tc-1", "name": "get_order", "arguments": '{"order_id":"A12345"}'},
    ])
    outbound: asyncio.Queue = asyncio.Queue()
    seq = iter(range(1, 999))
    pipe = AssistantPipe(
        call_id="C-3", conn=conn, outbound=outbound,
        next_seq=lambda: next(seq), reasoning_effort="high",
        order_id="A12345", context_summary="x",
    )
    await pipe.open()
    receiver = asyncio.create_task(pipe.run_receiver())
    # Give the dispatcher a moment to run.
    await asyncio.sleep(0.05)
    await conn.finish()
    await asyncio.wait_for(receiver, timeout=2)

    events = _drain(outbound)
    types = [e["type"] for e in events]
    assert "rt2.tool_call" in types
    assert "rt2.tool_result" in types
    tc = next(e for e in events if e["type"] == "rt2.tool_call")
    assert tc["payload"]["name"] == "get_order"
    assert tc["payload"]["arguments"] == {"order_id": "A12345"}
    tr = next(e for e in events if e["type"] == "rt2.tool_result")
    assert tr["payload"]["ok"] is True
    assert tr["payload"]["name"] == "get_order"

    # Dispatcher should have written function_call_output + response.create
    # back to the rt-2 session.
    sent_types = [e.get("type") for e in conn.sent_items]
    assert "conversation.item.create" in sent_types
    fco = next(e for e in conn.sent_items if e.get("type") == "conversation.item.create")
    assert fco["item"]["type"] == "function_call_output"
    assert fco["item"]["call_id"] == "tc-1"
    # And at least one response.create follow-up (in addition to initial one).
    assert sent_types.count("response.create") >= 2


async def test_unknown_tool_emits_tool_result_with_error():
    conn = FakeConnection(scripted_events=[
        {"type": "response.function_call_arguments.done",
         "call_id": "tc-x", "name": "nonexistent", "arguments": "{}"},
    ])
    outbound: asyncio.Queue = asyncio.Queue()
    seq = iter(range(1, 999))
    pipe = AssistantPipe(
        call_id="C-4", conn=conn, outbound=outbound,
        next_seq=lambda: next(seq), reasoning_effort="low",
        order_id=None, context_summary="ctx",
    )
    await pipe.open()
    receiver = asyncio.create_task(pipe.run_receiver())
    await asyncio.sleep(0.05)
    await conn.finish()
    await asyncio.wait_for(receiver, timeout=2)
    events = _drain(outbound)
    tr = next(e for e in events if e["type"] == "rt2.tool_result")
    assert tr["payload"]["ok"] is False
    assert "unknown_tool" in tr["payload"]["error"]


async def test_send_user_text_forwards_to_rt2_and_triggers_response():
    conn = FakeConnection()
    outbound: asyncio.Queue = asyncio.Queue()
    seq = iter(range(1, 999))
    pipe = AssistantPipe(
        call_id="C-5", conn=conn, outbound=outbound,
        next_seq=lambda: next(seq), reasoning_effort="medium",
        order_id="A12345", context_summary="x",
    )
    await pipe.open()
    conn.sent_items.clear()
    await pipe.send_user_text("再确认一下保险是否覆盖关税")
    types = [e.get("type") for e in conn.sent_items]
    assert "conversation.item.create" in types
    item = next(e for e in conn.sent_items if e.get("type") == "conversation.item.create")
    # Should be a user message with input_text
    assert item["item"]["role"] == "user"
    txt = item["item"]["content"][0]
    assert txt["type"] == "input_text"
    assert "保险" in txt["text"]
    assert "response.create" in types


async def test_send_audio_frame_appends_audio_b64():
    conn = FakeConnection()
    outbound: asyncio.Queue = asyncio.Queue()
    pipe = AssistantPipe(
        call_id="C-6", conn=conn, outbound=outbound,
        next_seq=lambda: 1, reasoning_effort="medium",
        order_id="A1", context_summary="x",
    )
    await pipe.open()
    await pipe.send_audio_frame("AAAA")
    assert conn.appended_audio == ["AAAA"]


async def test_receiver_resilient_to_unknown_event_types():
    conn = FakeConnection(scripted_events=[
        {"type": "session.created"},
        {"type": "rate_limits.updated"},
        {"type": "response.audio.delta", "delta": "QUJD"},
    ])
    outbound: asyncio.Queue = asyncio.Queue()
    pipe = AssistantPipe(
        call_id="C-7", conn=conn, outbound=outbound,
        next_seq=lambda: 1, reasoning_effort="medium",
        order_id="A1", context_summary="x",
    )
    await pipe.open()
    receiver = asyncio.create_task(pipe.run_receiver())
    await conn.finish()
    await asyncio.wait_for(receiver, timeout=2)
    types = [e["type"] for e in _drain(outbound)]
    assert "rt2.audio.delta" in types
