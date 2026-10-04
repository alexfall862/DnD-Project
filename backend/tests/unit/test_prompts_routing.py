"""Prompt repository and model routing."""

from __future__ import annotations

import pytest

from app.ai.prompts import PromptError, PromptRepository
from app.ai.providers import FakeModelProvider
from app.ai.roles import ROLES
from app.ai.routing import ModelRouter
from app.config import Settings

pytestmark = pytest.mark.unit


def test_every_role_has_a_versioned_prompt_with_matching_header():
    repo = PromptRepository()
    for name, spec in ROLES.items():
        p = repo.get(spec.prompt_id)
        assert p.header["role"] == name and p.version == 1 and p.body
        assert int(p.header["max_tokens"]) == spec.max_tokens, name
        system, prompt = repo.system_text(spec)
        assert system.splitlines()[0] == f"# role: {name}"
        assert "Use only the information supplied" in system
        if spec.output_model is not None:
            assert "Output JSON shape" in system and "{" in system
        else:
            assert "Output JSON shape" not in system
    assert (
        len(repo.get("ai_player").hash) == 64
        and repo.get("ai_player").hash == repo.get("ai_player", 1).hash
    )
    with pytest.raises(PromptError):
        repo.get("ai_player", 99)
    with pytest.raises(PromptError):
        repo.get("nonexistent")


def test_router_maps_roles_to_profiles_and_models_with_overrides():
    s = Settings(
        model_profile_fast_structured="ttrpg/fast",
        model_profile_balanced_reasoning="ttrpg/balanced",
        model_profile_creative_narrative="ttrpg/creative",
        model_profile_deep_world_author="ttrpg/deep",
    )
    r = ModelRouter(s, FakeModelProvider())
    assert r.resolve("intent_interpreter").model == "ttrpg/fast"
    assert (
        r.resolve("ai_player").model == "ttrpg/balanced"
        and r.resolve("narrator").model == "ttrpg/creative"
    )
    assert r.resolve("world_author").model == "ttrpg/deep"
    r2 = ModelRouter(
        s,
        FakeModelProvider(),
        campaign_overrides={
            "role_profiles": {"npc_actor": "fast_structured"},
            "profile_models": {"creative_narrative": "ttrpg/other"},
        },
    )
    assert (
        r2.resolve("npc_actor").model == "ttrpg/fast"
        and r2.resolve("narrator").model == "ttrpg/other"
    )
    assert {row["role"] for row in r.table()} == set(ROLES)
    with pytest.raises(KeyError):
        r.resolve("dungeon_master")
