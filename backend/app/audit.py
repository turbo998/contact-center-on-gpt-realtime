"""Append-only JSONL audit logger.

Spec: docs/02 step 6 (audit-{call_id}.jsonl with whisper raw, translate
parallel, rt-2 reasoning + tool calls), docs/04 §4.5, docs/05 §5.2.

Design notes
------------
- One file per session: ``audit-{session_id}.jsonl``.
- One JSON record per line (RFC 7464 jsonl); newline-terminated; UTF-8.
- Append-only — file handles are kept open per session and serialised by an
  asyncio.Lock so concurrent ``log_*`` calls never tear a line.
- Audio base64 deltas are **redacted** (replaced with ``{__redacted__, len}``)
  before write — keeps files <1 MB even for minute-long calls while
  preserving forensic information (size, presence) and the human-readable
  transcript that ships in the same envelope.
- Session-id validation is strict: any path traversal / whitespace / empty
  string raises ``ValueError`` *before* the file is touched.
- Sink abstraction: ``JsonlFileSink`` (default), ``NullSink`` (tests / smoke).
  Blob sink lives in docs/04 §4.5 plan, not in scope for #12.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Protocol

__all__ = ["AuditSink", "JsonlFileSink", "NullSink", "AuditLogger"]


# -------------------- session-id validation --------------------

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_session_id(session_id: str) -> None:
    if not session_id or not _SESSION_ID_RE.match(session_id) or session_id in {".", ".."}:
        raise ValueError(f"unsafe session_id: {session_id!r}")


# -------------------- sink protocol --------------------


class AuditSink(Protocol):
    """Write-only append sink, keyed by session_id."""

    async def write(self, session_id: str, record: dict[str, Any]) -> None: ...
    async def close(self, session_id: str) -> None: ...


# -------------------- file sink --------------------


class JsonlFileSink:
    """Append-only JSONL files under ``base_dir``, one per session.

    Thread-safe across async tasks via a per-instance ``asyncio.Lock``.
    """

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _path(self, session_id: str) -> Path:
        _validate_session_id(session_id)
        return self.base_dir / f"audit-{session_id}.jsonl"

    async def write(self, session_id: str, record: dict[str, Any]) -> None:
        path = self._path(session_id)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        async with self._lock:
            # Open / append / close per write — simpler than per-session FD
            # bookkeeping, and at our throughput (~10–100 records/sec/session)
            # the syscall cost is negligible.
            with path.open("a", encoding="utf-8") as f:
                f.write(line)

    async def close(self, session_id: str) -> None:
        # No-op for per-write open/close; method kept so the Protocol matches
        # future buffered sinks.
        _validate_session_id(session_id)


class NullSink:
    """Drops every record on the floor. Useful for tests / dry runs."""

    async def write(self, session_id: str, record: dict[str, Any]) -> None:
        return

    async def close(self, session_id: str) -> None:
        return


# -------------------- audit logger --------------------


def _ts_ms() -> int:
    return int(time.time() * 1000)


def _redact_audio(payload: dict[str, Any]) -> dict[str, Any]:
    """Replace base64 audio fields with a length-preserving placeholder.

    Targets the rt-2 / translate / whisper field names we know about. Other
    fields are passed through unchanged.
    """
    audio_keys = {"delta", "audio"}
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if k in audio_keys and isinstance(v, str) and len(v) > 64:
            out[k] = {"__redacted__": "base64-audio", "len": len(v)}
        else:
            out[k] = v
    return out


class AuditLogger:
    """High-level audit API on top of any ``AuditSink``."""

    def __init__(self, sink: AuditSink) -> None:
        self._sink = sink

    async def log_event(
        self,
        session_id: str,
        *,
        envelope: dict[str, Any],
        direction: str,
    ) -> None:
        """Record one WS envelope (client→server or server→client)."""
        await self._sink.write(
            session_id,
            {
                "ts_ms": _ts_ms(),
                "kind": "ws_event",
                "direction": direction,
                "envelope": envelope,
            },
        )

    async def log_model_io(
        self,
        session_id: str,
        *,
        model: str,
        direction: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Record one Foundry model in/out event (audio redacted)."""
        await self._sink.write(
            session_id,
            {
                "ts_ms": _ts_ms(),
                "kind": "model_io",
                "model": model,
                "direction": direction,
                "event_type": event_type,
                "payload": _redact_audio(payload),
            },
        )

    async def log_tool_call(
        self,
        session_id: str,
        *,
        call_id: str,
        name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        latency_ms: int,
    ) -> None:
        """Record one rt-2 function-call round trip."""
        await self._sink.write(
            session_id,
            {
                "ts_ms": _ts_ms(),
                "kind": "tool_call",
                "call_id": call_id,
                "name": name,
                "arguments": arguments,
                "result": result,
                "latency_ms": latency_ms,
            },
        )

    async def log_reasoning(
        self,
        session_id: str,
        *,
        trace: str,
        effort: str,
    ) -> None:
        """Record the rt-2 reasoning trace summary at the end of a response."""
        await self._sink.write(
            session_id,
            {
                "ts_ms": _ts_ms(),
                "kind": "reasoning",
                "effort": effort,
                "trace": trace,
            },
        )

    async def close(self, session_id: str) -> None:
        await self._sink.close(session_id)
