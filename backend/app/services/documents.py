"""DocumentService — reading immutable Documents (world-memory §15; communication-and-knowledge
§3 "Documents"; belief-update-rules §3 "Read in a Document").

A Document's text and `conveys[]` are fixed at creation and never re-extracted. Reading is an
Observation of the reader (`read_document`) whose Claims come from the stored list: when the
author is an actor the Claims are theirs (speaker = author); otherwise only Beliefs are stored
(`believed 0.85 × document_trust`). Document clues are discovered at `route = document`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import events as ev
from app.engine import beliefs as rules
from app.engine.beliefs import Proposition
from app.persistence.models import (
    Actor,
    Claim,
    Document,
    Entity,
    Event,
    Fact,
    Item,
    Observation,
    Scene,
)
from app.persistence.repositories.perspective import PerspectiveRepository
from app.services.events import EventTransaction
from app.services.knowledge import KnowledgeService
from app.services.mystery import MysteryService
from app.services.world import CampaignHandle, WorldError


@dataclass
class ReadResult:
    event: Event
    text: str
    content_hash: str
    observation: Observation
    claims: list[Claim] = field(default_factory=list)
    discoveries: list[uuid.UUID] = field(default_factory=list)


class DocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.knowledge = KnowledgeService(session)
        self.perspective = PerspectiveRepository(session)
        self.mystery = MysteryService(session)

    async def document(self, item_id: uuid.UUID) -> Document:
        d = await self.session.get(Document, item_id)
        if d is None:
            raise WorldError(f"item {item_id} is not a document")
        return d

    async def text(self, item_id: uuid.UUID) -> str:
        """The original text, byte for byte (frostbridge §35)."""
        return (await self.document(item_id)).original_text

    async def can_read(self, actor: Actor, item: Item, scene: Scene | None) -> bool:
        if item.destroyed_event_id is not None or item.concealed:
            return False
        if item.possessor_entity_id == actor.entity_id:
            return True
        return (
            scene is not None
            and scene.location_id is not None
            and item.location_id == scene.location_id
            and item.possessor_entity_id is None
        )

    async def read(
        self,
        h: CampaignHandle,
        actor_id: uuid.UUID,
        item_id: uuid.UUID,
        *,
        turn_id: uuid.UUID | None = None,
    ) -> ReadResult:
        actor = await self.session.get(Actor, actor_id)
        item = await self.session.get(Item, item_id)
        if actor is None or item is None:
            raise WorldError("actor or item not found")
        doc = await self.document(item_id)
        scene = await self.perspective.current_scene(actor_id)
        if not await self.can_read(actor, item, scene):
            raise WorldError("the document is not within reach")
        profile = actor.mechanical_profile or {}
        languages = set(profile.get("languages", [])) or {"common"}
        if doc.language not in languages and f"lang:{doc.language}" not in set(
            profile.get("capabilities", [])
        ):
            raise WorldError(f"{actor_id} cannot read {doc.language}")
        entity = await self.session.get(Entity, item.entity_id)
        author_actor = (
            (
                await self.session.execute(
                    select(Actor).where(Actor.entity_id == doc.author_entity_id)
                )
            ).scalar_one_or_none()
            if doc.author_entity_id
            else None
        )
        controller = await self.perspective.controller_type(actor_id)
        async with EventTransaction(
            self.session,
            h.campaign_id,
            h.timeline_id,
            created_by_type="human" if controller == "human" else "ai",
            created_by_id=actor_id,
        ) as tx:
            event = await tx.emit(
                ev.DocumentRead(actor_id=actor_id, item_id=item.id, claim_count=len(doc.conveys)),
                scene=scene,
                location_id=scene.location_id if scene else None,
                entities=[(item.entity_id, "subject"), (actor.entity_id, "reader")],
            )
            obs = Observation(
                campaign_id=h.campaign_id,
                actor_id=actor_id,
                source_event_id=event.id,
                channel="vision",
                observation_type="read_document",
                raw={
                    "event_type": "document.read",
                    "item_id": str(item.id),
                    "name": entity.canonical_name if entity else "a document",
                    "text": doc.original_text,
                },
                confidence=1.0,
                game_tick=event.game_tick,
                scene_id=scene.id if scene else None,
            )
            self.session.add(obs)
            await self.session.flush()
            claims: list[Claim] = []
            fact_ids: list[tuple[uuid.UUID, str]] = []
            trust = 1.0 if doc.author_entity_id else 0.7  # unsigned documents (belief §3)
            for raw in list(doc.conveys or []):
                item_ = dict(raw)
                if item_.get("kind") == "identity":
                    # the document names an entity: the reader learns that name
                    eid = await self._entity_or_none(item_.get("entity_id"))
                    if eid is not None and item_.get("name"):
                        await self.knowledge.learn_identity(
                            h, actor_id, eid, str(item_["name"]), tx=tx, cause=event
                        )
                    continue
                stance = item_.get("stance", "asserts_true")
                fidelity = item_.get("fidelity", "full")
                fact: Fact | None = None
                if item_.get("kind") == "fact_ref" and item_.get("ref_id"):
                    fact = await self.session.get(Fact, uuid.UUID(str(item_["ref_id"])))
                    if fact is None:
                        continue
                    prop = KnowledgeService.proposition_of(fact)
                else:
                    pdict = item_.get("proposition") or {}
                    if not pdict.get("predicate"):
                        continue
                    prop = Proposition.from_dict(pdict)
                claim: Claim | None = None
                if author_actor is not None:
                    claim = Claim(
                        campaign_id=h.campaign_id,
                        speaker_actor_id=author_actor.id,
                        statement_event_id=event.id,
                        subject_entity_id=await self._entity_or_none(prop.subject),
                        predicate=prop.predicate,
                        object_entity_id=await self._entity_or_none(prop.object),
                        object_value={"value": prop.value} if prop.value is not None else None,
                        speaker_stance=stance,
                        fidelity=fidelity,
                        deliberate_false=bool(item_.get("deliberate_false", False)),
                        about_speaker_self=bool(item_.get("about_speaker_self", False)),
                        source_fact_id=fact.id if fact else None,
                        conveyance_source="document",
                    )
                    self.session.add(claim)
                    await self.session.flush()
                    claims.append(claim)
                if stance == "question":
                    continue
                stance_prop = prop if stance != "asserts_false" else prop.negated()
                proposal = rules.from_document(stance_prop, trust)
                await self.knowledge.store_belief(
                    tx,
                    actor_id,
                    proposal,
                    fact_id=fact.id
                    if (fact and fidelity == "full" and stance == "asserts_true")
                    else None,
                    claim_id=claim.id if claim else None,
                    acquired_event=event,
                    source_actor_id=author_actor.id if author_actor else None,
                )
                if fact is not None:
                    fact_ids.append((fact.id, fidelity))
            discoveries = []
            for c in await self.mystery.clues_for_entity(item.entity_id):
                d = await self.mystery.discover(
                    tx, c, actor_id, route="document", cause=event, store_belief=False
                )
                if d is not None:
                    discoveries.append(d.id)
            for fid, fidelity in fact_ids:
                for c in await self.mystery.clues_for_fact(fid):
                    if c.physical_entity_id == item.entity_id:
                        continue
                    d = await self.mystery.discover(
                        tx,
                        c,
                        actor_id,
                        route="document",
                        cause=event,
                        fidelity=fidelity,
                        store_belief=False,
                    )
                    if d is not None:
                        discoveries.append(d.id)
        return ReadResult(event, doc.original_text, doc.content_hash, obs, claims, discoveries)

    async def _entity_or_none(self, v: str | None) -> uuid.UUID | None:
        if not v:
            return None
        try:
            eid = uuid.UUID(str(v))
        except ValueError:
            return None
        return eid if await self.session.get(Entity, eid) is not None else None
