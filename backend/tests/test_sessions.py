"""Tests for backend/app/realtime/sessions.py — verify the three session
configs match docs/12 character-for-character on the critical fields.

We do NOT inline-copy the full docs blob; instead we assert each documented
contract field-by-field. If you change the SOT here, also update docs/12.
"""
from __future__ import annotations

import pytest

from app.realtime.sessions import (
    ASSISTANT_SESSION,
    TRANSLATE_SESSION,
    WHISPER_SESSION,
    get_session,
)

# ---- translate (§12.2) ----


class TestTranslateSession:
    def test_modalities(self) -> None:
        assert TRANSLATE_SESSION["modalities"] == ["audio", "text"]

    def test_voice_alloy(self) -> None:
        assert TRANSLATE_SESSION["voice"] == "alloy"

    def test_audio_formats_pcm16(self) -> None:
        assert TRANSLATE_SESSION["input_audio_format"] == "pcm16"
        assert TRANSLATE_SESSION["output_audio_format"] == "pcm16"

    def test_no_input_transcription(self) -> None:
        assert TRANSLATE_SESSION["input_audio_transcription"] is None

    def test_server_vad(self) -> None:
        td = TRANSLATE_SESSION["turn_detection"]
        assert td["type"] == "server_vad"
        assert td["threshold"] == 0.5
        assert td["silence_duration_ms"] == 500
        assert td["create_response"] is True

    def test_temperature_0_6(self) -> None:
        assert TRANSLATE_SESSION["temperature"] == 0.6

    def test_no_tools(self) -> None:
        assert TRANSLATE_SESSION["tools"] == []
        assert TRANSLATE_SESSION["tool_choice"] == "none"

    def test_instructions_mention_bidirectional(self) -> None:
        instr = TRANSLATE_SESSION["instructions"]
        assert "中文" in instr and "英文" in instr
        assert "双向" in instr or "口译" in instr


# ---- whisper (§12.3) ----


class TestWhisperSession:
    def test_text_only(self) -> None:
        assert WHISPER_SESSION["modalities"] == ["text"]
        assert WHISPER_SESSION["output_audio_format"] is None
        assert WHISPER_SESSION["voice"] is None

    def test_input_transcription_present(self) -> None:
        t = WHISPER_SESSION["input_audio_transcription"]
        assert t is not None
        assert t["model"] == "whisper-1"
        assert t["language"] is None
        assert "订单号" in t["prompt"]

    def test_silence_700_no_response(self) -> None:
        td = WHISPER_SESSION["turn_detection"]
        assert td["silence_duration_ms"] == 700
        assert td["create_response"] is False

    def test_temperature_zero(self) -> None:
        assert WHISPER_SESSION["temperature"] == 0.0


# ---- assistant (§12.4) ----


class TestAssistantSession:
    def test_modalities(self) -> None:
        assert ASSISTANT_SESSION["modalities"] == ["audio", "text"]

    def test_voice_marin(self) -> None:
        assert ASSISTANT_SESSION["voice"] == "marin"

    def test_reasoning_high(self) -> None:
        assert ASSISTANT_SESSION["reasoning"] == {"effort": "high"}

    def test_max_tokens_1024(self) -> None:
        assert ASSISTANT_SESSION["max_response_output_tokens"] == 1024

    def test_three_tools_required(self) -> None:
        names = sorted(t["name"] for t in ASSISTANT_SESSION["tools"])
        assert names == ["check_insurance", "check_tariff", "get_order"]

    def test_tool_choice_auto(self) -> None:
        assert ASSISTANT_SESSION["tool_choice"] == "auto"

    def test_tools_have_strict_schema(self) -> None:
        for t in ASSISTANT_SESSION["tools"]:
            params = t["parameters"]
            assert params["type"] == "object"
            assert params["additionalProperties"] is False
            assert isinstance(params["required"], list) and params["required"]

    def test_input_transcription_zh(self) -> None:
        t = ASSISTANT_SESSION["input_audio_transcription"]
        assert t == {"model": "whisper-1", "language": "zh"}


# ---- get_session() helper ----


class TestGetSession:
    @pytest.mark.parametrize("kind", ["translate", "whisper", "assistant"])
    def test_returns_deep_copy(self, kind: str) -> None:
        a = get_session(kind)
        b = get_session(kind)
        assert a == b
        a["modalities"].append("MUTATED")
        c = get_session(kind)
        assert "MUTATED" not in c["modalities"]

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown session kind"):
            get_session("nope")
