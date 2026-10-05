"""Application settings.

All configuration comes from the environment (or the repo-root `.env`). Model providers are
referenced through logical profiles that map to A9 project names (docs/DECISIONS.md,
"Added at implementation start"); no concrete model name appears in application code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # application
    app_env: Literal["development", "test", "production"] = "development"
    debug_mode: bool = True
    # dice: 'manual' pauses a called-for check until the player rolls; 'auto' rolls at once.
    # Per campaign in settings.dice_mode; this is the default (tests run with 'auto').
    dice_mode_default: str = "manual"
    log_level: str = "INFO"
    engine_version: str = "0.1.0-dev"
    default_ruleset: str = "core_adventure"

    # database
    database_url: str = "postgresql+asyncpg://ttrpg:ttrpg@localhost:5434/ttrpg"
    test_database_url: str = "postgresql+asyncpg://ttrpg:ttrpg@localhost:5434/ttrpg_test"
    db_connect_timeout_s: float = 5.0

    # inference (A9 gateway; optional for deterministic development)
    a9_base_url: str = "http://afhserver.tail590cb0.ts.net:8100/v1"
    a9_token: str = ""
    a9_client_name: str = "ai-ttrpg"
    model_profile_fast_structured: str = "ttrpg/local-general"
    model_profile_balanced_reasoning: str = "ttrpg/local-general"
    model_profile_creative_narrative: str = "ttrpg/local-general"
    model_profile_deep_world_author: str = "ttrpg/local-general"
    model_profile_embedding: str = "ttrpg/local-embed"
    model_profile_rerank: str = "ttrpg/local-rerank"
    embedding_dimensions: int = 1024
    provider_mode: Literal["local_only", "local_preferred", "best_available", "cloud_only"] = (
        "local_only"
    )
    cloud_fallback_enabled: bool = False

    # budgets / concurrency
    max_sync_model_calls_per_turn: int = Field(default=4, ge=0)
    hard_cap_sync_model_calls_per_turn: int = Field(default=6, ge=0)
    spotlight_visible_reactions: int = Field(default=2, ge=0)  # AI reactions with a call per turn
    narrator_enabled: bool = True  # stream the Narrator after mechanics (06c)
    max_concurrent_inference: int = Field(default=2, ge=1)

    # world simulation (Milestone 08): a run per crossed boundary, bounded event budget
    simulation_granularity_seconds: int = Field(default=6 * 3600, ge=60)
    simulation_event_budget: int = Field(default=3, ge=1)
    catchup_granularity_seconds: int = Field(default=600, ge=60)
    max_offscreen_catchups_per_turn: int = Field(default=2, ge=0)

    @property
    def inference_configured(self) -> bool:
        return bool(self.a9_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()
