"""Rules-engine fixtures: the Core Adventure engine and the Frostbridge builds."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.engine.core import RULESETS_DIR, RulesEngine
from app.engine.ruleset import Ruleset, load_ruleset

FROSTBRIDGE_BUILDS = {
    "alex": {
        "attributes": {
            "attr.might": 5,
            "attr.agility": 6,
            "attr.intellect": 6,
            "attr.presence": 5,
            "attr.resolve": 5,
        },
        "skills": {
            "skill.investigation": 2,
            "skill.awareness": 2,
            "skill.persuasion": 1,
            "skill.athletics": 1,
            "skill.ranged": 1,
            "skill.survival": 1,
        },
    },
    "elara": {
        "attributes": {
            "attr.might": 5,
            "attr.agility": 7,
            "attr.intellect": 6,
            "attr.presence": 4,
            "attr.resolve": 6,
        },
        "skills": {
            "skill.survival": 3,
            "skill.awareness": 2,
            "skill.ranged": 2,
            "skill.stealth": 2,
            "skill.investigation": 1,
            "skill.medicine": 1,
        },
        "traits": ["trait.keen_observer", "trait.frontier_veteran"],
    },
    "tomas": {
        "attributes": {
            "attr.might": 6,
            "attr.agility": 5,
            "attr.intellect": 5,
            "attr.presence": 7,
            "attr.resolve": 6,
        },
        "skills": {
            "skill.persuasion": 3,
            "skill.melee": 2,
            "skill.awareness": 2,
            "skill.intimidation": 1,
            "skill.lore": 1,
            "skill.medicine": 1,
        },
        "traits": ["trait.guard_training", "trait.well_connected"],
    },
    "thief": {
        "attributes": {
            "attr.might": 4,
            "attr.agility": 6,
            "attr.intellect": 4,
            "attr.presence": 4,
            "attr.resolve": 4,
        },
        "skills": {"skill.stealth": 2, "skill.melee": 1, "skill.athletics": 1},
    },
}


@pytest.fixture(scope="session")
def core() -> Ruleset:
    return load_ruleset(RULESETS_DIR / "core_adventure")


@pytest.fixture
def engine(core: Ruleset) -> RulesEngine:
    from app.engine.dice import DiceService, SeedStream

    return RulesEngine(core, DiceService(SeedStream(42)))


@pytest.fixture
def builds(engine: RulesEngine):
    return {k: engine.actor(k, v) for k, v in FROSTBRIDGE_BUILDS.items()}


def write_package(root: Path, *, manifest: dict | None = None, **files: dict) -> Path:
    """Write a minimal ruleset package for validation tests. Unspecified sections are copied
    from Core Adventure so tests only state what they change."""
    core_dir = RULESETS_DIR / "core_adventure"
    base_manifest = yaml.safe_load((core_dir / "manifest.yaml").read_text(encoding="utf-8"))
    base_manifest["key"] = "test_pack"
    base_manifest["name"] = "Test pack"
    base_manifest.update(manifest or {})
    file_names = list(base_manifest["files"])
    for name in file_names:
        src = core_dir / name
        if name.replace(".yaml", "") in files:
            (root / name).write_text(
                yaml.safe_dump(files.pop(name.replace(".yaml", ""))), encoding="utf-8"
            )
        elif src.exists():
            (root / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    for extra, doc in files.items():
        (root / f"{extra}.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
        base_manifest["files"].append(f"{extra}.yaml")
    (root / "manifest.yaml").write_text(yaml.safe_dump(base_manifest), encoding="utf-8")
    return root
