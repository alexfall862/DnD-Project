"""SceneService — travel between locations and scene transitions (Milestone 07;
time-accounting §3 live/offscreen clocks, §5 reunion; human-visibility §3 split party).

`travel()` moves a group of actors along a location edge in one transaction: they leave their
scene, the clock advances once by the edge's travel time, and at the destination they either
join the active scene there (a *merge* when a whole scene arrives: `scene.merged_from`) or a
new scene starts from the location's seeded `space`. Reunion creates **no** Observations or
Claims about what the other group did — knowledge still moves only by communication. The only
Observations written here are arrivals (what everyone present can plainly see).

Offscreen scenes (no human-controlled participant) keep their `local_tick` behind the world
clock; a merge fast-forwards it (`scene.caught_up`). The bounded catch-up model call lives in
the orchestrator (Milestone 08 adds deterministic systems and plan steps).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import events as ev
from app.persistence.models import (
    Actor,
    Entity,
    Event,
    Location,
    LocationEdge,
    Observation,
    Scene,
    SceneParticipant,
)
from app.persistence.repositories.perspective import PerspectiveRepository
from app.services.events import EventTransaction
from app.services.world import CampaignHandle, WorldError, WorldService


@dataclass
class TravelResult:
    scene: Scene
    event: Event  # the first actor.moved event (cause of everything else)
    travel_seconds: int
    joined_existing: bool
    merged_from: list[uuid.UUID] = field(default_factory=list)
    ended_scene_ids: list[uuid.UUID] = field(default_factory=list)
    caught_up_from_tick: int | None = None


class SceneService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.world = WorldService(session)
        self.perspective = PerspectiveRepository(session)

    def _tx(self, h: CampaignHandle, **kw: Any) -> EventTransaction:
        return EventTransaction(self.session, h.campaign_id, h.timeline_id, **kw)

    # -- reads -------------------------------------------------------------------------------------

    async def active_scene_at(self, h: CampaignHandle, location_id: uuid.UUID) -> Scene | None:
        return (
            await self.session.execute(
                select(Scene).where(
                    Scene.timeline_id == h.timeline_id,
                    Scene.location_id == location_id,
                    Scene.status == "active",
                )
            )
        ).scalar_one_or_none()

    async def participants(self, scene_id: uuid.UUID) -> list[SceneParticipant]:
        return list(
            (
                await self.session.execute(
                    select(SceneParticipant).where(
                        SceneParticipant.scene_id == scene_id,
                        SceneParticipant.left_event_id.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )

    async def is_live(self, scene_id: uuid.UUID) -> bool:
        """A scene is live when a human-controlled actor is in it (human-visibility §2–§3)."""
        for p in await self.participants(scene_id):
            if await self.perspective.controller_type(p.actor_id) == "human":
                return True
        return False

    async def offscreen_scenes(self, h: CampaignHandle) -> list[Scene]:
        rows = (
            (
                await self.session.execute(
                    select(Scene).where(
                        Scene.timeline_id == h.timeline_id, Scene.status == "active"
                    )
                )
            )
            .scalars()
            .all()
        )
        return [s for s in rows if not await self.is_live(s.id)]

    async def connected_locations(
        self, location_id: uuid.UUID
    ) -> list[tuple[Location, Entity, int | None]]:
        """Every location reachable from here by edges, with the summed travel time of the
        shortest (by time) route. A traveller passes through intermediate places without
        scenes starting there."""
        edges = (await self.session.execute(select(LocationEdge))).scalars().all()
        graph: dict[uuid.UUID, list[tuple[uuid.UUID, int]]] = {}
        for e in edges:
            graph.setdefault(e.from_location_id, []).append(
                (e.to_location_id, int(e.travel_seconds or 0))
            )
        best: dict[uuid.UUID, int] = {location_id: 0}
        frontier = [location_id]
        while frontier:
            frontier.sort(key=lambda x: best[x])
            cur = frontier.pop(0)
            for nxt, secs in graph.get(cur, []):
                cand = best[cur] + secs
                if nxt not in best or cand < best[nxt]:
                    best[nxt] = cand
                    frontier.append(nxt)
        best.pop(location_id, None)
        if not best:
            return []
        rows = (
            await self.session.execute(
                select(Location, Entity)
                .join(Entity, Entity.id == Location.entity_id)
                .where(Location.id.in_(list(best)))
            )
        ).all()
        out = [(loc, ent, best[loc.id]) for loc, ent in rows]
        out.sort(key=lambda t: (t[2], t[1].canonical_name or ""))
        return out

    async def route_seconds(self, from_id: uuid.UUID, to_id: uuid.UUID) -> int | None:
        for loc, _ent, secs in await self.connected_locations(from_id):
            if loc.id == to_id:
                return secs
        return None

    # -- travel ------------------------------------------------------------------------------------

    async def travel(
        self,
        h: CampaignHandle,
        actor_ids: list[uuid.UUID],
        to_location_id: uuid.UUID,
        *,
        require_edge: bool = True,
        travel_seconds: int | None = None,
        scene_type: str = "social",
        created_by_type: str = "engine",
        created_by_id: uuid.UUID | None = None,
    ) -> TravelResult:
        if not actor_ids:
            raise WorldError("nobody is travelling")
        actors: list[Actor] = []
        for aid in actor_ids:
            a = await self.session.get(Actor, aid)
            if a is None:
                raise WorldError(f"actor {aid} not found")
            actors.append(a)
        froms = {a.current_location_id for a in actors}
        if len(froms) != 1:
            raise WorldError("travellers must start from the same location")
        from_location_id = froms.pop()
        if from_location_id == to_location_id:
            raise WorldError("already there")
        dest = await self.session.get(Location, to_location_id)
        if dest is None:
            raise WorldError("destination not found")
        if require_edge:
            if from_location_id is None:
                raise WorldError("travellers have no current location")
            secs = await self.route_seconds(from_location_id, to_location_id)
            if secs is None:
                raise WorldError("no route between those places")
            if travel_seconds is None:
                travel_seconds = secs
        travel_seconds = int(travel_seconds or 0)

        async with self._tx(h, created_by_type=created_by_type, created_by_id=created_by_id) as tx:
            # 1. leave
            first: Event | None = None
            left_scenes: dict[uuid.UUID, Scene] = {}
            for a in actors:
                part = await self.world._active_participation(a.id)
                scene = await self.session.get(Scene, part.scene_id) if part else None
                left_scene_id = scene.id if scene and scene.location_id != to_location_id else None
                move = await tx.emit(
                    ev.ActorMoved(
                        actor_id=a.id,
                        from_location_id=from_location_id,
                        to_location_id=to_location_id,
                        left_scene_id=left_scene_id,
                    ),
                    scene=scene if left_scene_id else None,
                    location_id=to_location_id,
                    cause=first,
                    entities=[(a.entity_id, "subject")],
                )
                first = first or move
                a.current_location_id = to_location_id
                a.updated_event_id = move.id
                if left_scene_id is not None and part is not None and scene is not None:
                    part.left_event_id = move.id
                    a.current_scene_id = None
                    await tx.emit(
                        ev.SceneParticipantLeft(scene_id=scene.id, actor_id=a.id),
                        scene=scene,
                        cause=move,
                        entities=[(a.entity_id, "subject")],
                    )
                    left_scenes[scene.id] = scene
            assert first is not None
            # 2. time passes once for the group
            if travel_seconds:
                await self.world._advance_clock(tx, travel_seconds, reason="travel", cause=first)
            # 3. empty scenes end; the rest stay active (offscreen if no human remains)
            ended: list[uuid.UUID] = []
            merged_from: list[uuid.UUID] = []
            for sid, scene in left_scenes.items():
                if not await self.participants(sid):
                    end = await tx.emit(ev.SceneEnded(scene_id=sid), scene=scene, cause=first)
                    scene.status, scene.end_event_id = "ended", end.id
                    scene.end_tick = tx.clock.current_tick
                    ended.append(sid)
                    merged_from.append(sid)
            # 4. arrive: join or start
            existing = await self.active_scene_at(h, to_location_id)
            caught_up_from: int | None = None
            if existing is not None:
                target = existing
                if target.local_tick < tx.clock.current_tick:
                    caught_up_from = target.local_tick
                    await tx.emit(
                        ev.SceneCaughtUp(
                            scene_id=target.id,
                            from_tick=target.local_tick,
                            to_tick=tx.clock.current_tick,
                        ),
                        scene=target,
                        cause=first,
                    )
                    target.local_tick = tx.clock.current_tick
                if merged_from:
                    await tx.emit(
                        ev.ScenesMerged(
                            from_scene_id=merged_from[0],
                            into_scene_id=target.id,
                            actor_ids=[a.id for a in actors],
                        ),
                        scene=target,
                        cause=first,
                    )
                    target.merged_from = list(target.merged_from or []) + merged_from
                space = dict(target.state.get("space") or {})
                positions = dict(space.get("positions", {}))
                entry = self._entry_zone(space, dest)
                for a in actors:
                    joined = await tx.emit(
                        ev.SceneParticipantJoined(scene_id=target.id, actor_id=a.id),
                        scene=target,
                        location_id=to_location_id,
                        cause=first,
                        entities=[(a.entity_id, "participant")],
                    )
                    self.session.add(
                        SceneParticipant(
                            scene_id=target.id, actor_id=a.id, joined_event_id=joined.id
                        )
                    )
                    a.current_scene_id = target.id
                    a.updated_event_id = joined.id
                    if entry is not None:
                        positions.setdefault(
                            str(a.id),
                            {"zone": entry, "engaged_with": [], "cover": "none", "elevated": False},
                        )
                if space:
                    target.state = {**target.state, "space": {**space, "positions": positions}}
                tx.touch_scene(target)
            else:
                space = dict((dest.properties or {}).get("space") or {})
                target = Scene(
                    campaign_id=h.campaign_id,
                    timeline_id=h.timeline_id,
                    location_id=to_location_id,
                    scene_type=scene_type,
                    start_tick=tx.clock.current_tick,
                    local_tick=tx.clock.current_tick,
                    state={},
                )
                # people already here and in no scene (residents, a shopkeeper) are part of
                # the scene that starts when someone arrives
                residents = await self._residents(to_location_id, {a.id for a in actors})
                if space:
                    positions = dict(space.get("positions", {}))
                    entry = self._entry_zone(space, dest)
                    zone_keys = [z["key"] for z in space.get("zones", [])]
                    for a in actors:
                        positions.setdefault(
                            str(a.id),
                            {"zone": entry, "engaged_with": [], "cover": "none", "elevated": False},
                        )
                    for r in residents:
                        home = (r.mechanical_profile or {}).get("home_zone")
                        zone = (
                            home if home in zone_keys else (zone_keys[-1] if zone_keys else entry)
                        )
                        positions.setdefault(
                            str(r.id),
                            {"zone": zone, "engaged_with": [], "cover": "none", "elevated": False},
                        )
                    target.state = {"space": {**space, "positions": positions}}
                self.session.add(target)
                await self.session.flush()
                everyone = [*actors, *residents]
                started = await tx.emit(
                    ev.SceneStarted(
                        scene_id=target.id,
                        location_id=to_location_id,
                        scene_type=scene_type,
                        participant_actor_ids=[a.id for a in everyone],
                    ),
                    scene=target,
                    location_id=to_location_id,
                    cause=first,
                    entities=[(a.entity_id, "participant") for a in everyone],
                )
                target.start_event_id = started.id
                for a in everyone:
                    self.session.add(
                        SceneParticipant(
                            scene_id=target.id, actor_id=a.id, joined_event_id=started.id
                        )
                    )
                    a.current_scene_id = target.id
                    a.updated_event_id = started.id
            await self.session.flush()
            # 5. arrival observations: what everyone present can plainly see
            await self._arrival_observations(tx, first, target, actors, dest)
        return TravelResult(
            target,
            first,
            travel_seconds,
            existing is not None,
            merged_from if existing is not None else [],
            ended,
            caught_up_from,
        )

    async def _residents(self, location_id: uuid.UUID, exclude: set[uuid.UUID]) -> list[Actor]:
        rows = (
            (
                await self.session.execute(
                    select(Actor).where(
                        Actor.current_location_id == location_id,
                        Actor.current_scene_id.is_(None),
                        Actor.alive.is_(True),
                        Actor.active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        out = []
        for a in rows:
            if a.id in exclude:
                continue
            if await self.perspective.controller_type(a.id) in (None, "dormant"):
                continue
            out.append(a)
        return out

    @staticmethod
    def _entry_zone(space: dict[str, Any], dest: Location) -> str | None:
        zones = space.get("zones") or []
        if not zones:
            return None
        wanted = (dest.properties or {}).get("entry_zone")
        keys = [z["key"] for z in zones]
        if wanted in keys:
            return wanted
        for z in zones:
            if z.get("exit"):
                return z["key"]
        return keys[0]

    async def _arrival_observations(
        self,
        tx: EventTransaction,
        event: Event,
        scene: Scene,
        arriving: list[Actor],
        dest: Location,
    ) -> None:
        present = await self.participants(scene.id)
        arriving_ids = {a.id for a in arriving}
        dest_entity = await self.session.get(Entity, dest.entity_id)
        for p in present:
            ident = await self.perspective.identity_knowledge(p.actor_id)
            loc_name = (
                ident[dest.entity_id].known_name
                if dest.entity_id in ident
                else ((dest_entity.metadata_ or {}).get("descriptor") if dest_entity else None)
            )
            if p.actor_id in arriving_ids:
                raws = [{"who": "you", "location": loc_name}]
            else:
                raws = []
                for a in arriving:
                    ent = await self.session.get(Entity, a.entity_id)
                    name = (
                        ident[a.entity_id].known_name
                        if a.entity_id in ident
                        else ((ent.metadata_ or {}).get("descriptor") if ent else None)
                        or "a stranger"
                    )
                    raws.append({"who": name, "location": loc_name, "entity_id": str(a.entity_id)})
            for raw in raws:
                self.session.add(
                    Observation(
                        campaign_id=tx.campaign_id,
                        actor_id=p.actor_id,
                        source_event_id=event.id,
                        channel="vision",
                        observation_type="arrived",
                        raw={"event_type": "actor.moved", **raw},
                        confidence=1.0,
                        game_tick=event.game_tick,
                        scene_id=scene.id,
                    )
                )
        await self.session.flush()
