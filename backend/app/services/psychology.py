"""PsychologyService — goals, emotions, autonomy profiles and event-linked relationship
changes (world-memory §4, §11, §12; database-schema §10, §12).

Everything here is a projection changed through an Event in the same transaction
(Invariant: no silent mutation). Relationship changes always write a `relationship_deltas`
row pointing at the causing event.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import events as ev
from app.engine.autonomy import DOMAINS, AutonomyProfile
from app.persistence.models import (
    Actor,
    ActorAIProfile,
    EmotionState,
    Event,
    Goal,
    GoalTarget,
    Plan,
    Relationship,
    RelationshipDelta,
)
from app.persistence.repositories.perspective import PerspectiveRepository
from app.services.events import EventTransaction
from app.services.knowledge import RELATIONSHIP_DIMENSIONS
from app.services.world import CampaignHandle, WorldError

MAX_PROPOSED_DELTA = 10  # per proposal, per dimension (ai-contracts: bounded proposals)
MAX_EMOTION_PROPOSALS = 1


@dataclass(frozen=True)
class GoalView:
    goal_id: uuid.UUID
    description: str
    priority: int
    status: str
    targets: frozenset[uuid.UUID]


class PsychologyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PerspectiveRepository(session)

    def _tx(self, h: CampaignHandle, **kw: Any) -> EventTransaction:
        return EventTransaction(self.session, h.campaign_id, h.timeline_id, **kw)

    # -- autonomy ----------------------------------------------------------------------------

    async def autonomy(self, actor_id: uuid.UUID) -> AutonomyProfile:
        """The `ask` defaults protect the human's party from their AI companions' big
        decisions (world-memory §4). An NPC without an explicit profile has no one to ask and
        is autonomous in every domain: a thief may surrender, a captain may walk out."""
        row = await self.repo.ai_profile(actor_id)
        if row is not None:
            return AutonomyProfile.from_dict(row.autonomy_profile)
        actor = await self.repo.actor(actor_id)
        if actor is not None and actor.actor_type != "pc":
            return AutonomyProfile({d: "autonomous" for d in DOMAINS})
        return AutonomyProfile.from_dict(None)

    async def set_ai_profile(
        self,
        actor_id: uuid.UUID,
        *,
        autonomy: dict[str, str] | None = None,
        decision_preferences: dict[str, Any] | None = None,
        tactical_preferences: dict[str, Any] | None = None,
        preferred_model_profile: str | None = None,
    ) -> ActorAIProfile:
        """Configuration, not world state: no event (it is not something an actor did)."""
        row = await self.repo.ai_profile(actor_id)
        if row is None:
            row = ActorAIProfile(actor_id=actor_id)
            self.session.add(row)
        if autonomy is not None:
            row.autonomy_profile = dict(autonomy)
        if decision_preferences is not None:
            row.decision_preferences = dict(decision_preferences)
        if tactical_preferences is not None:
            row.tactical_preferences = dict(tactical_preferences)
        if preferred_model_profile is not None:
            row.preferred_model_profile = preferred_model_profile
        await self.session.flush()
        return row

    # -- goals ---------------------------------------------------------------------------------

    async def goals(self, actor_id: uuid.UUID) -> list[GoalView]:
        rows = await self.repo.goals(actor_id)
        if not rows:
            return []
        targets = (
            await self.session.execute(
                select(GoalTarget.goal_id, GoalTarget.entity_id).where(
                    GoalTarget.goal_id.in_([g.id for g in rows])
                )
            )
        ).all()
        by_goal: dict[uuid.UUID, set[uuid.UUID]] = {}
        for gid, eid in targets:
            by_goal.setdefault(gid, set()).add(eid)
        return [
            GoalView(g.id, g.description, g.priority, g.status, frozenset(by_goal.get(g.id, ())))
            for g in rows
        ]

    async def goal_relevant(self, actor_id: uuid.UUID, entity_ids: set[uuid.UUID]) -> bool:
        if not entity_ids:
            return False
        return bool(entity_ids & await self.repo.goal_target_entities(actor_id))

    async def create_goal(
        self,
        h: CampaignHandle,
        owner_id: uuid.UUID,
        description: str,
        *,
        owner_type: str = "actor",
        priority: int = 50,
        goal_type: str = "personal",
        visibility: str = "private",
        target_entity_ids: list[uuid.UUID] | None = None,
        created_by_type: str = "engine",
        tx: EventTransaction | None = None,
    ) -> Goal:
        async with tx or self._tx(h, created_by_type=created_by_type, created_by_id=owner_id) as t:
            goal = Goal(
                campaign_id=h.campaign_id,
                owner_type=owner_type,
                owner_id=owner_id,
                description=description,
                goal_type=goal_type,
                priority=priority,
                visibility=visibility,
            )
            self.session.add(goal)
            await self.session.flush()
            for eid in target_entity_ids or []:
                self.session.add(GoalTarget(goal_id=goal.id, entity_id=eid))
            event = await t.emit(
                ev.GoalCreated(
                    goal_id=goal.id,
                    owner_type=owner_type,
                    owner_id=owner_id,
                    description=description,
                    priority=priority,
                    visibility=visibility,
                ),
                entities=[(eid, "target") for eid in (target_entity_ids or [])],
            )
            goal.created_event_id = event.id
        return goal

    async def create_plan(
        self,
        h: CampaignHandle,
        goal_id: uuid.UUID,
        steps: list[str],
        *,
        current_step: int = 0,
    ) -> Plan:
        """A plan is an ordered list of steps toward a goal (world-memory §4 faction plans).
        Steps advance only through events (`plan.advanced`), scheduled or simulated."""
        if not steps:
            raise WorldError("a plan needs steps")
        async with self._tx(h) as tx:
            goal = await self.session.get(Goal, goal_id)
            if goal is None:
                raise WorldError("goal not found")
            plan = Plan(goal_id=goal.id, steps=list(steps), current_step=current_step)
            self.session.add(plan)
            await self.session.flush()
            event = await tx.emit(
                ev.PlanCreated(plan_id=plan.id, goal_id=goal.id, steps=len(steps))
            )
            plan.created_event_id = event.id
        return plan

    async def update_goal(
        self,
        tx: EventTransaction,
        goal_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        status: str | None = None,
        priority: int | None = None,
        description: str | None = None,
        reason: str = "",
    ) -> Goal:
        goal = await self.session.get(Goal, goal_id)
        if goal is None or goal.owner_id != owner_id:
            raise WorldError("goal not found for this owner")
        changes: dict[str, Any] = {}
        if status is not None and status != goal.status:
            changes["status"] = status
            goal.status = status
        if priority is not None and priority != goal.priority:
            changes["priority"] = priority
            goal.priority = priority
        if description is not None and description != goal.description:
            changes["description"] = description
            goal.description = description
        if changes:
            event = await tx.emit(
                ev.GoalUpdated(goal_id=goal.id, owner_id=owner_id, changes=changes, reason=reason)
            )
            if status in ("succeeded", "failed", "abandoned", "superseded"):
                goal.resolved_event_id = event.id
        return goal

    # -- emotions ------------------------------------------------------------------------------

    async def emotions(self, actor_id: uuid.UUID) -> list[EmotionState]:
        return await self.repo.emotions(actor_id)

    async def strongest_emotion(self, actor_id: uuid.UUID) -> float:
        rows = await self.repo.emotions(actor_id)
        return max((float(r.intensity) for r in rows), default=0.0)

    async def set_emotion(
        self,
        tx: EventTransaction,
        actor_id: uuid.UUID,
        emotion_key: str,
        intensity: float,
        *,
        source: str = "proposal",
        source_event: Event | None = None,
        duration_ticks: int | None = 3600,
    ) -> EmotionState:
        """Replace the active state for this emotion key (resolution event = this change)."""
        intensity = max(0.0, min(1.0, float(intensity)))
        event = await tx.emit(
            ev.EmotionChanged(
                actor_id=actor_id, emotion_key=emotion_key, intensity=intensity, source=source
            )
        )
        for old in await self.repo.emotions(actor_id):
            if old.emotion_key == emotion_key:
                old.status = "resolved"
                old.resolution_event_id = event.id
        tick = tx.clock.current_tick
        row = EmotionState(
            campaign_id=tx.campaign_id,
            actor_id=actor_id,
            emotion_key=emotion_key,
            intensity=intensity,
            source_event_id=(source_event or event).id,
            start_tick=tick,
            expiry_tick=tick + duration_ticks if duration_ticks else None,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    # -- relationships -------------------------------------------------------------------------

    async def apply_relationship_delta(
        self,
        tx: EventTransaction,
        source_actor_id: uuid.UUID,
        target_entity_id: uuid.UUID,
        dimension: str,
        delta: int,
        *,
        reason: str = "",
        cause: Event | None = None,
    ) -> Relationship:
        """Change one dimension by a bounded delta with event-linked provenance: a
        relationship.changed event (caused by `cause` when given, e.g. the speech that
        offended) and a relationship_deltas row pointing at it."""
        if dimension not in RELATIONSHIP_DIMENSIONS:
            raise WorldError(f"unknown relationship dimension {dimension!r}")
        delta = max(-MAX_PROPOSED_DELTA, min(MAX_PROPOSED_DELTA, int(delta)))
        if delta == 0:
            raise WorldError("relationship delta must be non-zero")
        rel = await self.repo.relationship(source_actor_id, target_entity_id)
        if rel is None:
            rel = Relationship(
                campaign_id=tx.campaign_id,
                source_actor_id=source_actor_id,
                target_entity_id=target_entity_id,
            )
            self.session.add(rel)
            await self.session.flush()
        event = await tx.emit(
            ev.RelationshipChanged(
                source_actor_id=source_actor_id,
                target_entity_id=target_entity_id,
                dimension=dimension,
                delta=delta,
                reason=reason,
            ),
            cause=cause,
            entities=[(target_entity_id, "target")],
        )
        before = getattr(rel, dimension)
        lo, hi = (0, 100) if dimension == "familiarity" else (-100, 100)
        after = max(lo, min(hi, before + delta))
        setattr(rel, dimension, after)
        self.session.add(
            RelationshipDelta(
                relationship_id=rel.id,
                event_id=event.id,
                dimension=dimension,
                delta=after - before,
                reason=reason,
            )
        )
        rel.last_changed_event_id = event.id
        return rel

    async def has_relationship(self, source_actor_id: uuid.UUID, other_actor_id: uuid.UUID) -> bool:
        other = await self.session.get(Actor, other_actor_id)
        if other is None:
            return False
        return await self.repo.relationship(source_actor_id, other.entity_id) is not None
