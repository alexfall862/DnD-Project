"""Background extras become living characters when the players keep engaging them (play
session 2026-10-05: the gate merchant was a scripted extra, so the narrator voiced him,
nobody remembered the deal, and the scene went nowhere).

On the second engagement (addressed, persuaded, threatened or attacked) the engine promotes
the extra before others react, so they answer in that same turn:

1. one bounded `npc_materializer` call writes their psychology and their memory of what
   they witnessed, from their description and this scene's public history (the feed, minus
   whispers and private lines they could not have heard);
2. the result is applied through the ordinary services, each with its event: an
   `actor.promoted` event carrying the new behavior profile, goals, memories, an attitude
   toward each party member present, and the controller switch scripted → ai.

No world facts are created: what the extra claimed about their goods stays a claim. If the
call fails the extra is still promoted, with a plain profile and their witnessed lines as
memories, so continuity never depends on one model call.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextCompiler
from app.ai.roles import NPCMaterializerOut
from app.ai.runner import ModelRunner
from app.domain import events as ev
from app.persistence.models import Actor, Entity, PartyMembership, Scene
from app.services.events import EventTransaction
from app.services.knowledge import KnowledgeService
from app.services.memory import MemoryService
from app.services.perspective import PerspectiveService
from app.services.psychology import PsychologyService
from app.services.scene_log import render_turns, scene_turns
from app.services.turns import Turn
from app.services.world import CampaignHandle, WorldService

PROMOTE_AFTER = 2  # engagements before an extra becomes a living character
DIMENSIONS = (
    "risk_tolerance",
    "aggression",
    "empathy",
    "curiosity",
    "loyalty",
    "impulsiveness",
    "honesty",
    "sociability",
    "ambition",
)


class PromotionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        compiler: ContextCompiler,
        runner: ModelRunner,
        memory: MemoryService,
    ) -> None:
        self.session = session
        self.compiler = compiler
        self.runner = runner
        self.memory = memory
        self.world = WorldService(session)
        self.psy = PsychologyService(session)
        self.k = KnowledgeService(session)
        self.perspective = PerspectiveService(session)

    async def note_engagement(self, scene: Scene, actor_ids: set[uuid.UUID]) -> list[uuid.UUID]:
        """Count engagements with scripted extras in this scene; return those now due."""
        due: list[uuid.UUID] = []
        counts = dict(scene.state.get("engagements") or {})
        for aid in actor_ids:
            if await self.perspective.repo.controller_type(aid) != "scripted":
                continue
            counts[str(aid)] = int(counts.get(str(aid), 0)) + 1
            if counts[str(aid)] >= PROMOTE_AFTER:
                due.append(aid)
        if counts != (scene.state.get("engagements") or {}):
            scene.state = {**scene.state, "engagements": counts}
            await self.session.flush()
        return due

    async def promote(
        self,
        h: CampaignHandle,
        actor_id: uuid.UUID,
        *,
        focus_actor_id: uuid.UUID,
        scene: Scene,
        turn: Turn,
    ) -> str:
        actor = await self.session.get(Actor, actor_id)
        entity = await self.session.get(Entity, actor.entity_id) if actor else None
        if actor is None or entity is None:
            return "promotion skipped: actor not found"
        view = await self.perspective.scene_view(focus_actor_id)
        names = {str(p.actor_id): p.known_as for p in (view.participants if view else [])}
        known_as = (
            names.get(str(actor_id)) or (entity.metadata_ or {}).get("descriptor") or "a stranger"
        )
        me = await self.perspective.repo.self_name(focus_actor_id) or "the player"
        turns = await scene_turns(self.session, focus_actor_id, scene, limit=10)
        witnessed = render_turns(
            turns, player_name=me, names=names, public_only=True, narration_chars=500
        )
        descriptor = (entity.metadata_ or {}).get("descriptor") or entity.canonical_name
        profile_before = dict(actor.behavior_profile or {})
        ctx = await self.compiler.compile(
            h,
            "npc_materializer",
            actor_id=None,
            purpose=f"promote {entity.canonical_name}",
            situation=(
                f"Make {known_as} a living character. In the witnessed lines they appear as "
                f'"{known_as}". Return only JSON.'
            ),
            extra_sections={
                "person": (
                    f"Description: {descriptor}. Name: {entity.canonical_name}. "
                    f"Seen by the party as: {known_as}. "
                    + (
                        f"Notes: {profile_before.get('summary')}"
                        if profile_before.get("summary")
                        else ""
                    )
                ),
                "witnessed": "\n".join(f"- {w}" for w in witnessed) or "Nothing yet.",
                "scene": (
                    f"{view.location_known_as or 'here'}; present: "
                    + ", ".join(p.known_as for p in view.participants)
                    if view
                    else "unknown"
                ),
            },
        )
        res = await self.runner.run(h, ctx, turn_id=turn.turn_id)
        turn.record_call(
            "npc_materializer",
            sync=True,
            calls=res.calls,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
            context_tokens=ctx.estimated_tokens,
        )
        out: NPCMaterializerOut | None = res.output if res.ok else None  # type: ignore[assignment]
        if out is None:
            out = NPCMaterializerOut(
                summary=f"{descriptor}, drawn into the party's business.",
                memories=[{"summary": w[:400], "salience": 0.6} for w in witnessed[-3:]],  # type: ignore[list-item]
            )
            reason_note = f"materializer unusable ({res.status}); plain profile"
        else:
            reason_note = "materialized"
        dims = {
            k: max(0.0, min(1.0, float(v))) for k, v in out.dimensions.items() if k in DIMENSIONS
        }
        behavior = {
            **profile_before,
            "summary": out.summary,
            "occupation": out.occupation or profile_before.get("occupation", ""),
            "temperament": out.temperament,
            "dimensions": {**(profile_before.get("dimensions") or {}), **dims},
        }
        async with EventTransaction(self.session, h.campaign_id, h.timeline_id) as tx:
            await tx.emit(
                ev.ActorPromoted(
                    actor_id=actor_id,
                    reason=f"engaged {PROMOTE_AFTER}+ times in scene; {reason_note}",
                    behavior_profile=behavior,
                    goals=len(out.goals),
                    memories=len(out.memories),
                    model_run_id=res.model_run_id,
                ),
                entities=[(entity.id, "subject")],
            )
            actor.behavior_profile = behavior
            if actor.importance_tier == "background":
                actor.importance_tier = "standard"  # so their reactions are considered
            for g in out.goals:
                await self.psy.create_goal(h, actor_id, g.description, priority=g.priority, tx=tx)
        for m in out.memories:
            await self.memory.create_memory(
                h, actor_id, m.summary, seed=True, salience=m.salience, emotional_weight=0.3
            )
        party = await self._party_present(focus_actor_id, scene)
        att = out.attitude_to_party.model_dump()
        for member in party:
            if member == actor_id:
                continue
            try:
                await self.k.seed_relationship(h, actor_id, member, **att)
            except Exception:  # noqa: BLE001 - an existing relationship stays as it is
                pass
        await self.world.set_controller(h, actor_id, "ai")
        return f"promoted {entity.canonical_name} to a living character ({reason_note})"

    async def _party_present(self, focus_actor_id: uuid.UUID, scene: Scene) -> list[uuid.UUID]:
        parties = select(PartyMembership.party_id).where(PartyMembership.actor_id == focus_actor_id)
        members = set(
            (
                await self.session.execute(
                    select(PartyMembership.actor_id).where(PartyMembership.party_id.in_(parties))
                )
            )
            .scalars()
            .all()
        ) or {focus_actor_id}
        present = {a.id for a, _ in await self.perspective.repo.scene_participants(scene.id)}
        return [m for m in members if m in present]
