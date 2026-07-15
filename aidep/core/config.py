"""
Core configuration using pydantic-settings + YAML.
Env vars override config.yaml values.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings.

    Priority (highest → lowest):
        1. Environment variables
        2. .env file
        3. config.yaml
        4. Defaults declared here
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "AIDEP"
    app_version: str = "1.0.0"
    app_env: str = "development"
    app_debug: bool = True

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = (
        "postgresql+psycopg2://aidep:aidep_secret@localhost:5432/aidep_db"
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_model: str = "mock"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048
    llm_timeout: int = 120

    # API keys (read from env)
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None

    # ── Pipeline ──────────────────────────────────────────────────────────────
    num_instructions_to_generate: int = 10
    validation_similarity_threshold: float = 0.7
    quality_threshold: float = 0.65
    include_seed_tasks: bool = True

    # ── Storage ───────────────────────────────────────────────────────────────
    output_dir: str = "datasets"
    intermediate_dir: str = "datasets/intermediate"
    archives_dir: str = "datasets/archives"

    # ── Seed ──────────────────────────────────────────────────────────────────
    seed_tasks_path: str = ""


def _load_yaml_config(path: str = "config.yaml") -> dict:
    """Load YAML config if it exists; returns empty dict otherwise."""
    p = Path(path)
    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        # Flatten nested keys (app.name → app_name, llm.model → llm_model, etc.)
        flat: dict = {}
        for section, values in raw.items():
            if isinstance(values, dict):
                for k, v in values.items():
                    flat[f"{section}_{k}"] = v
            else:
                flat[section] = values
        return flat
    return {}


def _build_settings() -> Settings:
    """Build Settings, pre-seeding with YAML values."""
    yaml_defaults = _load_yaml_config()
    # pydantic-settings env-vars will still override these
    return Settings(**{k: v for k, v in yaml_defaults.items() if v is not None})


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return _build_settings()
