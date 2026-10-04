"""The Red Lantern tavern seed (frostbridge-demo.md §7–§12, §22, §25–§27, §42): Alex (human),
Elara and Tomas (AI PCs), Mira and Renn (AI NPCs), the locked objective truth about Oric,
Veyra's secret identity, the chipped dagger, goals, autonomy, relationships and a social scene.

Objective truth is seeded; only legitimate knowers hold beliefs. Symbolic names resolve to
runtime ids in the returned `SeededWorld` (tests never hard-code UUIDs).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.beliefs import Proposition
from app.persistence.models import Location
from app.services.knowledge import KnowledgeService
from app.services.psychology import PsychologyService
from app.services.world import CampaignHandle, WorldService

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

TAVERN_SPACE = {
    "zones": [{"key": "bar"}, {"key": "tables"}, {"key": "door"}],
    "adjacency": [["bar", "tables"], ["tables", "door"]],
    "positions": {},
}

BEHAVIOR = {
    "Elara": {
        "summary": "Former frontier scout searching for her missing younger brother Joren.",
        "traits": ["Keen Observer", "Frontier Veteran"],
        "dimensions": {
            "risk_tolerance": 0.65,
            "aggression": 0.40,
            "empathy": 0.67,
            "curiosity": 0.60,
            "loyalty": 0.72,
            "impulsiveness": 0.35,
            "honesty": 0.75,
            "sociability": 0.42,
            "ambition": 0.38,
        },
    },
    "Tomas": {
        "summary": "Former municipal guard and civic-minded traveler.",
        "traits": ["Guard Training", "Well Connected"],
        "dimensions": {
            "risk_tolerance": 0.50,
            "aggression": 0.45,
            "empathy": 0.62,
            "curiosity": 0.42,
            "loyalty": 0.68,
            "impulsiveness": 0.30,
            "honesty": 0.82,
            "sociability": 0.76,
            "ambition": 0.45,
        },
    },
    "Mira": {
        "summary": "Owner of the Red Lantern: practical, protective, observant, risk-averse.",
        "dimensions": {"risk_tolerance": 0.25, "honesty": 0.7, "sociability": 0.6},
    },
    "Renn": {
        "summary": "Captain of the town guard: controlled, status-conscious, desperate.",
        "dimensions": {"risk_tolerance": 0.55, "honesty": 0.2, "aggression": 0.6},
    },
}


@dataclass
class SeededWorld:
    h: CampaignHandle
    world: WorldService
    knowledge: KnowledgeService
    actors: dict[str, uuid.UUID] = field(default_factory=dict)  # name -> actor id
    entities: dict[str, uuid.UUID] = field(default_factory=dict)  # name -> entity id
    facts: dict[str, uuid.UUID] = field(default_factory=dict)
    tavern: uuid.UUID | None = None
    guard_house: uuid.UUID | None = None
    scene: uuid.UUID | None = None
    dagger: uuid.UUID | None = None
    veyra_entity: uuid.UUID | None = None

    def summary(self) -> dict:
        return {
            "campaign_id": str(self.h.campaign_id),
            "timeline_id": str(self.h.timeline_id),
            "scene_id": str(self.scene),
            "actors": {k: str(v) for k, v in self.actors.items()},
            "entities": {k: str(v) for k, v in self.entities.items()},
            "facts": {k: str(v) for k, v in self.facts.items()},
            "locations": {"tavern": str(self.tavern), "guard_house": str(self.guard_house)},
            "items": {"dagger": str(self.dagger)},
        }


async def seed_tavern(
    session: AsyncSession, *, name: str = "frostbridge-tavern", engine_version: str = "dev"
) -> SeededWorld:
    world = WorldService(session)
    k = KnowledgeService(session)
    h = await world.create_campaign(
        name, ruleset_key="core_adventure", ruleset_version="0.1.0", engine_version=engine_version
    )
    w = SeededWorld(h, world, k)
    w.tavern = (await world.create_location(h, "Red Lantern Tavern", location_type="building")).id
    w.guard_house = (await world.create_location(h, "Guard House", location_type="building")).id
    await world.connect_locations(h, w.tavern, w.guard_house, travel_seconds=300)

    async def actor(name, controller, build, importance="standard", extra=None):
        a = await world.create_actor(
            h,
            name,
            actor_type="pc" if controller == "human" or name in ("Elara", "Tomas") else "npc",
            controller_type=controller,
            location_id=w.tavern,
            importance_tier=importance,
            mechanical_profile={**build, **(extra or {})},
            behavior_profile=BEHAVIOR.get(name, {}),
            metadata={
                "descriptor": "a woman you have not met"
                if name in ("Elara", "Mira")
                else "a man you have not met"
            },
        )
        w.actors[name] = a.id
        w.entities[name] = a.entity_id
        return a

    await actor("Alex", "human", FROSTBRIDGE_BUILDS["alex"])
    await actor("Elara", "ai", FROSTBRIDGE_BUILDS["elara"], "full")
    await actor("Tomas", "ai", FROSTBRIDGE_BUILDS["tomas"], "full")
    await actor("Mira", "ai", {"attributes": {"attr.presence": 6}}, "important")
    await actor("Renn", "ai", {"attributes": {"attr.presence": 7, "attr.might": 6}}, "full")

    # everyone in the party knows each other; everyone knows the tavern by name
    party = [w.actors[n] for n in ("Alex", "Elara", "Tomas")]
    await k.introduce(h, party)
    tavern_entity = (await session.get(Location, w.tavern)).entity_id
    for a in w.actors.values():
        await k.learn_identity(h, a, tavern_entity, "Red Lantern Tavern")
    # the party knows Mira as the innkeeper only after being told; seed that for Alex/Elara/Tomas
    for n in ("Alex", "Elara", "Tomas"):
        await k.learn_identity(h, w.actors[n], w.entities["Mira"], "Mira")
    await k.learn_identity(h, w.actors["Mira"], w.entities["Renn"], "Captain Renn")
    await k.learn_identity(h, w.actors["Renn"], w.entities["Mira"], "Mira Holt")

    # goals (frostbridge §8, §9, §11, §12) and autonomy (world-memory §4)
    psy = PsychologyService(session)
    await psy.create_goal(h, w.actors["Elara"], "find my brother Joren", priority=90)
    await psy.create_goal(
        h, w.actors["Elara"], "protect vulnerable frontier residents where practical", priority=50
    )
    await psy.create_goal(
        h,
        w.actors["Tomas"],
        "prove public institutions can still serve people honestly",
        priority=80,
    )
    await psy.create_goal(
        h,
        w.actors["Mira"],
        "avoid open conflict with Captain Renn",
        priority=70,
        target_entity_ids=[w.entities["Renn"]],
    )
    await psy.set_ai_profile(w.actors["Elara"], autonomy={"item_transfer": "ask"})
    await psy.set_ai_profile(w.actors["Tomas"], autonomy={"item_transfer": "autonomous"})

    # relationships (frostbridge §10): Elara -> Alex trust 60 familiarity 50
    await k.seed_relationship(h, w.actors["Elara"], w.actors["Alex"], trust=60, familiarity=50)
    await k.seed_relationship(h, w.actors["Tomas"], w.actors["Alex"], trust=55, familiarity=50)
    await k.seed_relationship(h, w.actors["Mira"], w.actors["Renn"], trust=-35, fear=48)

    # objective truth: who knows what (leakage matrix §42)
    oric = await world.create_actor(
        h,
        "Oric Dane",
        actor_type="npc",
        controller_type="dormant",
        location_id=None,
        importance_tier="important",
    )
    w.actors["Oric"], w.entities["Oric"] = oric.id, oric.entity_id
    await psy.create_goal(
        h,
        w.actors["Renn"],
        "prevent discovery of Oric's fate",
        priority=95,
        target_entity_ids=[w.entities["Oric"]],
    )
    w.facts["renn_killed_oric"] = (
        await k.create_fact(
            h,
            key="renn_killed_oric",
            predicate="killed",
            subject_entity_id=w.entities["Renn"],
            object_entity_id=w.entities["Oric"],
            canon_status="established",
            sensitivity="secret",
            known_by=[w.actors["Renn"]],
        )
    ).id
    w.facts["renn_met_oric"] = (
        await k.create_fact(
            h,
            key="renn_met_oric",
            predicate="met privately the night before the disappearance",
            subject_entity_id=w.entities["Renn"],
            object_entity_id=w.entities["Oric"],
            canon_status="established",
            sensitivity="private",
            known_by=[w.actors["Renn"], w.actors["Mira"]],
        )
    ).id
    w.facts["oric_missing"] = (
        await k.create_fact(
            h,
            key="oric_missing",
            predicate="is missing",
            subject_entity_id=w.entities["Oric"],
            canon_status="established",
            sensitivity="public",
            known_by=[w.actors["Mira"], w.actors["Renn"]],
        )
    ).id
    await k.seed_belief(
        h,
        w.actors["Tomas"],
        Proposition("most guards are ordinary people trying to keep order"),
        "believed",
        0.78,
    )
    await k.seed_belief(
        h, w.actors["Elara"], Proposition("authority deserves scrutiny"), "believed", 0.70
    )

    # secret identity: one entity, two names
    veyra = await world.create_actor(
        h,
        "Lady Veyra",
        actor_type="npc",
        controller_type="dormant",
        location_id=None,
        importance_tier="important",
        metadata={"descriptor": "a masked woman"},
    )
    w.veyra_entity = veyra.entity_id
    w.actors["Veyra"] = veyra.id
    await k.learn_identity(h, w.actors["Alex"], veyra.entity_id, "the Masked Woman")
    await k.learn_identity(h, w.actors["Elara"], veyra.entity_id, "Lady Veyra")

    # hidden-property item possessed by Alex
    w.dagger = (
        await world.create_item(
            h,
            "Veyra's Chipped Dagger",
            template_key="item.dagger",
            possessor_actor_id=w.actors["Alex"],
            public_properties={"description": "well-made, chipped near the tip"},
            hidden_properties={
                "bonus_damage_vs_tags": {"spirit": 2},
                "lore": "forged from relay salvage",
            },
        )
    ).id

    space = dict(
        TAVERN_SPACE,
        positions={str(w.actors[n]): {"zone": "tables"} for n in ("Alex", "Elara", "Tomas")}
        | {str(w.actors["Mira"]): {"zone": "bar"}, str(w.actors["Renn"]): {"zone": "door"}},
    )
    scene = await world.start_scene(
        h,
        location_id=w.tavern,
        scene_type="social",
        participant_actor_ids=[w.actors[n] for n in ("Alex", "Elara", "Tomas", "Mira", "Renn")],
        space=space,
    )
    w.scene = scene.id
    return w
