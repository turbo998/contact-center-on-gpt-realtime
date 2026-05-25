"""Dual-pipe audio fork — fans /ws/customer audio into translate + whisper.

Spec: docs/05 §5.2 (fork-audio), docs/11 §11.2.2 (outbound events),
issue #9 acceptance.

Design
------
Two independent Foundry Realtime sessions per customer call:
  - **translate** (gpt-realtime / translate session) — emits audio + text deltas
    that we re-wrap as ``translate.audio.delta`` / ``translate.text.delta`` /
    ``translate.audio.done`` envelopes.
  - **whisper** (gpt-realtime-mini-transcribe / whisper session) — emits
    incremental transcripts that we re-wrap as ``whisper.transcript.delta`` /
    ``whisper.transcript.completed`` envelopes.

Both pipes share the **same** raw PCM16 frames (one ``feed()`` call appends to
both). Each pipe runs its own receiver coroutine; if one pipe raises, we emit
``error.raised{ code: E_FOUNDRY_DISCONNECT }`` and keep the other pipe alive
(acceptance criterion #3).

The Foundry SDK call lives in ``FoundryConnection`` (no-cover, mirrors
``backend/scripts/smoke_translate.py``). Tests inject a ``FakeConnection``
implementing the ``SessionConnection`` protocol.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from app.realtime.protocol import Envelope, make_envelope

log = logging.getLogger(__name__)


# Direction labels for translate envelopes (docs/11 §11.2.2).
DIR_CUSTOMER = "customer_to_agent"


class FoundryConnection:  # pragma: no cover — wraps the Azure OpenAI SDK
    """Real Foundry Realtime connection adapter (translate or whisper).

    Mirrors the streaming pattern from ``backend/scripts/smoke_translate.py``.
    Implements the :class:`SessionConnection` protocol so :class:`AudioFork`
    can drive either pipe.

    Auth: DefaultAzureCredential (Managed Identity in prod; key in dev).
    Created lazily; the actual SDK objects are bound in :meth:`open`.
    """

    def __init__(self, *, deployment: str, session_config: dict) -> None:
        self.deployment = deployment
        self.session_config = session_config
        self._cm: Any = None  # async-context manager from SDK
        self._conn: Any = None

    async def open(self) -> None:
        import base64  # noqa: F401  (kept for symmetry with append_audio docs)
        import os

        from azure.identity.aio import (
            DefaultAzureCredential,
            get_bearer_token_provider,
        )
        from openai import AsyncAzureOpenAI

        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
        if os.getenv("APP_ENV", "development") == "development" and os.getenv("AZURE_OPENAI_API_KEY"):
            client = AsyncAzureOpenAI(
                api_key=os.environ["AZURE_OPENAI_API_KEY"],
                api_version=api_version, azure_endpoint=endpoint,
            )
        else:
            cred = DefaultAzureCredential()
            tp = get_bearer_token_provider(cred, "https://cognitiveservices.azure.com/.default")
            client = AsyncAzureOpenAI(
                azure_ad_token_provider=tp,
                api_version=api_version, azure_endpoint=endpoint,
            )
        self._cm = client.beta.realtime.connect(model=self.deployment)
        self._conn = await self._cm.__aenter__()
        await self._conn.session.update(session=self.session_config)

    async def append_audio(self, audio_b64: str) -> None:
        await self._conn.input_audio_buffer.append(audio=audio_b64)

    async def commit(self) -> None:
        await self._conn.input_audio_buffer.commit()

    async def events(self) -> AsyncIterator[Any]:
        async for ev in self._conn:
            yield ev

    async def aclose(self) -> None:
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            finally:
                self._cm = None
                self._conn = None


class SessionConnection(Protocol):
    """Abstract Foundry session connection. Implemented by Fake/Foundry."""

    async def append_audio(self, audio_b64: str) -> None: ...
    async def commit(self) -> None: ...
    async def events(self) -> AsyncIterator[Any]: ...
    async def aclose(self) -> None: ...


class AudioFork:
    """Fan one PCM stream into two Foundry sessions; merge events into outbound."""

    def __init__(
        self,
        *,
        call_id: str,
        translate: SessionConnection,
        whisper: SessionConnection,
        outbound: asyncio.Queue,
        next_seq: Callable[[], int],
        direction: str = DIR_CUSTOMER,
    ) -> None:
        self.call_id = call_id
        self._tr = translate
        self._wh = whisper
        self._out = outbound
        self._next_seq = next_seq
        self._direction = direction
        self._tasks: list[asyncio.Task] = []
        self._t_first_feed: float | None = None
        self._t_first_translate_event: float | None = None
        self._t_first_whisper_event: float | None = None
        self._closed = False

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        self._tasks.append(asyncio.create_task(
            self._run_pipe(self._tr, self._on_translate_event, "translate"),
            name=f"fork-translate-{self.call_id}",
        ))
        self._tasks.append(asyncio.create_task(
            self._run_pipe(self._wh, self._on_whisper_event, "whisper"),
            name=f"fork-whisper-{self.call_id}",
        ))

    async def feed(self, audio_b64: str) -> None:
        if self._t_first_feed is None:
            self._t_first_feed = time.perf_counter()
        # Best-effort: if a pipe is broken, log and continue with the other.
        await asyncio.gather(
            self._safe_append(self._tr, audio_b64, "translate"),
            self._safe_append(self._wh, audio_b64, "whisper"),
        )

    async def commit(self) -> None:
        await asyncio.gather(
            self._safe(self._tr.commit, "translate.commit"),
            self._safe(self._wh.commit, "whisper.commit"),
        )

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await asyncio.gather(
            self._safe(self._tr.aclose, "translate.close"),
            self._safe(self._wh.aclose, "whisper.close"),
        )
        for t in self._tasks:
            if not t.done():
                t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    def metrics(self) -> dict[str, float | None]:
        def ms(t: float | None) -> float | None:
            if t is None or self._t_first_feed is None:
                return None
            return (t - self._t_first_feed) * 1000

        return {
            "translate_first_event_ms": ms(self._t_first_translate_event),
            "whisper_first_event_ms": ms(self._t_first_whisper_event),
        }

    # ------------------------------------------------------------------ pipes

    async def _safe_append(self, conn: SessionConnection, audio_b64: str, name: str) -> None:
        try:
            await conn.append_audio(audio_b64)
        except Exception as e:  # noqa: BLE001
            log.warning("append_audio failed pipe=%s err=%r", name, e)

    async def _safe(self, fn: Callable, label: str) -> None:
        try:
            await fn()
        except Exception as e:  # noqa: BLE001
            log.warning("call failed label=%s err=%r", label, e)

    async def _run_pipe(
        self,
        conn: SessionConnection,
        handler: Callable[[Any], Envelope | None],
        name: str,
    ) -> None:
        try:
            async for event in await self._wrap_events(conn):
                if name == "translate" and self._t_first_translate_event is None:
                    self._t_first_translate_event = time.perf_counter()
                if name == "whisper" and self._t_first_whisper_event is None:
                    self._t_first_whisper_event = time.perf_counter()
                env = handler(event)
                if env is not None:
                    await self._out.put(env)
        except Exception as e:  # noqa: BLE001
            log.warning("pipe %s crashed err=%r", name, e)
            await self._out.put(make_envelope(
                type="error.raised", call_id=self.call_id, seq=self._next_seq(),
                payload={
                    "code": "E_FOUNDRY_DISCONNECT",
                    "message": f"{name} pipe failed: {e!r}",
                    "retriable": True,
                },
            ))

    @staticmethod
    async def _wrap_events(conn: SessionConnection) -> AsyncIterator[Any]:
        """events() is either a coroutine returning an async iter, or an async gen.

        SDKs differ; we await once and only iterate if the result is awaitable-iterable.
        """
        ev = conn.events()
        if hasattr(ev, "__aiter__"):
            return ev  # async generator returned synchronously
        return await ev  # type: ignore[return-value]

    # ------------------------------------------------------------------ event mappers

    def _on_translate_event(self, event: Any) -> Envelope | None:
        et = getattr(event, "type", "") or (event.get("type", "") if isinstance(event, dict) else "")
        if et in ("response.text.delta", "response.audio_transcript.delta"):
            delta = getattr(event, "delta", "") or (event.get("delta", "") if isinstance(event, dict) else "")
            return make_envelope(
                type="translate.text.delta", call_id=self.call_id, seq=self._next_seq(),
                payload={"text": delta, "direction": self._direction, "is_final": False},
            )
        if et == "response.audio.delta":
            delta = getattr(event, "delta", "") or (event.get("delta", "") if isinstance(event, dict) else "")
            return make_envelope(
                type="translate.audio.delta", call_id=self.call_id, seq=self._next_seq(),
                payload={"audio": delta, "direction": self._direction},
            )
        if et in ("response.audio.done", "response.done"):
            return make_envelope(
                type="translate.audio.done", call_id=self.call_id, seq=self._next_seq(),
                payload={"direction": self._direction},
            )
        return None

    def _on_whisper_event(self, event: Any) -> Envelope | None:
        et = getattr(event, "type", "") or (event.get("type", "") if isinstance(event, dict) else "")
        if et == "conversation.item.input_audio_transcription.delta":
            delta = getattr(event, "delta", "") or (event.get("delta", "") if isinstance(event, dict) else "")
            return make_envelope(
                type="whisper.transcript.delta", call_id=self.call_id, seq=self._next_seq(),
                payload={"text": delta, "is_final": False},
            )
        if et == "conversation.item.input_audio_transcription.completed":
            text = (
                getattr(event, "transcript", "")
                or (event.get("transcript", "") if isinstance(event, dict) else "")
            )
            return make_envelope(
                type="whisper.transcript.completed", call_id=self.call_id, seq=self._next_seq(),
                payload={"text": text, "utt_id": f"utt-{self._next_seq()}"},
            )
        return None
