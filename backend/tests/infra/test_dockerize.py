"""#20 dockerize: static checks on Dockerfiles + compose for production readiness.

No docker daemon needed — parses the files and asserts hardening properties.
Acceptance criteria (issue #20):
  - multi-stage builds
  - healthcheck present
  - compose can reproduce local wiring (dev) AND has a prod profile
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_DF = ROOT / "backend" / "Dockerfile"
FRONTEND_DF = ROOT / "frontend" / "Dockerfile"
COMPOSE = ROOT / "docker-compose.yml"
COMPOSE_PROD = ROOT / "docker-compose.prod.yml"


def _read(p: Path) -> str:
    assert p.exists(), f"missing file: {p}"
    return p.read_text()


# ---------- Backend Dockerfile ----------


def test_backend_dockerfile_is_multistage():
    text = _read(BACKEND_DF)
    stages = re.findall(r"^FROM\s+\S+\s+AS\s+(\w+)", text, re.MULTILINE)
    assert len(stages) >= 2, f"backend Dockerfile must be multi-stage; saw stages={stages}"


def test_backend_dockerfile_runs_as_non_root():
    text = _read(BACKEND_DF)
    assert re.search(r"^USER\s+(?!root\b)\S+", text, re.MULTILINE), (
        "backend Dockerfile must drop privileges with a non-root USER directive"
    )


def test_backend_dockerfile_has_healthcheck():
    assert "HEALTHCHECK" in _read(BACKEND_DF)


def test_backend_dockerignore_excludes_tests_and_audit():
    di = ROOT / "backend" / ".dockerignore"
    assert di.exists(), "backend/.dockerignore required"
    body = di.read_text()
    for pat in ("tests", "audit", "__pycache__", ".pytest_cache"):
        assert pat in body, f"backend/.dockerignore missing pattern: {pat}"


# ---------- Frontend Dockerfile ----------


def test_frontend_dockerfile_is_multistage():
    text = _read(FRONTEND_DF)
    stages = re.findall(r"^FROM\s+\S+\s+AS\s+(\w+)", text, re.MULTILINE)
    assert len(stages) >= 3, (
        f"frontend Dockerfile should have deps/builder/runner stages; saw {stages}"
    )


def test_frontend_dockerfile_runs_as_non_root():
    text = _read(FRONTEND_DF)
    assert re.search(r"^USER\s+(?!root\b)\S+", text, re.MULTILINE), (
        "frontend Dockerfile must drop privileges with a non-root USER directive"
    )


def test_frontend_dockerfile_uses_standalone_output():
    text = _read(FRONTEND_DF)
    # Next standalone output ships a server.js — keeps image small.
    assert "server.js" in text or "standalone" in text, (
        "frontend Dockerfile should use Next.js standalone output for slim image"
    )


def test_frontend_dockerfile_has_healthcheck():
    assert "HEALTHCHECK" in _read(FRONTEND_DF)


def test_frontend_next_config_enables_standalone():
    cfg = (ROOT / "frontend" / "next.config.mjs").read_text()
    assert "standalone" in cfg, (
        "frontend/next.config.mjs must set output: 'standalone' for slim Docker image"
    )


def test_frontend_dockerignore_excludes_dev_artifacts():
    di = ROOT / "frontend" / ".dockerignore"
    assert di.exists(), "frontend/.dockerignore required"
    body = di.read_text()
    for pat in ("node_modules", ".next", "__tests__", "*.test.*"):
        assert pat in body, f"frontend/.dockerignore missing pattern: {pat}"


# ---------- Compose ----------


def test_compose_dev_has_both_services_and_dev_command():
    text = _read(COMPOSE)
    assert "backend:" in text and "frontend:" in text
    # Dev should mount source and use --reload / npm run dev
    assert "--reload" in text, "dev compose should use uvicorn --reload"


def test_compose_prod_overlay_exists_and_omits_bind_mounts():
    text = _read(COMPOSE_PROD)
    assert "backend:" in text and "frontend:" in text
    # Strip YAML comments so doc strings don't false-positive.
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    # Prod overlay must override the dev command — no --reload / npm run dev.
    assert "--reload" not in code, "prod compose must not use uvicorn --reload"
    assert "npm run dev" not in code, "prod compose must not use npm run dev"
    # Prod must define healthchecks for both services
    assert code.count("healthcheck:") >= 2, "prod compose needs healthchecks for both services"


def test_compose_prod_uses_restart_policy():
    text = _read(COMPOSE_PROD)
    assert "restart:" in text, "prod compose should set a restart policy"


@pytest.mark.parametrize(
    "env_var",
    [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "DEPLOYMENT_TRANSLATE",
        "DEPLOYMENT_WHISPER",
        "DEPLOYMENT_ASSISTANT",
    ],
)
def test_compose_dev_passes_required_env(env_var: str):
    assert env_var in _read(COMPOSE)
