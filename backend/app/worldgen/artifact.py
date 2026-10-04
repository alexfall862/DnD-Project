"""Generated artifact slot (frostbridge-demo §23): one bounded World Author call for a low-tier
unusual artifact made of registered primitives. Validated like any generated mechanic; one
corrective retry; if it still fails, the caller falls back to its fixed definition ("do less
rather than invent state")."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextCompiler
from app.ai.routing import ModelRouter
from app.ai.runner import ModelRunner
from app.config import Settings
from app.engine.core import RulesEngine
from app.services.memory import MemoryService
from app.services.turns import Turn, budget_from_settings
from app.services.world import CampaignHandle
from app.worldgen.envelope import WorldAuthorOut
from app.worldgen.service import FIELD_GUIDE
from app.worldgen.validate import ITEM_PRIMITIVES, mechanic_errors

FORBIDDEN_WORDS = re.compile(r"teleport|resurrect|revive|permanent", re.I)


async def generate_artifact(
    session: AsyncSession,
    h: CampaignHandle,
    *,
    provider,
    settings: Settings,
    theme: str,
    key: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Returns (definition, errors). `definition` is None when the model never produced a
    valid one; the caller decides the fallback."""
    engine = RulesEngine.load("core_adventure")
    compiler = ContextCompiler(session, memory=MemoryService(session), engine=engine)
    runner = ModelRunner(session, ModelRouter(settings, provider))
    turn = Turn(h, budget=budget_from_settings(settings, None))
    errors: list[str] = []
    for _attempt in range(2):
        task = [
            "STAGE artifact — one generated item.",
            f"Create one low-tier, unusual artifact: {theme}. At most one passive and one "
            "activated effect, composed only of the registered effect primitives listed. "
            "Forbidden: teleportation, resurrection, permanent attribute increases. "
            f'Use key "{key}" and tier "low".',
            "Allowed sections: " + FIELD_GUIDE["mechanics"],
            "Put the flavour in `description`; params hold only the values listed for each type.",
        ]
        if errors:
            task.append("Fix exactly these problems: " + " | ".join(errors[:8]))
        ctx = await compiler.compile(
            h,
            "world_author",
            actor_id=None,
            purpose="generated artifact slot",
            situation="Propose the artifact. Return only JSON.",
            extra_sections={
                "task": "\n".join(task),
                "rules_public": "Item effect types (only these): "
                + ", ".join(sorted(ITEM_PRIMITIVES))
                + "\nConditions: "
                + ", ".join(engine.ruleset.conditions)
                + "\nChecks: check.* (all checks) or "
                + ", ".join(engine.ruleset.checks)
                + "\nResources: "
                + ", ".join(engine.ruleset.resources)
                + "\nDamage types: "
                + ", ".join(k for k in engine.ruleset.defs["damage_types"]),
            },
        )
        res = await runner.run(h, ctx, turn_id=turn.turn_id)
        turn.record_call("world_author", sync=False, calls=res.calls)
        if not res.ok or not isinstance(res.output, WorldAuthorOut) or not res.output.mechanics:
            errors = ["return exactly one entry in `mechanics`"]
            continue
        if len(res.output.mechanics) != 1:
            errors = ["exactly one mechanic is required"]
            continue
        d = res.output.mechanics[0].model_dump()
        d["key"] = key
        errors = mechanic_errors(d, engine.ruleset)
        text = f"{d.get('name', '')} {d.get('description', '')}"
        if FORBIDDEN_WORDS.search(text):
            errors.append("the description promises a forbidden effect")
        if not errors:
            await turn.finish(session)
            return d, []
    await turn.finish(session)
    return None, errors
