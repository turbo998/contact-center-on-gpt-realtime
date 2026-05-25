"""Tests for backend/app/realtime/fork_audio.py — dual-pipe audio fan-out.

Spec: docs/05 §5.2 (fork-audio), docs/11 §11.2.2 (translate.*, whisper.*),
issue #9 acceptance:
  - same 24kHz PCM16 frame goes to both translate AND whisper
  - results return on both pipes with independent latency
  - one pipe crashing does not kill the other
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.realtime.fork_audio import AudioFork, SessionConnection

# --- Fake Foundry session for tests -----------------------------------------


@dataclass
class FakeEvent:
    type: str
    delta: str = ""
    text: str = ""
    transcript: str = ""


@dataclass
class FakeConnection(SessionConnection):
    name: str
    received_chunks: list[str] = field(default_factory=list)
    committed: int = 0
    closed: bool = False
    _scripted: list[FakeEvent] = field(default_factory=list)
    _delay_first_event_s: float = 0.0
    _raise_on_first_event: Exception | None = None
    _q: asyncio.Queue[FakeEvent] | None = None

    async def append_audio(self, audio_b64: str) -> None:
        self.received_chunks.append(audio_b64)

    async def commit(self) -> None:
        self.committed += 1

    async def events(self) -> AsyncIterator[Any]:
        if self._q is None:
            self._q = asyncio.Queue()
            for ev in self._scripted:
                await self._q.put(ev)
        first = True
        while True:
            ev = await self._q.get()
            if first and self._delay_first_event_s:
                await asyncio.sleep(self._delay_first_event_s)
            if first and self._raise_on_first_event is not None:
                raise self._raise_on_first_event
            first = False
            if ev.type == "__stop__":
                return
            yield ev

    async def aclose(self) -> None:
        self.closed = True
        if self._q is not None:
            await self._q.put(FakeEvent(type="__stop__"))


# --- Tests ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_duplicates_audio_to_both_pipes() -> None:
    """Acceptance #1: same PCM frame goes to both Foundry sessions."""
    tr = FakeConnection(name="translate", _scripted=[FakeEvent(type="__stop__")])
    wh = FakeConnection(name="whisper", _scripted=[FakeEvent(type="__stop__")])
    out: asyncio.Queue = asyncio.Queue()

    fork = AudioFork(call_id="C-1", translate=tr, whisper=wh, outbound=out, next_seq=lambda: 1)
    await fork.start()
    await fork.feed("AAAA")
    await fork.feed("BBBB")
    await fork.aclose()

    assert tr.received_chunks == ["AAAA", "BBBB"]
    assert wh.received_chunks == ["AAAA", "BBBB"]


@pytest.mark.asyncio
async def test_translate_events_emit_envelopes() -> None:
    """Translate session emits text/audio deltas → outbound envelopes."""
    tr = FakeConnection(name="translate", _scripted=[
        FakeEvent(type="response.audio_transcript.delta", delta="Hello"),
        FakeEvent(type="response.audio.delta", delta="QUJD"),
        FakeEvent(type="response.audio.done"),
        FakeEvent(type="__stop__"),
    ])
    wh = FakeConnection(name="whisper", _scripted=[FakeEvent(type="__stop__")])
    out: asyncio.Queue = asyncio.Queue()

    seq = iter(range(1, 100))
    fork = AudioFork(call_id="C-2", translate=tr, whisper=wh, outbound=out, next_seq=lambda: next(seq))
    await fork.start()
    await asyncio.sleep(0.05)  # let receivers drain
    await fork.aclose()

    types = []
    while not out.empty():
        types.append(out.get_nowait()["type"])
    assert "translate.text.delta" in types
    assert "translate.audio.delta" in types
    assert "translate.audio.done" in types


