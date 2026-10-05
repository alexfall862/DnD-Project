"""Where the focus character is, as they perceive it (play session 2: "a report of where we
are within the scene"; the scene strip showed only a zone key).

Everything comes from the focus actor's perspective: the place by the name they know (or what
it looks like), the scene's public layout, the people they can see and where they stand, the
places they can go from here, and the situations they can perceive (obstacles, statuses,
promises; `SituationService.visible_to`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.perspective import PerspectiveService


@dataclass
class HereZone:
    key: str
    name: str
    features: list[str]
    people: list[str]
    you_are_here: bool
    adjacent: bool


@dataclass
class HereExit:
    location_id: uuid.UUID
    known_as: str
    travel_minutes: int
    blocked_by: str | None = None


@dataclass
class HereView:
    actor_id: uuid.UUID
    location: str
    scene_type: str
    zone: str | None
    zones: list[HereZone]
    exits: list[HereExit]
    situations: list[dict[str, Any]] = field(default_factory=list)


async def neighbours(session: AsyncSession, location_id: uuid.UUID) -> set[uuid.UUID]:
    """Places one edge away."""
    from sqlalchemy import select

    from app.persistence.models import LocationEdge

    return set(
        (
            await session.execute(
                select(LocationEdge.to_location_id).where(
                    LocationEdge.from_location_id == location_id
                )
            )
        )
        .scalars()
        .all()
    )


class HereService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.perspective = PerspectiveService(session)

    async def view(self, actor_id: uuid.UUID) -> HereView | None:
        await self.perspective.require_focus_actor(actor_id)
        view = await self.perspective.scene_view(actor_id)
        scene = await self.perspective.repo.current_scene(actor_id)
        if view is None or scene is None:
            return None
        space = scene.state.get("space") or {}
        adjacency = {tuple(p) for p in space.get("adjacency", [])}
        mine = view.space_zone
        people: dict[str, list[str]] = {}
        for p in view.participants:
            if p.is_self:
                continue
            people.setdefault(p.zone or "", []).append(p.known_as)
        zones = [
            HereZone(
                key=z["key"],
                name=z.get("name") or z["key"],
                features=list(z.get("features") or []),
                people=sorted(people.get(z["key"], [])),
                you_are_here=z["key"] == mine,
                adjacent=(mine, z["key"]) in adjacency or (z["key"], mine) in adjacency,
            )
            for z in space.get("zones", [])
        ]
        if people.get(""):  # no layout, or people not placed in it
            zones.append(HereZone("", "around", [], sorted(people[""]), mine is None, False))
        exits: list[HereExit] = []
        situations: list[dict[str, Any]] = []
        from app.services.situations import SituationService

        sit = SituationService(self.session)
        if scene.location_id is not None:
            from app.services.scenes import SceneService

            names = await self.perspective.known_entities(actor_id)
            # the ways out are the neighbouring places, not everywhere reachable (A9 outcomes
            # eval: the whole map was listed)
            near = await neighbours(self.session, scene.location_id)
            for loc, ent, secs in await SceneService(self.session).connected_locations(
                scene.location_id
            ):
                if loc.id not in near:
                    continue
                label = names.get(ent.id) or (ent.metadata_ or {}).get("descriptor") or "somewhere"
                block = await sit.blocking(actor_id, scene.location_id, loc.id)
                exits.append(
                    HereExit(
                        loc.id,
                        label,
                        max(1, round((secs or 0) / 60)),
                        block.label if block is not None else None,
                    )
                )
            exits.sort(key=lambda e: e.travel_minutes)
        visible = await sit.visible_to(actor_id)
        names = {p.actor_id: p.known_as for p in view.participants if p.actor_id}
        names[actor_id] = "you"
        texts = await sit.lines(visible, names, refs=False)
        situations = [{"kind": s.kind, "text": t} for s, t in zip(visible, texts, strict=True)]
        return HereView(
            actor_id,
            view.location_known_as or "an unfamiliar place",
            view.scene_type,
            mine,
            zones,
            exits,
            situations,
        )
