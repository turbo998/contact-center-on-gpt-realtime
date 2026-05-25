"""Application settings (pydantic-settings, env-driven).

See docs/04-tech-stack.md and .env.example for the canonical variable list.
TODO (issue #01 scaffold): expand fields, add validators.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2025-04-01-preview"

    deployment_translate: str = "gpt-realtime-translate"
    deployment_whisper: str = "gpt-realtime-whisper"
    deployment_assistant: str = "gpt-realtime-2"

    max_call_duration_sec: int = 900
    audit_dir: str = "./audit"


@lru_cache
def get_settings() -> Settings:
    return Settings()
