"""AssistantPipe — rt-2 session manager for /ws/assist (#10 escalate-backend).

Spec: docs/11 §11.4 (assist envelopes), docs/12 §12.4 (ASSISTANT_SESSION),
docs/13-mock-data-and-tools.md (tools), issue #10.

Design
------
One ``AssistantPipe`` per assist session. It owns:
  - a ``SessionConnection`` to gpt-realtime-2 (Foundry),
  - a ``ToolDispatcher`` wired to the local mock tools,
  - an outbound ``asyncio.Queue`` shared with /ws/assist (gateway_base reads
    from it and ships envelopes to the agent UI),
  - an event-loop receiver that translates Foundry events into ``rt2.*``
    outbound envelopes (docs/11 §11.4.2).

Lifecycle::

    pipe.open()                       # session.update + initial response.create
    asyncio.create_task(pipe.run_receiver())
    pipe.send_user_text(text)         # agent follow-up question
    pipe.send_audio_frame(b64)        # agent voice follow-up (v0.2)
    pipe.aclose()                     # on assist.end or WS disconnect

The Foundry SDK lives in :class:`AssistantConnection` (no-cover, mirrors
``backend/scripts/smoke_rt2.py``). Tests inject a fake implementing
:class:`AssistantSessionConnection`.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from app.realtime.protocol import Envelope, make_envelope
from app.realtime.sessions import ASSISTANT_SESSION
from app.tools.dispatcher import ToolDispatcher

log = logging.getLogger(__name__)


def build_assistant_session(
    *,
    reasoning_effort: str,
    order_id: str | None,
    context_summary: str,
) -> dict[str, Any]:
    """Clone ASSISTANT_SESSION and inject escalate context.

    Required: at least one of ``order_id`` or ``context_summary``.

    The injected suffix tells rt-2 (a) what the customer call was about and
    (b) which order to look up first. Mirrors the system-prompt extension
    pattern from ``backend/scripts/smoke_rt2.build_session``.
    """
    if not order_id and not context_summary:
        raise ValueError("build_assistant_session requires order_id or context_summary")
    s = copy.deepcopy(ASSISTANT_SESSION)
    s["reasoning"] = {"effort": reasoning_effort}
    parts: list[str] = []
    if context_summary:
        parts.append(f"最近 30 秒对话摘要：{context_summary}")
    if order_id:
        parts.append(
            f"客户订单号：{order_id}。请先调用 get_order 工具确认订单详情，"
            f"再决定是否需要 check_tariff / check_insurance。"
        )
    s["instructions"] = s["instructions"] + "\n\n[本次 escalate 上下文]\n" + "\n".join(parts)
    return s


class AssistantSessionConnection(Protocol):
    """Abstract Foundry rt-2 session connection. Implemented by Fake/Real."""

    async def open(self) -> None: ...
    async def update_session(self, session_config: dict[str, Any]) -> None: ...
    async def append_audio(self, audio_b64: str) -> None: ...
    async def commit(self) -> None: ...
    async def send_event(self, event: dict[str, Any]) -> None: ...
    async def events(self) -> AsyncIterator[Any]: ...
    async def aclose(self) -> None: ...


class AssistantConnection:  # pragma: no cover — wraps Azure OpenAI SDK
    """Real Foundry rt-2 adapter. Mirrors smoke_rt2 streaming pattern.

    Auth: DefaultAzureCredential (Managed Identity in prod; key in dev).
    """

    def __init__(self, *, deployment: str) -> None:
        self.deployment = deployment
        self._cm: Any = None
        self._conn: Any = None

    async def open(self) -> None:
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

    async def update_session(self, session_config: dict[str, Any]) -> None:
        await self._conn.session.update(session=session_config)

    async def append_audio(self, audio_b64: str) -> None:
        await self._conn.input_audio_buffer.append(audio=audio_b64)

    async def commit(self) -> None:
        await self._conn.input_audio_buffer.commit()

    async def send_event(self, event: dict[str, Any]) -> None:
        # The SDK exposes typed senders; we proxy to the raw connection so
        # AssistantPipe can issue conversation.item.create / response.create
        # uniformly. Fall back to the typed method when possible.
        t = event.get("type")
        if t == "response.create":
            await self._conn.response.create()
            return
        if t == "conversation.item.create":
            await self._conn.conversation.item.create(item=event["item"])
            return
        # Unknown event type — let the SDK reject it loudly.
        await self._conn.send(event)  # type: ignore[attr-defined]

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


# ---- Event helpers ---------------------------------------------------------


def _ev_attr(ev: Any, key: str, default: Any = None) -> Any:
    """Read a field from either a dict event or an SDK pydantic object."""
    if isinstance(ev, dict):
        return ev.get(key, default)
    return getattr(ev, key, default)


def _ev_type(ev: Any) -> str:
    return str(_ev_attr(ev, "type", ""))


class AssistantPipe:
    """Drive one rt-2 assist session: open → run_receiver → aclose."""

    def __init__(
        self,
        *,
        call_id: str,
        conn: AssistantSessionConnection,
        outbound: asyncio.Queue,
        next_seq: Callable[[], int],
        reasoning_effort: str,
        order_id: str | None,
        context_summary: str,
    ) -> None:
        self.call_id = call_id
        self.conn = conn
        self.outbound = outbound
        self.next_seq = next_seq
        self.reasoning_effort = reasoning_effort
        self.order_id = order_id
        self.context_summary = context_summary

        self._dispatcher = ToolDispatcher(send_to_rt2=self.conn.send_event)
        # function_call argument buffers, keyed by rt-2 call_id (per tool call).
        self._fc_buffers: dict[str, dict[str, Any]] = {}
        # Track in-flight dispatch tasks so aclose can drain them.
        self._dispatch_tasks: set[asyncio.Task] = set()
        # Token + tool-call counters for rt2.done payload.
        self._tool_calls_count = 0

    # ---- lifecycle ---------------------------------------------------------

    async def open(self) -> None:
        await self.conn.open()
        session_cfg = build_assistant_session(
            reasoning_effort=self.reasoning_effort,
            order_id=self.order_id,
            context_summary=self.context_summary,
        )
        await self.conn.update_session(session_cfg)
        # Kick rt-2 to start reasoning over the injected context.
        await self.conn.send_event({"type": "response.create"})

    async def aclose(self) -> None:
        for task in list(self._dispatch_tasks):
            if not task.done():
                task.cancel()
        await self.conn.aclose()

    # ---- agent input -------------------------------------------------------

    async def send_user_text(self, text: str) -> None:
        """Inject an agent follow-up text into the rt-2 conversation."""
        await self.conn.send_event({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        })
        await self.conn.send_event({"type": "response.create"})

    async def send_audio_frame(self, audio_b64: str) -> None:
        """Append agent voice frame to rt-2 input buffer (v0.2 path)."""
        await self.conn.append_audio(audio_b64)

    # ---- event loop --------------------------------------------------------

    async def run_receiver(self) -> None:
        """Translate Foundry rt-2 events into rt2.* outbound envelopes."""
        t0 = time.perf_counter()
        usage: dict[str, Any] = {}
        try:
            async for ev in self.conn.events():
                etype = _ev_type(ev)
                try:
                    if etype in ("response.reasoning.delta", "response.reasoning_text.delta"):
                        await self._emit("rt2.reasoning.delta", {
                            "text": str(_ev_attr(ev, "delta", "")),
                        })
                    elif etype in (
                        "response.reasoning.done",
                        "response.reasoning_text.done",
                        "response.reasoning.completed",
                    ):
                        await self._emit("rt2.reasoning.completed", {
                            "summary": str(_ev_attr(ev, "text", "") or _ev_attr(ev, "summary", "")),
                        })
                    elif etype == "response.audio.delta":
                        await self._emit("rt2.audio.delta", {
                            "audio": str(_ev_attr(ev, "delta", "")),
                        })
                    elif etype == "response.audio.done":
                        await self._emit("rt2.audio.done", {})
                    elif etype in ("response.text.delta", "response.audio_transcript.delta"):
                        await self._emit("rt2.text.delta", {
                            "text": str(_ev_attr(ev, "delta", "")),
                        })
                    elif etype == "response.function_call_arguments.delta":
                        self._buffer_fc_delta(ev)
                    elif etype == "response.function_call_arguments.done":
                        await self._handle_fc_done(ev)
                    elif etype == "response.done":
                        resp = _ev_attr(ev, "response", {}) or {}
                        u = resp.get("usage", {}) if isinstance(resp, dict) else getattr(resp, "usage", {})
                        if u:
                            usage = u if isinstance(u, dict) else dict(u)
                    elif etype == "error":
                        await self._emit("error.raised", {
                            "code": "E_RT2_STREAM",
                            "message": str(_ev_attr(ev, "message", "rt2 error")),
                            "retriable": False,
                        })
                    # All other events (session.*, rate_limits.*, etc.) ignored.
                except Exception:  # noqa: BLE001
                    log.exception("rt2.receiver.event_failed", extra={"etype": etype})
        finally:
            # Drain in-flight dispatcher tasks before emitting rt2.done.
            if self._dispatch_tasks:
                await asyncio.gather(*self._dispatch_tasks, return_exceptions=True)
            await self._emit("rt2.done", {
                "total_tokens": _safe_int(usage.get("total_tokens") if isinstance(usage, dict) else None),
                "reasoning_tokens": _safe_int(
                    (usage.get("output_token_details", {}) or {}).get("reasoning_tokens")
                    if isinstance(usage, dict) else None
                ),
                "tool_calls_count": self._tool_calls_count,
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            })

    # ---- internals ---------------------------------------------------------

    def _buffer_fc_delta(self, ev: Any) -> None:
        cid = str(_ev_attr(ev, "call_id", ""))
        if not cid:
            return
        buf = self._fc_buffers.setdefault(cid, {
            "name": _ev_attr(ev, "name", ""),
            "args": "",
        })
        if not buf["name"]:
            buf["name"] = _ev_attr(ev, "name", "")
        buf["args"] += str(_ev_attr(ev, "delta", ""))

    async def _handle_fc_done(self, ev: Any) -> None:
        cid = str(_ev_attr(ev, "call_id", ""))
        name = str(_ev_attr(ev, "name", "") or self._fc_buffers.get(cid, {}).get("name", ""))
        args_json = str(
            _ev_attr(ev, "arguments", "")
            or self._fc_buffers.get(cid, {}).get("args", "")
            or "{}"
        )
        self._fc_buffers.pop(cid, None)
        self._tool_calls_count += 1

        # Emit rt2.tool_call to the agent UI (parsed arguments for display).
        import json
        try:
            parsed = json.loads(args_json or "{}")
        except json.JSONDecodeError:
            parsed = {"_raw": args_json}
        await self._emit("rt2.tool_call", {
            "call_id": cid, "name": name, "arguments": parsed,
        })

        # Wrap the dispatcher so we can also surface the result to the UI.
        results: dict[str, Any] = {}
        original_send = self._dispatcher._send  # type: ignore[attr-defined]

        async def capturing_send(event: dict[str, Any]) -> None:
            if event.get("type") == "conversation.item.create":
                item = event.get("item", {})
                if item.get("type") == "function_call_output" and item.get("call_id") == cid:
                    raw = item.get("output", "{}")
                    try:
                        results["payload"] = json.loads(raw)
                    except json.JSONDecodeError:
                        results["payload"] = {"_raw": raw}
            await original_send(event)

        self._dispatcher._send = capturing_send  # type: ignore[attr-defined]
        start = time.perf_counter()
        try:
            task = asyncio.create_task(
                self._dispatcher.dispatch(name=name, call_id=cid, arguments_json=args_json)
            )
            self._dispatch_tasks.add(task)
            try:
                await task
            finally:
                self._dispatch_tasks.discard(task)
        finally:
            self._dispatcher._send = original_send  # type: ignore[attr-defined]

        payload = results.get("payload", {})
        ok = "error" not in payload
        envelope_payload = {
            "call_id": cid,
            "name": name,
            "duration_ms": int((time.perf_counter() - start) * 1000),
            "ok": ok,
        }
        if ok:
            envelope_payload["result"] = payload
        else:
            envelope_payload["error"] = payload.get("error", "unknown")
            envelope_payload["detail"] = payload.get("detail", "")
        await self._emit("rt2.tool_result", envelope_payload)

    async def _emit(self, etype: str, payload: dict[str, Any]) -> None:
        env: Envelope = make_envelope(
            type=etype, call_id=self.call_id, seq=self.next_seq(), payload=payload,
        )
        await self.outbound.put(env)


def _safe_int(value: Any) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0
