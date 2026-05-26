"""Ensure Bicep-injected env var names match what backend code reads.

Regression: v0.1.0 shipped with bicep injecting
``AZURE_OPENAI_DEPLOYMENT_TRANSLATE/WHISPER/REALTIME2`` while ``app.main``
reads ``DEPLOYMENT_TRANSLATE/WHISPER/RT2``. Result: factories returned None
in production and the deployed backend silently fell back to handshake-only
mode — never actually calling the real Foundry models.

This test locks the contract between IaC and code.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BICEP = REPO / "infra" / "modules" / "container-app-backend.bicep"
MAIN_PY = REPO / "backend" / "app" / "main.py"


REQUIRED_ENV_NAMES = (
    "DEPLOYMENT_TRANSLATE",
    "DEPLOYMENT_WHISPER",
    "DEPLOYMENT_RT2",
)


def test_bicep_injects_env_names_backend_actually_reads():
    bicep_text = BICEP.read_text()
    main_text = MAIN_PY.read_text()
    for name in REQUIRED_ENV_NAMES:
        assert f"name: '{name}'" in bicep_text, (
            f"bicep must inject env var named exactly '{name}' "
            f"(backend reads os.getenv('{name}'))"
        )
        assert f'"{name}"' in main_text, (
            f"backend code must still read os.getenv('{name}') — "
            "if you renamed the env var, update both sides + this test."
        )