@pytest.mark.asyncio
async def test_whisper_events_emit_envelopes() -> None:
    """Whisper session emits transcription completed → whisper.transcript.* envelopes."""
    wh = FakeConnection(name="whisper", _scripted=[
        FakeEvent(type="conversation.item.input_audio_transcription.completed",
                  transcript="你好世界"),
        FakeEvent(type="__stop__"),
    ])
    tr = FakeConnection(name="translate", _scripted=[FakeEvent(type="__stop__")])
    out: asyncio.Queue = asyncio.Queue()

    seq = iter(range(1, 100))
    fork = AudioFork(call_id="C-3", translate=tr, whisper=wh, outbound=out, next_seq=lambda: next(seq))
    await fork.start()
    await asyncio.sleep(0.05)
    await fork.aclose()

    msgs = []
    while not out.empty():
        msgs.append(out.get_nowait())
    types = [m["type"] for m in msgs]
    assert "whisper.transcript.completed" in types
    completed = next(m for m in msgs if m["type"] == "whisper.transcript.completed")
    assert completed["payload"]["text"] == "你好世界"


@pytest.mark.asyncio
async def test_one_pipe_crash_does_not_kill_other() -> None:
    """Acceptance #3: a crash in whisper must not stop translate output."""
    tr = FakeConnection(name="translate", _scripted=[
        FakeEvent(type="response.audio_transcript.delta", delta="ok"),
        FakeEvent(type="__stop__"),
    ])
    wh = FakeConnection(
        name="whisper",
        _scripted=[FakeEvent(type="__stop__")],
        _raise_on_first_event=RuntimeError("whisper boom"),
    )
    out: asyncio.Queue = asyncio.Queue()
    seq = iter(range(1, 100))
    fork = AudioFork(call_id="C-4", translate=tr, whisper=wh, outbound=out, next_seq=lambda: next(seq))
    await fork.start()
    await asyncio.sleep(0.05)
    await fork.aclose()

    types: list[str] = []
    errors: list[dict] = []
    while not out.empty():
        m = out.get_nowait()
        types.append(m["type"])
        if m["type"] == "error.raised":
            errors.append(m)
    assert "translate.text.delta" in types
    assert any(e["payload"]["code"] == "E_FOUNDRY_DISCONNECT" for e in errors)


@pytest.mark.asyncio
async def test_latency_tracked_per_pipe() -> None:
    """Acceptance #2: independent latency timing per pipe."""
    tr = FakeConnection(name="translate", _scripted=[
        FakeEvent(type="response.audio_transcript.delta", delta="x"),
        FakeEvent(type="__stop__"),
    ], _delay_first_event_s=0.02)
    wh = FakeConnection(name="whisper", _scripted=[
        FakeEvent(type="conversation.item.input_audio_transcription.completed", transcript="hi"),
        FakeEvent(type="__stop__"),
    ], _delay_first_event_s=0.10)
    out: asyncio.Queue = asyncio.Queue()
    seq = iter(range(1, 100))
    fork = AudioFork(call_id="C-5", translate=tr, whisper=wh, outbound=out, next_seq=lambda: next(seq))
    await fork.start()
    await fork.feed("AAAA")
    await asyncio.sleep(0.20)
    await fork.aclose()

    m = fork.metrics()
    assert m["translate_first_event_ms"] is not None
    assert m["whisper_first_event_ms"] is not None
    # whisper has bigger artificial delay
    assert m["whisper_first_event_ms"] > m["translate_first_event_ms"]


@pytest.mark.asyncio
async def test_aclose_idempotent_and_closes_both() -> None:
    tr = FakeConnection(name="translate", _scripted=[FakeEvent(type="__stop__")])
    wh = FakeConnection(name="whisper", _scripted=[FakeEvent(type="__stop__")])
    out: asyncio.Queue = asyncio.Queue()
    fork = AudioFork(call_id="C-6", translate=tr, whisper=wh, outbound=out, next_seq=lambda: 1)
    await fork.start()
    await fork.aclose()
    await fork.aclose()
    assert tr.closed and wh.closed
