"""Model routing (orchestration §5, §42): role → logical profile → provider + model name.

Profiles map to A9 project/model names from settings; campaigns may override per role
(`settings.model_routing`, a tunable). No concrete model name lives in application code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.providers import ModelProvider
from app.ai.roles import ROLES, RoleSpec
from app.ai.roles import role as role_spec
from app.config import Settings


@dataclass(frozen=True)
class Route:
    role: RoleSpec
    profile: str
    model: str
    provider: ModelProvider


class ModelRouter:
    def __init__(
        self,
        settings: Settings,
        provider: ModelProvider,
        *,
        campaign_overrides: dict[str, Any] | None = None,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.overrides = dict(
            campaign_overrides or {}
        )  # {"role_profiles": {role: profile}, "profile_models": {profile: model}}

    def profile_model(self, profile: str) -> str:
        override = self.overrides.get("profile_models", {}).get(profile)
        if override:
            return override
        return {
            "fast_structured": self.settings.model_profile_fast_structured,
            "balanced_reasoning": self.settings.model_profile_balanced_reasoning,
            "creative_narrative": self.settings.model_profile_creative_narrative,
            "deep_world_author": self.settings.model_profile_deep_world_author,
            "embedding": self.settings.model_profile_embedding,
            "rerank": self.settings.model_profile_rerank,
        }[profile]

    def resolve(self, role_name: str) -> Route:
        spec = role_spec(role_name)
        profile = self.overrides.get("role_profiles", {}).get(role_name, spec.profile)
        return Route(spec, profile, self.profile_model(profile), self.provider)

    def table(self) -> list[dict[str, str]]:
        return [
            {
                "role": r,
                "profile": self.resolve(r).profile,
                "model": self.resolve(r).model,
                "provider": self.provider.name,
            }
            for r in ROLES
        ]
