"""Campaign-specific mechanical definitions (rules-engine §35; Invariant 12): validated
compositions of registered primitives, stored with snapshot semantics and an Event."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import events as ev
from app.engine.core import RulesEngine
from app.persistence.models import MechanicalDefinition
from app.services.events import EventTransaction
from app.services.rules_install import ensure_ruleset_installed
from app.services.world import CampaignHandle, WorldError
from app.worldgen.validate import mechanic_errors


async def store_mechanic(
    session: AsyncSession,
    h: CampaignHandle,
    definition: dict[str, Any],
    *,
    source_kind: str,
    ruleset_key: str = "core_adventure",
    ruleset=None,
) -> MechanicalDefinition:
    rs = ruleset or RulesEngine.load(ruleset_key).ruleset
    errors = mechanic_errors(definition, rs)
    if errors:
        raise WorldError("; ".join(errors))
    record = await ensure_ruleset_installed(session, RulesEngine.load(rs.key).ruleset)
    content_hash = hashlib.sha256(
        json.dumps(definition, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    async with EventTransaction(session, h.campaign_id, h.timeline_id) as tx:
        row = MechanicalDefinition(
            ruleset_id=record.id,
            campaign_id=h.campaign_id,
            definition_key=definition["key"],
            definition_type="item",
            source_kind=source_kind,
            definition=dict(definition),
            content_hash=content_hash,
            power={"tier": definition.get("tier")},
        )
        session.add(row)
        await session.flush()
        event = await tx.emit(
            ev.MechanicalDefinitionCreated(
                definition_id=row.id,
                definition_key=definition["key"],
                definition_type="item",
                source_kind=source_kind,
            )
        )
        row.created_event_id = event.id
    return row
