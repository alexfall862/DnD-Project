"""The Frostbridge deterministic demo fixture (docs/specifications/frostbridge-demo.md, all
sections): the full vertical-slice world — Veyr's Northern Reach town of Frostbridge with its
topology, the party (Alex human; Elara, Tomas AI), persistent NPCs (Mira, Renn), the locked
mystery of Oric Dane with redundant clue routes, the River Compact and its plan, the quarry
pressure, documents, the chipped dagger, scheduled clocks and the opening scene at the gate.

Objective truth is seeded as Facts; *who knows what* is seeded only through `known_by` and
explicit beliefs, following the leakage matrix (§42). Symbolic keys resolve to runtime ids in
the returned `FrostbridgeWorld` (tests never hard-code UUIDs). `verify()` checks the seed's
invariants (§40) and the seed is removed again if any check fails.

The smaller Red Lantern seed in `frostbridge_tavern.py` remains the fixture for the focused
leakage/orchestrator tests; this module is the playable world (`make seed-demo`, harness
`--new`) and the vertical-slice test's world.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import events as ev
from app.engine.beliefs import Proposition
from app.engine.core import RulesEngine
from app.persistence.models import (
    Actor,
    ActorController,
    Belief,
    Campaign,
    Document,
    Fact,
    Item,
    MechanicalDefinition,
    PartyMembership,
)
from app.seeds.frostbridge_tavern import BEHAVIOR, FROSTBRIDGE_BUILDS
from app.services.events import EventTransaction, unit_of_work
from app.services.knowledge import KnowledgeService
from app.services.memory import MemoryService
from app.services.mystery import MysteryService
from app.services.psychology import PsychologyService
from app.services.rules_install import ensure_ruleset_installed
from app.services.scenes import SceneService
from app.services.schedule import ScheduleService
from app.services.world import CampaignHandle, WorldService

DAY = 86400
HOUR = 3600
OPENING_TICK = 16 * HOUR  # Day 0, late afternoon

PARTY = ("Alex", "Elara", "Tomas")

# Scene spaces per location (positioning.Zone fields). Features are the improvisation hooks
# (§31); `exit` zones allow fleeing; `entry_zone` is where arrivals are placed.
SPACES: dict[str, dict[str, Any]] = {
    "town_gate": {
        "zones": [
            {"key": "gate", "name": "the gate arch", "exit": True},
            {"key": "wagon", "name": "the stuck wagon", "cover": "light"},
            {"key": "road", "name": "the muddy road"},
        ],
        "adjacency": [["gate", "wagon"], ["wagon", "road"], ["gate", "road"]],
        "positions": {},
    },
    "market_square": {
        "zones": [
            {"key": "square", "name": "the open square", "exit": True},
            {"key": "stalls", "name": "the covered stalls", "cover": "light"},
            {"key": "well", "name": "the well"},
        ],
        "adjacency": [["square", "stalls"], ["square", "well"], ["stalls", "well"]],
        "positions": {},
    },
    "red_lantern": {
        "zones": [
            {"key": "door", "name": "the door", "exit": True},
            {"key": "tables", "name": "the tables"},
            {"key": "bar", "name": "the bar", "cover": "light"},
            {"key": "hearth", "name": "the hearth"},
        ],
        "adjacency": [["door", "tables"], ["tables", "bar"], ["tables", "hearth"]],
        "positions": {},
    },
    "guard_house": {
        "zones": [
            {"key": "front_desk", "name": "the front desk", "exit": True},
            {"key": "records", "name": "the records room"},
            {"key": "cells", "name": "the cells"},
        ],
        "adjacency": [["front_desk", "records"], ["front_desk", "cells"]],
        "positions": {},
    },
    "warehouse_district": {
        "zones": [
            {"key": "street", "name": "the warehouse street", "exit": True},
            {"key": "alley", "name": "a narrow alley", "cover": "light"},
        ],
        "adjacency": [["street", "alley"]],
        "positions": {},
    },
    "oric_warehouse": {
        "zones": [
            {"key": "door", "name": "the warehouse door", "exit": True},
            {
                "key": "floor",
                "name": "the main floor",
                "cover": "heavy",
                "features": ["stacked crates", "a heavy shelf"],
            },
            {
                "key": "office",
                "name": "the office",
                "cover": "light",
                "features": ["a wooden table", "a hanging oil lantern"],
            },
            {
                "key": "loft",
                "name": "the loft",
                "features": ["a cloth curtain", "a side window"],
                "exit": True,
            },
        ],
        "adjacency": [["door", "floor"], ["floor", "office"], ["floor", "loft"]],
        "positions": {},
    },
    "restricted_dock": {
        "zones": [
            {"key": "fence", "name": "the fence gate", "exit": True},
            {"key": "pier", "name": "the pier"},
            {"key": "shed", "name": "the boat shed", "cover": "heavy"},
        ],
        "adjacency": [["fence", "pier"], ["pier", "shed"]],
        "positions": {},
    },
    "river_bridge": {
        "zones": [{"key": "span", "name": "the bridge span", "exit": True}],
        "adjacency": [],
        "positions": {},
    },
    "north_road": {
        "zones": [{"key": "road", "name": "the north road", "exit": True}],
        "adjacency": [],
        "positions": {},
    },
    "old_quarry": {
        "zones": [
            {"key": "entrance", "name": "the quarry entrance", "exit": True},
            {"key": "pit", "name": "the quarry pit", "cover": "heavy"},
        ],
        "adjacency": [["entrance", "pit"]],
        "positions": {},
    },
}

LOCATIONS: list[dict[str, Any]] = [
    # key, name, type, descriptor (what strangers see), features (narration decoration), entry
    {
        "key": "town_gate",
        "name": "Town Gate",
        "type": "gate",
        "descriptor": "the town gate",
        "features": ["a wagon with a lost wheel", "two guards arguing with a merchant"],
        "entry_zone": "gate",
    },
    {
        "key": "market_square",
        "name": "Market Square",
        "type": "square",
        "descriptor": "the market square",
        "features": ["rain-slick cobbles", "half-shuttered stalls"],
        "entry_zone": "square",
    },
    {
        "key": "red_lantern",
        "name": "Red Lantern Tavern",
        "type": "building",
        "descriptor": "a tavern with red-glowing windows",
        "features": ["a low fire in the hearth", "a long scarred bar"],
        "entry_zone": "door",
    },
    {
        "key": "guard_house",
        "name": "Guard House",
        "type": "building",
        "descriptor": "the guard house",
        "features": ["a front desk", "a shelf of patrol logs"],
        "entry_zone": "front_desk",
    },
    {
        "key": "warehouse_district",
        "name": "Warehouse District",
        "type": "district",
        "descriptor": "the warehouse district",
        "features": ["rows of locked warehouses", "the smell of the river"],
        "entry_zone": "street",
    },
    {
        "key": "oric_warehouse",
        "name": "Oric's Warehouse",
        "type": "building",
        "descriptor": "a shuttered warehouse with a faded merchant sign",
        "features": ["dust over everything", "a merchant's sign, paint flaking"],
        "entry_zone": "door",
    },
    {
        "key": "restricted_dock",
        "name": "Restricted Dock",
        "type": "dock",
        "descriptor": "a fenced dock with a guard post",
        "features": ["pale clay underfoot", "a locked boat shed"],
        "entry_zone": "fence",
    },
    {
        "key": "river_bridge",
        "name": "River Bridge",
        "type": "bridge",
        "descriptor": "the river bridge",
        "features": ["a toll post", "grey water below"],
        "entry_zone": "span",
    },
    {
        "key": "north_road",
        "name": "North Road",
        "type": "road",
        "descriptor": "the north road",
        "features": ["wheel ruts", "cold forest on both sides"],
        "entry_zone": "road",
    },
    {
        "key": "old_quarry",
        "name": "Old Quarry Entrance",
        "type": "site",
        "descriptor": "the old quarry road",
        "features": ["abandoned cutting gear", "a faint metallic sound from below"],
        "entry_zone": "entrance",
    },
]
LATENT_LOCATIONS = [
    "residences",
    "temple",
    "smithy",
    "other warehouses",
    "cemetery",
    "river islands",
]

# topology (§5) with travel times
EDGES: list[tuple[str, str, int]] = [
    ("town_gate", "market_square", 120),
    ("town_gate", "north_road", 300),
    ("market_square", "red_lantern", 60),
    ("market_square", "guard_house", 240),
    ("market_square", "river_bridge", 180),
    ("market_square", "warehouse_district", 420),
    ("warehouse_district", "oric_warehouse", 120),
    ("warehouse_district", "restricted_dock", 240),
    ("north_road", "old_quarry", 2400),
]
# §5: tavern → guard house 5 min (60+240); tavern → restricted dock 12 min (60+420+240);
# town (gate) → quarry 45 min (300+2400).

PARTY_KNOWN_LOCATIONS = (
    "town_gate",
    "market_square",
    "red_lantern",
    "guard_house",
    "warehouse_district",
    "river_bridge",
    "north_road",
)

MIRA_BUILD = {
    "attributes": {
        "attr.might": 4,
        "attr.agility": 5,
        "attr.intellect": 6,
        "attr.presence": 6,
        "attr.resolve": 6,
    },
    "skills": {"skill.awareness": 2, "skill.persuasion": 2},
}
RENN_BUILD = {
    "attributes": {
        "attr.might": 6,
        "attr.agility": 5,
        "attr.intellect": 5,
        "attr.presence": 7,
        "attr.resolve": 5,
    },
    "skills": {
        "skill.melee": 2,
        "skill.persuasion": 2,
        "skill.intimidation": 2,
        "skill.awareness": 1,
    },
}
GUARD_BUILD = {
    "attributes": {
        "attr.might": 5,
        "attr.agility": 5,
        "attr.intellect": 4,
        "attr.presence": 4,
        "attr.resolve": 5,
    },
    "skills": {"skill.melee": 1, "skill.awareness": 1},
}

FULL_BEHAVIOR = {
    **BEHAVIOR,
    "Mira": {
        "summary": (
            "Owner of the Red Lantern: practical, protective, observant, risk-averse, with a dry "
            "humour. Evades questions when guards are near; may say more privately once she "
            "trusts someone."
        ),
        "dimensions": {
            "risk_tolerance": 0.25,
            "aggression": 0.15,
            "empathy": 0.6,
            "curiosity": 0.5,
            "loyalty": 0.7,
            "impulsiveness": 0.2,
            "honesty": 0.7,
            "sociability": 0.6,
            "ambition": 0.3,
        },
    },
    "Renn": {
        "summary": (
            "Captain of the Frostbridge town guard: controlled, socially competent, pragmatic, "
            "status-conscious, increasingly desperate."
        ),
        "dimensions": {
            "risk_tolerance": 0.55,
            "aggression": 0.6,
            "empathy": 0.3,
            "curiosity": 0.4,
            "loyalty": 0.3,
            "impulsiveness": 0.3,
            "honesty": 0.2,
            "sociability": 0.65,
            "ambition": 0.8,
        },
    },
    "Dock thief": {
        "summary": "A desperate dock thief: wants useful goods and a way out, not a fight.",
        "dimensions": {"risk_tolerance": 0.4, "aggression": 0.3, "honesty": 0.3},
    },
}

LETTER_TEXT = (
    "If anything happens to me, look to the river. The manifests don't match what moves after "
    "midnight. I made the mistake of asking the wrong man about it."
)
LEDGER_TEXT = (
    "Private ledger of O. Dane. Crates received against the dock manifests: 14 short on the "
    "third, 9 short on the ninth, 21 short on the sixteenth — every shortfall on a night the "
    "restricted dock ran a late barge. Someone is moving salvage that never reaches the books."
)
NOTICE_TEXT = (
    "NOTICE. Oric Dane, merchant of the Warehouse District, has not been seen for nine days. "
    "Any person with knowledge of his whereabouts should report to the Guard House. A reward "
    "is offered by the Merchants' Table."
)

# §23 fixed generated artifact (FakeModel fixture mode): one passive, one activated effect,
# registered primitives only; no teleport / resurrection / permanent attribute increase.
FIXED_ARTIFACT = {
    "key": "item.frostglass_shard",
    "name": "Frostglass Shard",
    "tier": "low",
    "description": (
        "A thumb-sized shard of pre-Frost glass that holds a faint blue light in the cold."
    ),
    "passive": {
        "type": "modify_check",
        "params": {"check": "check.*", "op": "add", "amount": 1, "when": "darkness"},
    },
    "activated": {
        "type": "apply_condition",
        "params": {"condition": "condition.hidden", "duration_seconds": 60, "uses_per_day": 1},
    },
}
FORBIDDEN_ARTIFACT_PRIMITIVES = {"teleport", "resurrect", "modify_attribute"}


class SeedError(RuntimeError):
    pass


@dataclass
class FrostbridgeWorld:
    h: CampaignHandle
    world: WorldService
    knowledge: KnowledgeService
    actors: dict[str, uuid.UUID] = field(default_factory=dict)  # name -> actor id
    entities: dict[str, uuid.UUID] = field(default_factory=dict)  # name -> entity id
    facts: dict[str, uuid.UUID] = field(default_factory=dict)  # key -> fact id
    locations: dict[str, uuid.UUID] = field(default_factory=dict)  # key -> location id
    location_entities: dict[str, uuid.UUID] = field(default_factory=dict)
    items: dict[str, uuid.UUID] = field(default_factory=dict)  # key -> item id
    clues: dict[str, uuid.UUID] = field(default_factory=dict)
    scheduled: dict[str, uuid.UUID] = field(default_factory=dict)
    mystery: uuid.UUID | None = None
    party: uuid.UUID | None = None
    faction: uuid.UUID | None = None
    plan: uuid.UUID | None = None
    scene: uuid.UUID | None = None
    known_by: dict[str, set[str]] = field(default_factory=dict)  # fact key -> actor names
    artifact: dict[str, Any] = field(default_factory=dict)
    artifact_source: str = "fixture"  # fixture | world_author
    artifact_errors: list[str] = field(default_factory=list)

    # compatibility with the tavern `SeededWorld` shape used by shared helpers
    @property
    def tavern(self) -> uuid.UUID:
        return self.locations["red_lantern"]

    @property
    def guard_house(self) -> uuid.UUID:
        return self.locations["guard_house"]

    @property
    def dagger(self) -> uuid.UUID:
        return self.items["dagger"]

    def summary(self) -> dict[str, Any]:
        return {
            "campaign_id": str(self.h.campaign_id),
            "timeline_id": str(self.h.timeline_id),
            "scene_id": str(self.scene),
            "fixture": "frostbridge",
            "actors": {k: str(v) for k, v in self.actors.items()},
            "entities": {k: str(v) for k, v in self.entities.items()},
            "facts": {k: str(v) for k, v in self.facts.items()},
            "locations": {k: str(v) for k, v in self.locations.items()},
            "items": {k: str(v) for k, v in self.items.items()},
            "clues": {k: str(v) for k, v in self.clues.items()},
            "scheduled": {k: str(v) for k, v in self.scheduled.items()},
            "mystery_id": str(self.mystery),
            "party_id": str(self.party),
        }


async def seed_frostbridge(
    session: AsyncSession,
    *,
    name: str = "frostbridge",
    engine_version: str = "dev",
    artifact_provider=None,
    settings=None,
) -> FrostbridgeWorld:
    """Build the whole fixture, verify it (§40) and return the symbolic map. On any failure the
    campaign is deleted again (cascade) and the error re-raised: no half-seeded worlds."""
    world = WorldService(session)
    h = await world.create_campaign(
        name,
        ruleset_key="core_adventure",
        ruleset_version="0.1.0",
        engine_version=engine_version,
        settings={
            "player_canon_policy": "personal",
            "spotlight": {"visible_reactions": 2, "ai_to_ai_exchanges": 1},
            "narration_style": {"tone": "grounded frontier realism, cold rain"},
        },
    )
    w = FrostbridgeWorld(h, world, KnowledgeService(session))
    # §23: with a provider, the artifact is generated (one bounded call + one retry) before the
    # unit of work opens, so no database transaction waits on a model; FIXED_ARTIFACT is both
    # the fixture-mode answer and the fallback when generation fails validation.
    w.artifact = dict(FIXED_ARTIFACT)
    w.artifact_source = "fixture"
    if artifact_provider is not None:
        from app.config import get_settings
        from app.worldgen.artifact import generate_artifact

        definition, errors = await generate_artifact(
            session,
            h,
            provider=artifact_provider,
            settings=settings or get_settings(),
            theme="a relic of the Long Frost, the century-long winter that ended twenty years ago",
            key=FIXED_ARTIFACT["key"],
        )
        await session.commit()
        if definition is not None:
            w.artifact = {**definition, "description": definition.get("description") or ""}
            w.artifact_source = "world_author"
        else:
            w.artifact_errors = errors
    try:
        async with unit_of_work(session):
            await _build(session, w)
            await verify(session, w)
    except Exception:
        # the unit of work rolled everything back; the campaign row went with it
        await _remove_campaign(session, h.campaign_id)
        raise
    return w


async def _remove_campaign(session: AsyncSession, campaign_id: uuid.UUID) -> None:
    """The campaign row itself was created before the unit of work began (its own
    transaction); remove it so a failed seed leaves nothing behind."""
    try:
        await session.rollback()
        await session.execute(delete(Campaign).where(Campaign.id == campaign_id))
        await session.commit()
    except Exception:  # noqa: BLE001 - must not mask the seed error
        await session.rollback()


# ---------------------------------------------------------------------------------------------
# building
# ---------------------------------------------------------------------------------------------


async def _build(session: AsyncSession, w: FrostbridgeWorld) -> None:
    world, k, h = w.world, w.knowledge, w.h
    psy = PsychologyService(session)
    mem = MemoryService(session)
    myst = MysteryService(session)
    sched = ScheduleService(session)

    # -- clock: Day 0, late afternoon (§6, §19)
    await world.advance_time(h, OPENING_TICK, reason="campaign start: late afternoon, cold rain")

    # -- locations and topology (§5)
    for spec in LOCATIONS:
        loc = await world.create_location(
            h,
            spec["name"],
            location_type=spec["type"],
            detail_level="materialized",
            importance_tier="important"
            if spec["key"] in ("red_lantern", "oric_warehouse")
            else "standard",
            properties={
                "features": [
                    {
                        "description": f,
                        "classification": "furnishing",
                        "canon_status": "established",
                    }
                    for f in spec["features"]
                ],
                "space": SPACES[spec["key"]],
                "entry_zone": spec["entry_zone"],
            },
            metadata={"descriptor": spec["descriptor"], "fixture_key": spec["key"]},
        )
        w.locations[spec["key"]] = loc.id
        w.location_entities[spec["key"]] = loc.entity_id
    for nm in LATENT_LOCATIONS:
        await world.create_location(
            h, nm, location_type="other", detail_level="latent", importance_tier="background"
        )
    for a, b, secs in EDGES:
        await world.connect_locations(h, w.locations[a], w.locations[b], travel_seconds=secs)

    # -- actors (§7–§9, §11–§13, §30; gate dressing §6)
    async def actor(
        nm: str,
        *,
        controller: str,
        actor_type: str,
        build: dict[str, Any],
        where: str | None,
        importance: str,
        descriptor: str,
        behavior_key: str | None = None,
    ) -> Actor:
        a = await world.create_actor(
            h,
            nm,
            actor_type=actor_type,
            controller_type=controller,
            location_id=w.locations[where] if where else None,
            importance_tier=importance,
            mechanical_profile=dict(build),
            behavior_profile=dict(FULL_BEHAVIOR.get(behavior_key or nm, {})),
            metadata={"descriptor": descriptor},
        )
        w.actors[nm] = a.id
        w.entities[nm] = a.entity_id
        return a

    await actor(
        "Alex",
        controller="human",
        actor_type="pc",
        build=FROSTBRIDGE_BUILDS["alex"],
        where="town_gate",
        importance="full",
        descriptor="a travel-worn newcomer",
    )
    await actor(
        "Elara",
        controller="ai",
        actor_type="pc",
        build=FROSTBRIDGE_BUILDS["elara"],
        where="town_gate",
        importance="full",
        descriptor="a lean woman with a scout's bearing",
    )
    await actor(
        "Tomas",
        controller="ai",
        actor_type="pc",
        build=FROSTBRIDGE_BUILDS["tomas"],
        where="town_gate",
        importance="full",
        descriptor="a broad man who carries himself like a guard",
    )
    await actor(
        "Mira",
        controller="ai",
        actor_type="npc",
        build=MIRA_BUILD,
        where="red_lantern",
        importance="important",
        descriptor="the innkeeper",
    )
    await actor(
        "Renn",
        controller="ai",
        actor_type="npc",
        build=RENN_BUILD,
        where="red_lantern",
        importance="full",
        descriptor="a guard captain in a wet cloak",
    )
    oric = await actor(
        "Oric Dane",
        controller="dormant",
        actor_type="npc",
        build={"attributes": {"attr.intellect": 6}},
        where=None,
        importance="important",
        descriptor="a missing merchant",
    )
    w.actors["Oric"], w.entities["Oric"] = oric.id, oric.entity_id
    for i in (1, 2):
        await actor(
            f"Dock thief {i}",
            controller="ai",
            actor_type="npc",
            build=FROSTBRIDGE_BUILDS["thief"],
            where="warehouse_district",
            importance="background",
            descriptor="a thief in dark clothing",
            behavior_key="Dock thief",
        )
    for nm, desc in (
        ("Gate guard Hale", "a gate guard"),
        ("Gate guard Brisk", "a younger gate guard"),
        ("Irritated merchant", "an irritated merchant"),
    ):
        await actor(
            nm,
            controller="scripted",
            actor_type="npc",
            build=GUARD_BUILD,
            where="town_gate",
            importance="background",
            descriptor=desc,
        )

    # Oric is objectively dead (§13); the fact below is the event that records it
    oric.alive = False

    # -- party (§24) and equipment
    party_ids = [w.actors[n] for n in PARTY]
    w.party = (
        await world.create_party(
            h,
            "the travellers",
            party_ids,
            shared_resources={"currency": "modest", "supplies_days": 4},
        )
    ).id
    await k.introduce(h, party_ids)
    for n in PARTY:
        for key in PARTY_KNOWN_LOCATIONS:
            await k.learn_identity(h, w.actors[n], w.location_entities[key], _loc_name(key))
    for n in ("Mira", "Renn"):
        for key in w.locations:
            await k.learn_identity(h, w.actors[n], w.location_entities[key], _loc_name(key))
        await k.learn_identity(h, w.actors[n], w.entities["Oric"], "Oric Dane")
    await k.learn_identity(h, w.actors["Mira"], w.entities["Renn"], "Captain Renn")
    await k.learn_identity(h, w.actors["Renn"], w.entities["Mira"], "Mira Holt")
    for i in (1, 2):
        t = w.actors[f"Dock thief {i}"]
        await k.learn_identity(
            h, t, w.location_entities["warehouse_district"], "Warehouse District"
        )
        await k.learn_identity(h, t, w.location_entities["oric_warehouse"], "Oric's warehouse")
        await k.learn_identity(h, t, w.location_entities["restricted_dock"], "the restricted dock")
    await k.introduce(h, [w.actors["Dock thief 1"], w.actors["Dock thief 2"]])

    async def gear(owner: str, key: str, nm: str, template: str, **kw: Any) -> None:
        w.items[key] = (
            await world.create_item(
                h, nm, template_key=template, possessor_actor_id=w.actors[owner], **kw
            )
        ).id

    await gear("Alex", "alex_knife", "knife", "item.knife")
    await gear("Alex", "alex_bow", "hunting bow", "item.bow")
    await gear("Alex", "supplies", "travel supplies", "item.travel_supplies", equipped=False)
    await gear("Alex", "purse", "coin purse", "item.coin_purse", equipped=False)
    await gear("Elara", "elara_bow", "scout's bow", "item.bow")
    await gear("Elara", "elara_knife", "skinning knife", "item.knife")
    await gear("Tomas", "tomas_sword", "guard-issue sword", "item.sword")
    await gear("Tomas", "tomas_armor", "worn light armour", "item.light_armor")
    await gear("Renn", "renn_sword", "captain's sword", "item.sword")
    for i in (1, 2):
        await gear(f"Dock thief {i}", f"thief{i}_knife", "knife", "item.knife")

    # -- goals, autonomy, plans (§8, §9, §11, §12, §18)
    g = psy.create_goal
    await g(h, w.actors["Elara"], "find my brother Joren Venn", priority=90)
    await g(
        h, w.actors["Elara"], "protect vulnerable frontier residents where practical", priority=50
    )
    await g(h, w.actors["Elara"], "avoid becoming dependent on others", priority=40)
    await g(
        h,
        w.actors["Tomas"],
        "prove public institutions can still serve people honestly",
        priority=80,
    )
    await g(
        h, w.actors["Tomas"], "build useful civic connections in frontier settlements", priority=55
    )
    await g(h, w.actors["Tomas"], "avoid becoming cynical like my former colleagues", priority=45)
    await g(h, w.actors["Mira"], "keep my family and the Red Lantern safe", priority=85)
    await g(
        h,
        w.actors["Mira"],
        "avoid open conflict with Captain Renn",
        priority=70,
        target_entity_ids=[w.entities["Renn"]],
    )
    await g(
        h,
        w.actors["Renn"],
        "prevent discovery of Oric's fate",
        priority=95,
        target_entity_ids=[w.entities["Oric"]],
    )
    await g(
        h, w.actors["Renn"], "ensure the next smuggling shipment leaves successfully", priority=85
    )
    await g(
        h,
        w.actors["Renn"],
        "accumulate enough money to leave Frostbridge before it collapses",
        priority=70,
    )
    for i in (1, 2):
        await g(
            h,
            w.actors[f"Dock thief {i}"],
            "steal useful goods and escape; never fight to the death",
            priority=80,
        )
    await psy.set_ai_profile(w.actors["Elara"], autonomy={"item_transfer": "ask"})
    await psy.set_ai_profile(w.actors["Tomas"], autonomy={"item_transfer": "autonomous"})

    # -- River Compact (§18): a faction nobody knows exists, with a plan at step 1
    faction = await world.create_faction(
        h,
        "River Compact",
        description="Local smuggling ring moving restricted salvage through the river docks.",
        resources={
            "cash": "moderate",
            "dock_access": True,
            "laborers": 3,
            "corrupt_guard_captain": 1,
            "external_buyers": 2,
        },
        members={w.actors["Renn"]: "corrupt guard captain"},
        public=False,
    )
    w.faction = faction.id
    compact_goal = await g(
        h,
        faction.id,
        "move the next restricted-salvage shipment out of Frostbridge",
        owner_type="faction",
        goal_type="faction",
        priority=90,
    )
    renn_free_prereq = {"kind": "actor_free", "actor_id": str(w.actors["Renn"])}
    w.plan = (
        await psy.create_plan(
            h,
            compact_goal.id,
            [
                {"title": "assemble cargo", "at_tick": 2 * DAY + 12 * HOUR},
                {"title": "destroy documentation linking Renn"},  # the Day +3 scheduled event
                {
                    "title": "load barge",
                    "at_tick": 5 * DAY + 18 * HOUR,
                    "prerequisites": [renn_free_prereq],
                },
                {"title": "depart at night", "kind": "decision", "at_tick": 5 * DAY + 23 * HOUR},
                {"title": "pay external buyer", "at_tick": 6 * DAY + 12 * HOUR},
            ],
            current_step=0,
        )
    ).id

    # -- relationships (§10, §11)
    r = k.seed_relationship
    A, E, T, M, R = (w.actors[n] for n in ("Alex", "Elara", "Tomas", "Mira", "Renn"))
    await r(h, E, T, trust=48, respect=55, affection=20, fear=0, resentment=8, familiarity=45)
    await r(h, T, E, trust=62, respect=68, affection=28, fear=0, resentment=4, familiarity=45)
    await r(h, E, A, trust=60, respect=52, affection=35, fear=0, resentment=2, familiarity=50)
    await r(h, T, A, trust=55, respect=50, affection=30, fear=0, resentment=0, familiarity=50)
    await r(h, A, E, trust=55, respect=58, affection=30, fear=0, resentment=0, familiarity=50)
    await r(h, A, T, trust=50, respect=50, affection=25, fear=0, resentment=0, familiarity=50)
    await r(h, M, R, trust=-35, respect=5, fear=48, familiarity=60)
    await r(h, M, w.actors["Oric"], trust=58, affection=42, familiarity=55)
    await r(h, R, M, trust=10, respect=20, familiarity=60)

    # -- objective truth and who holds it (§11–§16, §20, §42)
    async def fact(
        key: str,
        predicate: str,
        *,
        subject: str | None = None,
        obj: str | None = None,
        value: Any = None,
        sensitivity: str = "secret",
        known_by: tuple[str, ...] = (),
        canon_status: str = "established",
    ) -> uuid.UUID:
        row = await k.create_fact(
            h,
            key=key,
            predicate=predicate,
            subject_entity_id=_ent(w, subject),
            object_entity_id=_ent(w, obj),
            value=value,
            canon_status=canon_status,
            sensitivity=sensitivity,
            known_by=[w.actors[n] for n in known_by],
        )
        w.facts[key] = row.id
        w.known_by[key] = set(known_by)
        return row.id

    await fact(
        "oric_missing",
        "has been missing for nine days",
        subject="Oric",
        sensitivity="public",
        known_by=("Mira", "Renn", "Dock thief 1", "Dock thief 2"),
    )
    await fact("oric_dead", "is dead", subject="Oric", known_by=("Renn",))
    await fact(
        "renn_met_oric",
        "met privately at the Red Lantern two nights before the disappearance",
        subject="Renn",
        obj="Oric",
        sensitivity="private",
        known_by=("Mira", "Renn"),
    )
    await fact(
        "renn_oric_argued",
        "argued tensely with",
        subject="Renn",
        obj="Oric",
        sensitivity="private",
        known_by=("Mira", "Renn"),
    )
    await fact(
        "oric_frightened_after",
        "appeared frightened after the captain left",
        subject="Oric",
        sensitivity="private",
        known_by=("Mira",),
    )
    await fact("renn_killed_oric", "killed", subject="Renn", obj="Oric", known_by=("Renn",))
    await fact(
        "renn_smuggling",
        "runs restricted salvage through the river docks",
        subject="Renn",
        known_by=("Renn",),
    )
    await fact(
        "oric_found_discrepancies",
        "found shipping discrepancies tied to the restricted dock",
        subject="Oric",
        known_by=("Renn",),
    )
    await fact(
        "oric_visited_dock",
        "confronted the captain at the restricted dock",
        subject="Oric",
        obj="Renn",
        known_by=("Renn",),
    )
    await fact(
        "body_concealed",
        "lies concealed outside town",
        subject="Oric",
        known_by=("Renn",),
    )
    await fact(
        "ledger_shows_discrepancies",
        "kept a private ledger of inventory shortfalls matching restricted-dock nights",
        subject="Oric",
        known_by=(),
    )
    await fact(
        "satchel_has_dock_clay",
        "carries pale clay found only at the restricted dock",
        subject="Oric",
        known_by=(),
    )
    await fact(
        "guard_log_gap",
        "has a numbering gap around the restricted-dock patrol on the night of the disappearance",
        value="guard patrol log",
        sensitivity="private",
        known_by=(),
    )
    await fact(
        "renn_altered_log",
        "removed a page from the guard patrol log",
        subject="Renn",
        known_by=("Renn",),
    )
    await fact(
        "next_shipment_day5",
        "plans a barge departure on the fifth night",
        subject="Renn",
        known_by=("Renn",),
    )
    await fact(
        "shipment_departed",
        "a barge of restricted salvage left Frostbridge on the fifth night",
        sensitivity="private",
        known_by=(),
        canon_status="latent",
    )
    await fact(
        "dagger_harms_spirits",
        "deals extra harm to spirits",
        value="Veyra's Chipped Dagger",
        known_by=(),
    )
    await fact(
        "oric_owed_mira",
        "owed an ordinary business debt to",
        subject="Oric",
        obj="Mira",
        sensitivity="private",
        known_by=("Mira", "Oric"),
    )
    await fact(
        "caravan_arrival",
        "a trade caravan arrives in Frostbridge",
        value="Day +2",
        sensitivity="public",
        known_by=(),
        canon_status="latent",
    )
    await fact(
        "quarry_disturbance",
        "metallic noises and blue light come from beneath the old quarry at night",
        value="Day +8 escalation",
        sensitivity="public",
        known_by=(),
        canon_status="latent",
    )
    await fact(
        "quarry_machinery",
        "ancient magical machinery beneath the quarry is intermittently activating",
        known_by=(),
        canon_status="latent",
    )
    # Renn is uncertain what else Oric hid (§12) and Mira only suspects the docks (§42)
    await k.seed_belief(
        h,
        w.actors["Renn"],
        Proposition("may have hidden further evidence", subject=str(w.entities["Oric"])),
        "suspected",
        0.5,
    )
    await k.seed_belief(
        h,
        w.actors["Mira"],
        Proposition("something unlawful moves through the restricted dock at night"),
        "suspected",
        0.4,
    )
    # companions' general beliefs (§8, §9)
    await k.seed_belief(
        h,
        w.actors["Elara"],
        Proposition("frontier authorities often protect themselves first"),
        "believed",
        0.65,
    )
    await k.seed_belief(
        h, w.actors["Elara"], Proposition("authority deserves scrutiny"), "believed", 0.70
    )
    await k.seed_belief(
        h,
        w.actors["Tomas"],
        Proposition("most guards are ordinary people trying to keep order"),
        "believed",
        0.78,
    )
    await k.seed_belief(
        h,
        w.actors["Tomas"],
        Proposition("accusations against officials require evidence"),
        "believed",
        0.82,
    )

    # -- core memories (§8)
    cm = mem.create_memory
    await cm(
        h,
        w.actors["Elara"],
        "Joren left home after our argument; I never took it back.",
        seed=True,
        is_core=True,
        salience=0.95,
        emotional_weight=0.8,
    )
    await cm(
        h,
        w.actors["Elara"],
        "The expedition where the officials never sent the aid they promised; we buried two.",
        seed=True,
        is_core=True,
        salience=0.85,
        emotional_weight=0.7,
    )
    await cm(
        h,
        w.actors["Elara"],
        "Alex pulled us through the river crossing when the ice went; I owe him for that.",
        seed=True,
        is_core=True,
        salience=0.8,
        emotional_weight=0.5,
        entity_ids=[w.entities["Alex"]],
    )
    await cm(
        h,
        w.actors["Tomas"],
        "The day I turned in my own sergeant for taking bribes, and was thanked by no one.",
        seed=True,
        is_core=True,
        salience=0.85,
        emotional_weight=0.6,
    )

    # -- items and documents (§15, §22, §31, §35; gate notice gives the party Oric's name)
    W = w.locations
    w.items["dagger"] = (
        await world.create_item(
            h,
            "Veyra's Chipped Dagger",
            template_key="item.dagger",
            location_id=W["oric_warehouse"],
            zone_key="floor",
            concealed=True,
            concealment_difficulty="routine",
            importance_tier="important",
            public_properties={"description": "a well-made old dagger, chipped near the tip"},
            hidden_properties={
                "bonus_damage_vs_tags": {"spirit": 2},
                "lore": "forged from metal salvaged from a pre-Frost relay structure",
            },
        )
    ).id
    w.items["ledger"] = (
        await world.create_item(
            h,
            "Oric's private ledger",
            template_key="item.document",
            location_id=W["oric_warehouse"],
            zone_key="office",
            concealed=True,
            concealment_difficulty="easy",
            importance_tier="important",
            public_properties={"description": "a slim ledger bound in grey cloth"},
            document={
                "text": LEDGER_TEXT,
                "author_entity_id": w.entities["Oric"],
                "conveys": [
                    {
                        "kind": "fact_ref",
                        "ref_id": str(w.facts["ledger_shows_discrepancies"]),
                        "stance": "asserts_true",
                        "about_speaker_self": True,
                    },
                    {
                        "kind": "proposition",
                        "proposition": {
                            "predicate": "every shortfall fell on a night the dock ran a late barge"
                        },
                        "stance": "asserts_true",
                    },
                ],
            },
        )
    ).id
    w.items["letter"] = (
        await world.create_item(
            h,
            "Oric's hidden letter",
            template_key="item.document",
            location_id=W["oric_warehouse"],
            zone_key="office",
            concealed=True,
            concealment_difficulty="moderate",
            importance_tier="important",
            public_properties={"description": "a folded letter, sealed with plain wax"},
            document={
                "text": LETTER_TEXT,
                "author_entity_id": w.entities["Oric"],
                "conveys": [
                    {
                        "kind": "fact_ref",
                        "ref_id": str(w.facts["oric_found_discrepancies"]),
                        "stance": "asserts_true",
                        "fidelity": "partial",
                        "about_speaker_self": True,
                    },
                    {
                        "kind": "proposition",
                        "proposition": {
                            "predicate": "the manifests do not match what moves after midnight"
                        },
                        "stance": "asserts_true",
                    },
                    {
                        "kind": "proposition",
                        "proposition": {
                            "subject_entity_id": str(w.entities["Oric"]),
                            "predicate": "asked the wrong man about the river",
                        },
                        "stance": "asserts_true",
                        "about_speaker_self": True,
                    },
                ],
            },
        )
    ).id
    w.items["satchel"] = (
        await world.create_item(
            h,
            "Oric's mud-caked satchel",
            template_key="item.satchel",
            location_id=W["oric_warehouse"],
            zone_key="floor",
            concealed=True,
            concealment_difficulty="routine",
            public_properties={"description": "a merchant's satchel caked in pale clay"},
        )
    ).id
    w.items["warehouse_lantern"] = (
        await world.create_item(
            h,
            "hanging oil lantern",
            template_key="item.oil_lantern",
            location_id=W["oric_warehouse"],
            zone_key="office",
            equipped=False,
        )
    ).id
    w.items["patrol_log"] = (
        await world.create_item(
            h,
            "guard patrol log",
            template_key="item.document",
            location_id=W["guard_house"],
            zone_key="records",
            concealed=True,
            concealment_difficulty="routine",
            public_properties={"description": "the bound patrol log; entry numbers skip once"},
            document={
                "text": (
                    "Patrol log, autumn. Entries 211, 212, 214, 215 — the restricted-dock "
                    "round of the ninth night is missing between 212 and 214."
                ),
                "conveys": [
                    {
                        "kind": "fact_ref",
                        "ref_id": str(w.facts["guard_log_gap"]),
                        "stance": "asserts_true",
                    }
                ],
            },
        )
    ).id
    w.items["log_draft"] = (
        await world.create_item(
            h,
            "patrol log draft sheet",
            template_key="item.document",
            location_id=W["guard_house"],
            zone_key="records",
            concealed=True,
            concealment_difficulty="easy",
            public_properties={"description": "a loose draft sheet in a clerk's hand"},
            document={
                "text": (
                    "Draft, ninth night: 213 — restricted dock round, Capt. R. and two men, "
                    "barge at the pier past midnight. To be copied fair."
                ),
                "conveys": [
                    {
                        "kind": "fact_ref",
                        "ref_id": str(w.facts["guard_log_gap"]),
                        "stance": "asserts_true",
                    },
                    {
                        "kind": "proposition",
                        "proposition": {
                            "predicate": "the captain walked the dock round on the ninth night"
                        },
                        "stance": "asserts_true",
                    },
                ],
            },
        )
    ).id
    w.items["gate_notice"] = (
        await world.create_item(
            h,
            "notice nailed to the gatepost",
            template_key="item.document",
            location_id=W["town_gate"],
            zone_key="gate",
            equipped=False,
            public_properties={"description": "a rain-spotted notice"},
            document={
                "text": NOTICE_TEXT,
                "conveys": [
                    {"kind": "identity", "entity_id": str(w.entities["Oric"]), "name": "Oric Dane"},
                    {
                        "kind": "fact_ref",
                        "ref_id": str(w.facts["oric_missing"]),
                        "stance": "asserts_true",
                    },
                ],
            },
        )
    ).id

    # -- §23 generated artifact slot (fixture mode: fixed, validated definition)
    await _store_artifact(session, w, w.artifact)
    w.items["artifact"] = (
        await world.create_item(
            h,
            w.artifact["name"],
            template_key="item.travel_supplies",
            possessor_actor_id=w.actors["Elara"],
            equipped=False,
            item_type="artifact",
            public_properties={"description": w.artifact.get("description", "")},
            hidden_properties={"definition_key": w.artifact["key"]},
        )
    ).id

    # -- mystery and clues (§14–§17)
    w.mystery = (
        await myst.create_mystery(
            h,
            key="oric_fate",
            question="What happened to Oric Dane?",
            truth_fact_ids=[
                w.facts["renn_killed_oric"],
                w.facts["renn_smuggling"],
                w.facts["oric_dead"],
            ],
            activate=True,
            stakeholders=["Mira Holt", "Captain Renn", "the Merchants' Table"],
        )
    ).id
    ent_of = {
        key: await _item_entity(session, w.items[key])
        for key in ("ledger", "letter", "satchel", "patrol_log", "log_draft")
    }

    async def clue(
        key: str, clue_type: str, fact_key: str | None, entity: uuid.UUID | None = None, **kw: Any
    ) -> None:
        c = await myst.create_clue(
            h,
            w.mystery,  # type: ignore[arg-type]
            key=key,
            clue_type=clue_type,
            supported_fact_id=w.facts[fact_key] if fact_key else None,
            physical_entity_id=entity,
            **kw,
        )
        w.clues[key] = c.id

    await clue(
        "ledger",
        "document",
        "ledger_shows_discrepancies",
        ent_of["ledger"],
        discovery_conditions={"location": "oric_warehouse", "zone": "office", "search": "easy"},
    )
    await clue("mira_account", "social", "renn_met_oric", reliability=0.9)
    await clue(
        "dock_mud",
        "physical",
        "satchel_has_dock_clay",
        ent_of["satchel"],
        discovery_conditions={"location": "oric_warehouse", "zone": "floor"},
    )
    await clue(
        "log_numbering",
        "physical",
        "guard_log_gap",
        ent_of["patrol_log"],
        discovery_conditions={"location": "guard_house", "zone": "records"},
    )
    await clue(
        "log_draft",
        "document",
        "guard_log_gap",
        ent_of["log_draft"],
        destructible=True,
        discovery_conditions={"location": "guard_house", "zone": "records", "until": "Day +3"},
    )
    await clue(
        "oric_letter",
        "document",
        "oric_found_discrepancies",
        ent_of["letter"],
        discovery_conditions={"location": "oric_warehouse", "zone": "office", "search": "moderate"},
    )

    # -- world clocks (§19, §36, §37, §38)
    w.scheduled["day2_caravan"] = (
        await sched.schedule(
            h,
            tick=2 * DAY + 10 * HOUR,
            event_type="fact.establish",
            payload={"fact_id": str(w.facts["caravan_arrival"]), "reason": "Day +2 caravan"},
            key="day2_caravan",
        )
    ).id
    w.scheduled["day2_market"] = (
        await sched.schedule(
            h,
            tick=2 * DAY + 10 * HOUR,
            event_type="location.state",
            payload={
                "location_id": str(W["market_square"]),
                "patch": {"activity": "high", "caravan_present": True},
            },
            key="day2_market",
        )
    ).id
    renn_free = [{"kind": "actor_free", "actor_id": str(w.actors["Renn"])}]
    w.scheduled["day3_log_draft"] = (
        await sched.schedule(
            h,
            tick=3 * DAY + 2 * HOUR,
            event_type="clue.destroy",
            payload={"clue_id": str(w.clues["log_draft"]), "reason": "Renn burns the draft"},
            prerequisites=renn_free
            + [{"kind": "clue_intact", "clue_id": str(w.clues["log_draft"])}],
            key="day3_log_draft",
        )
    ).id
    w.scheduled["day3_plan"] = (
        await sched.schedule(
            h,
            tick=3 * DAY + 2 * HOUR,
            event_type="plan.advance",
            payload={
                "plan_id": str(w.plan),
                "step": 1,
                "reason": "documentation linking Renn destroyed",
            },
            prerequisites=renn_free,
            key="day3_plan",
        )
    ).id
    w.scheduled["day5_renn_to_dock"] = (
        await sched.schedule(
            h,
            tick=5 * DAY + 22 * HOUR,
            event_type="actor.travel",
            payload={
                "actor_id": str(w.actors["Renn"]),
                "location_id": str(W["restricted_dock"]),
            },
            prerequisites=renn_free,
            key="day5_renn_to_dock",
        )
    ).id
    w.scheduled["day5_shipment"] = (
        await sched.schedule(
            h,
            tick=5 * DAY + 23 * HOUR,
            event_type="faction.shipment_departure",
            payload={
                "faction_id": str(w.faction),
                "plan_id": str(w.plan),
                "question": "The River Compact barge is loaded; does it depart tonight?",
                "on_proceed": {
                    "type": "fact.establish",
                    "fact_id": str(w.facts["shipment_departed"]),
                    "reason": "the shipment left",
                },
            },
            prerequisites=renn_free
            + [{"kind": "fact_true", "fact_id": str(w.facts["next_shipment_day5"])}],
            key="day5_shipment",
        )
    ).id
    w.scheduled["day8_quarry"] = (
        await sched.schedule(
            h,
            tick=8 * DAY + 22 * HOUR,
            event_type="fact.establish",
            payload={
                "fact_id": str(w.facts["quarry_disturbance"]),
                "reason": "Day +8 quarry escalation",
            },
            key="day8_quarry",
        )
    ).id

    # -- opening scene (§6): Town Gate, late afternoon, cold rain; no quest is presented
    gate_space = dict(SPACES["town_gate"])
    gate_space["positions"] = {
        **{str(w.actors[n]): {"zone": "gate"} for n in PARTY},
        str(w.actors["Gate guard Hale"]): {"zone": "wagon"},
        str(w.actors["Gate guard Brisk"]): {"zone": "wagon"},
        str(w.actors["Irritated merchant"]): {"zone": "wagon"},
    }
    scene = await world.start_scene(
        h,
        location_id=W["town_gate"],
        scene_type="social",
        participant_actor_ids=[
            *(w.actors[n] for n in PARTY),
            w.actors["Gate guard Hale"],
            w.actors["Gate guard Brisk"],
            w.actors["Irritated merchant"],
        ],
        state={"weather": "cold rain", "time_of_day": "late afternoon", "opening": True},
        space=gate_space,
    )
    w.scene = scene.id
    # Mira and Renn are in the tavern already: an offscreen scene until the party arrives
    tavern_space = dict(SPACES["red_lantern"])
    tavern_space["positions"] = {
        str(w.actors["Mira"]): {"zone": "bar"},
        str(w.actors["Renn"]): {"zone": "door"},
    }
    await world.start_scene(
        h,
        location_id=W["red_lantern"],
        scene_type="social",
        participant_actor_ids=[w.actors["Mira"], w.actors["Renn"]],
        space=tavern_space,
    )


# ---------------------------------------------------------------------------------------------
# verification (§40)
# ---------------------------------------------------------------------------------------------


async def verify(session: AsyncSession, w: FrostbridgeWorld) -> None:
    problems: list[str] = []
    # controllers: no gaps
    for nm, aid in w.actors.items():
        ctrl = (
            await session.execute(
                select(ActorController).where(
                    ActorController.actor_id == aid, ActorController.valid_until_event_id.is_(None)
                )
            )
        ).scalar_one_or_none()
        if ctrl is None:
            problems.append(f"actor {nm} has no active controller")
    # topology: every materialized location reachable from the gate
    reach = {
        loc.id
        for loc, _e, _s in await SceneService(session).connected_locations(w.locations["town_gate"])
    }
    for key, lid in w.locations.items():
        if key != "town_gate" and lid not in reach:
            problems.append(f"location {key} unreachable from the town gate")
    # mystery: present, locked, truth facts exist, routes redundant
    myst = MysteryService(session)
    if w.mystery is None:
        problems.append("mystery missing")
    else:
        m = await session.get(type(await myst._mystery(w.mystery)), w.mystery)
        if m is None or not m.solution_locked or m.status != "active":
            problems.append("mystery not active/locked")
        truths = await myst.truth_fact_ids(w.mystery)
        if not truths:
            problems.append("mystery has no truth facts")
        rr = await myst.routes_remaining(w.mystery)
        if not rr.solvable:
            problems.append("mystery has a fact with no intact clue route")
        if sum(1 for n in rr.intact_by_fact.values() if n > 0) < 3:
            problems.append("mystery needs at least three independent clue routes")
    # leakage matrix: belief rows linked to a non-public fact belong only to its knowers
    for key, fid in w.facts.items():
        fact = await session.get(Fact, fid)
        if fact is None:
            problems.append(f"fact {key} missing")
            continue
        if fact.sensitivity == "public":
            continue
        holders = {
            b.actor_id
            for b in (await session.execute(select(Belief).where(Belief.fact_id == fid))).scalars()
        }
        allowed = {w.actors[n] for n in w.known_by.get(key, set())}
        extra = holders - allowed
        if extra:
            names = [n for n, a in w.actors.items() if a in extra]
            problems.append(f"fact {key} leaked into beliefs of {names}")
    # items: templates exist in the ruleset; documents hash-match; hidden props stay hidden
    rs = RulesEngine.load("core_adventure").ruleset
    templates = set(getattr(rs, "equipment", {}).keys())
    for key, iid in w.items.items():
        item = await session.get(Item, iid)
        if item is None:
            problems.append(f"item {key} missing")
            continue
        if item.template_key and templates and item.template_key not in templates:
            problems.append(f"item {key} uses unknown template {item.template_key}")
        doc = await session.get(Document, iid)
        if (
            doc is not None
            and hashlib.sha256(doc.original_text.encode("utf-8")).hexdigest() != doc.content_hash
        ):
            problems.append(f"document {key} hash mismatch")
    dagger = await session.get(Item, w.items["dagger"])
    if dagger is None or dagger.hidden_properties.get("bonus_damage_vs_tags") != {"spirit": 2}:
        problems.append("dagger hidden property missing")
    if dagger is not None and "spirit" in str(dagger.public_properties):
        problems.append("dagger hidden property is public")
    # party membership
    members = {
        pm.actor_id
        for pm in (
            await session.execute(
                select(PartyMembership).where(PartyMembership.party_id == w.party)
            )
        ).scalars()
    }
    if members != {w.actors[n] for n in PARTY}:
        problems.append("party membership differs from Alex/Elara/Tomas")
    if problems:
        raise SeedError("; ".join(problems))


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------


def _loc_name(key: str) -> str:
    return next(s["name"] for s in LOCATIONS if s["key"] == key)


def _ent(w: FrostbridgeWorld, name: str | None) -> uuid.UUID | None:
    return w.entities[name] if name else None


async def _item_entity(session: AsyncSession, item_id: uuid.UUID) -> uuid.UUID:
    item = await session.get(Item, item_id)
    assert item is not None
    return item.entity_id


def validate_artifact(definition: dict[str, Any]) -> None:
    """§23 constraints, shared with generated campaigns (`worldgen.validate.mechanic_errors`):
    at most one passive and one activated effect, registered primitives only, nothing
    forbidden, low tier. Structural validity, not balance."""
    from app.worldgen.validate import mechanic_errors

    errors = mechanic_errors(definition, RulesEngine.load("core_adventure").ruleset)
    if errors:
        raise SeedError("; ".join(errors))


async def _store_artifact(
    session: AsyncSession, w: FrostbridgeWorld, definition: dict[str, Any]
) -> None:
    validate_artifact(definition)
    # §40: `make seed-demo` ensures Core Adventure is installed
    ruleset = await ensure_ruleset_installed(session, RulesEngine.load("core_adventure").ruleset)
    payload = dict(definition)
    content_hash = hashlib.sha256(repr(sorted(payload.items())).encode("utf-8")).hexdigest()
    async with EventTransaction(session, w.h.campaign_id, w.h.timeline_id) as tx:
        row = MechanicalDefinition(
            ruleset_id=ruleset.id,
            campaign_id=w.h.campaign_id,
            definition_key=definition["key"],
            definition_type="item",
            source_kind=w.artifact_source,
            source_ref="frostbridge §23 artifact slot",
            definition=payload,
            content_hash=content_hash,
            power={"tier": definition["tier"]},
        )
        session.add(row)
        await session.flush()
        event = await tx.emit(
            ev.MechanicalDefinitionCreated(
                definition_id=row.id,
                definition_key=definition["key"],
                definition_type="item",
                source_kind=w.artifact_source,
            )
        )
        row.created_event_id = event.id
