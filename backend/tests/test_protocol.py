"""Tests for backend.app.realtime.protocol — TypedDicts + envelope helpers.

Mirrors docs/11-api-contract.md §11.5 and §11.8 acceptance.
"""
from __future__ import annotations

import time

import pytest

from app.realtime import protocol as p


class TestEnvelope:
    def test_make_envelope_defaults(self) -> None:
        env = p.make_envelope(type="system.ping", call_id="C-1", seq=1, payload={})
        assert env["v"] == 1
        assert env["type"] == "system.ping"
        assert env["call_id"] == "C-1"
        assert env["seq"] == 1
        assert env["payload"] == {}
        # ts auto-populated with current millis (allow 5s skew)
        now_ms = int(time.time() * 1000)
        assert abs(env["ts"] - now_ms) < 5000

    def test_make_envelope_explicit_ts(self) -> None:
        env = p.make_envelope(type="x", call_id="C", seq=0, payload={}, ts=12345)
        assert env["ts"] == 12345

    def test_dumps_loads_roundtrip(self) -> None:
        env = p.make_envelope(type="audio.frame", call_id="C-7", seq=42, payload={"audio": "AAA=", "duration_ms": 20})
        raw = p.dumps(env)
        assert isinstance(raw, str)
        back = p.loads(raw)
        assert back == env

    def test_loads_rejects_non_object(self) -> None:
        with pytest.raises(p.ProtocolError):
            p.loads("[]")
        with pytest.raises(p.ProtocolError):
            p.loads('"oops"')

    def test_loads_rejects_missing_required_fields(self) -> None:
        with pytest.raises(p.ProtocolError):
            p.loads('{"v":1,"type":"x"}')

    def test_loads_rejects_wrong_version(self) -> None:
        with pytest.raises(p.ProtocolError):
            p.loads('{"v":2,"type":"x","ts":1,"call_id":"C","seq":0,"payload":{}}')

    def test_loads_rejects_invalid_json(self) -> None:
        with pytest.raises(p.ProtocolError):
            p.loads("not json {")


class TestErrorCodes:
    @pytest.mark.parametrize(
        "code",
        [
            "E_AUTH_FAILED",
            "E_FOUNDRY_DISCONNECT",
            "E_AUDIO_FORMAT",
            "E_AUDIO_TOO_LARGE",
            "E_ESCALATE_NO_CONTEXT",
            "E_TOOL_TIMEOUT",
            "E_TOOL_UNKNOWN",
            "E_RATE_LIMIT",
            "E_SESSION_EXPIRED",
            "E_INTERNAL",
        ],
    )
    def test_known_codes_present(self, code: str) -> None:
        assert code in p.ERROR_CODES
        assert isinstance(p.ERROR_CODES[code], bool)  # retriable flag

    def test_make_error_envelope(self) -> None:
        env = p.make_error(call_id="C-1", seq=99, code="E_TOOL_TIMEOUT", message="took too long")
        assert env["type"] == "error.raised"
        assert env["payload"]["code"] == "E_TOOL_TIMEOUT"
        assert env["payload"]["retriable"] is True
        assert env["payload"]["message"] == "took too long"

    def test_make_error_unknown_code_raises(self) -> None:
        with pytest.raises(p.ProtocolError):
            p.make_error(call_id="C", seq=0, code="E_NOT_REAL", message="x")


class TestTypedDictsImportable:
    """Smoke test: every TypedDict in docs §11.5 is exported."""

    @pytest.mark.parametrize(
        "name",
        [
            "Envelope",
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
            "EscalateRequestPayload",
            "EscalateAckedPayload",
            "AssistStartPayload",
            "AssistStartedPayload",
            "Rt2ReasoningDeltaPayload",
            "Rt2ToolCallPayload",
            "Rt2ToolResultPayload",
            "Rt2DonePayload",
            "ErrorPayload",
        ],
    )
    def test_typeddict_exported(self, name: str) -> None:
        assert hasattr(p, name), f"{name} missing from backend.app.realtime.protocol"

    def test_construct_call_start_payload(self) -> None:
        # TypedDicts are runtime dicts; just ensure shape works
        payload: p.CallStartPayload = {"role": "customer", "lang": "zh-CN", "target_lang": "en-US"}
        assert payload["role"] == "customer"
