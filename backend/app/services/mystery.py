"""MysteryService — objective mysteries, locked truth and clue routes
(docs/architecture/01-world-memory.md §13; database-schema.md §13; communication-and-knowledge
§6; Invariant 10).

Objective side: a `Mystery` with `MysteryTruthFact` rows that lock at activation; `Clue` rows
that are routes to one supported Fact. Subjective side: a `ClueDiscovery` records that one
actor learned a clue (route, fidelity, Claim) and, where the route itself is evidence
(physical find, mechanic, inference), the actor's Belief in the supported Fact
(belief-update-rules §3: engine-revealed proposition → `known 1.0`). Documents and testimony
store their beliefs elsewhere (DocumentService, SpeechService); here only the discovery is
recorded for them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import events as ev
from app.engine import beliefs as rules
from app.persistence.models import (
    Actor,
    Clue,
    ClueDiscovery,
    Entity,
    Event,
    Fact,
    Item,
    ItemHistory,
    Mystery,
    MysteryTruthFact,
)
from app.services.events import EventTransaction
from app.services.knowledge import KnowledgeService
from app.services.world import CampaignHandle, WorldError

ROUTES = {"physical", "document", "testimony", "inference", "mechanic"}
EVIDENCE_ROUTES = {"physical", "inference", "mechanic"}  # the route itself proves the fact


class MysteryLockedError(WorldError):
    """The mystery's answer is locked; changing it needs an explicit retcon (Invariant 10)."""


@dataclass(frozen=True)
class RoutesRemaining:
    mystery_id: uuid.UUID
    intact_by_fact: dict[uuid.UUID, int]
    destroyed: int

    @property
    def solvable(self) -> bool:
        """Every supported fact that has clues at all still has at least one intact route."""
        return all(n > 0 for n in self.intact_by_fact.values())


class MysteryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.knowledge = KnowledgeService(session)

    def _tx(self, h: CampaignHandle, **kw: Any) -> EventTransaction:
        return EventTransaction(self.session, h.campaign_id, h.timeline_id, **kw)

    # -- mysteries -------------------------------------------------------------------------------

    async def create_mystery(
        self,
        h: CampaignHandle,
        *,
        key: str | None,
        question: str,
        truth_fact_ids: list[uuid.UUID],
        activate: bool = True,
        stakeholders: list[str] | None = None,
        consequences: dict[str, Any] | None = None,
    ) -> Mystery:
        """Truth is generated before clues (world-memory §13): the answer facts must already
        exist. Activation locks the solution in the same transaction."""
        if not truth_fact_ids:
            raise WorldError("a mystery needs at least one truth fact")
        for fid in truth_fact_ids:
            fact = await self.session.get(Fact, fid)
            if fact is None or fact.campaign_id != h.campaign_id:
                raise WorldError(f"truth fact {fid} not found in campaign")
        async with self._tx(h) as tx:
            m = Mystery(
                campaign_id=h.campaign_id,
                key=key,
                question=question,
                status="latent",
                solution_locked=False,
                stakeholders=list(stakeholders or []),
                consequences=consequences or {},
            )
            self.session.add(m)
            await self.session.flush()
            for fid in truth_fact_ids:
                self.session.add(MysteryTruthFact(mystery_id=m.id, fact_id=fid))
            event = await tx.emit(
                ev.MysteryCreated(
                    mystery_id=m.id, key=key, question=question, truth_fact_ids=truth_fact_ids
                )
            )
            m.created_event_id = event.id
            if activate:
                act = await tx.emit(
                    ev.MysteryActivated(mystery_id=m.id, solution_locked=True), cause=event
                )
                m.status, m.solution_locked, m.activated_event_id = "active", True, act.id
        return m

    async def activate(self, h: CampaignHandle, mystery_id: uuid.UUID) -> Mystery:
        async with self._tx(h) as tx:
            m = await self._mystery(mystery_id)
            if m.status != "latent":
                return m
            act = await tx.emit(ev.MysteryActivated(mystery_id=m.id, solution_locked=True))
            m.status, m.solution_locked, m.activated_event_id = "active", True, act.id
        return m

    async def replace_truth(
        self, h: CampaignHandle, mystery_id: uuid.UUID, new_fact_ids: list[uuid.UUID]
    ) -> None:
        """Refused while locked. Development corrections use an explicit retcon or a timeline
        branch (Invariant 9/10); nothing in ordinary play may call this on an active mystery."""
        m = await self._mystery(mystery_id)
        if m.solution_locked:
            raise MysteryLockedError(f"mystery {m.key or m.id} is locked; retcon required")
        raise WorldError("replacing a latent mystery's truth is not supported in v0.1")

    async def truth_fact_ids(self, mystery_id: uuid.UUID) -> list[uuid.UUID]:
        return list(
            (
                await self.session.execute(
                    select(MysteryTruthFact.fact_id).where(
                        MysteryTruthFact.mystery_id == mystery_id
                    )
                )
            )
            .scalars()
            .all()
        )

    async def is_locked_truth(self, fact_id: uuid.UUID) -> bool:
        row = (
            await self.session.execute(
                select(Mystery.id)
                .join(MysteryTruthFact, MysteryTruthFact.mystery_id == Mystery.id)
                .where(MysteryTruthFact.fact_id == fact_id, Mystery.solution_locked.is_(True))
            )
        ).first()
        return row is not None

    async def _mystery(self, mystery_id: uuid.UUID) -> Mystery:
        m = await self.session.get(Mystery, mystery_id)
        if m is None:
            raise WorldError(f"mystery {mystery_id} not found")
        return m

    # -- clues -------------------------------------------------------------------------------------

    async def create_clue(
        self,
        h: CampaignHandle,
        mystery_id: uuid.UUID,
        *,
        key: str | None,
        clue_type: str,
        supported_fact_id: uuid.UUID | None,
        physical_entity_id: uuid.UUID | None = None,
        reliability: float = 1.0,
        discovery_conditions: dict[str, Any] | None = None,
        destructible: bool = False,
        forgeable: bool = False,
    ) -> Clue:
        if clue_type not in ("physical", "document", "social"):
            raise WorldError(f"invalid clue_type {clue_type!r}")
        if clue_type in ("physical", "document") and physical_entity_id is None:
            raise WorldError(f"a {clue_type} clue needs a physical entity")
        if supported_fact_id is not None:
            fact = await self.session.get(Fact, supported_fact_id)
            if fact is None or fact.campaign_id != h.campaign_id:
                raise WorldError(f"supported fact {supported_fact_id} not found in campaign")
        if physical_entity_id is not None:
            ent = await self.session.get(Entity, physical_entity_id)
            if ent is None or ent.campaign_id != h.campaign_id:
                raise WorldError(f"physical entity {physical_entity_id} not found in campaign")
        async with self._tx(h) as tx:
            m = await self._mystery(mystery_id)
            c = Clue(
                campaign_id=h.campaign_id,
                mystery_id=m.id,
                key=key,
                clue_type=clue_type,
                supported_fact_id=supported_fact_id,
                physical_entity_id=physical_entity_id,
                reliability=reliability,
                discovery_conditions=discovery_conditions or {},
                destructible=destructible,
                forgeable=forgeable,
            )
            self.session.add(c)
            await self.session.flush()
            event = await tx.emit(
                ev.ClueCreated(
                    clue_id=c.id,
                    mystery_id=m.id,
                    key=key,
                    supported_fact_id=supported_fact_id,
                    physical_entity_id=physical_entity_id,
                    clue_type=clue_type,
                ),
                entities=[(physical_entity_id, "subject")] if physical_entity_id else [],
            )
            c.created_event_id = event.id
        return c

    async def clue(self, clue_id: uuid.UUID) -> Clue:
        c = await self.session.get(Clue, clue_id)
        if c is None:
            raise WorldError(f"clue {clue_id} not found")
        return c

    async def clue_by_key(self, campaign_id: uuid.UUID, key: str) -> Clue | None:
        return (
            await self.session.execute(
                select(Clue).where(Clue.campaign_id == campaign_id, Clue.key == key)
            )
        ).scalar_one_or_none()

    async def clues_for_fact(self, fact_id: uuid.UUID, *, intact_only: bool = True) -> list[Clue]:
        q = select(Clue).where(Clue.supported_fact_id == fact_id)
        if intact_only:
            q = q.where(Clue.state == "intact")
        return list((await self.session.execute(q)).scalars().all())

    async def clues_for_entity(self, entity_id: uuid.UUID) -> list[Clue]:
        return list(
            (
                await self.session.execute(
                    select(Clue).where(Clue.physical_entity_id == entity_id, Clue.state == "intact")
                )
            )
            .scalars()
            .all()
        )

    async def routes_remaining(self, mystery_id: uuid.UUID) -> RoutesRemaining:
        clues = list(
            (await self.session.execute(select(Clue).where(Clue.mystery_id == mystery_id)))
            .scalars()
            .all()
        )
        by_fact: dict[uuid.UUID, int] = {}
        for c in clues:
            if c.supported_fact_id is None:
                continue
            by_fact.setdefault(c.supported_fact_id, 0)
            if c.state == "intact":
                by_fact[c.supported_fact_id] += 1
        return RoutesRemaining(mystery_id, by_fact, sum(1 for c in clues if c.state == "destroyed"))

    # -- discovery (subjective; always inside the discovering transaction) ----------------------

    async def discover(
        self,
        tx: EventTransaction,
        clue: Clue,
        actor_id: uuid.UUID,
        *,
        route: str,
        cause: Event | None,
        fidelity: str = "full",
        claim_id: uuid.UUID | None = None,
        store_belief: bool | None = None,
    ) -> ClueDiscovery | None:
        """Record that `actor_id` learned `clue` by `route`. Idempotent per
        (clue, actor, route, fidelity). For evidence routes the actor also gains `known 1.0`
        in the supported fact (belief-update §3, engine-revealed proposition)."""
        if route not in ROUTES:
            raise WorldError(f"invalid discovery route {route!r}")
        if clue.state != "intact":
            return None
        existing = (
            await self.session.execute(
                select(ClueDiscovery).where(
                    ClueDiscovery.clue_id == clue.id,
                    ClueDiscovery.actor_id == actor_id,
                    ClueDiscovery.route == route,
                    ClueDiscovery.fidelity == fidelity,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        event = await tx.emit(
            ev.ClueDiscovered(
                clue_id=clue.id,
                actor_id=actor_id,
                route=route,
                fidelity=fidelity,
                claim_id=claim_id,
            ),
            cause=cause,
            entities=[(clue.physical_entity_id, "subject")] if clue.physical_entity_id else [],
        )
        row = ClueDiscovery(
            clue_id=clue.id,
            actor_id=actor_id,
            discovery_event_id=event.id,
            route=route,
            claim_id=claim_id,
            fidelity=fidelity,
        )
        self.session.add(row)
        await self.session.flush()
        if store_belief is None:
            store_belief = route in EVIDENCE_ROUTES and fidelity == "full"
        if store_belief and clue.supported_fact_id is not None:
            fact = await self.session.get(Fact, clue.supported_fact_id)
            if fact is not None:
                await self.knowledge.store_belief(
                    tx,
                    actor_id,
                    rules.from_mechanic(KnowledgeService.proposition_of(fact)),
                    fact_id=fact.id,
                    acquired_event=event,
                )
        return row

    async def discover_physical(
        self,
        tx: EventTransaction,
        *,
        entity_id: uuid.UUID,
        observer_actor_ids: list[uuid.UUID],
        cause: Event,
    ) -> list[ClueDiscovery]:
        """A revealed/handled object: physical clues are evidence in themselves; document
        clues are only *found* here (their content is learned by reading)."""
        out = []
        for c in await self.clues_for_entity(entity_id):
            route = "document" if c.clue_type == "document" else "physical"
            for aid in observer_actor_ids:
                d = await self.discover(
                    tx,
                    c,
                    aid,
                    route=route,
                    cause=cause,
                    fidelity="full" if c.clue_type == "physical" else "partial",
                    store_belief=c.clue_type == "physical",
                )
                if d is not None:
                    out.append(d)
        return out

    async def discover_by_testimony(
        self,
        tx: EventTransaction,
        *,
        fact_id: uuid.UUID,
        recipient_actor_id: uuid.UUID,
        claim_id: uuid.UUID,
        fidelity: str,
        cause: Event,
    ) -> list[ClueDiscovery]:
        """c&k §6: a Claim conveying a clue's supported fact reaches a party actor. The
        belief itself was stored by the speech pipeline; only the discovery is recorded."""
        actor = await self.session.get(Actor, recipient_actor_id)
        if actor is None or actor.actor_type != "pc":
            return []
        out = []
        for c in await self.clues_for_fact(fact_id):
            d = await self.discover(
                tx,
                c,
                recipient_actor_id,
                route="testimony",
                cause=cause,
                fidelity=fidelity,
                claim_id=claim_id,
                store_belief=False,
            )
            if d is not None:
                out.append(d)
        return out

    async def discoveries(self, actor_id: uuid.UUID) -> list[ClueDiscovery]:
        return list(
            (
                await self.session.execute(
                    select(ClueDiscovery)
                    .where(ClueDiscovery.actor_id == actor_id)
                    .order_by(ClueDiscovery.created_at)
                )
            )
            .scalars()
            .all()
        )

    # -- destruction -------------------------------------------------------------------------------

    async def destroy_clue(
        self,
        h: CampaignHandle,
        clue_id: uuid.UUID,
        *,
        reason: str = "",
        tx: EventTransaction | None = None,
        cause: Event | None = None,
    ) -> Clue:
        """Destroys the route (and its physical item, if any). Other routes to the same fact
        remain: loss of one clue never changes the locked answer (frostbridge §17, §36)."""
        if tx is None:
            async with self._tx(h) as tx2:
                return await self.destroy_clue(h, clue_id, reason=reason, tx=tx2, cause=cause)
        c = await self.clue(clue_id)
        if c.state == "destroyed":
            return c
        if not c.destructible:
            raise WorldError(f"clue {c.key or c.id} is not destructible")
        event = await tx.emit(
            ev.ClueDestroyed(clue_id=c.id, reason=reason),
            cause=cause,
            entities=[(c.physical_entity_id, "subject")] if c.physical_entity_id else [],
        )
        c.state, c.destroyed_event_id = "destroyed", event.id
        if c.physical_entity_id is not None:
            item = (
                await self.session.execute(
                    select(Item).where(Item.entity_id == c.physical_entity_id)
                )
            ).scalar_one_or_none()
            if item is not None and item.destroyed_event_id is None:
                destroyed = await tx.emit(
                    ev.ItemDestroyed(item_id=item.id, reason=reason or "clue destroyed"),
                    cause=event,
                    entities=[(item.entity_id, "subject")],
                )
                item.destroyed_event_id = destroyed.id
                item.possessor_entity_id, item.location_id, item.zone_key = None, None, None
                self.session.add(
                    ItemHistory(
                        item_id=item.id,
                        event_id=destroyed.id,
                        change_type="destroyed",
                        payload={"reason": reason},
                    )
                )
                ent = await self.session.get(Entity, item.entity_id)
                if ent is not None:
                    ent.lifecycle_state = "destroyed"
        return c
