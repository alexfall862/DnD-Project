"""Rules-engine fixtures: the Core Adventure engine and the Frostbridge builds."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.engine.core import RULESETS_DIR, RulesEngine
from app.engine.ruleset import Ruleset, load_ruleset
from app.seeds.frostbridge_tavern import FROSTBRIDGE_BUILDS

__all__ = ["FROSTBRIDGE_BUILDS", "core", "engine", "builds"]

# The Frostbridge builds live with the seed; re-exported here for the rules tests.


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
