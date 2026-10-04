"""Milestone 09 follow-up: genre modules add declarative content to a campaign's ruleset
(campaign-generation §4; core-adventure-rules §19) and never redefine the base."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from app.engine.core import RULESETS_DIR, RulesEngine
from app.engine.ruleset import RulesetError, available_modules, load_ruleset, modules_for_genres
from app.worldgen.brief import CampaignBrief
from app.worldgen.envelope import WorldAuthorOut
from app.worldgen.stages import STAGE_BY_KEY
from tests.fixtures.saltreach import BRIEF
from tests.fixtures.saltreach import STAGES as SCRIPT
from tests.unit.test_worldgen_validate import catalog_before

pytestmark = pytest.mark.unit
ROOT = RULESETS_DIR / "core_adventure"


def test_modules_are_discovered_and_selected_by_genre() -> None:
    assert {"fantasy", "horror", "survival", "scifi"} <= set(available_modules(ROOT))
    assert modules_for_genres(ROOT, ["low fantasy"]) == []
    assert modules_for_genres(ROOT, ["cosmic horror"]) == ["horror"]
    assert set(modules_for_genres(ROOT, ["post-apocalyptic"])) == {"survival", "scifi"}
    assert set(modules_for_genres(ROOT, ["dark fantasy"])) == {"fantasy", "horror"}


def test_a_module_adds_content_and_changes_the_hash() -> None:
    base = RulesEngine.load("core_adventure").ruleset
    horror = RulesEngine.load("core_adventure", modules=("horror",)).ruleset
    assert not base.has("skill.occult") and horror.has("skill.occult")
    assert horror.has("condition.shaken") and horror.has("resource.stability")
    assert horror.content_hash != base.content_hash and horror.module_keys == ("horror",)
    st = RulesEngine.load("core_adventure", modules=("horror",)).actor(
        "x", {"attributes": {"attr.resolve": 5}}
    )
    assert st.resources["resource.stability"].current == 15
    assert any("[Horror]" in c for c in horror.worldgen_constraints())


def test_modules_cannot_redefine_base_content_or_be_unknown(tmp_path: Path) -> None:
    import shutil

    copy_root = tmp_path / "core_adventure"
    shutil.copytree(ROOT, copy_root)
    bad = copy_root / "modules" / "bad"
    bad.mkdir()
    (bad / "module.yaml").write_text(
        yaml.safe_dump({"key": "bad", "name": "Bad", "files": ["c.yaml"]}), encoding="utf-8"
    )
    (bad / "c.yaml").write_text(
        yaml.safe_dump(
            {"skills": [{"key": "skill.melee", "name": "Melee", "default_attribute": "attr.might"}]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(RulesetError, match="duplicate definition"):
        load_ruleset(copy_root, modules=("bad",))
    with pytest.raises(RulesetError, match="unknown genre module"):
        load_ruleset(copy_root, modules=("nope",))


def test_generation_validates_against_the_campaign_modules() -> None:
    from app.worldgen.validate import validate_stage

    env = copy.deepcopy(SCRIPT["npcs"])
    env["actors"][0]["skills"]["occult"] = 2
    brief = CampaignBrief.model_validate(BRIEF)
    stage, cat = STAGE_BY_KEY["npcs"], catalog_before("npcs")
    base = RulesEngine.load("core_adventure").ruleset
    horror = RulesEngine.load("core_adventure", modules=("horror",)).ruleset
    without = WorldAuthorOut.model_validate(copy.deepcopy(env))
    notes: list[str] = []
    errs = validate_stage(stage, without, cat, ruleset=base, brief=brief, notes=notes)
    assert errs == [] and "occult" not in without.actors[0].skills
    assert any("unknown skill 'occult' dropped" in n for n in notes)
    with_module = WorldAuthorOut.model_validate(copy.deepcopy(env))
    errs = validate_stage(stage, with_module, catalog_before("npcs"), ruleset=horror, brief=brief)
    assert errs == [] and with_module.actors[0].skills["occult"] == 2
