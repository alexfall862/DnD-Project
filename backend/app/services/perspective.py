"""PerspectiveService — what one actor is entitled to see (Invariant 3; world-memory §6, §9;
human-visibility §2; api-contracts §26).

This module imports only `PerspectiveRepository`. It never touches facts, claims' private
fields, hidden item properties, other actors' beliefs, or offscreen scenes. Every method takes
the actor whose perspective is being built and returns nothing that actor could not know.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.repositories.perspective import HeardClaim, KnownItem, PerspectiveRepository
from app.services.observations import ObservationService

VISIBLE_CONDITIONS = {
    "condition.incapacitated",
    "condition.surrendered",
    "condition.in_cover",
    "condition.fleeing",
    "condition.prone",
    "condition.restrained",
    "condition.burning",
}


class UnauthorizedPerspective(PermissionError):
    pass


@dataclass
class VisibleParticipant:
    entity_id: uuid.UUID
    known_as: str
    is_self: bool
    visible_conditions: list[str] = field(default_factory=list)
    zone: str | None = None


@dataclass
class SceneView:
    scene_id: uuid.UUID
    scene_type: str
    location_known_as: str | None
    world_tick: int
    participants: list[VisibleParticipant]
    space_zone: str | None = None


@dataclass
class BeliefView:
    belief_id: uuid.UUID
    proposition: dict[str, Any]
    belief_type: str
    confidence: float
    status: str
    source_type: str
    source_known_as: str | None = None
    fact_id: uuid.UUID | None = (
        None  # the actor's own link to a fact they hold; the id reveals nothing
    )


class PerspectiveService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = PerspectiveRepository(session)

    # -- authorization --------------------------------------------------------------------------

    async def require_focus_actor(self, actor_id: uuid.UUID) -> None:
        """Normal endpoints render one human-controlled actor's perspective and nothing else
        (human-visibility §2, api-contracts §9b). Knowing an AI actor's id grants nothing."""
        if await self.repo.controller_type(actor_id) != "human":
            raise UnauthorizedPerspective("normal endpoints serve human-controlled actors only")

    # -- views -----------------------------------------------------------------------------------

    async def known_entities(self, actor_id: uuid.UUID) -> dict[uuid.UUID, str]:
        return {
            eid: row.known_name
            for eid, row in (await self.repo.identity_knowledge(actor_id)).items()
        }

    async def scene_view(self, actor_id: uuid.UUID) -> SceneView | None:
        actor = await self.repo.actor(actor_id)
        scene = await self.repo.current_scene(actor_id)
        if actor is None or scene is None:
            return None
        names = await self.known_entities(actor_id)
        rows = await self.repo.scene_participants(scene.id)
        conds = await self.repo.active_conditions([e.id for _, e in rows])
        space = scene.state.get("space") or {}
        positions = space.get("positions", {})
        detected = set(scene.state.get("detected", {}).get(str(actor_id), []))
        participants: list[VisibleParticipant] = []
        for a, e in rows:
            is_self = a.id == actor_id
            c = conds.get(e.id, set())
            if "condition.hidden" in c and not is_self and str(a.id) not in detected:
                continue  # undetected hidden actors do not exist for this observer
            participants.append(
                VisibleParticipant(
                    entity_id=e.id,
                    known_as="you"
                    if is_self
                    else names.get(e.id) or (e.metadata_ or {}).get("descriptor") or "a stranger",
                    is_self=is_self,
                    visible_conditions=sorted(k for k in c if k in VISIBLE_CONDITIONS),
                    zone=(positions.get(str(a.id)) or {}).get("zone"),
                )
            )
        location_name = None
        if scene.location_id is not None:
            loc_entity_id = await self._location_entity(scene.location_id)
            location_name = names.get(loc_entity_id) if loc_entity_id else None
        clock_tick = scene.local_tick
        return SceneView(
            scene.id,
            scene.scene_type,
            location_name,
            clock_tick,
            participants,
            (positions.get(str(actor_id)) or {}).get("zone"),
        )

    async def _location_entity(self, location_id: uuid.UUID) -> uuid.UUID | None:
        from app.persistence.models import Location  # read-only lookup of a public structural row

        loc = await self.repo.s.get(Location, location_id)
        return loc.entity_id if loc else None

    async def inventory(self, actor_id: uuid.UUID) -> list[KnownItem]:
        actor = await self.repo.actor(actor_id)
        if actor is None:
            return []
        return await self.repo.possessed_items(actor.entity_id)

    async def beliefs(self, actor_id: uuid.UUID) -> list[BeliefView]:
        names = await self.known_entities(actor_id)
        out = []
        for b in await self.repo.beliefs(actor_id):
            src = None
            if b.source_actor_id:
                src_actor = await self.repo.actor(b.source_actor_id)
                src = names.get(src_actor.entity_id) if src_actor else None
            out.append(
                BeliefView(
                    b.id,
                    dict(b.proposition),
                    b.belief_type,
                    float(b.confidence),
                    b.status,
                    b.source_type,
                    src,
                    b.fact_id,
                )
            )
        return out

    async def heard_claims(self, actor_id: uuid.UUID, *, limit: int = 50) -> list[HeardClaim]:
        return await self.repo.heard_claims(actor_id, limit=limit)

    async def recent_observations(
        self, actor_id: uuid.UUID, *, limit: int = 30
    ) -> list[dict[str, Any]]:
        rows = await self.repo.observations(actor_id, limit=limit)
        names = await self.known_entities(actor_id)
        return [
            {
                "tick": o.game_tick,
                "type": o.observation_type,
                "raw": o.raw,
                "rendered": self.render(o.observation_type, o.raw, names),
            }
            for o in rows
        ]

    @staticmethod
    def render(kind: str, raw: dict[str, Any], names: dict[uuid.UUID, str] | None = None) -> str:
        if kind == "event":
            return ObservationService.render(raw)
        if kind == "heard_claim":
            p = {**raw.get("proposition", {})}
            for key in ("subject_entity_id", "object_entity_id"):
                v = p.get(key)
                if v:
                    try:
                        p[key] = (names or {}).get(uuid.UUID(str(v)), "someone")
                    except ValueError:
                        pass  # free-text subject
            stance = raw.get("stance")
            verb = {
                "question": "asks whether",
                "uncertain": "suggests",
                "asserts_false": "denies that",
                "hypothetical": "wonders if",
            }.get(stance, "says")
            subj = p.get("subject_entity_id") or ""
            obj = p.get("object_entity_id") or ""
            val = p.get("value") or ""
            who = raw.get("speaker", "someone").capitalize()
            return (
                f"{who} {verb} {subj} {p.get('predicate')} {obj} {val}".replace("  ", " ").strip()
                + "."
            )
        if kind == "speech_in_unknown_language":
            who = raw.get("speaker", "someone").capitalize()
            return f"{who} says something in a language you do not understand."
        if kind == "spoke":
            return f"You {'whisper' if raw.get('channel') == 'whisper' else 'say'} something."
        if kind == "read_document":
            return f'You read {raw.get("name") or "a document"}: "{raw.get("text", "")}"'
        if kind == "arrived":
            who = raw.get("who", "someone")
            verb = "arrive" if who == "you" else "arrives"
            return f"{who.capitalize()} {verb} at {raw.get('location') or 'a place'}."
        return kind

    async def entity_view(self, actor_id: uuid.UUID, entity_id: uuid.UUID) -> dict[str, Any] | None:
        """What this actor knows about an entity: a name, if any, and their own beliefs that
        mention it. An id alone yields nothing (leakage §16)."""
        names = await self.known_entities(actor_id)
        eid = str(entity_id)
        beliefs = [
            b
            for b in await self.beliefs(actor_id)
            if eid
            in (b.proposition.get("subject_entity_id"), b.proposition.get("object_entity_id"))
        ]
        if entity_id not in names and not beliefs:
            return None
        return {"entity_id": entity_id, "known_as": names.get(entity_id), "beliefs": beliefs}

    async def context_candidates(self, actor_id: uuid.UUID) -> dict[str, Any]:
        """Everything the Context Compiler (Milestone 05) may draw on for this actor. By
        construction nothing here came from an objective table except through the actor's own
        beliefs/observations/identity knowledge."""
        actor = await self.repo.actor(actor_id)
        if actor is None:
            return {}
        scene = await self.scene_view(actor_id)
        return {
            "actor_id": str(actor_id),
            "scene": scene,
            "beliefs": await self.beliefs(actor_id),
            "heard_claims": await self.heard_claims(actor_id),
            "observations": await self.recent_observations(actor_id),
            "known_entities": {str(k): v for k, v in (await self.known_entities(actor_id)).items()},
            "inventory": await self.inventory(actor_id),
            "resources": [
                {"key": r.resource_key, "current": r.current, "max": r.max_value}
                for r in await self.repo.own_resources(actor.entity_id)
            ],
            "relationships": [
                {
                    "target_entity_id": str(r.target_entity_id),
                    "trust": r.trust,
                    "familiarity": r.familiarity,
                }
                for r in await self.repo.relationships_from(actor_id)
            ],
        }
