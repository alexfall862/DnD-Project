"""Invariant 3 at the code level (database-schema.md §21, §22).

- Perspective code (`PerspectiveService`, `PerspectiveRepository`) never imports the objective
  repository or selects private columns.
- `deliberate_false`, `fidelity`, `source_fact_id`, `source_belief_id`, `truth_status`,
  `canon_status` and `hidden_properties` never appear in the perspective repository's queries.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.invariants]

ROOT = Path(__file__).resolve().parents[2] / "app"
PERSPECTIVE_FILES = [
    ROOT / "persistence" / "repositories" / "perspective.py",
    ROOT / "services" / "perspective.py",
    ROOT / "ai" / "context.py",  # the Context Compiler builds model context: perspective only
]
FORBIDDEN_TOKENS = (
    "deliberate_false",
    "Claim.fidelity",
    "source_fact_id",
    "source_belief_id",
    "truth_status",
    "canon_status",
    "hidden_properties",
    "select(Fact",
    "Fact)",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
    return out


@pytest.mark.parametrize("path", PERSPECTIVE_FILES, ids=lambda p: p.name)
def test_perspective_code_never_imports_the_objective_repository(path: Path) -> None:
    mods = _imports(path)
    assert not any("objective" in m for m in mods), mods
    assert not any(
        m.startswith("app.services.knowledge") or m.startswith("app.services.speech") for m in mods
    ), mods


@pytest.mark.parametrize("path", PERSPECTIVE_FILES, ids=lambda p: p.name)
def test_perspective_code_never_touches_private_columns(path: Path) -> None:
    src = path.read_text(encoding="utf-8")
    code_only = "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("#") and '"""' not in line
    )
    # strip docstrings crudely: drop module docstring block
    code_only = re.sub(r'"""[\s\S]*?"""', "", src)
    hits = [tok for tok in FORBIDDEN_TOKENS if tok in code_only and tok != "Fact)"]
    assert not hits, f"{path.name} references private/objective columns: {hits}"
    # Fact model must not be imported at all
    assert "Fact" not in _models_imported(path), "perspective code imports the Fact model"


def _models_imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("app.persistence.models")
        ):
            names |= {a.name for a in node.names}
    return names
