"""#21 bicep-infra: structural + lint tests for Bicep modules.

Requires `az bicep` (already required to deploy). Skips gracefully if absent.

Acceptance criteria covered:
  - All 6 modules exist and are non-empty (no `TODO` stub markers).
  - `az bicep build infra/main.bicep` exits 0 with no warnings.
  - `foundry-role.bicep` assigns the built-in `Cognitive Services OpenAI User` role
    (role definition GUID `5e0bd9bd-7b93-4f28-af87-19fc36ad61bd`) to the MI's principalId.
  - main.bicep wires every module.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
INFRA = ROOT / "infra"
MODULES = INFRA / "modules"

REQUIRED_MODULES = [
    "log-analytics.bicep",
    "container-env.bicep",
    "managed-identity.bicep",
    "foundry-role.bicep",
    "container-app-backend.bicep",
    "container-app-frontend.bicep",
]

OPENAI_USER_ROLE_GUID = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


@pytest.mark.parametrize("mod", REQUIRED_MODULES)
def test_module_exists_and_is_implemented(mod: str):
    p = MODULES / mod
    assert p.exists(), f"missing module: {mod}"
    text = _read(p)
    assert len(text) > 200, f"{mod} looks like a stub (<200 bytes)"
    # No TODO stub markers from the placeholder version.
    assert "TODO (issue #19 bicep-infra)" not in text, f"{mod} still contains stub TODO"


def test_main_bicep_references_all_modules():
    text = _read(INFRA / "main.bicep")
    for mod in REQUIRED_MODULES:
        # main.bicep imports as modules/<name> — strip dir.
        assert f"modules/{mod}" in text, f"main.bicep does not reference modules/{mod}"


def test_foundry_role_assigns_openai_user_role():
    text = _read(MODULES / "foundry-role.bicep")
    assert OPENAI_USER_ROLE_GUID in text, (
        "foundry-role.bicep must reference the 'Cognitive Services OpenAI User' "
        f"built-in role GUID {OPENAI_USER_ROLE_GUID}"
    )
    assert "Microsoft.Authorization/roleAssignments" in text
    assert "principalId" in text
    # principalType must be ServicePrincipal for managed identities.
    assert "ServicePrincipal" in text


def test_backend_module_uses_user_assigned_identity():
    text = _read(MODULES / "container-app-backend.bicep")
    assert "UserAssigned" in text
    assert "AZURE_CLIENT_ID" in text, "backend must pass AZURE_CLIENT_ID for DefaultAzureCredential"
    assert "AZURE_OPENAI_ENDPOINT" in text


def test_frontend_module_derives_wss_url():
    text = _read(MODULES / "container-app-frontend.bicep")
    assert "wss://" in text or "replace(backendUrl" in text


def test_az_bicep_build_clean():
    """az bicep build must succeed with zero warnings."""
    az = shutil.which("az")
    if az is None:
        pytest.skip("az CLI not installed")
    result = subprocess.run(
        [az, "bicep", "build", "--file", str(INFRA / "main.bicep")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"az bicep build failed:\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}"
    )
    combined = (result.stdout + result.stderr).lower()
    assert "warning" not in combined, (
        f"bicep build produced warnings:\n{result.stdout}\n{result.stderr}"
    )
