"""Tests for backend/scripts/smoke_translate.py — wav helpers + CLI plumbing.

Does NOT hit the live Foundry endpoint; the streaming `run_smoke` coroutine is
covered by a separate `pragma: no cover` since it needs Azure creds.
"""
from __future__ import annotations

import wave
from pathlib import Path

import pytest

from scripts.smoke_translate import (
    SAMPLE_RATE,
    main,
    make_synthetic_pcm16,
    read_pcm16_wav,
    write_pcm16_wav,
)


def test_make_synthetic_pcm16_length() -> None:
    pcm = make_synthetic_pcm16(seconds=0.5, freq=440.0)
    # 24000 samples/sec * 0.5s * 2 bytes/sample
    assert len(pcm) == int(0.5 * SAMPLE_RATE) * 2


def test_wav_roundtrip(tmp_path: Path) -> None:
    pcm = make_synthetic_pcm16(seconds=0.2)
    p = tmp_path / "x.wav"
    write_pcm16_wav(p, pcm)
    with wave.open(str(p), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == SAMPLE_RATE
    assert read_pcm16_wav(p) == pcm


def test_read_rejects_wrong_format(tmp_path: Path) -> None:
    p = tmp_path / "stereo.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"\x00" * 4)
    with pytest.raises(ValueError, match="need mono 16-bit"):
        read_pcm16_wav(p)


def test_cli_missing_file_returns_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([str(tmp_path / "missing.wav")])
    assert rc == 2
    assert "not found" in capsys.readouterr().err
