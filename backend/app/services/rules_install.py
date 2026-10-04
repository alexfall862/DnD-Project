"""Ruleset installation record (database-schema.md §14 `rulesets` / `rule_modules`).

Rulesets are declarative files loaded by `RulesEngine`; the database keeps a record of what is
installed so campaign-specific `mechanical_definitions` (generated items, rulings) can
reference the ruleset they extend. Installing is idempotent per (key, version).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.ruleset import Ruleset
from app.persistence.models import RuleModule, RulesetRecord

SECTIONS = ("attributes", "skills", "resources", "checks", "conditions", "equipment", "actions")


def _dump(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _dump(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_dump(v) for v in obj]
    return obj


async def ensure_ruleset_installed(session: AsyncSession, ruleset: Ruleset) -> RulesetRecord:
    manifest = ruleset.manifest
    key = getattr(manifest, "key", None) or ruleset.key
    version = str(getattr(manifest, "version", None) or "0.1.0")
    existing = (
        await session.execute(
            select(RulesetRecord).where(RulesetRecord.key == key, RulesetRecord.version == version)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    record = RulesetRecord(
        key=key,
        name=getattr(manifest, "name", None) or key,
        version=version,
        manifest=_dump(manifest),
        content_hash=ruleset.content_hash,
    )
    session.add(record)
    await session.flush()
    for section in SECTIONS:
        defs = getattr(ruleset, section, None)
        if not isinstance(defs, dict) or not defs:
            continue
        definition = {k: _dump(v) for k, v in defs.items()}
        session.add(
            RuleModule(
                ruleset_id=record.id,
                module_key=f"{key}.{section}",
                module_type=section,
                version=version,
                definition=definition,
                content_hash=hashlib.sha256(
                    json.dumps(definition, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest(),
            )
        )
    await session.flush()
    return record
