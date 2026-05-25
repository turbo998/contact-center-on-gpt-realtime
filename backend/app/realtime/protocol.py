"""WebSocket protocol types and helpers.

Implements docs/11-api-contract.md §11.5 — TypedDict definitions for all
inbound/outbound message payloads across /ws/customer, /ws/agent, /ws/assist,
plus an envelope builder, JSON (de)serializer, and error-code registry.

All wire messages are JSON text frames with the shared envelope:

    {"v": 1, "type": "ns.action", "ts": ms, "call_id": str, "seq": int, "payload": {...}}

This module is **pure** — no I/O, no network. WebSocket gateways import
``make_envelope``/``dumps``/``loads`` and validate inbound frames.
"""
from __future__ import annotations

import json
import time
from typing import Any, Literal, TypedDict

__all__ = [
    # envelope + helpers
    "PROTOCOL_VERSION",
    "Envelope",
    "ProtocolError",
    "make_envelope",
    "make_error",
    "dumps",
    "loads",
    # error registry
    "ERROR_CODES",
    # shared
    "Role",
    "TranslateDirection",
    "ReasoningEffort",
    "CallStartPayload",
    "AudioFramePayload",
    "CallEndPayload",
    "CallStartedPayload",
    "WhisperTranscriptDeltaPayload",
    "WhisperTranscriptCompletedPayload",
    "TranslateTextDeltaPayload",
    "TranslateAudioDeltaPayload",
    "TranslateAudioDonePayload",
    "CallEndedPayload",
    # agent
    "EscalateRequestPayload",
    "EscalateAckedPayload",
    # assist
    "AssistStartPayload",
    "AssistStartedPayload",
    "Rt2ReasoningDeltaPayload",
    "Rt2ToolCallPayload",
    "Rt2ToolResultPayload",
    "Rt2DonePayload",
    # error
    "ErrorPayload",
]

PROTOCOL_VERSION: Literal[1] = 1


# ============================================================================
# Envelope
# ============================================================================

class Envelope(TypedDict):
    v: Literal[1]
    type: str
    ts: int
    call_id: str
    seq: int
    payload: dict[str, Any]


class ProtocolError(ValueError):
    """Raised when an inbound frame violates the protocol contract."""


def make_envelope(
    *, type: str, call_id: str, seq: int, payload: dict[str, Any], ts: int | None = None
) -> Envelope:
    """Build a v1 envelope. ``ts`` defaults to current wall-clock millis."""
    return Envelope(
        v=PROTOCOL_VERSION,
        type=type,
        ts=ts if ts is not None else int(time.time() * 1000),
        call_id=call_id,
        seq=seq,
        payload=payload,
    )


def dumps(env: Envelope) -> str:
    """Serialize envelope to a JSON text frame. Uses stdlib json (UTF-8, compact)."""
    return json.dumps(env, separators=(",", ":"), ensure_ascii=False)


_REQUIRED_FIELDS = ("v", "type", "ts", "call_id", "seq", "payload")


def loads(raw: str | bytes) -> Envelope:
    """Parse a wire frame into an Envelope, validating shape and version.

    Raises ProtocolError on:
      - invalid JSON
      - non-object root
      - missing required envelope fields
      - unknown protocol version
    """
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ProtocolError(f"invalid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ProtocolError(f"envelope must be JSON object, got {type(obj).__name__}")
    for f in _REQUIRED_FIELDS:
        if f not in obj:
            raise ProtocolError(f"envelope missing required field: {f!r}")
    if obj["v"] != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version: {obj['v']!r}")
    return obj  # type: ignore[return-value]


# ============================================================================
# Error registry (see docs/11 §11.1.2)
# ============================================================================

#: Maps error code -> retriable flag.
ERROR_CODES: dict[str, bool] = {
    "E_AUTH_FAILED": False,
    "E_FOUNDRY_DISCONNECT": True,
    "E_AUDIO_FORMAT": False,
    "E_AUDIO_TOO_LARGE": True,
    "E_ESCALATE_NO_CONTEXT": False,
    "E_TOOL_TIMEOUT": True,
    "E_TOOL_UNKNOWN": False,
    "E_RATE_LIMIT": True,
    "E_SESSION_EXPIRED": False,
    "E_INTERNAL": False,
}


def make_error(
    *,
    call_id: str,
    seq: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> Envelope:
    """Build an ``error.raised`` envelope. Raises if ``code`` isn't registered."""
    if code not in ERROR_CODES:
        raise ProtocolError(f"unknown error code: {code!r}")
    payload: dict[str, Any] = {
        "code": code,
        "message": message,
        "retriable": ERROR_CODES[code],
    }
    if details is not None:
        payload["details"] = details
    return make_envelope(type="error.raised", call_id=call_id, seq=seq, payload=payload)


# ============================================================================
# Shared payloads (/ws/customer & /ws/agent)
# ============================================================================

Role = Literal["customer", "agent"]
TranslateDirection = Literal["customer_to_agent", "agent_to_customer"]
ReasoningEffort = Literal["minimal", "low", "medium", "high"]


class CallStartPayload(TypedDict):
    role: Role
    lang: str
    target_lang: str


class AudioFramePayload(TypedDict):
    audio: str  # base64 PCM16 LE, 24kHz, mono, 20ms
    duration_ms: int


class CallEndPayload(TypedDict):
    reason: Literal["user_hangup", "timeout", "error"]


class CallStartedPayload(TypedDict):
    call_id: str
    voice: str
    started_at: int


class WhisperTranscriptDeltaPayload(TypedDict):
    text: str
    is_final: bool


class WhisperTranscriptCompletedPayload(TypedDict):
    text: str
    utt_id: str


class TranslateTextDeltaPayload(TypedDict):
    text: str
    direction: TranslateDirection
    is_final: bool


class TranslateAudioDeltaPayload(TypedDict):
    audio: str
    direction: TranslateDirection


class TranslateAudioDonePayload(TypedDict):
    direction: TranslateDirection


class CallEndedPayload(TypedDict):
    duration_ms: int
    audit_url: str


# ============================================================================
# /ws/agent specific
# ============================================================================

class EscalateRequestPayload(TypedDict, total=False):
    order_id: str
    note: str


class EscalateAckedPayload(TypedDict):
    assist_ws_url: str
    context_summary: str


# ============================================================================
# /ws/assist
# ============================================================================

class AssistStartPayload(TypedDict, total=False):
    call_id: str
    context_summary: str
    order_id: str
    reasoning_effort: ReasoningEffort


class AssistStartedPayload(TypedDict):
    session_id: str
    model: str
    reasoning_effort: ReasoningEffort


class Rt2ReasoningDeltaPayload(TypedDict):
    text: str
    step: int


class Rt2ToolCallPayload(TypedDict):
    call_id: str
    name: str
    arguments: dict[str, Any]


class Rt2ToolResultPayload(TypedDict):
    call_id: str
    name: str
    result: dict[str, Any]
    duration_ms: int
    ok: bool


class Rt2DonePayload(TypedDict):
    total_tokens: int
    reasoning_tokens: int
    tool_calls_count: int


# ============================================================================
# Error
# ============================================================================

class ErrorPayload(TypedDict, total=False):
    code: str
    message: str
    retriable: bool
    details: dict[str, Any]
