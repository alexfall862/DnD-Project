"""SituationService: recorded obstacles, statuses, promises, clocks, alarms, prices, debts and
followers (DECISIONS 10d).

Situations are objective state. They are opened, changed and closed only here, each with its
event in the caller's transaction. Reads come in two kinds:

- `visible_to(actor)`: what one actor perceives (public situations where they are, and those
  about them). This is what reaches actor-scoped model calls and the player.
- `at_location(...)`: the objective list, for the Rules Adjudicator (an objective role) and the
  engine's own checks (`blocking`).

No soft-blocks: an obstacle never blocks someone it has passed, and it does not block when its
holder is absent, distracted, or has promised to let them through. Model-made obstacles always
expire (`MAX_OBSTACLE_SECONDS`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import events as ev
from app.persistence.models import Actor, Event, Scene, Situation, WorldClock
from app.services.events import EventTransaction

DEFAULT_OBSTACLE_SECONDS = 3600
MAX_OBSTACLE_SECONDS = 6 * 3600
DEFAULT_WAYS_PAST = ["talk your way through", "find another way around", "wait it out"]
BLOCKED_HINT_AFTER = 3  # blocked attempts before the notice lists the ways past


def sref(s: Situation) -> str:
    """The short ref a model sees for a situation."""
    return "s_" + s.id.hex[:6]


@dataclass
class Blocked:
    situation: Situation
    label: str
    ways_past: list[str]
    attempts: int


class SituationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- time ----------------------------------------------------------------------------------

    async def now(self, timeline_id: uuid.UUID) -> int:
        clock = await self.session.get(WorldClock, timeline_id)
        return int(clock.current_tick) if clock else 0

    @staticmethod
    def _live(now: int):
        return or_(Situation.expires_tick.is_(None), Situation.expires_tick > now)

    # -- reads ---------------------------------------------------------------------------------

    async def at_location(
        self, campaign_id: uuid.UUID, location_id: uuid.UUID | None, now: int
    ) -> list[Situation]:
        """Every live situation held at a place, plus those about anyone in a scene there."""
        if location_id is None:
            return []
        here = (
            select(Scene.id).where(Scene.location_id == location_id, Scene.status == "active")
        ).scalar_subquery()
        people = select(Actor.id).where(Actor.current_scene_id.in_(here))
        rows = (
            (
                await self.session.execute(
                    select(Situation)
                    .where(
                        Situation.campaign_id == campaign_id,
                        Situation.status == "active",
                        self._live(now),
                        or_(
                            Situation.location_id == location_id,
                            Situation.subject_actor_id.in_(people),
                        ),
                    )
                    .order_by(Situation.created_at)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def visible_to(self, actor_id: uuid.UUID) -> list[Situation]:
        """What this actor perceives: public situations where they are, and every situation
        about them or held by them."""
        actor = await self.session.get(Actor, actor_id)
        if actor is None or actor.current_scene_id is None:
            return []
        scene = await self.session.get(Scene, actor.current_scene_id)
        if scene is None:
            return []
        now = await self.now(scene.timeline_id)
        out = []
        for s in await self.at_location(scene.campaign_id, scene.location_id, now):
            if s.visibility == "public" or actor_id in (s.subject_actor_id, s.holder_actor_id):
                out.append(s)
        mine = (
            (
                await self.session.execute(
                    select(Situation).where(
                        Situation.subject_actor_id == actor_id,
                        Situation.status == "active",
                        self._live(now),
                    )
                )
            )
            .scalars()
            .all()
        )
        seen = {s.id for s in out}
        out += [s for s in mine if s.id not in seen]
        return out

    async def lines(
        self, situations: list[Situation], names: dict[uuid.UUID, str], *, refs: bool = True
    ) -> list[str]:
        """Plain lines for a model or the player; `names` maps actor ids to how the reader
        knows them."""
        out = []
        for s in situations:
            who = names.get(s.subject_actor_id) if s.subject_actor_id else None
            holder = names.get(s.holder_actor_id) if s.holder_actor_id else None
            line = s.label
            if s.kind == "status" and who:
                line = f"{who}: {s.label}"
            elif s.kind == "commitment" and who:
                # "You promised Alex, Elara: …" (play session 3 read "you has promised")
                to = []
                for a in s.data.get("for") or []:
                    try:
                        n = names.get(uuid.UUID(str(a)))
                    except ValueError:
                        n = None
                    if n and n != who:
                        to.append(n)
                verb = "refused" if s.data.get("refused") else "promised"
                what = s.label.removeprefix("refused: ")
                subject = "You" if who == "you" else who[:1].upper() + who[1:]
                line = f"{subject} {verb}" + (f" {', '.join(to)}" if to else "") + f": {what}"
            elif s.kind == "follower" and who:
                line = f"{who} is accompanying the party"
            elif s.kind == "clock":
                line = f"{s.label}: {s.data.get('value', 0)}/{s.data.get('of', 4)}"
            elif s.kind == "obstacle":
                line = f"Obstacle: {s.label}" + (f" (held by {holder})" if holder else "")
                passed = [names.get(uuid.UUID(a)) for a in s.data.get("passed", [])]
                if any(passed):
                    line += "; let through: " + ", ".join(p for p in passed if p)
            elif s.kind == "price" and who:
                line = f"{who}'s prices: {s.label}"
            elif s.kind == "debt" and who:
                line = f"{who} owes: {s.label}"
            out.append((f"[{sref(s)}] " if refs else "") + line)
        return out

    async def resolve_ref(self, situations: list[Situation], ref: str | None) -> Situation | None:
        if not ref:
            return None
        r = str(ref).strip().strip("[]")
        for s in situations:
            if r in (sref(s), str(s.id)):
                return s
        low = r.lower()
        hits = [s for s in situations if low and low in s.label.lower()]
        return hits[0] if len(hits) == 1 else None

    async def linked_party(self, actor_id: uuid.UUID) -> list[uuid.UUID]:
        """Who travels with this actor because they are linked (an agreed escort or someone
        accompanying the party, DECISIONS 10e): the party member it is with and that member's
        party, as far as they are in the same scene."""
        actor = await self.session.get(Actor, actor_id)
        if actor is None or actor.current_scene_id is None:
            return []
        scene = await self.session.get(Scene, actor.current_scene_id)
        now = await self.now(scene.timeline_id) if scene else 0
        rows = (
            (
                await self.session.execute(
                    select(Situation).where(
                        Situation.subject_actor_id == actor_id,
                        Situation.kind == "follower",
                        Situation.status == "active",
                        self._live(now),
                    )
                )
            )
            .scalars()
            .all()
        )
        from app.persistence.models import PartyMembership

        out: list[uuid.UUID] = []
        for s in rows:
            try:
                lead = uuid.UUID(str(s.data.get("with")))
            except ValueError:
                continue
            parties = select(PartyMembership.party_id).where(PartyMembership.actor_id == lead)
            members = set(
                (
                    await self.session.execute(
                        select(PartyMembership.actor_id).where(
                            PartyMembership.party_id.in_(parties)
                        )
                    )
                )
                .scalars()
                .all()
            ) | {lead}
            for m in members:
                other = await self.session.get(Actor, m)
                if (
                    other is not None
                    and other.current_scene_id == actor.current_scene_id
                    and m not in out
                    and m != actor_id
                ):
                    out.append(m)
        return out

    async def status_of(self, actor_id: uuid.UUID, label: str) -> Situation | None:
        rows = (
            (
                await self.session.execute(
                    select(Situation).where(
                        Situation.subject_actor_id == actor_id,
                        Situation.kind == "status",
                        Situation.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        for s in rows:
            if s.label.lower() == label.lower():
                return s
        return None

    # -- obstacles -----------------------------------------------------------------------------

    async def _holder_yields(self, s: Situation, actor_id: uuid.UUID, now: int) -> bool:
        """An obstacle's holder who is gone, distracted, or promised passage does not block."""
        if s.holder_actor_id is None:
            return False
        holder = await self.session.get(Actor, s.holder_actor_id)
        if holder is None or holder.current_scene_id is None:
            return True
        scene = await self.session.get(Scene, holder.current_scene_id)
        if scene is None or scene.location_id != s.location_id:
            return True
        rows = (
            (
                await self.session.execute(
                    select(Situation).where(
                        Situation.subject_actor_id == s.holder_actor_id,
                        Situation.status == "active",
                        self._live(now),
                        Situation.kind.in_(("status", "commitment")),
                    )
                )
            )
            .scalars()
            .all()
        )
        for r in rows:
            if r.kind == "status" and r.data.get("distracted"):
                return True
            if r.kind == "commitment" and r.data.get("lets_pass") == str(s.id):
                to = r.data.get("for") or []
                if not to or str(actor_id) in to:
                    return True
        return False

    async def blocking(
        self, actor_id: uuid.UUID, from_location_id: uuid.UUID | None, to_location_id: uuid.UUID
    ) -> Blocked | None:
        """The obstacle that stops this actor going from here to there, if any."""
        if from_location_id is None:
            return None
        actor = await self.session.get(Actor, actor_id)
        scene = await self.session.get(Scene, actor.current_scene_id) if actor else None
        now = await self.now(scene.timeline_id) if scene else 0
        rows = (
            (
                await self.session.execute(
                    select(Situation).where(
                        Situation.location_id == from_location_id,
                        Situation.kind == "obstacle",
                        Situation.status == "active",
                        self._live(now),
                    )
                )
            )
            .scalars()
            .all()
        )
        for s in rows:
            blocks = s.data.get("blocks") or ["*"]
            if "*" not in blocks and str(to_location_id) not in blocks:
                continue
            if str(actor_id) in (s.data.get("passed") or []):
                continue
            if await self._holder_yields(s, actor_id, now):
                continue
            return Blocked(
                s,
                s.label,
                list(s.data.get("ways_past") or DEFAULT_WAYS_PAST),
                int(s.data.get("attempts", 0)),
            )
        return None

    # -- writes (inside the caller's transaction) ----------------------------------------------

    async def open(
        self,
        tx: EventTransaction,
        *,
        kind: str,
        label: str,
        location_id: uuid.UUID | None = None,
        subject_actor_id: uuid.UUID | None = None,
        holder_actor_id: uuid.UUID | None = None,
        data: dict[str, Any] | None = None,
        visibility: str = "public",
        expires_tick: int | None = None,
        cause: Event | None = None,
        scene: Scene | None = None,
    ) -> Situation:
        sid = uuid.uuid4()
        data = dict(data or {})
        event = await tx.emit(
            ev.SituationOpened(
                situation_id=sid,
                kind=kind,
                label=label,
                location_id=location_id,
                subject_actor_id=subject_actor_id,
                holder_actor_id=holder_actor_id,
                data=data,
                visibility=visibility,
                expires_tick=expires_tick,
            ),
            cause=cause,
            scene=scene,
            location_id=location_id,
        )
        row = Situation(
            id=sid,
            campaign_id=tx.campaign_id,
            kind=kind,
            label=label,
            location_id=location_id,
            subject_actor_id=subject_actor_id,
            holder_actor_id=holder_actor_id,
            data=data,
            visibility=visibility,
            expires_tick=expires_tick,
            created_event_id=event.id,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def change(
        self,
        tx: EventTransaction,
        s: Situation,
        changes: dict[str, Any],
        *,
        cause: Event | None = None,
    ) -> None:
        previous = {k: s.data.get(k) for k in changes}
        await tx.emit(
            ev.SituationChanged(situation_id=s.id, changes=changes, previous=previous),
            cause=cause,
            location_id=s.location_id,
        )
        s.data = {**s.data, **changes}
        await self.session.flush()

    async def close(
        self,
        tx: EventTransaction,
        s: Situation,
        *,
        reason: str = "",
        status: str = "closed",
        cause: Event | None = None,
    ) -> None:
        event = await tx.emit(
            ev.SituationClosed(situation_id=s.id, reason=reason, status=status),
            cause=cause,
            location_id=s.location_id,
        )
        s.status, s.closed_event_id = status, event.id
        await self.session.flush()
