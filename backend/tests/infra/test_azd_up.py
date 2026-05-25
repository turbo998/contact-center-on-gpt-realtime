"""Static checks for `azure.yaml` and azd integration wiring.

These tests verify the contract `azd up` relies on without invoking azd itself:
1. azure.yaml schema-shape (services, hosts, docker contexts)
2. Bicep modules tag Container Apps with `azd-service-name` matching azure.yaml
3. main.bicep emits the env vars azd commands need (AZURE_CONTAINER_REGISTRY_ENDPOINT, etc.)
4. preprovision / postdeploy hooks exist and reference required env vars
5. ACR module exists and grants AcrPull to the workload identity
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
AZURE_YAML = ROOT / "azure.yaml"
INFRA = ROOT / "infra"
MAIN_BICEP = INFRA / "main.bicep"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_azure_yaml_exists_and_parses() -> None:
    assert AZURE_YAML.exists(), "azure.yaml must exist at repo root"
    data = yaml.safe_load(_read(AZURE_YAML))
    assert data["name"] == "contact-center-on-gpt-realtime"


def test_azure_yaml_declares_both_services() -> None:
    data = yaml.safe_load(_read(AZURE_YAML))
    services = data["services"]
    assert set(services) == {"backend", "frontend"}
    for name, svc in services.items():
        assert svc["host"] == "containerapp", f"{name} must host on containerapp"
        assert svc["docker"]["path"] == "Dockerfile"
        assert svc["docker"]["context"] == "."


def test_azure_yaml_infra_points_at_bicep_main() -> None:
    data = yaml.safe_load(_read(AZURE_YAML))
    infra = data["infra"]
    assert infra["provider"] == "bicep"
    assert infra["path"] == "infra"
    assert infra["module"] == "main"


def test_azure_yaml_has_preprovision_and_postdeploy_hooks() -> None:
    data = yaml.safe_load(_read(AZURE_YAML))
    hooks = data["hooks"]
    assert "preprovision" in hooks, "preprovision hook required for env-var validation"
    assert "postdeploy" in hooks, "postdeploy hook required for URL summary"
    # Preprovision must check required azd env vars (fail fast).
    pre = hooks["preprovision"]["run"]
    for required in (
        "AZURE_ENV_NAME",
        "AZURE_LOCATION",
        "AZURE_FOUNDRY_ACCOUNT_NAME",
        "AZURE_OPENAI_ENDPOINT",
    ):
        assert required in pre, f"preprovision must validate {required}"
    # Postdeploy must surface URLs.
    post = hooks["postdeploy"]["run"]
    assert "FRONTEND_URL" in post and "BACKEND_URL" in post


def test_backend_container_app_carries_azd_service_name_tag() -> None:
    src = _read(INFRA / "modules" / "container-app-backend.bicep")
    assert "azd-service-name" in src, "backend ACA must tag azd-service-name"
    assert "'backend'" in src, "default serviceName must equal 'backend'"


def test_frontend_container_app_carries_azd_service_name_tag() -> None:
    src = _read(INFRA / "modules" / "container-app-frontend.bicep")
    assert "azd-service-name" in src
    assert "'frontend'" in src


def test_main_bicep_exposes_azd_required_outputs() -> None:
    src = _read(MAIN_BICEP)
    for output in (
        "AZURE_RESOURCE_GROUP",
        "AZURE_LOCATION",
        "AZURE_CONTAINER_REGISTRY_ENDPOINT",  # azd needs this to push images
        "BACKEND_URL",
        "FRONTEND_URL",
    ):
        assert re.search(rf"^output\s+{output}\s+string", src, re.MULTILINE), (
            f"main.bicep missing required output: {output}"
        )


def test_container_registry_module_exists_and_grants_acr_pull() -> None:
    acr_module = INFRA / "modules" / "container-registry.bicep"
    assert acr_module.exists(), "container-registry.bicep must exist for image push"
    src = _read(acr_module)
    # AcrPull role definition ID — required so UAMI can pull images at runtime.
    assert "7f951dda-4ed3-4680-a7ca-43fe172d538d" in src, (
        "ACR module must assign AcrPull role to the workload UAMI"
    )
    # Admin user must be disabled (we authenticate via UAMI).
    assert re.search(r"adminUserEnabled\s*:\s*false", src), (
        "ACR admin user must be disabled — auth is via UAMI"
    )


def test_main_bicep_wires_acr_into_container_apps() -> None:
    src = _read(MAIN_BICEP)
    assert "module registry " in src, "main.bicep must instantiate the registry module"
    assert "acrLoginServer: registry.outputs.loginServer" in src, (
        "Container Apps must receive ACR login server for the registries block"
    )


def test_frontend_module_supports_acr_managed_identity_pull() -> None:
    src = _read(INFRA / "modules" / "container-app-frontend.bicep")
    assert "managedIdentityId" in src, "frontend must accept UAMI for ACR pull"
    assert "registries" in src, "frontend must declare ACA registries block"
