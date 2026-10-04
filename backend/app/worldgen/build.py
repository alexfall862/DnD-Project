"""WorldBuilder — turn validated World Author envelopes into world rows through the ordinary
services, so every row commits with its Event (Invariant 4) and every piece of knowledge is
assigned to the actors who hold it (Invariant 2). Used by `GenerationService.start` (the whole
pipeline, inside one unit of work) and by progressive materialization (one envelope, applied
incrementally with a ref map read back from the database).

Order matters and is fixed: places → routes → other entities → people → facts that do not
mention objects → objects (documents convey existing facts) → facts about objects →
psychology and identity → factions and plans → mysteries and clues → mechanics → clocks →
party → opening scene. Every generated entity remembers its `gen_ref` in metadata.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.beliefs import Proposition
from app.persistence.models import Actor, Entity, Fact, Item, Location
from app.services.knowledge import KnowledgeService
from app.services.memory import MemoryService
from app.services.mystery import MysteryService
from app.services.psychology import PsychologyService
from app.services.schedule import ScheduleService
from app.services.world import CampaignHandle, WorldError, WorldService
from app.worldgen.envelope import GenActor, GenFact, GenFaction, GenLocation, WorldAuthorOut
from app.worldgen.validate import merge_actor, merge_faction, merge_location, norm_key

DAY = 86400
HOUR = 3600


def combine(envelopes: list[WorldAuthorOut]) -> WorldAuthorOut:
    """One envelope from many, in stage order; actors with the same ref are merged."""
    out = WorldAuthorOut()
    actors: dict[str, GenActor] = {}
    factions: dict[str, GenFaction] = {}
    locations: dict[str, GenLocation] = {}
    for env in envelopes:
        for section in (
            "facts",
            "routes",
            "cultures",
            "conflicts",
            "pressures",
            "mysteries",
            "clues",
            "items",
            "mechanics",
            "opportunities",
            "schedules",
        ):
            getattr(out, section).extend(getattr(env, section))
        for a in env.actors:
            actors[a.ref] = merge_actor(actors.get(a.ref), a)[0]
        for f in env.factions:
            factions[f.ref] = merge_faction(factions.get(f.ref), f)
        for loc in env.locations:
            locations[loc.ref] = merge_location(locations.get(loc.ref), loc)
        if env.opening is not None:
            out.opening = env.opening
        if env.summary:
            out.summary = (out.summary + "\n" + env.summary).strip()
    if out.opening is not None:  # the party begins where the opening scene is
        for a in actors.values():
            if a.role != "npc" and a.ref in out.opening.present_refs:
                a.location_ref = out.opening.location_ref
    out.actors = list(actors.values())
    out.factions = list(factions.values())
    out.locations = list(locations.values())
    return out


def _features(texts: list[str], canon: str) -> list[dict[str, Any]]:
    return [
        {"description": t, "classification": "furnishing", "canon_status": canon} for t in texts
    ]


def _space(loc: GenLocation) -> dict[str, Any] | None:
    if not loc.zones:
        return None
    return {
        "zones": [
            {
                "key": z.key,
                "name": z.name or z.key,
                "cover": z.cover,
                "exit": z.exit,
                "features": list(z.features),
            }
            for z in loc.zones
        ],
        "adjacency": [list(p) for p in loc.adjacency],
        "positions": {},
    }


def _profile(a: GenActor) -> dict[str, Any]:
    return {
        "attributes": {norm_key("attr", k): int(v) for k, v in a.attributes.items()},
        "skills": {norm_key("skill", k): int(v) for k, v in a.skills.items()},
        "traits": [norm_key("trait", t) for t in a.traits],
    }


class WorldBuilder:
    def __init__(
        self,
        session: AsyncSession,
        h: CampaignHandle,
        *,
        refs: dict[str, uuid.UUID] | None = None,
        ruleset=None,
    ) -> None:
        self.session = session
        self.h = h
        self.ruleset = ruleset
        self.world = WorldService(session)
        self.k = KnowledgeService(session)
        self.psy = PsychologyService(session)
        self.memory = MemoryService(session)
        self.mystery = MysteryService(session)
        self.schedule = ScheduleService(session)
        # ref -> id of the row that carries it: entity id for entities, actor id for actors,
        # location id for locations, item id for items, faction id, mystery id, clue id
        self.refs: dict[str, uuid.UUID] = dict(refs or {})
        self.entity_of: dict[str, uuid.UUID] = {}  # ref -> entity id (actors/locations/items)
        self.facts: dict[str, uuid.UUID] = {}
        self.plans: dict[str, uuid.UUID] = {}  # faction ref -> plan id
        self.opening_scene: uuid.UUID | None = None
        self.player: uuid.UUID | None = None
        self.party: uuid.UUID | None = None
        self._labels: dict[str, str] = {}

    @classmethod
    async def for_existing(cls, session: AsyncSession, h: CampaignHandle) -> WorldBuilder:
        """A builder whose ref map is read back from the campaign's entities (materialization)."""
        b = cls(session, h)
        rows = (
            await session.execute(select(Entity).where(Entity.campaign_id == h.campaign_id))
        ).scalars()
        for e in rows:
            ref = (e.metadata_ or {}).get("gen_ref")
            if not ref:
                continue
            b.entity_of[ref] = e.id
            if e.entity_type == "actor":
                a = (
                    await session.execute(select(Actor).where(Actor.entity_id == e.id))
                ).scalar_one_or_none()
                if a:
                    b.refs[ref] = a.id
            elif e.entity_type == "location":
                loc = (
                    await session.execute(select(Location).where(Location.entity_id == e.id))
                ).scalar_one_or_none()
                if loc:
                    b.refs[ref] = loc.id
            elif e.entity_type == "item":
                it = (
                    await session.execute(select(Item).where(Item.entity_id == e.id))
                ).scalar_one_or_none()
                if it:
                    b.refs[ref] = it.id
            else:
                b.refs[ref] = e.id
        for f in (
            await session.execute(select(Fact).where(Fact.campaign_id == h.campaign_id))
        ).scalars():
            if f.key:
                b.facts[f.key] = f.id
        return b

    # -- helpers -------------------------------------------------------------------------------

    def ent(self, ref: str | None) -> uuid.UUID | None:
        if ref is None:
            return None
        if ref in self.entity_of:
            return self.entity_of[ref]
        return self.refs.get(ref)  # cultures/conflicts/…: the ref maps to the entity itself

    def _fact_mentions_item(self, f: GenFact, item_refs: set[str]) -> bool:
        return f.subject_ref in item_refs or f.object_ref in item_refs

    # -- the build -----------------------------------------------------------------------------

    async def build(self, env: WorldAuthorOut, *, start_hour: int | None = None) -> None:
        h = self.h
        for group in (env.factions, env.locations, env.cultures):
            for x in group:
                self._labels[x.ref] = x.name
        for a in env.actors:
            self._labels[a.ref] = a.name or a.ref
        if start_hour is not None:
            clock = await self.world.clock(h)
            if clock.current_tick < start_hour * HOUR:
                await self.world.advance_time(
                    h, start_hour * HOUR - clock.current_tick, reason="campaign start"
                )
        opening_ref = env.opening.location_ref if env.opening else None
        await self._locations(env, opening_ref)
        for r in env.routes:
            await self.world.connect_locations(
                h, self.refs[r.from_ref], self.refs[r.to_ref], travel_seconds=r.travel_minutes * 60
            )
        for c in env.cultures:
            await self._entity("culture", c.ref, c.name, c.model_dump())
        for x in env.conflicts:
            await self._entity("conflict", x.ref, x.title, x.model_dump())
        for x in env.pressures:
            await self._entity("pressure", x.ref, x.title, x.model_dump())
        for o in env.opportunities:
            await self._entity("opportunity", o.ref, o.title, o.model_dump())
        for a in env.actors:
            await self._actor(a)
        item_refs = {i.ref for i in env.items}
        knowers = self._knowers(env)
        first = [f for f in env.facts if not self._fact_mentions_item(f, item_refs)]
        later = [f for f in env.facts if self._fact_mentions_item(f, item_refs)]
        for f in first:
            await self._fact(f, knowers)
        pending_items = list(env.items)
        for it in list(pending_items):
            if it.document is None or all(k in self.facts for k in it.document.conveys_fact_keys):
                await self._item(it)
                pending_items.remove(it)
        for f in later:
            await self._fact(f, knowers)
        for it in pending_items:
            await self._item(it)
        for a in env.actors:
            await self._psychology(a, env)
        for f in env.factions:
            await self._faction(f, env)
        for m in env.mysteries:
            await self._mystery(m)
        for cl in env.clues:
            c = await self.mystery.create_clue(
                h,
                self.refs[cl.mystery_ref],
                key=cl.ref,
                clue_type=cl.clue_type,
                supported_fact_id=self.facts[cl.supports_fact_key],
                physical_entity_id=self.ent(cl.entity_ref),
                reliability=cl.reliability,
                destructible=cl.destructible,
            )
            self.refs[cl.ref] = c.id
        for m in env.mechanics:
            await self._mechanic(m.model_dump())
        for s in env.schedules:
            await self._schedule(s)
        await self._party(env)
        if env.opening is not None:
            await self._opening(env)

    # -- sections ------------------------------------------------------------------------------

    async def _locations(self, env: WorldAuthorOut, opening_ref: str | None) -> None:
        pending = list(env.locations)
        guard = 0
        while pending:
            guard += 1
            if guard > 1000:
                raise WorldError("location parents form a cycle")
            loc = pending.pop(0)
            if loc.parent_ref and loc.parent_ref not in self.refs:
                pending.append(loc)
                continue
            space = _space(loc)
            props: dict[str, Any] = {
                "features": _features(
                    loc.features, "established" if loc.ref == opening_ref else "latent"
                ),
                "settlement": loc.settlement,
                "kind": loc.type,
            }
            if space:
                props["space"] = space
            if loc.entry_zone:
                props["entry_zone"] = loc.entry_zone
            row = await self.world.create_location(
                self.h,
                loc.name,
                location_type=loc.type[:32],
                parent_location_id=self.refs.get(loc.parent_ref) if loc.parent_ref else None,
                detail_level=loc.detail,
                importance_tier="important" if loc.settlement or space else "standard",
                properties=props,
                metadata={"descriptor": loc.descriptor or loc.name, "gen_ref": loc.ref},
                simulation_state=dict(loc.simulation_state),
            )
            self.refs[loc.ref] = row.id
            self.entity_of[loc.ref] = row.entity_id

    async def _entity(self, kind: str, ref: str, name: str, data: dict[str, Any]) -> None:
        e = await self.world.create_entity(self.h, kind, name, metadata={**data, "gen_ref": ref})
        self.refs[ref] = e.id
        self.entity_of[ref] = e.id

    async def _actor(self, a: GenActor) -> None:
        controller = {"pc_human": "human", "pc_ai": "ai"}.get(a.role, "ai")
        if not a.alive:
            controller = "dormant"
        row = await self.world.create_actor(
            self.h,
            a.name or a.ref,
            actor_type="pc" if a.role != "npc" else "npc",
            controller_type=controller,
            location_id=self.refs.get(a.location_ref) if a.location_ref and a.alive else None,
            importance_tier=a.importance,
            mechanical_profile=_profile(a),
            behavior_profile={
                "summary": a.summary or a.occupation,
                "dimensions": dict(a.dimensions),
                "traits": [t.replace("_", " ").title() for t in a.traits],
            },
            metadata={
                "descriptor": a.descriptor or "a stranger",
                "occupation": a.occupation,
                "gen_ref": a.ref,
            },
        )
        if not a.alive:
            row.alive = False
        self.refs[a.ref] = row.id
        self.entity_of[a.ref] = row.entity_id
        for eq in a.equipment:
            await self.world.create_item(
                self.h, eq.name, template_key=eq.template_key, possessor_actor_id=row.id
            )

    def _knowers(self, env: WorldAuthorOut) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for f in env.facts:
            out.setdefault(f.key, set()).update(f.known_by_refs)
        for a in env.actors:
            for k in a.knows_fact_keys:
                out.setdefault(k, set()).add(a.ref)
        return out

    async def _fact(self, f: GenFact, knowers: dict[str, set[str]]) -> None:
        subject = self.ent(f.subject_ref) if f.subject_ref else None
        predicate = f.predicate
        if f.subject_ref and subject is None:
            predicate = f"{self._label(f.subject_ref)} {predicate}"  # factions have no entity
        obj = self.ent(f.object_ref) if f.object_ref else None
        value = f.value
        if f.object_ref and obj is None:
            value = self._label(f.object_ref) if value is None else value
        row = await self.k.create_fact(
            self.h,
            key=f.key,
            predicate=predicate,
            subject_entity_id=subject,
            object_entity_id=obj,
            value=value,
            canon_status=f.canon,
            sensitivity=f.sensitivity,
            known_by=[self.refs[r] for r in sorted(knowers.get(f.key, set())) if r in self.refs],
            provenance={"source": "world_author", "era": f.era}
            if f.era
            else {"source": "world_author"},
        )
        self.facts[f.key] = row.id

    def _label(self, ref: str) -> str:
        return self._labels.get(ref, ref)

    async def _item(self, it) -> None:
        document = None
        if it.document is not None:
            conveys: list[dict[str, Any]] = [
                {"kind": "fact_ref", "ref_id": str(self.facts[k]), "stance": "asserts_true"}
                for k in it.document.conveys_fact_keys
                if k in self.facts
            ]
            conveys += [
                {"kind": "proposition", "proposition": {"predicate": p}, "stance": "asserts_true"}
                for p in it.document.conveys_propositions
            ]
            for r in it.document.names_refs:
                eid = self.ent(r)
                if eid is not None:
                    name = (await self.session.get(Entity, eid)).canonical_name  # type: ignore[union-attr]
                    conveys.append({"kind": "identity", "entity_id": str(eid), "name": name})
            document = {
                "text": it.document.text,
                "author_entity_id": self.ent(it.document.author_ref),
                "conveys": conveys,
            }
        holder = self.refs.get(it.holder_ref) if it.holder_ref else None
        hidden = dict(it.hidden)
        if it.mechanics_key:
            hidden["definition_key"] = it.mechanics_key
        row = await self.world.create_item(
            self.h,
            it.name,
            template_key=it.template_key,
            possessor_actor_id=holder,
            location_id=None if holder else self.refs.get(it.location_ref),
            zone_key=None if holder else it.zone,
            equipped=False,
            concealed=bool(it.concealed and not holder),
            concealment_difficulty=it.concealment_difficulty,
            public_properties=dict(it.public),
            hidden_properties=hidden,
            importance_tier=it.importance,
            document=document,
            metadata={"gen_ref": it.ref},
        )
        self.refs[it.ref] = row.id
        self.entity_of[it.ref] = row.entity_id

    async def _psychology(self, a: GenActor, env: WorldAuthorOut) -> None:
        aid = self.refs[a.ref]
        for g in a.goals:
            await self.psy.create_goal(
                self.h,
                aid,
                g.description,
                priority=g.priority,
                target_entity_ids=[e for e in (self.ent(r) for r in g.target_refs) if e],
            )
        for b in a.beliefs:
            s, o = self.ent(b.subject_ref), self.ent(b.object_ref)
            await self.k.seed_belief(
                self.h,
                aid,
                Proposition(
                    b.predicate, subject=str(s) if s else None, object=str(o) if o else None
                ),
                b.type,
                b.confidence,
            )
        for text in a.core_memories:
            await self.memory.create_memory(
                self.h, aid, text, seed=True, is_core=True, salience=0.85, emotional_weight=0.5
            )
        # names: what this person can call things (identity knowledge, never omniscience)
        known = set(a.knows_refs)
        if a.location_ref:
            known.add(a.location_ref)
            parent = next((x for x in env.locations if x.ref == a.location_ref), None)
            while parent is not None and parent.parent_ref:
                known.add(parent.parent_ref)
                parent = next((x for x in env.locations if x.ref == parent.parent_ref), None)
        for r in sorted(known):
            eid = self.ent(r)
            if eid is None or eid == self.entity_of.get(a.ref):
                continue
            ent = await self.session.get(Entity, eid)
            await self.k.learn_identity(self.h, aid, eid, ent.canonical_name or r)  # type: ignore[union-attr]
        for rel in a.relationships:
            if rel.target_ref not in self.refs:
                continue
            await self.k.seed_relationship(
                self.h,
                aid,
                self.refs[rel.target_ref],
                trust=rel.trust,
                respect=rel.respect,
                affection=rel.affection,
                fear=rel.fear,
                resentment=rel.resentment,
                familiarity=rel.familiarity,
            )
        if a.role == "pc_ai":
            await self.psy.set_ai_profile(aid, autonomy={"item_transfer": "ask", **a.autonomy})
        elif a.autonomy:
            await self.psy.set_ai_profile(aid, autonomy=dict(a.autonomy))

    async def _faction(self, f, env: WorldAuthorOut) -> None:
        members = {
            self.refs[a.ref]: ("leader" if a.leads_faction_ref == f.ref else "member")
            for a in env.actors
            if f.ref in a.faction_refs or a.leads_faction_ref == f.ref
        }
        row = await self.world.create_faction(
            self.h,
            f.name,
            description=f.description,
            resources=dict(f.resources),
            capabilities={
                "kind": f.kind,
                "scope": f.scope,
                "ideology": f.ideology,
                "public_goal": f.public_goal,
                "allies": f.allies,
                "rivals": f.rivals,
                "gen_ref": f.ref,
            },
            members=members,
            public=f.public,
        )
        row.simulation_priority = f.simulation_priority
        row.territory = {
            "location_ids": [str(self.refs[r]) for r in f.territory_refs if r in self.refs]
        }
        self.refs[f.ref] = row.id
        if f.plan_steps:
            goal = await self.psy.create_goal(
                self.h,
                row.id,
                f.hidden_goal or f.public_goal or f"advance the {f.name}",
                owner_type="faction",
                goal_type="faction",
                priority=int(70 + 30 * f.simulation_priority),
            )
            steps = [
                {
                    "title": s.title,
                    "kind": s.kind,
                    **({"at_tick": int(s.at_day * DAY)} if s.at_day is not None else {}),
                }
                for s in f.plan_steps
            ]
            plan = await self.psy.create_plan(self.h, goal.id, steps)
            self.plans[f.ref] = plan.id

    async def _mystery(self, m) -> None:
        row = await self.mystery.create_mystery(
            self.h,
            key=m.ref,
            question=m.question,
            truth_fact_ids=[self.facts[k] for k in m.truth_fact_keys],
            activate=True,
            stakeholders=[self._label(r) for r in m.participant_refs],
            consequences={"timeline": m.timeline, "red_herrings": m.red_herring_fact_keys},
        )
        self.refs[m.ref] = row.id

    async def _mechanic(self, definition: dict[str, Any]) -> None:
        from app.worldgen.mechanics import store_mechanic

        await store_mechanic(
            self.session, self.h, definition, source_kind="world_author", ruleset=self.ruleset
        )

    async def _schedule(self, s) -> None:
        # day 0 (or an hour before the opening) means "as play begins", never the past
        # (09c A9 run: "cannot schedule in the past" at start)
        now = (await self.world.clock(self.h)).current_tick
        tick = max(int(s.at_day * DAY), now)
        if s.type == "fact.establish":
            await self.schedule.schedule(
                self.h,
                tick=tick,
                event_type="fact.establish",
                payload={"fact_id": str(self.facts[s.fact_key]), "reason": s.key},
                key=s.key,
            )
        elif s.type == "clue.destroy":
            cid = str(self.refs[s.clue_ref])
            await self.schedule.schedule(
                self.h,
                tick=tick,
                event_type="clue.destroy",
                payload={"clue_id": cid, "reason": s.key},
                prerequisites=[{"kind": "clue_intact", "clue_id": cid}]
                + (
                    [{"kind": "actor_free", "actor_id": str(self.refs[s.actor_ref])}]
                    if s.actor_ref
                    else []
                ),
                key=s.key,
            )
        elif s.type == "location.state":
            await self.schedule.schedule(
                self.h,
                tick=tick,
                event_type="location.state",
                payload={"location_id": str(self.refs[s.location_ref]), "patch": dict(s.patch)},
                key=s.key,
            )
        elif s.type == "actor.travel":
            aid = str(self.refs[s.actor_ref])
            await self.schedule.schedule(
                self.h,
                tick=tick,
                event_type="actor.travel",
                payload={"actor_id": aid, "location_id": str(self.refs[s.location_ref])},
                prerequisites=[{"kind": "actor_free", "actor_id": aid}],
                key=s.key,
            )
        else:  # a decision left to the World Simulator
            payload: dict[str, Any] = {"question": s.question or s.key}
            if s.faction_ref and s.faction_ref in self.plans:
                payload["plan_id"] = str(self.plans[s.faction_ref])
            await self.schedule.schedule(
                self.h,
                tick=tick,
                event_type="world.decision",
                payload=payload,
                prerequisites=(
                    [{"kind": "actor_free", "actor_id": str(self.refs[s.actor_ref])}]
                    if s.actor_ref
                    else []
                ),
                key=s.key,
            )

    async def _party(self, env: WorldAuthorOut) -> None:
        pcs = [a for a in env.actors if a.role != "npc"]
        if not pcs:
            return
        ids = [self.refs[a.ref] for a in pcs]
        self.party = (await self.world.create_party(self.h, "the party", ids)).id
        await self.k.introduce(self.h, ids)
        for a in pcs:
            if a.role == "pc_human":
                self.player = self.refs[a.ref]

    async def _opening(self, env: WorldAuthorOut) -> None:
        op = env.opening
        assert op is not None
        loc_id = self.refs[op.location_ref]
        loc = await self.session.get(Location, loc_id)
        present = [self.refs[r] for r in op.present_refs]
        for r in op.present_refs:
            a = await self.session.get(Actor, self.refs[r])
            if a is not None and a.current_location_id != loc_id:
                raise WorldError(f"opening: {r} is not at {op.location_ref}")
        space = dict((loc.properties or {}).get("space") or {}) if loc else {}
        if space:
            first_zone = (loc.properties or {}).get("entry_zone") or space["zones"][0]["key"]
            space["positions"] = {
                str(self.refs[r]): {"zone": op.positions.get(r, first_zone)}
                for r in op.present_refs
            }
        scene = await self.world.start_scene(
            self.h,
            location_id=loc_id,
            scene_type="social",
            participant_actor_ids=present,
            state={
                "weather": op.weather,
                "time_of_day": f"{op.hour:02d}:00",
                "situation": op.situation,
                "opening": True,
            },
            space=space or None,
        )
        self.opening_scene = scene.id
