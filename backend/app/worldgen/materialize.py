"""Progressive materialization (campaign-generation §27; orchestration §27): when play reaches
a place that is still an outline, the World Author fills in what is needed — a playable space,
the people and objects that belong there, local facts — validated against established canon
and built incrementally. Content stays latent until play establishes it.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextCompiler
from app.ai.routing import ModelRouter
from app.ai.runner import ModelRunner
from app.config import Settings
from app.engine.core import RulesEngine
from app.persistence.models import Campaign, Entity, Fact, Location
from app.services.events import unit_of_work
from app.services.memory import MemoryService
from app.services.turns import Turn, budget_from_settings
from app.services.world import CampaignHandle, WorldError, WorldService
from app.worldgen.brief import CampaignBrief
from app.worldgen.build import WorldBuilder, _features, _space
from app.worldgen.envelope import GenFact, GenLocation, WorldAuthorOut
from app.worldgen.service import FIELD_GUIDE
from app.worldgen.stages import Stage
from app.worldgen.validate import Catalog, validate_stage

MATERIALIZE = Stage(
    "materialize",
    "Materialize a place",
    "Make the target place playable: repeat its ref once as a location with detail "
    "materialized and zones; add only the people (role npc, importance standard or "
    "background), objects and local facts this place needs. Contradict nothing established.",
    frozenset({"locations", "routes", "actors", "items", "facts"}),
    (),
    {"locations": 1},
    max_detail="materialized",
)


class MaterializeService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        engine: RulesEngine,
        provider,
        embedder=None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.engine = engine
        memory = MemoryService(session, embedder)
        self.compiler = ContextCompiler(session, memory=memory, engine=engine)
        self.runner = ModelRunner(session, ModelRouter(settings, provider))

    async def _catalog(self, h: CampaignHandle, b: WorldBuilder) -> Catalog:
        """The objective catalog of an existing world: refs by kind, established facts."""
        c = Catalog()
        for ref, eid in b.entity_of.items():
            e = await self.session.get(Entity, eid)
            if e is None:
                continue
            c.kinds[ref], c.names[ref] = e.entity_type, e.canonical_name or ref
        rev = {v: k for k, v in b.entity_of.items()}
        for f in (
            await self.session.execute(select(Fact).where(Fact.campaign_id == h.campaign_id))
        ).scalars():
            gf = GenFact(
                key=f.key or str(f.id),
                predicate=f.predicate,
                subject_ref=rev.get(f.subject_entity_id) if f.subject_entity_id else None,
                object_ref=rev.get(f.object_entity_id) if f.object_entity_id else None,
                value=(f.object_value or {}).get("value"),
                sensitivity=f.sensitivity,  # type: ignore[arg-type]
                canon="established" if f.canon_status == "established" else "latent",
            )
            c.facts[gf.key] = gf
            if gf.canon == "established":
                c.established.append(gf)
        return c

    async def materialize_location(
        self, h: CampaignHandle, location_id: uuid.UUID, *, need: str = ""
    ) -> dict[str, Any]:
        loc = await self.session.get(Location, location_id)
        if loc is None:
            raise WorldError("location not found")
        if loc.detail_level == "materialized":
            return {"status": "already materialized"}
        ent = await self.session.get(Entity, loc.entity_id)
        target_ref = (ent.metadata_ or {}).get("gen_ref") if ent else None
        b = await WorldBuilder.for_existing(self.session, h)
        if not target_ref:
            target_ref = f"loc_{location_id.hex[:8]}"
            b.entity_of[target_ref] = loc.entity_id
            b.refs[target_ref] = loc.id
        catalog = await self._catalog(h, b)
        catalog.kinds.pop(target_ref, None)  # the target may be repeated (refined) once
        campaign = await self.session.get(Campaign, h.campaign_id)
        brief = (
            CampaignBrief.model_validate(campaign.generation_brief or {})
            if campaign
            else CampaignBrief()
        )
        turn = Turn(h, budget=budget_from_settings(self.settings, None))
        errors: list[str] = []
        env: WorldAuthorOut | None = None
        for _attempt in range(2):
            task = [
                MATERIALIZE.task,
                f"Target: ref {target_ref} — {ent.canonical_name if ent else 'a place'} "
                f"({loc.location_type}); what a stranger sees: "
                f"{(ent.metadata_ or {}).get('descriptor', '') if ent else ''}.",
                f"Why now: {need or 'the party is going there'}.",
                "Allowed sections: "
                + "; ".join(FIELD_GUIDE[s] for s in sorted(MATERIALIZE.sections)),
            ]
            if errors:
                task.append("Fix exactly these problems: " + " | ".join(errors[:12]))
            ctx = await self.compiler.compile(
                h,
                "world_author",
                actor_id=None,
                purpose="materialize location",
                situation="Materialize the target place. Return only JSON.",
                extra_sections={
                    "brief": brief.as_context(),
                    "established_canon": "\n".join(
                        f"{f.key}: {f.subject_ref or '-'} {f.predicate} {f.object_ref or ''}"
                        for f in catalog.established
                    )
                    or "none",
                    "latent_canon": "\n".join(catalog.summary_lines(include_secrets=True)),
                    "task": "\n".join(task),
                },
            )
            res = await self.runner.run(h, ctx, turn_id=turn.turn_id)
            turn.record_call("world_author", sync=False, calls=res.calls)
            if not res.ok or not isinstance(res.output, WorldAuthorOut):
                errors = [f"output unusable: {res.status}"]
                continue
            env = res.output
            errors = validate_stage(
                MATERIALIZE,
                env,
                catalog,
                ruleset=RulesEngine.for_campaign(
                    campaign.ruleset_key if campaign else "core_adventure",
                    campaign.settings if campaign else None,
                ).ruleset,
                brief=brief,
            )
            target = [x for x in env.locations if x.ref == target_ref]
            if not target:
                errors.append(f"the target {target_ref} must be repeated as a location")
            elif target[0].detail != "materialized":
                errors.append("the target must come back materialized")
            if not errors:
                break
        await turn.finish(self.session)
        if errors or env is None:
            await self.session.commit()
            raise WorldError("materialization rejected: " + "; ".join(errors[:6]))
        target_loc: GenLocation = next(x for x in env.locations if x.ref == target_ref)
        rest = env.model_copy(
            update={"locations": [x for x in env.locations if x.ref != target_ref]}
        )
        await self.session.commit()
        async with unit_of_work(self.session):
            await WorldService(self.session).materialize_location(
                h,
                location_id,
                space=_space(target_loc) or {},
                features=_features(target_loc.features, "latent"),
                entry_zone=target_loc.entry_zone,
            )
            await b.build(rest)
        return {
            "status": "materialized",
            "location_id": str(location_id),
            "zones": len(target_loc.zones),
            "actors": len(env.actors),
            "items": len(env.items),
            "facts": len(env.facts),
        }
