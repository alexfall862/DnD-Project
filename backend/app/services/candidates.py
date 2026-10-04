"""Perspective-safe entity candidates for one actor's model call (orchestration §10).

Refs (`mira`, `a_thief`, `a_thief_2`, zone keys, item slugs) are derived from what *this*
actor can see and the names *this* actor knows, in a deterministic order, so the model can
cite them and the engine can map them back to ids without ever exposing an unknown identity.
Shared by the orchestrator (human intents) and the AI actor service (AI intentions).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from app.persistence.models import Scene
from app.services.actions import ActionService
from app.services.perspective import PerspectiveService
from app.services.world import CampaignHandle, WorldError


@dataclass
class Candidate:
    ref: str
    kind: str  # actor | zone | item | self
    id: str  # actor id / zone key / item id
    known_as: str
    entity_id: uuid.UUID | None = None
    hostile: bool | None = None


def slug(text: str, fallback: str = "someone") -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or fallback


async def build_candidates(
    perspective: PerspectiveService,
    actions: ActionService,
    h: CampaignHandle,
    actor_id: uuid.UUID,
    scene: Scene,
) -> list[Candidate]:
    view = await perspective.scene_view(actor_id)
    out: list[Candidate] = [Candidate("self", "self", str(actor_id), "you")]
    used: dict[str, int] = {}
    enc = scene.state.get("encounter") or {}
    sides = enc.get("sides", {})
    me_side = sides.get(str(actor_id))
    rows = await perspective.repo.scene_participants(scene.id)
    actor_by_entity = {e.id: a for a, e in rows}
    created = {e.id: e.created_at for _a, e in rows}
    if view:
        # same display name ("a thief", "a thief") -> the earlier-created entity comes first, so
        # "the second one" is stable across turns and processes
        for p in sorted(
            view.participants,
            key=lambda p: (p.known_as.lower(), created.get(p.entity_id), str(p.entity_id)),
        ):
            if p.is_self:
                continue
            base = slug(p.known_as)
            used[base] = used.get(base, 0) + 1
            ref = base if used[base] == 1 else f"{base}_{used[base]}"
            a = actor_by_entity.get(p.entity_id)
            aid = str(a.id) if a else None
            hostile = (
                (sides[aid] != me_side) if (aid and sides and me_side and aid in sides) else None
            )
            out.append(Candidate(ref, "actor", aid or "", p.known_as, p.entity_id, hostile))
    for z in (scene.state.get("space") or {}).get("zones", []):
        out.append(Candidate(z["key"], "zone", z["key"], z.get("name") or z["key"]))
    for i in await perspective.inventory(actor_id):
        name = i.name or i.template_key or "item"
        out.append(Candidate(slug(name, "item"), "item", str(i.item_id), name))
    try:
        loaded = await actions.load_scene(h, scene.id)
        for items in loaded.ctx.ground.values():
            for it in items:
                name = it.name or it.def_key
                out.append(Candidate(slug(name, "item"), "item", it.instance_key, name))
    except WorldError:
        pass
    return out


def candidates_text(cands: list[Candidate]) -> str:
    actors = ", ".join(
        f"{c.ref} ({c.known_as}{', hostile' if c.hostile else ''})"
        for c in cands
        if c.kind == "actor"
    )
    zones = ", ".join(c.ref for c in cands if c.kind == "zone")
    items = ", ".join(f"{c.ref} ({c.known_as})" for c in cands if c.kind == "item")
    return (
        f"Entity refs you may use — people: self, {actors or 'none'}; "
        f"zones: {zones or 'none'}; items: {items or 'none'}."
    )
