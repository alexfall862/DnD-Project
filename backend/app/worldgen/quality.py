"""Initial quality checks on a built world (campaign-generation §25). They run inside the
start transaction: any problem rolls the whole build back and the campaign stays a draft."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.core import RulesEngine
from app.persistence.models import (
    Actor,
    ActorController,
    Belief,
    Clue,
    Entity,
    Fact,
    Faction,
    Goal,
    Item,
    Location,
    Mystery,
    MysteryTruthFact,
    Plan,
    Scene,
)
from app.services.scenes import SceneService
from app.services.world import CampaignHandle
from app.worldgen.build import WorldBuilder
from app.worldgen.validate import pc_budget_errors


async def quality_errors(
    session: AsyncSession, h: CampaignHandle, b: WorldBuilder, env, ruleset=None
) -> list[str]:
    out: list[str] = []
    cid = h.campaign_id
    # opening scene: active, at a materialized place, with the player in it
    if b.opening_scene is None or b.player is None:
        out.append("no opening scene or no player character")
    else:
        scene = await session.get(Scene, b.opening_scene)
        player = await session.get(Actor, b.player)
        if scene is None or scene.status != "active" or player.current_scene_id != scene.id:
            out.append("the player is not in the opening scene")
        loc = await session.get(Location, scene.location_id) if scene else None
        if loc is None or loc.detail_level != "materialized":
            out.append("the opening location is not materialized")
        # the starting settlement is reachable from where play begins
        reach: set[uuid.UUID] = set()
        if loc is not None:
            reach = {loc.id} | {
                x.id for x, _e, _s in await SceneService(session).connected_locations(loc.id)
            }
        for s in (x for x in env.locations if x.settlement):
            inside = _contains(env, s.ref, scene_loc_ref(env))
            linked = s.ref in _reachable(env, scene_loc_ref(env))
            if b.refs.get(s.ref) not in reach and not inside and not linked:
                out.append(f"settlement {s.ref} is not reachable from the opening scene")
    # AI PCs are mechanically legal under the creation budget
    for a in env.actors:
        if a.role != "npc":
            out.extend(pc_budget_errors(a))
    # important NPCs have goals
    for a in env.actors:
        if a.role == "npc" and a.importance in ("full", "important") and a.alive:
            n = (
                (
                    await session.execute(
                        select(Goal).where(
                            Goal.owner_type == "actor", Goal.owner_id == b.refs[a.ref]
                        )
                    )
                )
                .scalars()
                .all()
            )
            if not n:
                out.append(f"important NPC {a.ref} has no goals")
    # actionable factions have active plans
    for f in (await session.execute(select(Faction).where(Faction.campaign_id == cid))).scalars():
        if (f.capabilities or {}).get("kind") == "polity":
            continue
        plans = (
            (
                await session.execute(
                    select(Plan)
                    .join(Goal, Goal.id == Plan.goal_id)
                    .where(
                        Goal.owner_type == "faction", Goal.owner_id == f.id, Plan.status == "active"
                    )
                )
            )
            .scalars()
            .all()
        )
        if not plans:
            out.append(f"faction {f.name} has no active plan")
    # opportunities have discovery routes
    for o in env.opportunities:
        if len(o.routes) < 2:
            out.append(f"opportunity {o.ref} has fewer than two discovery routes")
    # mysteries: fixed truth, redundant clue routes
    for m in (await session.execute(select(Mystery).where(Mystery.campaign_id == cid))).scalars():
        if not m.solution_locked:
            out.append(f"mystery {m.key} is not locked")
        truths = (
            (
                await session.execute(
                    select(MysteryTruthFact.fact_id).where(MysteryTruthFact.mystery_id == m.id)
                )
            )
            .scalars()
            .all()
        )
        if not truths:
            out.append(f"mystery {m.key} has no truth facts")
        clues = (
            (
                await session.execute(
                    select(Clue).where(Clue.mystery_id == m.id, Clue.state == "intact")
                )
            )
            .scalars()
            .all()
        )
        if len(clues) < 2:
            out.append(f"mystery {m.key} needs at least two clue routes (redundancy)")
        if len({c.clue_type for c in clues}) < 2 and len(clues) < 3:
            out.append(f"mystery {m.key}: clue routes should not all be of one kind")
    # perspectives do not leak: no party member holds a secret or a mystery truth
    pcs = [b.refs[a.ref] for a in env.actors if a.role != "npc"]
    secret_ids = set(
        (
            await session.execute(
                select(Fact.id).where(Fact.campaign_id == cid, Fact.sensitivity == "secret")
            )
        ).scalars()
    ) | set(
        (
            await session.execute(
                select(MysteryTruthFact.fact_id)
                .join(Mystery, Mystery.id == MysteryTruthFact.mystery_id)
                .where(Mystery.campaign_id == cid)
            )
        ).scalars()
    )
    if pcs and secret_ids:
        leaked = (
            (
                await session.execute(
                    select(Belief).where(Belief.actor_id.in_(pcs), Belief.fact_id.in_(secret_ids))
                )
            )
            .scalars()
            .all()
        )
        for bl in leaked:
            out.append(f"party member {bl.actor_id} starts knowing a secret ({bl.fact_id})")
    # ruleset references are valid (item templates)
    rs = ruleset or RulesEngine.load("core_adventure").ruleset
    for it in (
        await session.execute(
            select(Item).join(Entity, Entity.id == Item.entity_id).where(Entity.campaign_id == cid)
        )
    ).scalars():
        if it.template_key and it.template_key not in rs.equipment:
            out.append(f"item {it.id} uses unknown template {it.template_key}")
    # every actor has a controller; distant content stays shallow
    for aid in b.refs.values():
        a = await session.get(Actor, aid)
        if a is None:
            continue
        ctrl = (
            await session.execute(
                select(ActorController).where(
                    ActorController.actor_id == aid, ActorController.valid_until_event_id.is_(None)
                )
            )
        ).scalar_one_or_none()
        if ctrl is None:
            out.append(f"actor {aid} has no controller")
    return out


def scene_loc_ref(env) -> str | None:
    return env.opening.location_ref if env.opening else None


def _reachable(env, start: str | None) -> set[str]:
    """Places reachable from `start` over routes and containment, any number of hops (09c A9
    run: the opening square is inside Calder, Calder has a route to Oakhaven)."""
    if not start:
        return set()
    edges: dict[str, set[str]] = {}
    for r in env.routes:
        edges.setdefault(r.from_ref, set()).add(r.to_ref)
        edges.setdefault(r.to_ref, set()).add(r.from_ref)
    for x in env.locations:
        if x.parent_ref:
            edges.setdefault(x.ref, set()).add(x.parent_ref)
            edges.setdefault(x.parent_ref, set()).add(x.ref)
    seen, todo = {start}, [start]
    while todo:
        for n in edges.get(todo.pop(), ()):
            if n not in seen:
                seen.add(n)
                todo.append(n)
    return seen


def _contains(env, ancestor: str, ref: str | None) -> bool:
    """Is `ref` inside `ancestor` (the opening place is a building in the settlement)?"""
    by = {x.ref: x for x in env.locations}
    cur = by.get(ref) if ref else None
    while cur is not None:
        if cur.ref == ancestor:
            return True
        cur = by.get(cur.parent_ref) if cur.parent_ref else None
    return False


__all__ = ["quality_errors", "uuid"]
