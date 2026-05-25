"""Tests for backend/scripts/smoke_rt2.py — CLI plumbing + session builder.

Live Foundry streaming covered by `# pragma: no cover`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.realtime.sessions import ASSISTANT_SESSION
from scripts.smoke_rt2 import build_session, main


def test_build_session_overrides_reasoning_effort() -> None:
    s = build_session("low", None)
    assert s["reasoning"] == {"effort": "low"}
    # Should not mutate original
    assert ASSISTANT_SESSION["reasoning"] == {"effort": "high"}


def test_build_session_appends_order_hint() -> None:
    s = build_session("medium", "A12345")
    assert "A12345" in s["instructions"]
    assert "get_order" in s["instructions"]
    # Original kept clean
    assert "A12345" not in ASSISTANT_SESSION["instructions"]


def test_build_session_no_hint_when_omitted() -> None:
    base_len = len(ASSISTANT_SESSION["instructions"])
    s = build_session("high", None)
    assert len(s["instructions"]) == base_len


def test_main_missing_file_returns_2(tmp_path: Path) -> None:
    rc = main([str(tmp_path / "nope.wav")])
    assert rc == 2


def test_main_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
