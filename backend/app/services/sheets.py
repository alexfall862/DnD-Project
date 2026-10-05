"""Character sheets and party status for the player client (api-contracts §7, §13;
human-visibility §2, §4).

The sheet is the player-agent layer of a human-controlled actor: attributes, skills, traits,
resources, conditions. The party view shows each member as the focus actor perceives them:
names as the focus actor knows them; for members sharing the focus actor's scene, visible
conditions and a coarse wound state (resources are owner-visible in the ruleset, so exact
numbers are never shown for others); members elsewhere are only "away" — where they went and
how they fare is learned in play, not from the party panel (split party, §3)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.core import RulesEngine
from app.persistence.models import Actor, ActorController, Entity, PartyMembership
from app.persistence.models.mechanics import ConditionInstanceRow, ResourceStateRow
from app.services.perspective import VISIBLE_CONDITIONS, PerspectiveService


@dataclass
class SheetEntry:
    key: str
    name: str
    value: int
    description: str = ""


@dataclass
class ResourceEntry:
    key: str
    name: str
    current: int
    max: int
    tracked_as: str = "pool"  # pool (current/max) | count (coin)


@dataclass
class ConditionEntry:
    key: str
    name: str
    intensity: int


@dataclass
class Sheet:
    actor_id: uuid.UUID
    name: str
    attributes: list[SheetEntry]
    skills: list[SheetEntry]
    traits: list[SheetEntry]
    resources: list[ResourceEntry]
    conditions: list[ConditionEntry]


@dataclass
class PartyMember:
    actor_id: uuid.UUID
    known_as: str
    controller: str  # human | ai | dormant
    is_focus: bool
    with_you: bool
    wound_state: str | None = None  # unhurt | hurt | badly hurt | down (only when with you)
    visible_conditions: list[str] = field(default_factory=list)


def wound_state(current: int, maximum: int) -> str:
    if maximum <= 0:
        return "unhurt"
    frac = current / maximum
    if current <= 0:
        return "down"
    if frac >= 0.999:
        return "unhurt"
    return "hurt" if frac > 0.5 else "badly hurt"


class SheetService:
    def __init__(self, session: AsyncSession, engine: RulesEngine) -> None:
        self.session = session
        self.engine = engine
        self.psv = PerspectiveService(session)

    async def _resources(self, entity_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
        rows = (
            (
                await self.session.execute(
                    select(ResourceStateRow).where(ResourceStateRow.entity_id.in_(entity_ids))
                )
            )
            .scalars()
            .all()
        )
        out: dict[uuid.UUID, dict[str, int]] = {}
        for r in rows:
            out.setdefault(r.entity_id, {})[r.resource_key] = r.current
        return out

    async def _conditions(self, entity_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Any]]:
        rows = (
            (
                await self.session.execute(
                    select(ConditionInstanceRow).where(
                        ConditionInstanceRow.target_entity_id.in_(entity_ids),
                        ConditionInstanceRow.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        out: dict[uuid.UUID, list[Any]] = {}
        for c in rows:
            out.setdefault(c.target_entity_id, []).append(c)
        return out

    def _state(self, actor: Actor, resources: dict[str, int], conditions: list[Any]):
        profile = dict(actor.mechanical_profile or {})
        profile.pop("equipment", None)
        profile["resources"] = {k: {"current": v} for k, v in resources.items()}
        profile["conditions"] = [
            {"key": c.condition_key, "intensity": c.intensity, "instance_id": c.instance_key}
            for c in conditions
            if c.condition_key in self.engine.ruleset.conditions
        ]
        return self.engine.actor(str(actor.id), profile)

    async def sheet(self, actor_id: uuid.UUID) -> Sheet:
        """The focus actor's own sheet (raises UnauthorizedPerspective for anyone else)."""
        await self.psv.require_focus_actor(actor_id)
        actor = await self.session.get(Actor, actor_id)
        entity = await self.session.get(Entity, actor.entity_id)
        res = (await self._resources([entity.id])).get(entity.id, {})
        conds = (await self._conditions([entity.id])).get(entity.id, [])
        st = self._state(actor, res, conds)
        rs = self.engine.ruleset
        calc = self.engine.calc
        return Sheet(
            actor_id=actor.id,
            name=entity.canonical_name,
            attributes=[
                SheetEntry(k, d.name, st.attributes.get(k, d.default), d.description)
                for k, d in rs.attributes.items()
            ],
            skills=[
                SheetEntry(k, rs.skills[k].name, v, rs.skills[k].description)
                for k, v in sorted(st.skills.items())
                if k in rs.skills and v > 0
            ],
            traits=[
                SheetEntry(t, rs.traits[t].name, 1, rs.traits[t].description)
                for t in st.traits
                if t in rs.traits
            ],
            resources=[
                ResourceEntry(
                    k,
                    d.name,
                    st.resources[k].current if k in st.resources else 0,
                    calc.resource_max(st, k).value,
                    d.tracked_as,
                )
                for k, d in rs.resources.items()
            ],
            conditions=[
                ConditionEntry(c.key, rs.conditions[c.key].name, c.intensity)
                for c in st.conditions
                if c.key in rs.conditions
            ],
        )

    async def party(self, focus_id: uuid.UUID) -> list[PartyMember]:
        """The focus actor's party as the focus actor perceives it."""
        await self.psv.require_focus_actor(focus_id)
        party_ids = (
            (
                await self.session.execute(
                    select(PartyMembership.party_id).where(PartyMembership.actor_id == focus_id)
                )
            )
            .scalars()
            .all()
        )
        if not party_ids:
            return []
        rows = (
            await self.session.execute(
                select(Actor, Entity)
                .join(PartyMembership, PartyMembership.actor_id == Actor.id)
                .join(Entity, Entity.id == Actor.entity_id)
                .where(PartyMembership.party_id.in_(party_ids))
            )
        ).all()
        focus = next((a for a, _ in rows if a.id == focus_id), None)
        names = await self.psv.known_entities(focus_id)
        res = await self._resources([e.id for _, e in rows])
        conds = await self._conditions([e.id for _, e in rows])
        out: list[PartyMember] = []
        seen: set[uuid.UUID] = set()
        for a, e in rows:
            if a.id in seen:
                continue
            seen.add(a.id)
            ctrl = (
                await self.session.execute(
                    select(ActorController.controller_type).where(
                        ActorController.actor_id == a.id,
                        ActorController.valid_until_event_id.is_(None),
                    )
                )
            ).scalar_one_or_none() or "ai"
            is_focus = a.id == focus_id
            with_you = is_focus or (
                focus is not None
                and focus.current_scene_id is not None
                and a.current_scene_id == focus.current_scene_id
            )
            member = PartyMember(
                actor_id=a.id,
                known_as="you" if is_focus else names.get(e.id) or "a companion",
                controller=ctrl,
                is_focus=is_focus,
                with_you=with_you,
            )
            if with_you:
                c = conds.get(e.id, [])
                st = self._state(a, res.get(e.id, {}), c)
                if "resource.health" in st.resources:
                    member.wound_state = wound_state(
                        st.resources["resource.health"].current,
                        self.engine.calc.resource_max(st, "resource.health").value,
                    )
                member.visible_conditions = sorted(
                    {x.condition_key for x in c if x.condition_key in VISIBLE_CONDITIONS}
                )
            out.append(member)
        out.sort(key=lambda m: (not m.is_focus, m.known_as))
        return out
