"""KnowledgeService — objective knowledge writes: facts, identity knowledge, relationships,
and the single belief-storage path that applies the deterministic rules.

Facts never become anyone's knowledge by being created: `known_by` seeds explicit beliefs for
the actors who objectively know them (a murderer knows what he did).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import events as ev
from app.engine import beliefs as rules
from app.engine.beliefs import BeliefProposal, ExistingBelief, Proposition, RelationshipView
from app.persistence.models import (
    Actor,
    Belief,
    Entity,
    EntityIdentityKnowledge,
    Event,
    Fact,
    Relationship,
    RelationshipDelta,
)
from app.persistence.repositories.perspective import PerspectiveRepository
from app.services.events import EventTransaction
from app.services.world import CampaignHandle, WorldError

RELATIONSHIP_DIMENSIONS = (
    "trust",
    "affection",
    "respect",
    "fear",
    "resentment",
    "obligation",
    "familiarity",
)


class KnowledgeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.perspective_repo = PerspectiveRepository(session)

    def _tx(self, h: CampaignHandle, **kw: Any) -> EventTransaction:
        return EventTransaction(self.session, h.campaign_id, h.timeline_id, **kw)

    # -- facts ---------------------------------------------------------------------------------

    async def create_fact(
        self,
        h: CampaignHandle,
        *,
        key: str | None,
        predicate: str,
        subject_entity_id: uuid.UUID | None = None,
        object_entity_id: uuid.UUID | None = None,
        value: Any = None,
        canon_status: str = "latent",
        truth_status: str = "true",
        sensitivity: str = "public",
        known_by: list[uuid.UUID] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> Fact:
        async with self._tx(h) as tx:
            fact = Fact(
                campaign_id=h.campaign_id,
                key=key,
                predicate=predicate,
                subject_entity_id=subject_entity_id,
                object_entity_id=object_entity_id,
                object_value={"value": value} if value is not None else None,
                canon_status=canon_status,
                truth_status=truth_status,
                sensitivity=sensitivity,
                provenance=provenance or {},
            )
            self.session.add(fact)
            await self.session.flush()
            event = await tx.emit(
                ev.FactCreated(
                    fact_id=fact.id, key=key, canon_status=canon_status, sensitivity=sensitivity
                ),
                entities=[(subject_entity_id, "subject")] if subject_entity_id else [],
            )
            fact.created_event_id = event.id
            if canon_status == "established":
                fact.established_event_id = event.id
            for actor_id in known_by or []:
                await self.store_belief(
                    tx,
                    actor_id,
                    BeliefProposal(
                        self.proposition_of(fact),
                        "known",
                        1.0,
                        "seeded",
                        ("objective knowledge holder",),
                    ),
                    fact_id=fact.id,
                    acquired_event=event,
                )
        return fact

    async def establish_fact(
        self, h: CampaignHandle, fact_id: uuid.UUID, *, reason: str = ""
    ) -> Fact:
        async with self._tx(h) as tx:
            fact = await self.session.get(Fact, fact_id)
            if fact is None:
                raise WorldError(f"fact {fact_id} not found")
            if fact.canon_status == "established":
                return fact
            event = await tx.emit(ev.FactEstablished(fact_id=fact.id, key=fact.key, reason=reason))
            fact.canon_status = "established"
            fact.established_event_id = event.id
        return fact

    @staticmethod
    def proposition_of(fact: Fact) -> Proposition:
        return Proposition(
            fact.predicate,
            subject=str(fact.subject_entity_id) if fact.subject_entity_id else None,
            object=str(fact.object_entity_id) if fact.object_entity_id else None,
            value=(fact.object_value or {}).get("value"),
        )

    # -- identity --------------------------------------------------------------------------------

    async def learn_identity(
        self,
        h: CampaignHandle,
        actor_id: uuid.UUID,
        entity_id: uuid.UUID,
        known_name: str,
        *,
        recognized_as: uuid.UUID | None = None,
        tx: EventTransaction | None = None,
        cause: Event | None = None,
    ) -> EntityIdentityKnowledge:
        if tx is None:
            async with self._tx(h) as tx2:
                return await self.learn_identity(
                    h,
                    actor_id,
                    entity_id,
                    known_name,
                    recognized_as=recognized_as,
                    tx=tx2,
                    cause=cause,
                )
        existing = await self.perspective_repo.identity_knowledge(actor_id)
        row = existing.get(entity_id)
        if row is not None and row.known_name == known_name:
            return row
        event = await tx.emit(
            ev.IdentityLearned(
                actor_id=actor_id,
                entity_id=entity_id,
                known_name=known_name,
                recognized_as_entity_id=recognized_as,
            ),
            cause=cause,
            entities=[(entity_id, "subject")],
        )
        if row is not None:
            row.status = "superseded"
            await self.session.flush()
        row = EntityIdentityKnowledge(
            campaign_id=h.campaign_id,
            actor_id=actor_id,
            entity_id=entity_id,
            known_name=known_name,
            recognized_as_entity_id=recognized_as,
            learned_event_id=event.id,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def introduce(
        self, h: CampaignHandle, actor_ids: list[uuid.UUID], *, by_canonical_name: bool = True
    ) -> None:
        """Everyone in the list learns everyone else's canonical name (mutual acquaintance)."""
        actors = {a: await self.session.get(Actor, a) for a in actor_ids}
        async with self._tx(h) as tx:
            for me in actor_ids:
                for other in actor_ids:
                    if me == other:
                        continue
                    ent = await self.session.get(Entity, actors[other].entity_id)
                    await self.learn_identity(h, me, ent.id, ent.canonical_name or "someone", tx=tx)

    # -- relationships ---------------------------------------------------------------------------

    async def seed_relationship(
        self,
        h: CampaignHandle,
        source_actor_id: uuid.UUID,
        target_actor_id: uuid.UUID,
        **values: int,
    ) -> Relationship:
        bad = set(values) - set(RELATIONSHIP_DIMENSIONS)
        if bad:
            raise WorldError(f"unknown relationship dimensions {sorted(bad)}")
        target = await self.session.get(Actor, target_actor_id)
        if target is None:
            raise WorldError("target actor not found")
        async with self._tx(h) as tx:
            event = await tx.emit(
                ev.RelationshipSeeded(
                    source_actor_id=source_actor_id,
                    target_entity_id=target.entity_id,
                    values=values,
                ),
                entities=[(target.entity_id, "target")],
            )
            rel = await self.perspective_repo.relationship(source_actor_id, target.entity_id)
            if rel is None:
                rel = Relationship(
                    campaign_id=h.campaign_id,
                    source_actor_id=source_actor_id,
                    target_entity_id=target.entity_id,
                )
                self.session.add(rel)
                await self.session.flush()
            for dim, v in values.items():
                before = getattr(rel, dim)
                setattr(rel, dim, v)
                self.session.add(
                    RelationshipDelta(
                        relationship_id=rel.id,
                        event_id=event.id,
                        dimension=dim,
                        delta=v - before,
                        reason="seed",
                    )
                )
            rel.last_changed_event_id = event.id
        return rel

    async def relationship_view(
        self, source_actor_id: uuid.UUID, target_actor_id: uuid.UUID
    ) -> RelationshipView:
        target = await self.session.get(Actor, target_actor_id)
        rel = (
            await self.perspective_repo.relationship(source_actor_id, target.entity_id)
            if target
            else None
        )
        return (
            RelationshipView(trust=rel.trust, familiarity=rel.familiarity)
            if rel
            else RelationshipView()
        )

    # -- beliefs ---------------------------------------------------------------------------------

    async def seed_belief(
        self,
        h: CampaignHandle,
        actor_id: uuid.UUID,
        proposition: Proposition,
        belief_type: str,
        confidence: float,
        *,
        fact_id: uuid.UUID | None = None,
    ) -> Belief:
        async with self._tx(h) as tx:
            event = await tx.emit(
                ev.BeliefSeeded(
                    actor_id=actor_id,
                    proposition_key=proposition.key,
                    belief_type=belief_type,
                    confidence=confidence,
                    fact_id=fact_id,
                )
            )
            return await self.store_belief(
                tx,
                actor_id,
                BeliefProposal(proposition, belief_type, confidence, "seeded"),
                fact_id=fact_id,
                acquired_event=event,
            )

    async def existing_beliefs(self, actor_id: uuid.UUID) -> list[ExistingBelief]:
        rows = await self.perspective_repo.beliefs(actor_id)
        return [
            ExistingBelief(
                Proposition.from_dict(b.proposition),
                b.belief_type,
                float(b.confidence),
                b.status,
                ref=b,
            )
            for b in rows
        ]

    async def store_belief(
        self,
        tx: EventTransaction,
        actor_id: uuid.UUID,
        proposal: BeliefProposal,
        *,
        fact_id: uuid.UUID | None = None,
        claim_id: uuid.UUID | None = None,
        acquired_event: Event | None = None,
        source_actor_id: uuid.UUID | None = None,
    ) -> Belief | None:
        """Apply §5 reconciliation and persist. Returns the new row, or None when skipped."""
        existing = await self.existing_beliefs(actor_id)
        rec = rules.reconcile(proposal, existing)
        if rec.skip:
            return None
        event_id = (
            acquired_event.id if acquired_event else (tx.events[-1].id if tx.events else None)
        )
        for old in rec.supersede:
            old.ref.status = "superseded"
            old.ref.superseded_event_id = event_id
        status = "contested" if rec.contest_with else "active"
        for other in rec.contest_with:
            other.ref.status = "contested"
        row = Belief(
            campaign_id=tx.campaign_id,
            actor_id=actor_id,
            fact_id=fact_id,
            claim_id=claim_id,
            proposition=proposal.proposition.to_dict(),
            proposition_key=proposal.proposition.key,
            belief_type=proposal.belief_type,
            confidence=round(proposal.confidence, 3),
            source_type=proposal.source_type,
            source_actor_id=source_actor_id,
            acquired_event_id=event_id,
            status=status,
            metadata_={
                "reasons": list(proposal.reasons),
                "weaker_alternative": rec.weaker_alternative,
            },
        )
        self.session.add(row)
        await self.session.flush()
        return row
