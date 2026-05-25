"""Tests for backend/scripts/smoke_whisper.py — CLI plumbing only.

Live Foundry streaming covered by `# pragma: no cover`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.smoke_whisper import main


def test_cli_missing_file_returns_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main([str(tmp_path / "missing.wav")])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_imports_whisper_session() -> None:
    """Verify the script wires up the right session config."""
    from app.realtime.sessions import WHISPER_SESSION
    from scripts import smoke_whisper

    assert smoke_whisper.WHISPER_SESSION is WHISPER_SESSION
