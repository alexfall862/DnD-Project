"""AIActorService — independent AI players and NPCs (Milestone 06b; orchestration §8, §12,
§16, §18–§20, §34; ai-contracts §5–§7, §12; communication-and-knowledge §2–§5;
belief-update-rules §7).

    what just happened ──► eligibility + significance (engine/reactions) ──► top N visible
      ──► one decision per actor from the same scene snapshot (concurrent provider calls)
        ──► apply, one at a time, revalidated against the current scene:
              speech  → conveys[] authorised + corroborated → SpeechService (Claims, beliefs)
              intent  → autonomy gate → ActionService (never outcomes; the engine resolves)
              beliefs / emotions / goals / relationship deltas → event-linked projections
              fallback policy → stored for the next combat turn

The model only ever expresses what the actor wants. Everything it says is checked against the
speaker's own perspective, everything it does goes through the rules engine, and every change
it causes is an Event.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextCompiler
from app.ai.roles import AIPlayerOut, BeliefProcessorOut, ClaimExtractorOut, NPCActorOut
from app.ai.runner import ModelRunner, RunResult
from app.config import Settings
from app.domain import events as ev
from app.engine import beliefs as rules
from app.engine.actions import ActionRequest
from app.engine.autonomy import gate as autonomy_gate
from app.engine.beliefs import BeliefProposal, GateInput, Proposition, belief_processor_gate
from app.engine.core import RulesEngine
from app.engine.reactions import ReactionSignals, significance, tier
from app.engine.tactics import (
    FallbackPolicy,
    behavior_reaction_chooser,
    choose_action,
    hostiles,
    situation_unchanged,
)
from app.persistence.models import Actor, Belief, Fact, Scene
from app.services.actions import ActionService, LoadedScene, StaleStateError
from app.services.candidates import Candidate, build_candidates, candidates_text, slug
from app.services.events import EventTransaction
from app.services.knowledge import KnowledgeService
from app.services.perspective import PerspectiveService
from app.services.psychology import PsychologyService
from app.services.speech import ConveysItem, LeakageError, SpeechResult, SpeechService
from app.services.turns import Turn
from app.services.vocab import FREE_TYPES, SPEECH_TYPES, action_key_for
from app.services.world import CampaignHandle, WorldError

STOP = {
    "the",
    "a",
    "an",
    "and",
    "that",
    "this",
    "with",
    "from",
    "about",
    "before",
    "after",
    "into",
    "have",
    "has",
    "was",
    "were",
    "not",
    "you",
    "your",
}
PHATIC_MAX_WORDS = 12
MAX_CONVEYS = 3
MAX_INTENTIONS = 2
MAX_EMOTIONS = 1


@dataclass
class Happenings:
    """What the player's turn did, as engine facts (not perspective content), for reaction
    eligibility only."""

    acting_actor: uuid.UUID
    in_combat: bool = False
    addressed: set[uuid.UUID] = field(default_factory=set)  # whisper / explicit speech targets
    asked: set[uuid.UUID] = field(default_factory=set)  # received a question-stance Claim
    informed: set[uuid.UUID] = field(default_factory=set)  # received any Claim
    claim_entities: set[uuid.UUID] = field(default_factory=set)
    attacked: set[uuid.UUID] = field(default_factory=set)
    speech_results: list[SpeechResult] = field(default_factory=list)

    def note_speech(self, r: SpeechResult, targets: list[uuid.UUID]) -> None:
        self.speech_results.append(r)
        self.addressed |= set(targets)
        self.informed |= set(r.recipients)
        asked = set(r.recipients) & set(targets) if targets else set(r.recipients)
        for c in r.claims:
            if c.speaker_stance == "question":
                self.asked |= asked  # a question to someone is not a question to everyone
            for eid in (c.subject_entity_id, c.object_entity_id):
                if eid is not None:
                    self.claim_entities.add(eid)


@dataclass
class Decision:
    actor_id: uuid.UUID
    role: str
    run: RunResult
    cands: list[Candidate]
    ref_map: dict[str, uuid.UUID]
    based_on_scene_version: int
    score: float = 0.0
    kind: str = "reaction"  # reaction | combat

    @property
    def output(self) -> AIPlayerOut | NPCActorOut | None:
        return self.run.output if self.run.ok else None  # type: ignore[return-value]


@dataclass
class Applied:
    actor_id: uuid.UUID
    kind: str
    spoke: bool = False
    speech: dict[str, Any] | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    paused: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    rejected: str | None = None
    claim_extractor_used: bool = False
    speech_result: SpeechResult | None = None


class AIActorService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        engine: RulesEngine,
        compiler: ContextCompiler,
        runner: ModelRunner,
        actions: ActionService,
        speech: SpeechService,
    ) -> None:
        self.session = session
        self.settings = settings
        self.engine = engine
        self.compiler = compiler
        self.runner = runner
        self.actions = actions
        self.speech = speech
        self.perspective = PerspectiveService(session)
        self.knowledge = KnowledgeService(session)
        self.psychology = PsychologyService(session)

    # -- who reacts ------------------------------------------------------------------------------

    async def ai_participants(self, scene: Scene) -> list[Actor]:
        out = []
        for a, _e in await self.perspective.repo.scene_participants(scene.id):
            if not a.alive or not a.active:
                continue
            if await self.perspective.repo.controller_type(a.id) == "ai":
                out.append(a)
        return out

    async def signals_for(self, scene: Scene, actor: Actor, hap: Happenings) -> ReactionSignals:
        aid = actor.id
        rel = await self.psychology.has_relationship(aid, hap.acting_actor)
        goal = await self.psychology.goal_relevant(aid, hap.claim_entities)
        emo = await self.psychology.strongest_emotion(aid)
        seen = scene.state.get("reaction_kinds", {}).get(str(aid), [])
        kind = "attacked" if aid in hap.attacked else "asked" if aid in hap.asked else "told"
        return ReactionSignals(
            actor_id=str(aid),
            importance=actor.importance_tier,
            direct_target=aid in hap.addressed or aid in hap.attacked,
            asked=aid in hap.asked,
            danger=hap.in_combat and aid in hap.attacked,
            new_information=aid in hap.informed,
            goal_relevant=goal,
            relationship_relevant=rel,
            emotional_weight=emo,
            novelty=0.0 if kind in seen else 1.0,
            combat_turn=False,
            scene_importance=float(scene.state.get("importance", 0.7)),
        )

    async def select_reactions(
        self, scene: Scene, hap: Happenings, turn: Turn
    ) -> tuple[list[tuple[Actor, float]], list[tuple[Actor, float]]]:
        """(visible, silent): visible get a model call (bounded by the spotlight budget), silent
        are medium-significance actors whose state is noted without a call."""
        scored = []
        for a in await self.ai_participants(scene):
            if a.id == hap.acting_actor:
                continue
            s = await self.signals_for(scene, a, hap)
            sc = significance(s)
            if sc > 0:
                scored.append((a, sc))
        scored.sort(key=lambda x: (-x[1], str(x[0].id)))
        limit = turn.budget["visible_reactions"]
        if turn.degraded("reduce_visible_reactions_to_1"):
            limit = min(limit, 1)
        visible = [(a, sc) for a, sc in scored if tier(sc) == "high"][:limit]
        silent = [(a, sc) for a, sc in scored if (a, sc) not in visible and tier(sc) != "low"]
        return visible, silent

    # -- deciding --------------------------------------------------------------------------------

    @staticmethod
    def role_for(actor: Actor) -> str:
        return "ai_player" if actor.actor_type == "pc" else "npc_actor"

    async def decide_many(
        self,
        h: CampaignHandle,
        scene: Scene,
        actors: list[Actor],
        situations: dict[uuid.UUID, str],
        turn: Turn,
        *,
        kind: str = "reaction",
        scores: dict[uuid.UUID, float] | None = None,
    ) -> list[Decision]:
        """All decisions are compiled from the same scene snapshot and generated concurrently
        (orchestration §18); nothing is applied here."""
        ctxs, metas = [], []
        for a in actors:
            if not turn.can_make_sync_call():
                turn.notes.append(f"ai decision skipped for {a.id}: call cap")
                continue
            cands = await build_candidates(self.perspective, self.actions, h, a.id, scene)
            available = await self._available_actions(h, scene, str(a.id), kind)
            ctx = await self.compiler.compile(
                h,
                self.role_for(a),
                actor_id=a.id,
                purpose=f"{kind} decision",
                situation=situations[a.id],
                extra_sections={
                    "candidates": candidates_text(cands),
                    "available_actions": available,
                },
                now_tick=scene.local_tick,
            )
            ctxs.append(ctx)
            metas.append((a, cands, ctx))
        runs = await self.runner.run_many(h, ctxs, turn_id=turn.turn_id)
        out = []
        for (a, cands, ctx), run in zip(metas, runs, strict=True):
            turn.record_call(
                self.role_for(a),
                calls=run.calls,
                prompt_tokens=run.prompt_tokens,
                completion_tokens=run.completion_tokens,
                context_tokens=ctx.estimated_tokens,
            )
            out.append(
                Decision(
                    a.id,
                    self.role_for(a),
                    run,
                    cands,
                    dict(ctx.ref_map),
                    scene.version,
                    (scores or {}).get(a.id, 0.0),
                    kind,
                )
            )
        return out

    async def _available_actions(
        self, h: CampaignHandle, scene: Scene, actor_key: str, kind: str
    ) -> str:
        rs = self.engine.ruleset
        keys = [k for k, d in rs.actions.items() if not d.reaction_trigger]
        if kind != "combat":
            keys = [k for k in keys if k not in ("action.attack", "action.engage", "action.flee")]
            keys = ["say", "whisper", *keys]
        return (
            "Action types you may intend: "
            + ", ".join(k.replace("action.", "") for k in keys)
            + ". Use target_ref from the candidate list. Intentions are proposals; the rules "
            "engine resolves them."
        )

    # -- applying --------------------------------------------------------------------------------

    async def apply(
        self,
        h: CampaignHandle,
        scene_id: uuid.UUID,
        d: Decision,
        turn: Turn,
        emit=None,
    ) -> Applied:
        emit = emit or (lambda name, payload: None)
        applied = Applied(d.actor_id, d.kind)
        out = d.output
        if out is None:
            applied.rejected = f"no valid decision ({d.run.status}: {'; '.join(d.run.errors)})"
            return applied
        scene = await self.session.get(Scene, scene_id)
        assert scene is not None
        by_ref = {c.ref: c for c in d.cands}
        stale = scene.version != d.based_on_scene_version

        # 1. speech: conveys[] authorisation, corroboration, extractor fallback, then utter
        spoken = (out.spoken_text or "").strip()
        if spoken and not self._silenced(out):
            try:
                items, notes = await self._conveys(h, d, out, spoken, by_ref, turn)
            except LeakageError as exc:
                applied.rejected = f"leakage: {exc.kind} {exc.ref_id} ({exc.reason})"
                return applied
            applied.notes += notes
            applied.claim_extractor_used = any(n.startswith("claim extractor") for n in notes)
            channel = getattr(out, "speech_channel", "say")
            if channel == "none":
                channel = "say"
            targets: list[uuid.UUID] = []
            tref = getattr(out, "speech_target_ref", None)
            if tref and tref in by_ref and by_ref[tref].kind == "actor":
                targets = [uuid.UUID(by_ref[tref].id)]
            if channel == "whisper" and not targets:
                channel = "say"
                applied.notes.append("whisper without a target downgraded to say")
            try:
                r = await self.speech.utter(
                    h,
                    scene.id,
                    d.actor_id,
                    spoken,
                    channel=channel,
                    conveys=items,
                    target_actor_ids=targets,
                    conveyance_source="structured",
                    turn_id=turn.turn_id,
                )
            except LeakageError as exc:
                applied.rejected = f"leakage: {exc.kind} {exc.ref_id} ({exc.reason})"
                return applied  # the whole proposal is rejected; nothing else is applied
            applied.spoke = True
            applied.speech_result = r
            applied.speech = {
                "actor_id": str(d.actor_id),
                "channel": channel,
                "text": spoken,
                "recipients": [str(x) for x in r.recipients],
                "claims": len(r.claims),
            }
            emit("reaction", {"actor_id": str(d.actor_id), "channel": channel})

        # 2. intentions through autonomy gates and the rules engine
        for it in out.intentions[:MAX_INTENTIONS]:
            kind = it.action_type.lower().strip().replace(" ", "_")
            if kind in SPEECH_TYPES or kind in FREE_TYPES:
                continue
            key = action_key_for(kind)
            if key is None:
                applied.notes.append(f"unknown intention {kind!r} ignored")
                continue
            profile = await self.psychology.autonomy(d.actor_id)
            g = autonomy_gate(profile, key, params={"private": it.private})
            target = self._target_id(by_ref, it.target_ref)
            if not g.execute:
                async with self._tx(h, d.actor_id) as tx:
                    await tx.emit(
                        ev.AutonomyPaused(
                            actor_id=d.actor_id,
                            domain=g.domain,
                            level=g.level,
                            action_key=key,
                            target=target,
                        )
                    )
                entry = {
                    "action": key,
                    "target": target,
                    "domain": g.domain,
                    "level": g.level,
                    "description": it.description,
                    "private": it.private,
                }
                if g.paused:
                    fresh = await self.session.get(Scene, scene.id)
                    assert fresh is not None
                    pending = list(fresh.state.get("autonomy_pending", []))
                    pending.append({**entry, "actor_id": str(d.actor_id)})
                    fresh.state = {**fresh.state, "autonomy_pending": pending}
                applied.paused.append(entry)
                continue
            outcome = await self._perform(h, scene, d, key, target, it.private, stale, turn)
            if outcome is not None:
                applied.actions.append(outcome)

        # 3. beliefs / emotions / goals / relationships (event-linked projections)
        goal_updates = list(getattr(out, "goal_updates", []))[:2]
        has_state = bool(
            out.belief_proposals
            or out.emotion_proposals
            or out.relationship_proposals
            or goal_updates
        )
        if has_state:
            await self._apply_state(h, d, out, by_ref, applied, goal_updates)

        # 4. fallback policy for later combat turns
        fp = getattr(out, "fallback_policy", None)
        if fp is not None:
            policy = FallbackPolicy(
                target=self._target_id(by_ref, fp.target_ref),
                intent=fp.intent,
                flee_below=fp.flee_below,
                protect=self._target_id(by_ref, fp.protect_ref),
                scene_version=scene.version,
            )
            await self._store_policy(scene, str(d.actor_id), policy)
        await self._note_reaction_kind(scene.id, d)
        return applied

    async def _apply_state(
        self,
        h: CampaignHandle,
        d: Decision,
        out: Any,
        by_ref: dict[str, Candidate],
        applied: Applied,
        goal_updates: list[Any],
    ) -> None:
        async with self._tx(h, d.actor_id) as tx:
            cause = applied.speech_result.event if applied.speech_result else None
            for bp in out.belief_proposals[:3]:
                prop = self._prop(bp.proposition.model_dump(), by_ref, d.ref_map)
                btype = "believed" if bp.belief_type == "known" else bp.belief_type
                conf = min(float(bp.confidence), 0.9)
                event = await tx.emit(
                    ev.BeliefFormed(
                        actor_id=d.actor_id,
                        proposition_key=prop.key,
                        belief_type=btype,
                        confidence=conf,
                        model_run_id=d.run.model_run_id,
                    )
                )
                await self.knowledge.store_belief(
                    tx,
                    d.actor_id,
                    BeliefProposal(prop, btype, conf, "self", ("ai proposal",)),
                    acquired_event=event,
                )
            for ep in out.emotion_proposals[:MAX_EMOTIONS]:
                await self.psychology.set_emotion(
                    tx, d.actor_id, ep.emotion.lower()[:32], ep.intensity, source_event=cause
                )
            for rp in out.relationship_proposals[:2]:
                c = by_ref.get(rp.target_ref)
                if c is None or c.kind != "actor" or c.entity_id is None:
                    applied.notes.append(f"relationship proposal to unknown ref {rp.target_ref!r}")
                    continue
                if rp.delta == 0:
                    continue
                await self.psychology.apply_relationship_delta(
                    tx,
                    d.actor_id,
                    c.entity_id,
                    rp.dimension,
                    rp.delta,
                    reason=rp.reason or "ai decision",
                    cause=cause,
                )
            for gu in goal_updates:
                if gu.goal_ref and gu.goal_ref in d.ref_map:
                    await self.psychology.update_goal(
                        tx,
                        d.ref_map[gu.goal_ref],
                        d.actor_id,
                        status=gu.status,
                        priority=gu.priority,
                        description=gu.description,
                        reason="ai decision",
                    )
                elif gu.description and gu.goal_ref is None:
                    await self.psychology.create_goal(
                        h,
                        d.actor_id,
                        gu.description,
                        priority=gu.priority or 50,
                        created_by_type="ai",
                        tx=tx,
                    )

    @staticmethod
    def _silenced(out: Any) -> bool:
        sa = getattr(out, "speech_act", None)
        return sa is not None and sa.type == "silence"

    def _tx(self, h: CampaignHandle, actor_id: uuid.UUID) -> EventTransaction:
        return EventTransaction(
            self.session, h.campaign_id, h.timeline_id, created_by_type="ai", created_by_id=actor_id
        )

    @staticmethod
    def _target_id(by_ref: dict[str, Candidate], ref: str | None) -> str | None:
        if not ref:
            return None
        c = by_ref.get(ref)
        return c.id if c else None

    @staticmethod
    def _prop(
        raw: dict[str, Any],
        by_ref: dict[str, Candidate],
        ref_map: dict[str, uuid.UUID],
        known: dict[str, uuid.UUID] | None = None,
    ) -> Proposition:
        out = dict(raw)
        by_actor_id = {c.id: c for c in by_ref.values() if c.kind == "actor" and c.entity_id}
        known_ids = {str(v) for v in (known or {}).values()}
        for key in ("subject_entity_id", "object_entity_id"):
            v = out.get(key)
            if not v:
                continue
            v = str(v)
            if v in by_ref and by_ref[v].entity_id is not None:
                out[key] = str(by_ref[v].entity_id)
            elif v in ref_map:
                out[key] = str(ref_map[v])
            elif known and slug(v) in known:
                out[key] = str(known[slug(v)])  # a name this actor knows, slug-spelled
            elif v in by_actor_id:
                out[key] = str(by_actor_id[v].entity_id)
            elif _is_uuid(v) and v not in known_ids:
                out[key] = None  # an id this actor was never given is not a reference
        if isinstance(out.get("predicate"), str):
            out["predicate"] = out["predicate"].replace("_", " ").strip()
        return Proposition.from_dict(out)

    async def _note_reaction_kind(self, scene_id: uuid.UUID, d: Decision) -> None:
        scene = await self.session.get(Scene, scene_id)  # re-read: earlier commits expired it
        assert scene is not None
        kinds = dict(scene.state.get("reaction_kinds", {}))
        seen = list(kinds.get(str(d.actor_id), []))
        if d.kind not in seen:
            seen.append(d.kind)
        kinds[str(d.actor_id)] = seen
        scene.state = {**scene.state, "reaction_kinds": kinds}

    async def _store_policy(self, scene: Scene, actor_key: str, policy: FallbackPolicy) -> None:
        fresh = await self.session.get(Scene, scene.id)
        assert fresh is not None
        policies = dict(fresh.state.get("fallback_policies", {}))
        policies[actor_key] = policy.to_dict()
        fresh.state = {**fresh.state, "fallback_policies": policies}

    # -- conveys[] -------------------------------------------------------------------------------

    async def _conveys(
        self,
        h: CampaignHandle,
        d: Decision,
        out: Any,
        spoken: str,
        by_ref: dict[str, Candidate],
        turn: Turn,
    ) -> tuple[list[ConveysItem], list[str]]:
        notes: list[str] = []
        names = await self.perspective.known_entities(d.actor_id)
        me = await self.perspective.repo.actor(d.actor_id)
        if me is not None and me.entity_id not in names:
            own = await self.perspective.repo.self_name(d.actor_id)
            if own:
                names = {**names, me.entity_id: own}
        lower = spoken.lower()
        known = {slug(n): eid for eid, n in names.items()}
        # the question this speech most plausibly answers: its terms count as corroboration
        question_terms: set[str] = set()
        for c in await self.perspective.heard_claims(d.actor_id, limit=6):
            if c.stance == "question":
                question_terms |= _terms(c.predicate)
                for eid in (c.subject_entity_id, c.object_entity_id):
                    if eid in names:
                        question_terms |= _terms(names[eid])
        lying = self._silenced(out) is False and (
            getattr(getattr(out, "speech_act", None), "knowingly_false", False)
            or getattr(getattr(out, "speech_act", None), "type", "") == "lie"
        )
        items: list[ConveysItem] = []
        for c in out.conveys[:MAX_CONVEYS]:
            deliberate = bool(c.contradicts_ref and c.contradicts_ref in d.ref_map)
            if c.ref_id:
                rid = d.ref_map.get(c.ref_id)
                if rid is None and _is_uuid(c.ref_id):
                    rid = uuid.UUID(c.ref_id)  # a raw id: SpeechService authorises it
                if rid is None:
                    # a short ref that was never supplied is a reference to knowledge outside the
                    # speaker's context: a leakage incident, and the whole proposal is rejected
                    kind = "belief_ref" if c.ref_id.startswith("b_") else "fact_ref"
                    await self.speech._record_leak(
                        h, d.actor_id, kind, c.ref_id, "ref not in the speaker's supplied context"
                    )
                    raise LeakageError(d.actor_id, kind, c.ref_id, "ref not in supplied context")
                kind = "belief_ref" if c.ref_id.startswith("b_") else "fact_ref"
                record = await self._record_terms(d.actor_id, kind, rid, names)
                if record is None:
                    # held by someone else, or not at all: outside the speaker's perspective
                    await self.speech._record_leak(
                        h, d.actor_id, kind, str(rid), "ref outside the speaker's perspective"
                    )
                    raise LeakageError(d.actor_id, kind, str(rid), "outside speaker perspective")
                # corroboration (c&k §2, tightened after the first live session): an
                # assertion must restate part of the record's predicate in the spoken text
                # or in the question it answers — naming the people involved is not enough,
                # or "Captain Renn's been in" would carry "Renn met Oric the night before".
                # A denial (asserts_false / contradicts_ref) rarely restates the predicate,
                # so names in the text or the question suffice for it.
                denial = c.stance == "asserts_false" or deliberate
                pred_terms, name_terms = record
                spoken_terms = _terms(lower)
                if c.stance != "question":
                    if denial:
                        ok = bool((pred_terms | name_terms) & (spoken_terms | question_terms))
                    else:
                        ok = bool(pred_terms & (spoken_terms | question_terms))
                    if not ok:
                        notes.append(
                            f"conveys ref {c.ref_id!r} not corroborated by the spoken text; dropped"
                        )
                        continue
                items.append(
                    ConveysItem(
                        kind,
                        ref_id=str(rid),
                        stance=c.stance,
                        fidelity=c.fidelity,
                        deliberate_false=deliberate or lying,
                        about_speaker_self=c.about_speaker_self,
                    )
                )
            elif c.proposition is not None and c.proposition.predicate:
                prop = self._prop(c.proposition.model_dump(), by_ref, d.ref_map, known)
                items.append(
                    ConveysItem(
                        "proposition",
                        proposition=prop.to_dict(),
                        stance=c.stance,
                        fidelity=c.fidelity,
                        deliberate_false=deliberate or lying,
                        about_speaker_self=c.about_speaker_self,
                    )
                )
        # completeness heuristic (c&k §3): phatic speech may carry nothing; otherwise a known
        # name in the text that no item references means the list is incomplete → extractor
        mentioned = {eid for eid, nm in names.items() if nm and _terms(nm) & _terms(lower)} - {
            await self._self_entity(d.actor_id)
        }
        referenced: set[str] = set()
        for it in items:
            if it.proposition:
                referenced |= {
                    str(it.proposition.get("subject_entity_id") or ""),
                    str(it.proposition.get("object_entity_id") or ""),
                }
        # with at least one item from the model, the list counts as incomplete only when
        # most of the names it mentions go unreferenced (the extractor costs a full call)
        unreferenced = [e for e in mentioned if str(e) not in referenced]
        incomplete = (
            len(unreferenced) > len(mentioned) - len(unreferenced) if items else bool(mentioned)
        )
        phatic = len(lower.split()) <= PHATIC_MAX_WORDS and not mentioned
        if (not items and not phatic) or incomplete:
            extracted = await self._claim_extractor(h, d, spoken, by_ref, turn)
            if extracted:
                notes.append(f"claim extractor added {len(extracted)} item(s)")
                items += extracted
            else:
                notes.append("claim extractor yielded nothing")
        return items, notes

    async def _self_entity(self, actor_id: uuid.UUID) -> uuid.UUID | None:
        a = await self.perspective.repo.actor(actor_id)
        return a.entity_id if a else None

    async def _record_terms(
        self, speaker: uuid.UUID, kind: str, rid: uuid.UUID, names: dict[uuid.UUID, str]
    ) -> tuple[set[str], set[str]] | None:
        """(predicate terms, entity-name terms) of a referenced belief/fact as the speaker
        would name them."""
        if kind == "belief_ref":
            b = await self.perspective.repo.holds_belief(speaker, rid)
            if b is None:
                return None
            prop = Proposition.from_dict(b.proposition)
        else:
            if not await self.perspective.repo.holds_fact(speaker, rid):
                return None
            fact = await self.session.get(Fact, rid)
            if fact is None:
                return None
            prop = KnowledgeService.proposition_of(fact)
        pred = _terms(prop.predicate)
        if prop.value is not None:
            pred |= _terms(str(prop.value))
        name_terms: set[str] = set()
        for ref in (prop.subject, prop.object):
            try:
                eid = uuid.UUID(str(ref)) if ref else None
            except ValueError:
                eid = None
            if eid in names:
                name_terms |= _terms(names[eid])
        return pred, name_terms

    async def _claim_extractor(
        self,
        h: CampaignHandle,
        d: Decision,
        spoken: str,
        by_ref: dict[str, Candidate],
        turn: Turn,
    ) -> list[ConveysItem]:
        if turn.degraded("drop_canon_extractor") and turn.at_risk(complex_turn=True):
            turn.notes.append("claim extractor skipped: budget")
            return []
        if not turn.can_make_sync_call():
            return []
        ctx = await self.compiler.compile(
            h,
            "claim_extractor",
            actor_id=d.actor_id,
            purpose="extract claims",
            situation=f'Utterance: "{spoken}"',
            extra_sections={"candidates": candidates_text(d.cands)},
        )
        res = await self.runner.run(h, ctx, turn_id=turn.turn_id)
        turn.record_call(
            "claim_extractor",
            calls=res.calls,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
            context_tokens=ctx.estimated_tokens,
        )
        turn.claim_extractor_invoked += 1
        if not res.ok or not isinstance(res.output, ClaimExtractorOut):
            return []
        items = []
        for c in res.output.conveys[:4]:
            if c.proposition is None or not c.proposition.predicate:
                continue
            prop = self._prop(c.proposition.model_dump(), by_ref, d.ref_map)
            items.append(
                ConveysItem(
                    "proposition",
                    proposition=prop.to_dict(),
                    stance=c.stance,
                    fidelity=c.fidelity,
                    about_speaker_self=c.about_speaker_self,
                )
            )
        return items

    # -- intentions ------------------------------------------------------------------------------

    async def _perform(
        self,
        h: CampaignHandle,
        scene: Scene,
        d: Decision,
        key: str,
        target: str | None,
        private: bool,
        stale: bool,
        turn: Turn,
    ) -> dict[str, Any] | None:
        actor_key = str(d.actor_id)
        loaded = await self.actions.load_scene(h, scene.id)
        ctx = loaded.ctx
        # revalidation against current state (orchestration §18, §34)
        if key in ("action.attack", "action.engage", "action.move", "action.sprint") and target:
            if target in loaded.actors:
                st = ctx.states.get(target)
                gone = (
                    st is None
                    or st.has_condition("condition.incapacitated")
                    or target not in ctx.space.positions
                )
                if gone:
                    foes = hostiles(ctx, actor_key)
                    async with self._tx(h, d.actor_id) as tx:
                        await tx.emit(
                            ev.ProposalInvalidated(
                                actor_id=d.actor_id,
                                action_key=key,
                                target=target,
                                reason="target no longer available",
                                based_on_scene_version=d.based_on_scene_version,
                                fallback_used=bool(foes),
                            )
                        )
                    if not foes:
                        return {"action": key, "target": target, "status": "invalidated"}
                    target = foes[0]
                if key in ("action.move", "action.sprint") and target in ctx.space.positions:
                    mine = ctx.space.position(actor_key).zone
                    theirs = ctx.space.position(target).zone
                    key, target = (
                        ("action.engage", target) if mine == theirs else ("action.move", theirs)
                    )
        elif key == "action.pick_up" and target:
            held = any(target == it.instance_key for its in ctx.ground.values() for it in its)
            if not held:
                async with self._tx(h, d.actor_id) as tx:
                    await tx.emit(
                        ev.ProposalInvalidated(
                            actor_id=d.actor_id,
                            action_key=key,
                            target=target,
                            reason="item no longer on the ground",
                            based_on_scene_version=d.based_on_scene_version,
                        )
                    )
                return {"action": key, "target": target, "status": "invalidated"}
        if ctx.in_combat and ctx.encounter.current_actor != actor_key:  # type: ignore[union-attr]
            return {
                "action": key,
                "target": target,
                "status": "deferred",
                "reason": "not their turn",
            }
        dims = {
            k: (a.behavior_profile or {}).get("dimensions", {}) for k, a in loaded.actors.items()
        }
        try:
            outcome = await self.actions.perform(
                h,
                scene.id,
                ActionRequest(
                    actor_key,
                    key,
                    target,
                    params={"private": True} if private else {},
                    source="ai",
                ),
                chooser=behavior_reaction_chooser(dims),
                turn_id=turn.turn_id,
            )
        except StaleStateError as exc:
            return {"action": key, "target": target, "status": "stale", "reason": str(exc)}
        except WorldError as exc:
            return {"action": key, "target": target, "status": "invalid", "reason": str(exc)}
        return {
            "action": outcome.request.action_key,
            "target": outcome.request.target,
            "status": outcome.status,
            "reason": outcome.reason,
            "private": private,
            "summary": outcome.trace.summary if outcome.trace else "",
        }

    # -- combat turns ----------------------------------------------------------------------------

    async def run_combat_turns(
        self,
        h: CampaignHandle,
        scene_id: uuid.UUID,
        turn: Turn,
        *,
        stop_at: set[uuid.UUID],
        emit=None,
        max_turns: int = 12,
    ) -> list[dict[str, Any]]:
        """Advance AI combatants in initiative order until it is a `stop_at` actor's turn, the
        encounter ends, or the cap is hit. Fallback policies replace model calls whenever the
        situation is unchanged (turn-budget §5 step 4; orchestration §19)."""
        emit = emit or (lambda name, payload: None)
        log: list[dict[str, Any]] = []
        for _ in range(max_turns):
            loaded = await self.actions.load_scene(h, scene_id)
            enc = loaded.ctx.encounter
            if enc is None or enc.status != "active":
                break
            cur = enc.current_actor
            if cur is None or uuid.UUID(cur) in stop_at:
                break
            row = loaded.actors.get(cur)
            st = loaded.ctx.states.get(cur)
            controller = await self.perspective.repo.controller_type(row.id) if row else None
            skip = (
                row is None
                or controller != "ai"
                or cur not in enc.sides
                or st is None
                or st.has_condition("condition.incapacitated")
                or st.has_condition("condition.surrendered")
            )
            if skip:
                await self.actions.next_turn(h, scene_id)
                continue
            entry = await self._combat_turn(h, loaded, row, turn, emit)
            log.append(entry)
            emit("mechanics", {"ai_turn": entry})
            after = await self.actions.load_scene(h, scene_id)
            if after.ctx.encounter and after.ctx.encounter.status == "active":
                if after.ctx.encounter.current_actor == cur:
                    await self.actions.next_turn(h, scene_id)
        return log

    async def _combat_turn(
        self, h: CampaignHandle, loaded: LoadedScene, actor: Actor, turn: Turn, emit
    ) -> dict[str, Any]:
        ctx = loaded.ctx
        key = str(actor.id)
        policies = loaded.scene.state.get("fallback_policies", {})
        policy = FallbackPolicy.from_dict(policies.get(key))
        reuse = policy is not None and (
            situation_unchanged(ctx, key, policy) or turn.degraded("use_fallback_policy_in_combat")
        )
        source = "policy"
        if not reuse and turn.can_make_sync_call():
            if turn.at_risk(complex_turn=True) and policy is not None:
                turn.degrade()  # takes the next ladder step; policy reuse is one of them
                reuse = turn.degraded("use_fallback_policy_in_combat")
        if not reuse and turn.can_make_sync_call():
            foes = hostiles(ctx, key)
            sit = (
                f"It is your turn in combat (round {ctx.encounter.round}). "  # type: ignore[union-attr]
                f"Standing hostiles: {len(foes)}. Choose one intention and a fallback_policy."
            )
            decisions = await self.decide_many(
                h, loaded.scene, [actor], {actor.id: sit}, turn, kind="combat"
            )
            d = decisions[0] if decisions else None
            if d is not None and d.output is not None:
                source = "model"
                applied = await self.apply(h, loaded.scene.id, d, turn, emit)
                fresh = await self.actions.load_scene(h, loaded.scene.id)
                policy = FallbackPolicy.from_dict(
                    fresh.scene.state.get("fallback_policies", {}).get(key)
                )
                if any(
                    a.get("status") in ("succeeded", "failed", "partial") for a in applied.actions
                ):
                    return {"actor": key, "source": source, "actions": applied.actions}
                ctx = fresh.ctx  # the model intended something unusable: fall through to tactics
            else:
                turn.notes.append(f"combat decision for {key} failed; policy used")
        if policy is None:
            policy = FallbackPolicy(intent="attack")
            source = "default_policy"
        action_key, target, reason = choose_action(ctx, key, policy)
        if action_key in ("action.attack", "action.engage") and target in hostiles(ctx, key):
            policy.target = target  # the concrete target the policy will be judged against
        policy.hp_at_decision = (
            ctx.states[key].resources["resource.health"].current
            if "resource.health" in ctx.states[key].resources
            else None
        )
        await self._store_policy(loaded.scene, key, policy)
        try:
            outcome = await self.actions.perform(
                h,
                loaded.scene.id,
                ActionRequest(key, action_key, target, source="ai"),
                chooser=behavior_reaction_chooser(
                    {
                        k: (a.behavior_profile or {}).get("dimensions", {})
                        for k, a in loaded.actors.items()
                    }
                ),
                turn_id=turn.turn_id,
            )
            status, out_reason = outcome.status, outcome.reason
        except (WorldError, StaleStateError) as exc:
            status, out_reason = "invalid", str(exc)
        return {
            "actor": key,
            "source": source,
            "actions": [
                {
                    "action": action_key,
                    "target": target,
                    "status": status,
                    "reason": out_reason or reason,
                }
            ],
        }

    # -- belief processor gating ------------------------------------------------------------------

    async def belief_processor_pass(
        self,
        h: CampaignHandle,
        scene: Scene,
        results: list[SpeechResult],
        turn: Turn,
        *,
        inline: set[uuid.UUID],
    ) -> int:
        """belief-update-rules §7: schedule a bounded Belief Processor call for AI recipients
        whose new testimony belief is goal-relevant or contradicting and lands near a type
        boundary. Returns the number scheduled; inline ones (the recipient decides this turn)
        run now, the rest are queued on the scene for downtime."""
        scheduled = 0
        for r in results:
            claim_ids = [c.id for c in r.claims]
            if not claim_ids:
                continue
            for rid in r.recipients:
                actor = await self.perspective.repo.actor(rid)
                if actor is None or await self.perspective.repo.controller_type(rid) != "ai":
                    continue
                rows = (
                    (
                        await self.session.execute(
                            select(Belief).where(
                                Belief.actor_id == rid,
                                Belief.claim_id.in_(claim_ids),
                                Belief.source_type == "told",
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for b in rows:
                    prop = Proposition.from_dict(b.proposition)
                    ents = {uuid.UUID(x) for x in (prop.subject, prop.object) if x and _is_uuid(x)}
                    existing = await self.knowledge.existing_beliefs(rid)
                    neg = prop.negated().key
                    contradicts = any(
                        e.proposition.key == neg and e.confidence >= 0.6 and e.ref.id != b.id
                        for e in existing
                    )
                    contested = sum(
                        1
                        for e in existing
                        if e.proposition.key == prop.key and e.status == "contested"
                    )
                    g = GateInput(
                        True,
                        actor.importance_tier,
                        await self.psychology.goal_relevant(rid, ents),
                        contradicts,
                        contested,
                    )
                    proposal = BeliefProposal(prop, b.belief_type, float(b.confidence), "told")
                    if not belief_processor_gate(g, proposal):
                        continue
                    scheduled += 1
                    turn.belief_processor_scheduled += 1
                    if rid in inline and turn.can_make_sync_call():
                        await self._belief_processor(h, rid, b, r, turn)
                    else:
                        q = list(scene.state.get("belief_processor_queue", []))
                        q.append({"actor_id": str(rid), "belief_id": str(b.id)})
                        scene.state = {**scene.state, "belief_processor_queue": q}
        return scheduled

    async def _belief_processor(
        self, h: CampaignHandle, actor_id: uuid.UUID, b: Belief, r: SpeechResult, turn: Turn
    ) -> None:
        names = await self.perspective.known_entities(actor_id)
        prop = Proposition.from_dict(b.proposition)
        subj = names.get(_uuid_or_none(prop.subject), prop.subject or "")
        obj = names.get(_uuid_or_none(prop.object), prop.object or "")
        speaker = await self.perspective.repo.actor(r.event.payload.get("speaker_actor_id"))
        who = names.get(speaker.entity_id, "someone") if speaker else "someone"
        ctx = await self.compiler.compile(
            h,
            "belief_processor",
            actor_id=actor_id,
            purpose="belief adjustment",
            situation=(
                f"{who} just told you: {subj} {prop.predicate} {obj}. The engine's default: "
                f"{b.belief_type} at confidence {float(b.confidence):.2f} "
                f"({'; '.join((b.metadata_ or {}).get('reasons', []))}). Adjust by at most 0.25."
            ),
        )
        res = await self.runner.run(h, ctx, turn_id=turn.turn_id)
        turn.record_call(
            "belief_processor",
            calls=res.calls,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
            context_tokens=ctx.estimated_tokens,
        )
        if not res.ok or not isinstance(res.output, BeliefProcessorOut):
            return
        out = res.output
        if not out.confidence_adjustment and not out.inferences:
            return
        async with self._tx(h, actor_id) as tx:
            if out.confidence_adjustment:
                before = float(b.confidence)
                after = rules.clamp(round(before + out.confidence_adjustment, 3), 0.05, 0.95)
                await tx.emit(
                    ev.BeliefAdjusted(
                        actor_id=actor_id,
                        belief_id=b.id,
                        confidence_before=before,
                        confidence_after=after,
                        model_run_id=res.model_run_id,
                        reason=out.reason,
                    )
                )
                b.confidence = after
                b.belief_type = rules.type_for_confidence(
                    after, secondhand=b.belief_type == "rumor"
                )
                b.metadata_ = {**(b.metadata_ or {}), "belief_processor": str(res.model_run_id)}
            for inf in out.inferences[:2]:
                p = Proposition.from_dict(inf.proposition.model_dump())
                conf = min(float(inf.confidence), 0.7)
                event = await tx.emit(
                    ev.BeliefFormed(
                        actor_id=actor_id,
                        proposition_key=p.key,
                        belief_type="inference",
                        confidence=conf,
                        model_run_id=res.model_run_id,
                    )
                )
                await self.knowledge.store_belief(
                    tx,
                    actor_id,
                    BeliefProposal(p, "inference", conf, "inference", (f"from {b.id}",)),
                    acquired_event=event,
                )


def _terms(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2 and t not in STOP}


def _is_uuid(v: str) -> bool:
    try:
        uuid.UUID(str(v))
        return True
    except ValueError:
        return False


def _uuid_or_none(v: str | None) -> uuid.UUID | None:
    return uuid.UUID(str(v)) if v and _is_uuid(v) else None
