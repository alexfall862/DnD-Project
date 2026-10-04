"""MemoryProcessingService — checkpoints, journal and encyclopedia (orchestration §23;
ai-contracts §11, §15; observation-authoring §6; human-visibility §7; database-schema §16).

Memory processing runs at checkpoints (scene end, combat end, rest, significant event,
session checkpoint), one bounded Memory Processor call per AI actor with new observations.
The model sees that actor's rendered observations and heard dialogue for the window, never
the human-facing narration or anyone else's events. Every memory it proposes must cite
observation ids that belong to the actor (MemoryService enforces lineage) or it is dropped.

Journal entries are the same idea for the human-controlled character (Journal Writer, from
the character's perspective, misconceptions preserved). The encyclopedia is a deterministic,
rebuildable projection of identity knowledge + beliefs; no model.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextCompiler
from app.ai.roles import JournalWriterOut, MemoryProcessorOut
from app.ai.runner import ModelRunner
from app.domain import events as ev
from app.engine.beliefs import BeliefProposal, Proposition
from app.persistence.models import (
    EncyclopediaEntry,
    Event,
    JournalEntry,
    Observation,
    Scene,
)
from app.services.events import EventTransaction
from app.services.knowledge import KnowledgeService
from app.services.memory import MemoryLineageError, MemoryService
from app.services.perspective import PerspectiveService
from app.services.psychology import PsychologyService
from app.services.turns import Turn
from app.services.world import CampaignHandle

CHECKPOINT_REASONS = {
    "scene_end",
    "combat_end",
    "rest",
    "significant_event",
    "session_checkpoint",
    "discovery",
}
MAX_WINDOW = 40


@dataclass
class CheckpointResult:
    actor_id: uuid.UUID
    reason: str
    observations: int
    memories_created: int
    deferred: bool = False
    status: str = "ok"


class MemoryProcessingService:
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
        self.perspective = PerspectiveService(session)
        self.knowledge = KnowledgeService(session)
        self.psychology = PsychologyService(session)

    # -- window ------------------------------------------------------------------------------------

    async def window(self, actor_id: uuid.UUID, scene: Scene | None) -> list[Observation]:
        """Observations since this actor's last checkpoint (recorded on the scene)."""
        since = None
        if scene is not None:
            since = (scene.state.get("memory_checkpoints") or {}).get(str(actor_id))
        q = select(Observation).where(Observation.actor_id == actor_id)
        if since is not None:
            q = q.where(Observation.created_at > since_dt(since))
        rows = (
            (await self.session.execute(q.order_by(Observation.created_at).limit(MAX_WINDOW)))
            .scalars()
            .all()
        )
        return list(rows)

    # -- checkpoint ------------------------------------------------------------------------------

    async def checkpoint(
        self,
        h: CampaignHandle,
        actor_id: uuid.UUID,
        *,
        reason: str,
        turn: Turn,
        scene: Scene | None = None,
        defer: bool = False,
    ) -> CheckpointResult:
        obs = await self.window(actor_id, scene)
        if not obs:
            return CheckpointResult(actor_id, reason, 0, 0, status="nothing_new")
        if defer or not turn.can_make_sync_call():
            async with self._tx(h) as tx:
                await tx.emit(
                    ev.MemoryCheckpoint(
                        actor_id=actor_id, reason=reason, observations=len(obs), deferred=True
                    )
                )
            if scene is not None:
                pending = list(scene.state.get("memory_checkpoint_pending", []))
                if str(actor_id) not in pending:
                    pending.append(str(actor_id))
                scene.state = {**scene.state, "memory_checkpoint_pending": pending}
            return CheckpointResult(actor_id, reason, len(obs), 0, deferred=True, status="deferred")
        names = await self.perspective.known_entities(actor_id)
        lines = [
            f"o_{o.id.hex[:8]} [t{o.game_tick}] "
            + PerspectiveService.render(o.observation_type, o.raw, names)
            for o in obs
        ]
        ref_map = {f"o_{o.id.hex[:8]}": o.id for o in obs}
        ctx = await self.compiler.compile(
            h,
            "memory_processor",
            actor_id=actor_id,
            purpose=f"memory checkpoint: {reason}",
            situation=(
                f"Checkpoint ({reason}). Your experience since the last checkpoint, with ids "
                "to cite as source_observation_ids:\n- " + "\n- ".join(lines)
            ),
            query=" ".join(lines[-5:]),
            now_tick=scene.local_tick if scene else None,
        )
        res = await self.runner.run(h, ctx, turn_id=turn.turn_id)
        turn.record_call(
            "memory_processor",
            sync=False,
            calls=res.calls,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
            context_tokens=ctx.estimated_tokens,
        )
        created = 0
        if res.ok and isinstance(res.output, MemoryProcessorOut):
            for cand in res.output.memories[:3]:
                ids = []
                for ref in cand.source_observation_ids:
                    if ref in ref_map:
                        ids.append(ref_map[ref])
                    else:
                        try:
                            ids.append(uuid.UUID(str(ref)))
                        except ValueError:
                            continue
                if not ids:
                    ids = [o.id for o in obs[-3:]]  # the window itself is the lineage
                entity_ids = sorted({eid for o in obs if o.id in ids for eid in _entity_ids_of(o)})
                try:
                    await self.memory.create_memory(
                        h,
                        actor_id,
                        cand.summary,
                        source_observation_ids=ids,
                        emotional_interpretation=cand.emotional_interpretation,
                        salience=cand.salience,
                        emotional_weight=cand.emotional_weight,
                        is_core=cand.is_core,
                        entity_ids=entity_ids,
                        metadata={"model_run_id": str(res.model_run_id), "reason": reason},
                    )
                    created += 1
                except MemoryLineageError as exc:
                    turn.notes.append(f"memory candidate dropped for {actor_id}: {exc}")
            async with self._tx(h, created_by_id=actor_id) as tx:
                for bp in res.output.belief_proposals[:2]:
                    prop = Proposition.from_dict(bp.proposition.model_dump())
                    btype = "believed" if bp.belief_type == "known" else bp.belief_type
                    conf = min(float(bp.confidence), 0.9)
                    event = await tx.emit(
                        ev.BeliefFormed(
                            actor_id=actor_id,
                            proposition_key=prop.key,
                            belief_type=btype,
                            confidence=conf,
                            model_run_id=res.model_run_id,
                        )
                    )
                    await self.knowledge.store_belief(
                        tx,
                        actor_id,
                        BeliefProposal(prop, btype, conf, "self", ("memory processing",)),
                        acquired_event=event,
                    )
                for ep in res.output.emotion_proposals[:1]:
                    await self.psychology.set_emotion(
                        tx, actor_id, ep.emotion.lower()[:32], ep.intensity, source="memory"
                    )
                await tx.emit(
                    ev.MemoryCheckpoint(
                        actor_id=actor_id,
                        reason=reason,
                        observations=len(obs),
                        memories_created=created,
                    )
                )
        else:
            async with self._tx(h) as tx:
                await tx.emit(
                    ev.MemoryCheckpoint(
                        actor_id=actor_id, reason=reason, observations=len(obs), memories_created=0
                    )
                )
        if scene is not None:
            fresh = await self.session.get(Scene, scene.id)
            if fresh is not None:
                marks = dict(fresh.state.get("memory_checkpoints", {}))
                marks[str(actor_id)] = obs[-1].created_at.isoformat()
                pending = [
                    p
                    for p in fresh.state.get("memory_checkpoint_pending", [])
                    if p != str(actor_id)
                ]
                fresh.state = {
                    **fresh.state,
                    "memory_checkpoints": marks,
                    "memory_checkpoint_pending": pending,
                }
        return CheckpointResult(actor_id, reason, len(obs), created, status=res.status)

    # -- journal -------------------------------------------------------------------------------

    async def write_journal(
        self,
        h: CampaignHandle,
        actor_id: uuid.UUID,
        *,
        turn: Turn,
        scene: Scene | None,
        entry_type: str = "session",
    ) -> JournalEntry | None:
        """One Journal Writer call from the character's perspective (ai-contracts §15)."""
        obs = await self.window(actor_id, scene)
        if not obs or not turn.can_make_sync_call():
            return None
        names = await self.perspective.known_entities(actor_id)
        lines = [PerspectiveService.render(o.observation_type, o.raw, names) for o in obs]
        ctx = await self.compiler.compile(
            h,
            "journal_writer",
            actor_id=actor_id,
            purpose="journal entry",
            situation="Since your last entry:\n- " + "\n- ".join(lines),
        )
        res = await self.runner.run(h, ctx, turn_id=turn.turn_id)
        turn.record_call(
            "journal_writer",
            sync=False,
            calls=res.calls,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
            context_tokens=ctx.estimated_tokens,
        )
        if not res.ok or not isinstance(res.output, JournalWriterOut):
            return None
        seqs = [e.sequence_number for e in await self._events_of(obs)]
        async with self._tx(h, created_by_id=actor_id) as tx:
            entry = JournalEntry(
                campaign_id=h.campaign_id,
                timeline_id=h.timeline_id,
                actor_id=actor_id,
                entry_type=entry_type,
                title=res.output.title,
                body=res.output.body,
                from_sequence=min(seqs) if seqs else None,
                to_sequence=max(seqs) if seqs else None,
                game_tick=tx.clock.current_tick,
                model_run_id=res.model_run_id,
            )
            self.session.add(entry)
            await self.session.flush()
            event = await tx.emit(
                ev.JournalEntryWritten(
                    actor_id=actor_id,
                    entry_id=entry.id,
                    entry_type=entry_type,
                    model_run_id=res.model_run_id,
                )
            )
            entry.created_event_id = event.id
        return entry

    async def journal(self, actor_id: uuid.UUID) -> list[JournalEntry]:
        return list(
            (
                await self.session.execute(
                    select(JournalEntry)
                    .where(JournalEntry.actor_id == actor_id)
                    .order_by(JournalEntry.created_at)
                )
            )
            .scalars()
            .all()
        )

    # -- encyclopedia ------------------------------------------------------------------------------

    async def rebuild_encyclopedia(
        self, h: CampaignHandle, actor_id: uuid.UUID
    ) -> list[EncyclopediaEntry]:
        """Deterministic projection: one entry per entity the actor knows by name, with their
        beliefs about it grouped by type. Known facts and suspicions stay distinguishable."""
        names = await self.perspective.known_entities(actor_id)
        beliefs = await self.perspective.beliefs(actor_id)
        by_entity: dict[uuid.UUID, dict[str, list[str]]] = {}
        for b in beliefs:
            if b.proposition.get("predicate") == "asserted":
                continue
            for key in ("subject_entity_id", "object_entity_id"):
                v = b.proposition.get(key)
                try:
                    eid = uuid.UUID(str(v)) if v else None
                except ValueError:
                    eid = None
                if eid is None or eid not in names:
                    continue
                subj = _name(names, b.proposition.get("subject_entity_id"))
                obj = _name(names, b.proposition.get("object_entity_id"))
                line = f"{subj} {b.proposition.get('predicate')} {obj}".replace("  ", " ").strip()
                by_entity.setdefault(eid, {}).setdefault(b.belief_type, [])
                if line not in by_entity[eid][b.belief_type]:
                    by_entity[eid][b.belief_type].append(line)
        existing = {
            e.entity_id: e
            for e in (
                await self.session.execute(
                    select(EncyclopediaEntry).where(EncyclopediaEntry.actor_id == actor_id)
                )
            )
            .scalars()
            .all()
        }
        out: list[EncyclopediaEntry] = []
        for eid, display in names.items():
            category = await self._category(eid)
            knowledge = by_entity.get(eid, {})
            known = knowledge.get("known", [])
            summary = (
                f"{display}: " + "; ".join(known[:2]) if known else f"{display}: known by name"
            )
            row = existing.get(eid)
            if row is None:
                row = EncyclopediaEntry(
                    campaign_id=h.campaign_id,
                    timeline_id=h.timeline_id,
                    actor_id=actor_id,
                    entity_id=eid,
                    category=category,
                    display_name=display,
                )
                self.session.add(row)
            row.display_name, row.category, row.summary, row.knowledge = (
                display,
                category,
                summary,
                knowledge,
            )
            out.append(row)
        await self.session.flush()
        return out

    async def _category(self, entity_id: uuid.UUID) -> str:
        from app.persistence.models import Entity

        ent = await self.session.get(Entity, entity_id)
        if ent is None:
            return "other"
        return {"actor": "person", "location": "place", "item": "thing"}.get(
            ent.entity_type, "other"
        )

    # -- helpers ---------------------------------------------------------------------------------

    def _tx(self, h: CampaignHandle, *, created_by_id: uuid.UUID | None = None) -> EventTransaction:
        return EventTransaction(
            self.session,
            h.campaign_id,
            h.timeline_id,
            created_by_type="ai" if created_by_id else "engine",
            created_by_id=created_by_id,
        )

    async def _events_of(self, obs: list[Observation]) -> list[Event]:
        ids = {o.source_event_id for o in obs}
        if not ids:
            return []
        return list(
            (await self.session.execute(select(Event).where(Event.id.in_(ids)))).scalars().all()
        )


def since_dt(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)


def _entity_ids_of(o: Observation) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    raw = o.raw or {}
    for p in raw.get("participants", []):
        v = p.get("entity_id")
        try:
            out.append(uuid.UUID(str(v)))
        except (ValueError, TypeError):
            pass
    prop = raw.get("proposition") or {}
    for key in ("subject_entity_id", "object_entity_id"):
        v = prop.get(key)
        try:
            out.append(uuid.UUID(str(v)))
        except (ValueError, TypeError):
            pass
    return out


def _name(names: dict[uuid.UUID, str], raw: Any) -> str:
    if not raw:
        return ""
    try:
        return names.get(uuid.UUID(str(raw)), "someone")
    except ValueError:
        return str(raw)
