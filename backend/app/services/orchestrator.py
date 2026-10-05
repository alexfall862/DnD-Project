"""SessionOrchestrator.process_player_input (implementation-plan §14; orchestration §2,
§9–§11, §36; api-contracts §9–§11; time-accounting §2; player-authored-canon).

Milestone 06a scope: steps 1–10 and 14–19 with the AI-actor steps (11–13) stubbed, no
narrator yet (a plain structured result is returned), budgets and `turn_metrics` from the
first commit, streaming hooks (`emit`), clarifications, player-canon policy, conversation
time bands, and the Rules Adjudicator for actions the ruleset does not cover.

    1 raw message → 2 channel (deterministic prefixes, else Intent Interpreter) → 3 compile
    intent context → 4 parse intent → 5 resolve entities (deterministic; engine-side ambiguity
    → clarification, nothing committed) → 6 actions → 7 mechanics (ActionService /
    SpeechService) → 8 adjudicate uncovered actions → 9 commit (+ player assertions) →
    10 observations → 14 bundle → 19 response + turn_metrics
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextCompiler
from app.ai.embeddings import Embedder
from app.ai.providers import ModelProvider
from app.ai.roles import AssertedFactOut, IntentInterpreterOut, RulesAdjudicatorOut
from app.ai.routing import ModelRouter
from app.ai.runner import ModelRunner
from app.config import Settings
from app.domain import events as ev
from app.engine.actions import ActionOutcome, ActionRequest
from app.engine.core import RulesEngine
from app.engine.effects import REGISTRY, EffectError, validate_step
from app.engine.ruleset import EffectStep
from app.engine.spotlight import SpotlightBudget, SpotlightLedger
from app.persistence.models import (
    Campaign,
    Event,
    Observation,
    PendingClarification,
    ResourceStateRow,
    Roll,
    Scene,
    TranscriptMessage,
)
from app.services.actions import ActionService, StaleStateError
from app.services.ai_actors import AIActorService, Happenings
from app.services.candidates import Candidate, build_candidates, candidates_text, slug
from app.services.documents import DocumentService
from app.services.events import EventTransaction
from app.services.jobs import JobQueue
from app.services.memory import MemoryService
from app.services.memory_processing import MemoryProcessingService
from app.services.narration import NarrationService
from app.services.observations import ObservationService
from app.services.perspective import PerspectiveService, UnauthorizedPerspective
from app.services.player_canon import DEFAULT_POLICY, PlayerCanonService
from app.services.scenes import SceneService
from app.services.simulation import SimulationService
from app.services.speech import ConveysItem, LeakageError, SpeechService
from app.services.turns import Turn, budget_from_settings
from app.services.vocab import (
    ACTION_MAP,
    FREE_TYPES,
    READ_TYPES,
    SOCIAL_SKILLS,
    SPEECH_TYPES,
    canonical_kind,
)
from app.services.world import CampaignHandle, WorldError, WorldService

Channel = Literal["auto", "do", "say", "whisper", "private", "ooc"]
TIME_BANDS = {"brief": 15, "normal": 45, "long": 180, "extended": 600, "none": 0}
CONVERSATION_CAP_S = 3600
PREFIXES = {
    "/do": "do",
    "/say": "say",
    "/whisper": "whisper",
    "/think": "private",
    "/private": "private",
    "/ooc": "ooc",
}
PRONOUN_RE = re.compile(
    r"\b(him|her|them|it|that one|the (?:guard|thief|man|woman|stranger|one|other))\b", re.I
)
QUOTE_RE = re.compile(r"[\"“]([^\"”]+)[\"”]")
STOP = {"a", "an", "the", "you", "have", "not", "met", "someone", "stranger"}


class NeedsClarification(Exception):
    def __init__(
        self,
        clarification_id: uuid.UUID,
        question: str,
        candidates: list[dict[str, Any]],
        original_input: str,
        reason: str = "AMBIGUOUS",
    ) -> None:
        super().__init__(question)
        self.clarification_id, self.question, self.candidates, self.original_input, self.reason = (
            clarification_id,
            question,
            candidates,
            original_input,
            reason,
        )


class StaleState(Exception):
    def __init__(self, world_version: int, scene_version: int | None) -> None:
        super().__init__("stale client state")
        self.world_version, self.scene_version = world_version, scene_version


@dataclass
class PlayRequest:
    actor_id: uuid.UUID
    text: str
    channel: Channel = "auto"
    target_actor_ids: list[uuid.UUID] = field(default_factory=list)
    known_world_version: int | None = None
    known_scene_version: int | None = None
    clarification_id: uuid.UUID | None = None
    roll_request_id: uuid.UUID | None = None  # answering a called-for check
    roll_decision: str | None = None  # "roll" | "reconsider"


@dataclass
class PlayResult:
    turn_id: uuid.UUID
    narration: str | None = None
    speakers: list[dict[str, Any]] = field(default_factory=list)
    visible_rolls: list[dict[str, Any]] = field(default_factory=list)
    mechanical_notices: list[str] = field(default_factory=list)
    state_changes: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    assertions: list[dict[str, Any]] = field(default_factory=list)
    time_advanced_seconds: int = 0
    versions: dict[str, int | None] = field(default_factory=dict)
    needs_player_input: bool = True
    metrics: dict[str, Any] = field(default_factory=dict)
    ooc: str | None = None
    channel: str = "auto"
    # engine notes for dev view only: rulings, policy decisions, generic observation lines
    # (play session 2026-10-05: "no adjudicator available" and "You attempt." reached the player)
    dev_notes: list[str] = field(default_factory=list)
    # a check the game called for, waiting on the player (manual dice): see PendingRoll
    roll_request: dict[str, Any] | None = None


def _natural(raw: Any) -> int | None:
    """The face the die showed (single-die rolls); None for pools."""
    nums: list[int] = []

    def walk(x: Any) -> None:
        if isinstance(x, bool):
            return
        if isinstance(x, int):
            nums.append(x)
        elif isinstance(x, (list, tuple)):
            for y in x:
                walk(y)
        elif isinstance(x, dict):
            for k in ("dice", "rolls", "values", "kept", "faces"):
                if k in x:
                    walk(x[k])
                    return
            for y in x.values():
                walk(y)

    walk(raw)
    return nums[0] if len(nums) == 1 else None


def narration_outcomes(result: PlayResult) -> list[str]:
    """The focus actor's own attempts as the narrator must render them: what succeeded, what
    failed, what could not be attempted at all. Engine reasons are paraphrased, never shown
    raw (the narrator never mentions rules internals)."""
    out: list[str] = []
    for a in result.actions:
        what = str(a.get("action", "")).removeprefix("action.").replace("_", " ")
        target = a.get("target")
        label = f"{what} ({target})" if target else what
        status = a.get("status")
        if status == "succeeded":
            out.append(f"{label}: succeeded")
        elif status == "failed":
            out.append(f"{label}: attempted and FAILED; it did not achieve its aim")
        elif status in ("invalid", "rejected", "cancelled"):
            reason = str(a.get("reason") or "").strip()
            out.append(
                f"{label}: did NOT happen (not possible right now"
                + (f": {reason}" if reason else "")
                + "); do not narrate it happening"
            )
        elif status:
            out.append(f"{label}: {status}")
    if not result.actions and any(
        n.startswith("(OOC) ruling rejected")
        for n in [*result.mechanical_notices, *result.dev_notes]
    ):
        out.append(
            "your attempt had no effect at all; describe only what you observe, never the attempt "
            "succeeding or revealing anything"
        )
    return out


GENERIC_NOTICES = {"You attempt.", "You say something.", "You whisper something."}

SOCIAL_STAKES = {
    "persuade": {
        "success": "They are inclined to go along with you.",
        "failure": "They are unmoved, and may be warier of you.",
        "retry": "You can try again with a better offer or a different approach.",
    },
    "deceive": {
        "success": "They believe you, for now.",
        "failure": "They doubt you, and may remember the lie.",
        "retry": "The same lie will not land twice.",
    },
    "intimidate": {
        "success": "They back down or give ground.",
        "failure": "They hold firm, and may resent it or tell someone.",
        "retry": "Pushing harder risks a fight.",
    },
    "bribe": {
        "success": "They take the money and help.",
        "failure": "They refuse, perhaps loudly.",
        "retry": "A bigger offer might work, or might insult them.",
    },
    "perform": {
        "success": "You hold the room.",
        "failure": "It falls flat.",
        "retry": "Read the room and try something else.",
    },
}


def roll_prompt(checks: list[dict[str, Any]]) -> str:
    """How the table asks for the roll, from the engine's own numbers (never the model's)."""
    parts = []
    for c in checks:
        who = f" with {c['target_known_as']}" if c.get("target_known_as") else ""
        bonus = c.get("bonus", 0)
        parts.append(
            f"This calls for a {c['label']} check{who}: {c['die']} "
            f"{'+' if bonus >= 0 else '-'} {abs(bonus)} against {c['dc']}."
        )
    return " ".join(parts)


class SessionOrchestrator:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        engine: RulesEngine,
        provider: ModelProvider,
        embedder: Embedder | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.engine = engine
        self.provider = provider
        self.world = WorldService(session)
        self.perspective = PerspectiveService(session)
        self.actions = ActionService(session, engine)
        self.speech = SpeechService(session)
        self.canon = PlayerCanonService(session)
        self.scenes = SceneService(session)
        self.documents = DocumentService(session)
        self.memory = MemoryService(session, embedder)
        self.jobs = JobQueue(session)
        self.compiler = ContextCompiler(session, memory=self.memory, engine=engine)
        self.runner = ModelRunner(session, ModelRouter(settings, provider))
        self.ai = AIActorService(
            session,
            settings,
            engine=engine,
            compiler=self.compiler,
            runner=self.runner,
            actions=self.actions,
            speech=self.speech,
            scenes=self.scenes,
        )
        self.narration = NarrationService(session, compiler=self.compiler, runner=self.runner)
        self.simulation = SimulationService(
            session, settings, engine=engine, compiler=self.compiler, runner=self.runner
        )
        self.memory_processing = MemoryProcessingService(
            session, compiler=self.compiler, runner=self.runner, memory=self.memory
        )
        from app.services.promotion import PromotionService

        self.promotion = PromotionService(
            session, compiler=self.compiler, runner=self.runner, memory=self.memory
        )

    # -- entry -------------------------------------------------------------------------------------

    async def process_player_input(
        self, h: CampaignHandle, req: PlayRequest, emit=None
    ) -> PlayResult:
        emit = emit or (lambda name, payload: None)
        self.runner.observer = emit  # model-call progress rides the turn stream
        self._ruling_cache: dict[str, dict] = {}  # rulings made this turn, by the attempt text
        campaign = await self.session.get(Campaign, h.campaign_id)
        turn = Turn(
            h, budget=budget_from_settings(self.settings, campaign.settings if campaign else None)
        )
        emit("accepted", {"turn_id": str(turn.turn_id)})
        self.current_turn_id = turn.turn_id
        result = PlayResult(turn.turn_id)
        first_scene = await self.perspective.repo.current_scene(req.actor_id)
        if first_scene is None or not self._in_combat(first_scene):
            turn.inapplicable.add("use_fallback_policy_in_combat")  # the ladder skips it
        try:
            await self.perspective.require_focus_actor(req.actor_id)
            await self._run(h, req, turn, result, emit, campaign)
        except NeedsClarification as exc:
            result.needs_player_input = True
            emit(
                "error",
                {
                    "code": "ACTION_NEEDS_CLARIFICATION",
                    "message": exc.question,
                    "clarification_id": str(exc.clarification_id),
                    "question": exc.question,
                    "candidates": exc.candidates,
                    "details": {
                        "clarification_id": str(exc.clarification_id),
                        "question": exc.question,
                        "candidates": exc.candidates,
                        "original_input": exc.original_input,
                        "reason": exc.reason,
                    },
                },
            )
            await turn.finish(self.session)
            await self.session.commit()
            raise
        except (StaleState, UnauthorizedPerspective):
            await turn.finish(self.session)
            await self.session.commit()
            raise
        except Exception as exc:
            # the turn's world changes roll back, but its audit stays: model runs, the contexts
            # they were sent, decision traces and the turn's metrics (play session 2026-10-05:
            # failed turns left no record of the call that failed)
            await self._keep_audit_after_failure(turn, exc)
            raise
        result.metrics = turn.summary()
        await turn.finish(self.session)
        await self.session.commit()
        emit(
            "complete", {"metrics": result.metrics, "needs_player_input": result.needs_player_input}
        )
        return result

    async def _ooc_answer(
        self, h: CampaignHandle, req: PlayRequest, text: str, scene: Scene, turn: Turn
    ) -> str:
        """An out-of-character question answered from the focus character's perspective by
        the table assistant (play session 2026-10-05: OOC was "noted" and never reached the
        model). No events: nothing in the world happens."""
        rs = self.engine.ruleset
        rules = (
            "Attributes: "
            + ", ".join(d.name for d in rs.attributes.values())
            + ". Skills: "
            + ", ".join(d.name for d in rs.skills.values())
            + ". Checks roll 1d20 + attribute + skill against a difficulty: "
            + ", ".join(f"{k} {v}" for k, v in rs.manifest.difficulty_scale.items())
            + "."
        )
        log = await self._scene_log(req.actor_id, scene, limit=6)
        ctx = await self.compiler.compile(
            h,
            "table_assistant",
            actor_id=req.actor_id,
            purpose="answer an out-of-character question",
            situation=f'The player asks (out of character): "{text}"',
            extra_sections={
                "rules_public": rules,
                **({"recent_turns": "This scene so far:\n- " + "\n- ".join(log)} if log else {}),
            },
        )
        res = await self.runner.run(h, ctx, turn_id=turn.turn_id)
        turn.record_call(
            "table_assistant",
            calls=res.calls,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
            context_tokens=ctx.estimated_tokens,
        )
        answer = (res.text or "").strip() if res.status in ("ok", "repaired") else ""
        return answer or "The table could not answer that just now; try asking again."

    async def _scene_log(
        self, actor_id: uuid.UUID, scene: Scene | None, *, limit: int = 6
    ) -> list[str]:
        """This scene so far, as this player saw it (app/services/scene_log.py)."""
        from app.services.scene_log import render_turns, scene_turns

        if scene is None:
            scene = await self.perspective.repo.current_scene(actor_id)
        view = await self.perspective.scene_view(actor_id)
        names = {str(p.actor_id): p.known_as for p in (view.participants if view else [])}
        me = await self.perspective.repo.self_name(actor_id) or "You"
        turns = await scene_turns(self.session, actor_id, scene, limit=limit)
        return render_turns(turns, player_name=me, names=names)

    async def _keep_audit_after_failure(self, turn: Turn, exc: Exception) -> None:
        """The turn's world changes roll back; its audit stays: model runs, the contexts they
        were sent (snapshots and items) and decision traces (play session 2026-10-05: failed
        turns left no record of the call that failed). The rows are read back inside the
        still-open transaction, then written again after the rollback."""
        import logging

        from app.persistence.models import ContextItem, ContextSnapshot, DecisionTrace, ModelRun

        def cols(obj, cls) -> dict:
            return {c.key: getattr(obj, c.key) for c in cls.__table__.columns}

        kept: list[tuple[type, dict]] = []
        try:
            await self.session.flush()
            runs = (
                (
                    await self.session.execute(
                        select(ModelRun).where(ModelRun.turn_id == turn.turn_id)
                    )
                )
                .scalars()
                .all()
            )
            snap_ids = {r.context_snapshot_id for r in runs if r.context_snapshot_id}
            snaps = (
                (
                    await self.session.execute(
                        select(ContextSnapshot).where(ContextSnapshot.id.in_(snap_ids))
                    )
                )
                .scalars()
                .all()
                if snap_ids
                else []
            )
            items = (
                (
                    await self.session.execute(
                        select(ContextItem).where(ContextItem.snapshot_id.in_(snap_ids))
                    )
                )
                .scalars()
                .all()
                if snap_ids
                else []
            )
            traces = (
                (
                    await self.session.execute(
                        select(DecisionTrace).where(
                            DecisionTrace.model_run_id.in_([r.id for r in runs])
                        )
                    )
                )
                .scalars()
                .all()
                if runs
                else []
            )
            for cls, rows in (
                (ContextSnapshot, snaps),
                (ContextItem, items),
                (ModelRun, runs),
                (DecisionTrace, traces),
            ):
                kept += [(cls, cols(r, cls)) for r in rows]
        except Exception:  # noqa: BLE001 - the session may be unusable after the failure
            logging.getLogger(__name__).exception("could not read the failed turn's audit")
        await self.session.rollback()
        # parents before children: snapshots, their items, the runs, then decision traces
        for cls in (ContextSnapshot, ContextItem, ModelRun, DecisionTrace):
            for kcls, data in kept:
                if kcls is not cls:
                    continue
                if cls is ModelRun and data.get("status") == "pending":
                    data["status"] = "failed"
                    data["error"] = data.get("error") or f"turn failed: {type(exc).__name__}"
                self.session.add(cls(**data))
            try:
                await self.session.flush()
            except Exception:  # noqa: BLE001 - a row tied to rolled-back state cannot return
                logging.getLogger(__name__).exception("audit rows %s not kept", cls.__name__)
                await self.session.rollback()
                break
        turn.notes.append(f"turn failed: {type(exc).__name__}: {str(exc)[:300]}")
        await turn.finish(self.session)
        try:
            await self.session.commit()
        except Exception:  # noqa: BLE001 - never mask the original failure
            logging.getLogger(__name__).exception("could not keep the failed turn's audit")
            await self.session.rollback()

    # -- the turn ------------------------------------------------------------------------------

    async def _run(
        self,
        h: CampaignHandle,
        req: PlayRequest,
        turn: Turn,
        result: PlayResult,
        emit,
        campaign: Campaign | None,
    ) -> None:
        scene = await self.perspective.repo.current_scene(req.actor_id)
        if scene is None:
            raise WorldError("actor is not in an active scene")
        if req.known_scene_version is not None and req.known_scene_version > scene.version:
            raise StaleState(campaign.world_version if campaign else 0, scene.version)
        seq_start = await self._last_sequence(h)
        hp_before = await self._resources(req.actor_id)
        tick_start = (await self.world.clock(h)).current_tick

        # 1–2: raw text, channel prefix, pending clarification
        text, channel = self._parse_prefix(req.text, req.channel)
        pending = await self._open_clarification(req.actor_id)
        forced_target: str | None = None
        if req.clarification_id is not None:
            if pending is None or pending.clarification_id != req.clarification_id:
                raise WorldError("no such open clarification")
            forced_target = self._answer_clarification(pending, text)  # candidate id
            if forced_target is None:
                raise NeedsClarification(
                    pending.clarification_id,
                    pending.question,
                    pending.candidate_entity_ids,
                    pending.original_input,
                    pending.reason,
                )
            pending.status = "answered"
            text, channel = self._parse_prefix(pending.original_input, "auto")
        elif pending is not None:
            pending.status = "cancelled"  # an unrelated input cancels it
        resume = None
        if req.roll_request_id is not None:
            from app.persistence.models import PendingRoll

            resume = await self.session.get(PendingRoll, req.roll_request_id)
            if resume is None or resume.actor_id != req.actor_id or resume.status != "open":
                raise WorldError("no such open roll request")
            if req.roll_decision == "reconsider":
                resume.status = "reconsidered"
                result.channel = "ooc"
                result.ooc = "You hold off. Nothing happens; try a different approach."
                result.versions = await self._versions(h, scene)
                return
            resume.status = "rolled"
            text, channel = resume.original_input, resume.channel
            req.target_actor_ids = [uuid.UUID(x) for x in resume.target_actor_ids]
            self._ruling_cache = dict(resume.rulings or {})
            result.dev_notes.append(f"rolling for request {resume.id}: interpretation reused")
        else:
            # an unanswered roll request lapses when the player does something else
            from app.persistence.models import PendingRoll

            for stale in (
                (
                    await self.session.execute(
                        select(PendingRoll).where(
                            PendingRoll.actor_id == req.actor_id, PendingRoll.status == "open"
                        )
                    )
                )
                .scalars()
                .all()
            ):
                stale.status = "lapsed"
        result.channel = channel
        channel_in = channel

        if channel == "ooc":
            emit("stage", {"stage": "ooc", "label": "Asking the table"})
            result.ooc = await self._ooc_answer(h, req, text, scene, turn)
            result.versions = await self._versions(h, scene)
            return
        if channel == "private":
            self.session.add(
                TranscriptMessage(
                    campaign_id=h.campaign_id,
                    timeline_id=h.timeline_id,
                    scene_id=scene.id,
                    speaker_actor_id=req.actor_id,
                    channel="private",
                    raw_text=text,
                    game_tick=scene.local_tick,
                    source="human",
                    turn_id=turn.turn_id,
                )
            )
            result.mechanical_notices.append("(private) noted")
            result.versions = await self._versions(h, scene)
            return

        # 3–4: intent context + Intent Interpreter
        hap = Happenings(req.actor_id, in_combat=self._in_combat(scene))
        candidates = await self._candidates(h, req.actor_id, scene)
        explicit_speech = channel in ("say", "whisper")  # /say, /whisper or request channel
        emit("stage", {"stage": "interpreting", "label": "Reading what you do"})
        if resume is not None:
            from app.ai.roles import IntentInterpreterOut

            intent = IntentInterpreterOut.model_validate(resume.intent)
        else:
            intent = await self._interpret(h, req, text, channel, candidates, turn)
        emit("stage", {"stage": "resolving", "label": "Resolving actions"})
        if channel == "auto":
            channel = intent.channel
            result.channel = channel
            if channel in ("say", "whisper") and intent.asserted_facts:
                # interpreted as speech: what the character says becomes Claims, not canon
                # assertions (A9 slice: "Tomas, we found Oric's ledger…" cost three rulings)
                turn.notes.append(
                    f"{len(intent.asserted_facts)} asserted fact(s) ignored in speech"
                )
                intent.asserted_facts = []
        if explicit_speech:
            # the text IS the utterance: what it says becomes Claims through conveys[], never
            # canon assertions or actions (player-authored-canon applies to deeds, not dialogue)
            if intent.asserted_facts:
                turn.notes.append(
                    f"{len(intent.asserted_facts)} asserted fact(s) ignored in explicit speech"
                )
                intent.asserted_facts = []
            kept = [
                it
                for it in intent.intents
                if it.action_type.lower().replace(" ", "_") in SPEECH_TYPES
            ]
            if len(kept) != len(intent.intents):
                turn.notes.append("non-speech intents ignored in explicit speech")
            intent.intents = kept
        if channel == "ooc":
            emit("stage", {"stage": "ooc", "label": "Asking the table"})
            result.ooc = await self._ooc_answer(h, req, text, scene, turn)
            result.versions = await self._versions(h, scene)
            return

        # 5: entity resolution + engine-side ambiguity. The model's own requires_clarification
        # is advisory only (orchestration §10; 04b): GLM flags unambiguous inputs. The engine
        # decides from the candidates.
        if intent.requires_clarification:
            turn.notes.append(
                f"model requested clarification (ignored): {intent.clarification_question!r}"
            )
        resolved = self._resolve_targets(intent, candidates, text, forced_target)
        turn.notes.extend(item["note"] for item in resolved if item.get("note"))
        for item in resolved:
            if item["ambiguous"]:
                await self._raise_clarification(
                    h, req, scene, text, f"Which {item['kind']} do you mean?", item["options"], turn
                )

        # dice (manual): a check the game calls for pauses here, before anything happens
        dice_mode = ((campaign.settings or {}).get("dice_mode") if campaign else None) or getattr(
            self.settings, "dice_mode_default", "manual"
        )
        if resume is None and dice_mode == "manual":
            checks = await self._preflight_checks(h, req, scene, resolved, channel, text, turn)
            if checks:
                from app.persistence.models import PendingRoll

                pr = PendingRoll(
                    campaign_id=h.campaign_id,
                    actor_id=req.actor_id,
                    turn_id=turn.turn_id,
                    original_input=text,
                    channel=channel_in,
                    target_actor_ids=[str(x) for x in req.target_actor_ids],
                    intent=intent.model_dump(),
                    rulings=dict(self._ruling_cache),
                    checks=checks,
                )
                self.session.add(pr)
                await self.session.flush()
                result.roll_request = {
                    "id": str(pr.id),
                    "checks": checks,
                    "prompt": roll_prompt(checks),
                }
                result.needs_player_input = True
                emit("roll_request", result.roll_request)
                result.versions = await self._versions(h, scene)
                return

        # 9 (part): player assertions, per policy
        policy = (
            campaign.settings.get("player_canon_policy") if campaign else None
        ) or DEFAULT_POLICY
        rulings_left = [1]  # one assertion ruling per turn (each is a full model call)

        async def adjudicate_once(assertion):
            if not rulings_left[0]:
                turn.notes.append("assertion not adjudicated: one ruling per turn")
                return None
            rulings_left[0] -= 1
            return await self._adjudicate_assertion(h, req.actor_id, assertion, turn)

        for a in intent.asserted_facts:
            outcome = await self.canon.handle(
                h,
                req.actor_id,
                a,
                policy=policy,
                scene_id=scene.id,
                auto_accepts_so_far=int(scene.state.get("player_assertions_accepted", 0)),
                adjudicate=adjudicate_once,
                location_id=scene.location_id,
            )
            result.assertions.append(
                {
                    "proposition": outcome.proposition,
                    "class": outcome.class_,
                    "decision": outcome.decision,
                    "result": outcome.result,
                    "note": outcome.note,
                }
            )
            if outcome.result in ("accepted", "adjudicated_accepted"):
                scene.state = {
                    **scene.state,
                    "player_assertions_accepted": int(
                        scene.state.get("player_assertions_accepted", 0)
                    )
                    + 1,
                }
            else:
                result.dev_notes.append(f"assertion {outcome.result}: {outcome.note}")

        # a player action that names latent decoration establishes it (canon allowlist §2)
        if channel == "do":
            promoted = await self.narration.establish_referenced(h, scene, text)
            if promoted:
                turn.extra["canon_established"] = promoted

        # 6–8: actions in order; a failed/interrupted step stops the chain
        spoke = False
        last_action: str | None = None
        social_done: set[str] = set()
        for step in resolved:
            # an earlier step may have moved the actor (travel): act where they are now
            # (A9 replay: a later improvised step ran in the old scene and crashed the turn)
            scene = await self.perspective.repo.current_scene(req.actor_id) or scene
            kind = canonical_kind(step["intent"].action_type, channel)
            if kind != step["intent"].action_type.lower().replace(" ", "_"):
                turn.notes.append(f"action type {step['intent'].action_type!r} read as {kind!r}")
            if kind in SOCIAL_SKILLS:
                # spoken to the target, and how well it lands is the engine's roll
                if not spoke:
                    spoke = await self._speak(
                        h,
                        req,
                        scene,
                        text,
                        channel if channel in ("say", "whisper") else "say",
                        intent,
                        step,
                        candidates,
                        turn,
                        result,
                        emit,
                        hap,
                    )
                target = step["candidate"].id if step["candidate"] is not None else ""
                if f"{kind}:{target}" not in social_done:
                    social_done.add(f"{kind}:{target}")
                    await self._social(h, req, scene, kind, step, turn, result, emit, hap, text)
                continue
            if kind in SPEECH_TYPES or (
                channel in ("say", "whisper") and kind in ("say", "whisper", "talk")
            ):
                if spoke:
                    # one utterance per turn, however many speech intents describe it (A9
                    # replay: "Excuse me, merchant!" was spoken three times); later listeners
                    # are addressed by it already when the speech named them
                    if step["candidate"] is not None and step["candidate"].kind == "actor":
                        hap.addressed.add(uuid.UUID(step["candidate"].id))
                    continue
                spoke = (
                    await self._speak(
                        h,
                        req,
                        scene,
                        text,
                        channel,
                        intent,
                        step,
                        candidates,
                        turn,
                        result,
                        emit,
                        hap,
                    )
                    or spoke
                )
                continue
            if kind in FREE_TYPES:
                result.mechanical_notices.append(f"You {kind}.")
                continue
            outcome = await self._act(
                h, req, scene, kind, step, candidates, turn, result, emit, text
            )
            if outcome is not None and outcome.status != "invalid":
                last_action = outcome.request.action_key
                if outcome.request.target and outcome.request.action_key == "action.attack":
                    hap.attacked.add(uuid.UUID(outcome.request.target))
            if outcome is not None and outcome.status in ("failed", "interrupted", "invalid"):
                break
        if not spoke and channel in ("say", "whisper") and (not resolved or explicit_speech):
            spoke = await self._speak(
                h, req, scene, text, channel, intent, None, candidates, turn, result, emit, hap
            )
        moved = await self.perspective.repo.current_scene(req.actor_id)
        if moved is None:
            raise WorldError("actor left every scene")
        if moved.id != scene.id:
            scene = moved  # the destination is now the live scene
            hap.in_combat = self._in_combat(scene)

        # conversation time (time-accounting §2)
        if spoke:
            result.time_advanced_seconds += await self._conversation_time(
                h, scene, intent.conversation_time_band
            )

        # 11–13: AI actors — reactions in social scenes, initiative turns in combat
        await self.session.flush()
        # background extras the player keeps engaging become living characters (and answer
        # this very turn); play session 2026-10-05
        engaged = set(hap.addressed) | set(hap.social) | set(hap.attacked)
        if engaged and not hap.in_combat:
            fresh_scene = await self.session.get(Scene, scene.id)
            for aid in await self.promotion.note_engagement(fresh_scene, engaged):
                emit("stage", {"stage": "promoting", "label": "Someone comes to life"})
                result.dev_notes.append(
                    await self.promotion.promote(
                        h, aid, focus_actor_id=req.actor_id, scene=fresh_scene, turn=turn
                    )
                )
        await self._reset_spotlight(scene)
        emit("stage", {"stage": "reactions", "label": "Others respond"})
        if hap.in_combat:
            await self._ai_combat(h, req, scene, turn, result, emit, last_action)
        else:
            await self._ai_reactions(h, req, scene, hap, turn, result, emit)

        # 13b: offscreen scenes catch up (bounded), without anything reaching the human
        await self._catch_up_offscreen(h, turn, result)

        # 13c: the world moves when enough time passed, or when the player waited/rested
        # (time-accounting §6; orchestration §25): one bounded simulation run
        tick_now = (await self.world.clock(h)).current_tick
        if tick_now > tick_start and (
            self.simulation.crosses_boundary(tick_start, tick_now)
            or last_action in ("action.wait", "action.short_rest", "action.long_rest")
        ):
            run = await self.simulation.tick(h, from_tick=tick_start, to_tick=tick_now, turn=turn)
            turn.extra["simulation"] = run.to_dict()

        # 14: bundle the turn as the focus actor perceived it
        await self.session.flush()
        events = await self._events_since(h, seq_start)
        result.visible_rolls = await self._visible_rolls(events)
        for n in await self._notices(req.actor_id, events):
            # bare renderings of the player's own act carry nothing the player didn't do
            (result.dev_notes if n in GENERIC_NOTICES else result.mechanical_notices).append(n)
        result.state_changes = await self._state_changes(req.actor_id, hp_before)
        result.versions = await self._versions(h, scene)
        turn.mark_first_output()
        emit(
            "mechanics",
            {
                "visible_rolls": result.visible_rolls,
                "state_changes": result.state_changes,
                "versions": result.versions,
            },
        )

        # 15–17: narrator (streamed), canon pass, checkpoints
        emit("stage", {"stage": "narrating", "label": "Narrating"})
        await self._narrate(h, req, scene, events, text, turn, result, emit, campaign)
        emit("stage", {"stage": "wrapping_up", "label": "Updating memories and canon"})
        await self._checkpoints(h, req, scene, events, turn)

    # -- channel / clarification ----------------------------------------------------------------

    @staticmethod
    def _parse_prefix(text: str, channel: str) -> tuple[str, str]:
        t = text.strip()
        for prefix, ch in PREFIXES.items():
            if t.lower().startswith(prefix + " ") or t.lower() == prefix:
                return t[len(prefix) :].strip(), ch
        return t, channel

    async def _open_clarification(self, actor_id: uuid.UUID) -> PendingClarification | None:
        return (
            await self.session.execute(
                select(PendingClarification).where(
                    PendingClarification.actor_id == actor_id, PendingClarification.status == "open"
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    def _answer_clarification(pending: PendingClarification, answer: str) -> str | None:
        """Map a free-text answer to one stored candidate's id: exact ref, then exact name, then
        an ordinal ("the second one", "2nd", "2"), then a name mentioned in the answer. The id is
        returned rather than the ref because refs are recomputed from scene order each turn."""
        a = answer.lower().strip()
        cands = pending.candidate_entity_ids
        for c in cands:
            if a == c["ref"] or a == c["known_as"].lower() or a.replace(" ", "_") == c["ref"]:
                return c["id"]
        ordinals = {
            "first": 1,
            "second": 2,
            "third": 3,
            "fourth": 4,
            "1st": 1,
            "2nd": 2,
            "3rd": 3,
            "4th": 4,
        }
        for word, n in ordinals.items():
            if re.search("(?<![a-z0-9])" + word + "(?![a-z0-9])", a) and n <= len(cands):
                return cands[n - 1]["id"]
        digits = re.findall("[0-9]+", a)
        if digits and 1 <= int(digits[0]) <= len(cands):
            return cands[int(digits[0]) - 1]["id"]
        # a candidate's ref or name inside the answer; longest match wins (a_thief_2 over a_thief)
        hits = [c for c in cands if c["ref"] in a.replace(" ", "_") or c["known_as"].lower() in a]
        if len(hits) == 1:
            return hits[0]["id"]
        if hits:
            return max(hits, key=lambda c: len(c["ref"]))["id"]
        return None

    async def _raise_clarification(
        self,
        h: CampaignHandle,
        req: PlayRequest,
        scene: Scene,
        text: str,
        question: str,
        options: list[Any],
        turn: Turn,
    ) -> None:
        cands = [
            o
            if isinstance(o, dict)
            else {"ref": o.ref, "kind": o.kind, "id": o.id, "known_as": o.known_as}
            for o in options
        ]
        row = PendingClarification(
            campaign_id=h.campaign_id,
            scene_id=scene.id,
            actor_id=req.actor_id,
            clarification_id=uuid.uuid4(),
            original_input=text,
            question=question,
            candidate_entity_ids=cands,
            reason="AMBIGUOUS",
        )
        self.session.add(row)
        await self.session.flush()
        raise NeedsClarification(row.clarification_id, question, cands, text)

    # -- candidates / resolution ----------------------------------------------------------------

    async def _candidates(
        self, h: CampaignHandle, actor_id: uuid.UUID, scene: Scene
    ) -> list[Candidate]:
        return await build_candidates(self.perspective, self.actions, h, actor_id, scene)

    @staticmethod
    def _candidates_text(cands: list[Candidate]) -> str:
        return candidates_text(cands)

    @staticmethod
    def _in_combat(scene: Scene) -> bool:
        enc = scene.state.get("encounter") or {}
        return enc.get("status") == "active"

    # -- AI actors (06b) ------------------------------------------------------------------------

    async def _reset_spotlight(self, scene: Scene) -> None:
        """Player input always has priority: the governor's counters restart here."""
        fresh = await self.session.get(Scene, scene.id)
        if fresh is not None:
            fresh.state = {**fresh.state, "spotlight": SpotlightLedger().to_dict()}

    async def _narrate(
        self,
        h: CampaignHandle,
        req: PlayRequest,
        scene: Scene,
        events: list[Event],
        text: str,
        turn: Turn,
        result: PlayResult,
        emit,
        campaign: Campaign | None,
    ) -> None:
        settings = campaign.settings if campaign else {}
        if not self.settings.narrator_enabled or settings.get("narrator") == "off":
            return
        complex_turn = bool(result.speakers) or bool(turn.extra.get("ai_combat_turns"))
        if turn.at_risk(complex_turn=complex_turn):
            step = turn.degrade()  # takes the next ladder step; the narrator steps come last
            while step is not None and step not in ("short_narrator_prompt", "skip_narrator"):
                if turn.elapsed_ms > turn.budget["first_narration_hard_ms"] * 0.9:
                    step = turn.degrade()
                else:
                    break
        if turn.degraded("skip_narrator") or not turn.can_make_sync_call():
            turn.notes.append("narrator skipped: budget")
            return
        fresh = await self.session.get(Scene, scene.id)
        ledger = SpotlightLedger.from_dict((fresh.state if fresh else {}).get("spotlight"))
        compressed = (
            [f"{len(ledger.compressed)} other(s) present react quietly without speaking up."]
            if ledger.compressed
            else []
        )
        bundle = await self.narration.bundle(
            req.actor_id,
            events,
            own_input=text,
            visible_rolls=result.visible_rolls,
            state_changes=result.state_changes,
            style=settings.get("narration_style"),
            short=turn.degraded("short_narrator_prompt"),
            compressed=compressed,
            outcomes=narration_outcomes(result),
            recent=await self._scene_log(req.actor_id, scene),
        )
        try:
            narration, _run = await self.narration.narrate(h, bundle, turn, emit)
        except Exception as exc:  # noqa: BLE001 - narration is presentation; never lose the turn
            turn.notes.append(f"narrator error: {type(exc).__name__}: {exc}")
            narration = None
        result.narration = narration
        if narration:
            # narration may only quote what was actually said this turn (dev check; the
            # prompt forbids it; play session 2026-10-05 had Tomas "agree" to a deal)
            spoken = " ".join(bundle.dialogue).lower()
            for q in re.findall(r'["“]([^"”]{12,})["”]', narration):
                if q.strip().lower()[:40] not in spoken:
                    result.dev_notes.append(f"narration quoted words nobody said: {q[:120]!r}")
        if narration and not turn.degraded("drop_canon_extractor") and fresh is not None:
            if turn.at_risk(complex_turn=True):
                turn.degrade()
            if not turn.degraded("drop_canon_extractor"):
                turn.extra["canon"] = await self.narration.extract_canon(
                    h, fresh, req.actor_id, narration, turn
                )

    async def _checkpoints(
        self,
        h: CampaignHandle,
        req: PlayRequest,
        scene: Scene,
        events: list[Event],
        turn: Turn,
    ) -> None:
        """Memory processing at checkpoints (orchestration §23): combat end and rest this turn.
        Scene end is `end_scene`. Ladder step 2 defers it to the next checkpoint."""
        types = {e.event_type for e in events}
        reason = None
        if "encounter.ended" in types:
            reason = "combat_end"
        elif any(
            e.event_type == "action.resolved"
            and e.payload.get("action") in ("action.short_rest", "action.long_rest")
            for e in events
        ):
            reason = "rest"
        if reason is None:
            return
        fresh = await self.session.get(Scene, scene.id)
        if turn.at_risk(complex_turn=True) and not turn.degraded("defer_memory_processing"):
            while True:
                step = turn.degrade()
                if step in (None, "defer_memory_processing"):
                    break
        defer = turn.degraded("defer_memory_processing")
        results = []
        created = 0
        for a in await self.ai.ai_participants(scene):
            r = await self.memory_processing.checkpoint(
                h, a.id, reason=reason, turn=turn, scene=fresh, defer=defer
            )
            results.append(r.__dict__ | {"actor_id": str(r.actor_id)})
            created += r.memories_created
            if r.deferred:
                # the worker finishes what the turn budget could not (orchestration §37)
                await self.jobs.enqueue(
                    "memory.process",
                    campaign_id=h.campaign_id,
                    timeline_id=h.timeline_id,
                    subject_id=a.id,
                    payload={"scene_id": str(scene.id), "reason": reason},
                )
        if not defer:
            await self.memory_processing.write_journal(h, req.actor_id, turn=turn, scene=fresh)
        elif any(r.get("deferred") for r in results):
            await self.jobs.enqueue(
                "journal.update",
                campaign_id=h.campaign_id,
                timeline_id=h.timeline_id,
                subject_id=req.actor_id,
                payload={"scene_id": str(scene.id), "entry_type": "scene"},
            )
        if created and self.memory.embedder is not None:
            await self.jobs.enqueue(
                "memory.embedding", campaign_id=h.campaign_id, timeline_id=h.timeline_id
            )
        turn.extra["checkpoints"] = results

    async def end_scene(
        self, h: CampaignHandle, scene_id: uuid.UUID, *, emit=None
    ) -> dict[str, Any]:
        """Scene end is the main memory checkpoint: every AI participant's Memory Processor,
        the human's Journal Writer, then the scene is closed (one turn record)."""
        campaign = await self.session.get(Campaign, h.campaign_id)
        turn = Turn(
            h, budget=budget_from_settings(self.settings, campaign.settings if campaign else None)
        )
        scene = await self.session.get(Scene, scene_id)
        if scene is None:
            raise WorldError("scene not found")
        results = []
        humans = []
        for a, _e in await self.perspective.repo.scene_participants(scene.id):
            ctype = await self.perspective.repo.controller_type(a.id)
            if ctype == "ai":
                r = await self.memory_processing.checkpoint(
                    h, a.id, reason="scene_end", turn=turn, scene=scene
                )
                results.append(r.__dict__ | {"actor_id": str(r.actor_id)})
            elif ctype == "human":
                humans.append(a.id)
        journals = []
        for actor_id in humans:
            entry = await self.memory_processing.write_journal(
                h, actor_id, turn=turn, scene=scene, entry_type="scene"
            )
            if entry is not None:
                journals.append(str(entry.id))
        await self.world.end_scene(h, scene_id)
        turn.extra["checkpoints"] = results
        turn.extra["journals"] = journals
        await turn.finish(self.session)
        await self.session.commit()
        return turn.summary()

    async def _reaction_situation(self, actor_id: uuid.UUID, hap: Happenings) -> str:
        """How this actor was addressed and who else heard, from the actor's own perspective
        (A9 slice: a whispered question reached Mira as "something happened", so she could not
        tell it from a public one and evaded as if the captain were listening)."""
        generic = (
            "Something just happened in the scene that concerns you (see your observations "
            "and heard dialogue). React as your character: speak, act, or do nothing."
        )
        view = await self.perspective.scene_view(actor_id)
        if view is None or not hap.speech_results:
            return generic
        by_actor = {str(p.actor_id): p.known_as for p in view.participants if p.actor_id}
        lines: list[str] = []
        for r in hap.speech_results:
            pl = r.event.payload
            if actor_id not in r.recipients:
                continue
            speaker = by_actor.get(str(pl.get("speaker_actor_id")), "someone")
            heard = {str(x) for x in r.recipients} | {str(pl.get("speaker_actor_id"))}
            others = [n for aid, n in by_actor.items() if aid not in heard and aid != str(actor_id)]
            if pl.get("channel") == "whisper":
                line = f"{speaker} just whispered to you; only you heard it."
                if others:
                    line += (
                        f" Also present, and they did NOT hear it: {', '.join(others)}. "
                        "Whisper back if they must not hear your answer."
                    )
            else:
                line = f"{speaker} just spoke aloud."
                if others:
                    line += f" Everyone present heard it, including {', '.join(others)}."
                line += " Anything you say aloud, they will hear too."
            lines.append(line)
        if actor_id in hap.social:
            label, convincing, margin = hap.social[actor_id]
            lines.append(
                f"They are making a {label} attempt on you. The engine's roll says it was "
                + (
                    "convincing" + (" — very" if margin >= 5 else "")
                    if convincing
                    else "unconvincing" + (" — badly" if margin <= -5 else "")
                )
                + ". Let that shape your answer: a convincing appeal should move you, an "
                "unconvincing one should not, within what your character would ever do."
            )
        if not lines:
            return generic
        return (
            " ".join(lines)
            + " React as your character (see your heard dialogue): speak, act, or do nothing."
        )

    async def _ai_reactions(
        self,
        h: CampaignHandle,
        req: PlayRequest,
        scene: Scene,
        hap: Happenings,
        turn: Turn,
        result: PlayResult,
        emit,
    ) -> None:
        fresh = await self.session.get(Scene, scene.id)
        assert fresh is not None
        visible, silent = await self.ai.select_reactions(fresh, hap, turn)
        for a, sc in silent:
            turn.notes.append(f"silent reaction: {a.id} significance {sc}")
        if hap.speech_results:
            await self.ai.belief_processor_pass(
                h, fresh, hap.speech_results, turn, inline={a.id for a, _ in visible}
            )
        if not visible:
            turn.extra["reactions"] = {"visible": 0, "silent": len(silent)}
            return
        if turn.at_risk(complex_turn=True) and len(visible) > 1:
            step = turn.degrade()
            while step is not None and step != "reduce_visible_reactions_to_1":
                step = turn.degrade()
            visible = visible[:1]
        situations = {a.id: await self._reaction_situation(a.id, hap) for a, _ in visible}
        decisions = await self.ai.decide_many(
            h,
            fresh,
            [a for a, _ in visible],
            situations,
            turn,
            scores={a.id: sc for a, sc in visible},
        )
        budget = SpotlightBudget.from_settings(
            (await self.session.get(Campaign, h.campaign_id)).settings  # type: ignore[union-attr]
        )
        applied_all = await self._apply_wave(
            h, req, scene, decisions, turn, result, emit, budget, ai_to_ai=False
        )
        # a bounded second wave: AI speech that addresses another AI actor (orchestration §13)
        second = Happenings(req.actor_id, in_combat=False)
        spoke_ids: set[uuid.UUID] = set()
        for a in applied_all:
            if a.speech_result is not None:
                second.speech_results.append(a.speech_result)
                second.informed |= set(a.speech_result.recipients)
                spoke_ids.add(a.actor_id)
                second.acting_actor = a.actor_id
        wave2: list[Any] = []
        fresh = await self.session.get(Scene, scene.id)
        ledger = SpotlightLedger.from_dict(fresh.state.get("spotlight") if fresh else None)
        if (
            second.speech_results
            and ledger.allows_ai_to_ai(budget)
            and not turn.at_risk(complex_turn=True)
        ):
            visible2, silent2 = await self.ai.select_reactions(fresh, second, turn)
            visible2 = [(a, sc) for a, sc in visible2 if a.id not in spoke_ids][:1]
            for a, sc in [(a, sc) for a, sc in silent2 if a.id not in spoke_ids]:
                turn.notes.append(f"silent reaction (wave 2): {a.id} significance {sc}")
            if visible2:
                decisions2 = await self.ai.decide_many(
                    h,
                    fresh,
                    [a for a, _ in visible2],
                    {
                        a.id: (
                            "Another character just spoke to or about you. React briefly as "
                            "your character, or stay out of it."
                        )
                        for a, _ in visible2
                    },
                    turn,
                    scores={a.id: sc for a, sc in visible2},
                )
                wave2 = await self._apply_wave(
                    h, req, scene, decisions2, turn, result, emit, budget, ai_to_ai=True
                )
        turn.extra["reactions"] = {
            "visible": len(visible),
            "silent": len(silent),
            "spoke": sum(1 for a in applied_all + wave2 if a.spoke),
            "rejected": sum(1 for a in applied_all + wave2 if a.rejected),
            "paused": sum(len(a.paused) for a in applied_all + wave2),
            "ai_to_ai": len(wave2),
        }

    async def _apply_wave(
        self,
        h: CampaignHandle,
        req: PlayRequest,
        scene: Scene,
        decisions: list[Any],
        turn: Turn,
        result: PlayResult,
        emit,
        budget: SpotlightBudget,
        *,
        ai_to_ai: bool,
    ) -> list[Any]:
        applied_all = []
        for d in sorted(decisions, key=lambda d: -d.score):
            fresh = await self.session.get(Scene, scene.id)
            assert fresh is not None
            ledger = SpotlightLedger.from_dict(fresh.state.get("spotlight"))
            if not ledger.allows_visible(budget):
                ledger.compress(str(d.actor_id))  # over budget: summarised in narration
                fresh.state = {**fresh.state, "spotlight": ledger.to_dict()}
                turn.notes.append(f"spotlight: {d.actor_id} compressed")
                continue
            applied = await self.ai.apply(h, scene.id, d, turn, emit)
            applied_all.append(applied)
            turn.notes.extend(f"{d.actor_id}: {n}" for n in applied.notes)
            if applied.rejected:
                turn.notes.append(f"ai proposal rejected for {d.actor_id}: {applied.rejected}")
            if applied.spoke or applied.actions:
                fresh = await self.session.get(Scene, scene.id)
                ledger = SpotlightLedger.from_dict(fresh.state.get("spotlight"))
                ledger.note_visible(ai_to_ai=ai_to_ai)
                fresh.state = {**fresh.state, "spotlight": ledger.to_dict()}
            if applied.speech and str(req.actor_id) in applied.speech["recipients"]:
                line = {k: v for k, v in applied.speech.items() if k != "claims"}
                result.speakers.append(line)
                emit("speaker", {"actor": line["actor_id"], "text": line["text"]})
                turn.mark_first_output()
            if applied.speech_result is not None:
                await self.ai.belief_processor_pass(
                    h, fresh, [applied.speech_result], turn, inline=set()
                )
        return applied_all

    async def _ai_combat(
        self,
        h: CampaignHandle,
        req: PlayRequest,
        scene: Scene,
        turn: Turn,
        result: PlayResult,
        emit,
        last_action: str | None,
    ) -> None:
        loaded = await self.actions.load_scene(h, scene.id)
        enc = loaded.ctx.encounter
        if enc is None or enc.status != "active":
            return
        me = str(req.actor_id)
        if enc.current_actor == me:
            spent = enc.budget(me).major < 1 or last_action in (
                "action.wait",
                "action.flee",
                "action.surrender",
            )
            if not spent:
                return  # the player still has their major action; it stays their turn
            await self.actions.next_turn(h, scene.id)
        humans = {
            a.id
            for a, _e in await self.perspective.repo.scene_participants(scene.id)
            if await self.perspective.repo.controller_type(a.id) == "human"
        }
        log = await self.ai.run_combat_turns(h, scene.id, turn, stop_at=humans, emit=emit)
        turn.extra["ai_combat_turns"] = log

    def _resolve_targets(
        self, intent: IntentInterpreterOut, cands: list[Candidate], text: str, forced: str | None
    ) -> list[dict[str, Any]]:
        by_id = {c.id: c for c in cands if c.id}
        lower = text.lower()
        out = []
        for it in sorted(intent.intents, key=lambda i: i.order):
            note: str | None = None
            if forced is not None:
                cand = by_id.get(forced)  # the answered clarification names a candidate id
            else:
                cand = match_ref(cands, it.target_ref)
                if cand is None and it.target_ref:
                    # the model's own ref words ("irritated_merchant") name the candidate it
                    # meant (A9 replay: unmatched, the player's sentence then matched a place)
                    cand = by_ref_words(cands, it.target_ref)
                    if cand is not None:
                        note = f"target {it.target_ref!r} -> {cand.ref}: by the ref's own words"
                # only a targeted intent is re-checked ("rest by the gate" has no target),
                # and only against the kinds of thing that action can take (A9 slice: "attack
                # the closest thief" matched a place by one word and Alex walked out of a fight)
                kinds = WORD_MATCH_KINDS.get(ACTION_MAP.get(it.action_type.lower()) or "")
                if not kinds and it.action_type.lower() in READ_TYPES:
                    kinds = ("item",)
                better = (
                    closer_to_words(cands, cand, text, kinds=kinds)
                    if it.target_ref and kinds
                    else None
                )
                if better is not None:
                    note = (
                        f"target {it.target_ref!r} -> {better.ref}: the player's words describe it"
                    )
                    cand = better
            kind = it.action_type.lower()
            needs_actor = (
                ACTION_MAP.get(kind) in ("action.attack", "action.engage")
                or kind in SPEECH_TYPES
                and intent.channel == "whisper"
            )
            amb = False
            options: list[Candidate] = []
            if needs_actor and forced is None and cand is None:
                # the player's words name the person ("attack the merchant"; play session
                # 2026-10-05 offered only the guards)
                cand = actor_by_words(cands, text)
                if cand is not None:
                    note = f"target {it.target_ref!r} -> {cand.ref}: the player's words name them"
            if needs_actor and forced is None:
                actors = [c for c in cands if c.kind == "actor"]
                pool = (
                    [c for c in actors if c.hostile]
                    if ACTION_MAP.get(kind) == "action.attack" and any(c.hostile for c in actors)
                    else actors
                )
                named = cand is not None and any(tok in lower for tok in _tokens(cand.known_as))
                if cand is None or (PRONOUN_RE.search(lower) and not named and len(pool) > 1):
                    if len(pool) > 1:
                        amb, options = True, pool
                    elif len(pool) == 1:
                        cand = pool[0]
            out.append(
                {
                    "intent": it,
                    "candidate": cand,
                    "ambiguous": amb,
                    "options": options,
                    "kind": "actor" if needs_actor else "target",
                    "note": note,
                    "targets": list(intent.targets or []),
                    "text": text,
                }
            )
        return out

    # -- model calls ------------------------------------------------------------------------------

    async def _interpret(
        self,
        h: CampaignHandle,
        req: PlayRequest,
        text: str,
        channel: str,
        cands: list[Candidate],
        turn: Turn,
    ) -> IntentInterpreterOut:
        if not turn.can_make_sync_call():
            raise WorldError("turn call budget exhausted before intent parsing")
        by_id = {c.id: c.ref for c in cands if c.kind == "actor"}
        situation = f'Player input (channel: {channel}): "{text}"' + (
            "\nExplicit whisper targets: "
            + ", ".join(by_id.get(str(t), "someone") for t in req.target_actor_ids)
            if req.target_actor_ids
            else ""
        )
        ctx = await self.compiler.compile(
            h,
            "intent_interpreter",
            actor_id=req.actor_id,
            purpose="interpret player input",
            situation=situation,
            extra_sections={
                "candidates": self._candidates_text(cands),
                **(
                    {"recent_turns": "Earlier in this scene (oldest first):\n- " + "\n- ".join(log)}
                    if (log := await self._scene_log(req.actor_id, None, limit=4))
                    else {}
                ),
            },
        )
        self._last_ref_map = dict(ctx.ref_map)
        res = await self.runner.run(h, ctx, turn_id=turn.turn_id)
        turn.record_call(
            "intent_interpreter",
            calls=res.calls,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
            context_tokens=ctx.estimated_tokens,
        )
        if not res.ok or res.output is None:
            # never lose the player's turn to a parse failure (play session 2026-10-05): what
            # they wrote is spoken if it reads as speech, otherwise ruled on as one attempt
            from app.ai.roles import IntentInterpreterOut

            spoken = channel in ("say", "whisper") or '"' in text or "“" in text
            fallback = channel if channel in ("say", "whisper") else ("say" if spoken else "do")
            turn.notes.append(
                f"interpreter output unusable ({res.status}: {'; '.join(res.errors)[:200]}); "
                f"fallback: {fallback}"
            )
            return IntentInterpreterOut.model_validate(
                {
                    "channel": fallback,
                    "confidence": 0.3,
                    "intents": []
                    if fallback in ("say", "whisper")
                    else [{"order": 1, "action_type": "other", "target_ref": None}],
                }
            )
        return res.output  # type: ignore[return-value]

    async def _adjudicate(
        self, h: CampaignHandle, actor_id: uuid.UUID, description: str, turn: Turn
    ) -> RulesAdjudicatorOut | None:
        if not turn.can_make_sync_call():
            turn.notes.append("adjudicator skipped: call cap")
            return None
        rs = self.engine.ruleset
        rules_public = (
            "Effect primitives: "
            + ", ".join(sorted(REGISTRY))
            + ".\nChecks: "
            + ", ".join(sorted(rs.checks))
            + ".\nSkills: "
            + ", ".join(sorted(rs.skills))
            + ".\nAttributes: "
            + ", ".join(sorted(rs.attributes))
            + ".\nConditions: "
            + ", ".join(sorted(rs.conditions))
            + ".\nDifficulties: "
            + ", ".join(f"{k}={v}" for k, v in rs.manifest.difficulty_scale.items())
        )
        ctx = await self.compiler.compile(
            h,
            "rules_adjudicator",
            actor_id=None,
            purpose="adjudicate",
            situation=f"Actor {actor_id} attempts: {description}",
            extra_sections={"rules_public": rules_public},
        )
        res = await self.runner.run(h, ctx, turn_id=turn.turn_id)
        turn.record_call(
            "rules_adjudicator",
            calls=res.calls,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
            context_tokens=ctx.estimated_tokens,
        )
        return res.output if res.ok else None  # type: ignore[return-value]

    async def _adjudicate_assertion(
        self, h: CampaignHandle, actor_id: uuid.UUID, assertion: AssertedFactOut, turn: Turn
    ) -> RulesAdjudicatorOut | None:
        p = assertion.proposition
        return await self._adjudicate(
            h,
            actor_id,
            f"player asserts ({assertion.class_}): {p.subject_entity_id or 'self'} {p.predicate} "
            f"{p.object_entity_id or ''} {p.value or ''}".strip(),
            turn,
        )

    def validate_ruling(self, ruling: RulesAdjudicatorOut) -> dict[str, Any]:
        """Schema/reference validation of a MechanicalProposal (rules-engine §30 steps 1–4)."""
        rs = self.engine.ruleset
        out = ruling.model_dump()
        if ruling.requires_check:
            chk = ruling.check or {}
            if chk.get("check", "check.core") not in rs.checks:
                raise EffectError(f"unknown check {chk.get('check')!r}")
            for key in ("attribute", "skill"):
                if chk.get(key) and not rs.has(chk[key]):
                    raise EffectError(f"unknown {key} {chk[key]!r}")
            d = chk.get("difficulty", "moderate")
            if isinstance(d, str) and d not in rs.manifest.difficulty_scale:
                raise EffectError(f"unknown difficulty {d!r}")
        for branch in ("on_success", "on_failure"):
            for raw in out.get(branch) or []:
                validate_step(rs, EffectStep.model_validate(raw))
        return out

    # -- execution ------------------------------------------------------------------------------

    async def _act(
        self,
        h: CampaignHandle,
        req: PlayRequest,
        scene: Scene,
        kind: str,
        step: dict[str, Any],
        cands: list[Candidate],
        turn: Turn,
        result: PlayResult,
        emit,
        text: str,
    ) -> ActionOutcome | None:
        actor_key = str(req.actor_id)
        action_key = ACTION_MAP.get(kind)
        cand: Candidate | None = step["candidate"]
        target: str | None = None
        if cand is not None and cand.kind == "location":
            return await self._travel(h, req, scene, step, cands, turn, result, emit)
        if kind in READ_TYPES and cand is not None and cand.kind == "item":
            return await self._read(h, req, cand, turn, result, emit)
        if kind in READ_TYPES:
            # nothing readable in reach by that description: an invalid action, not a ruling
            # (A9 slice: unmatched reads went to the Rules Adjudicator, whose ruling invented
            # fields, was rejected, and cost a model call for nothing)
            entry = {
                "action": "read",
                "target": step["intent"].target_ref,
                "status": "invalid",
                "reason": "there is nothing like that within reach to read",
            }
            result.actions.append(entry)
            result.mechanical_notices.append(f"(OOC) {entry['reason']}")
            return None
        if action_key is not None:
            if (
                action_key in ("action.move", "action.sprint")
                and cand is not None
                and cand.kind == "actor"
            ):
                loaded = await self.actions.load_scene(h, scene.id)
                my_zone = loaded.ctx.space.position(actor_key).zone
                their_zone = (
                    loaded.ctx.space.position(cand.id).zone
                    if cand.id in loaded.ctx.space.positions
                    else my_zone
                )
                action_key, target = (
                    ("action.engage", cand.id)
                    if my_zone == their_zone
                    else ("action.move", their_zone)
                )
            elif cand is not None:
                target = cand.id
            elif action_key == "action.search":
                loaded = await self.actions.load_scene(h, scene.id)
                target = loaded.ctx.space.position(actor_key).zone
            try:
                outcome = await self.actions.perform(
                    h,
                    scene.id,
                    ActionRequest(
                        actor_key,
                        action_key,
                        target,
                        params=dict(step["intent"].params),
                        based_on_scene_version=req.known_scene_version,
                        source="human",
                    ),
                    turn_id=turn.turn_id,
                )
            except StaleStateError as exc:
                raise StaleState(0, exc.actual) from exc
        else:
            ruling = await self._cached_ruling(h, req.actor_id, text, turn)
            if ruling is None:
                result.dev_notes.append(f"could not adjudicate '{kind}'; nothing happened")
                return None
            try:
                validated = self.validate_ruling(ruling)
            except (EffectError, Exception) as exc:  # noqa: BLE001
                result.dev_notes.append(f"(OOC) ruling rejected: {exc}")
                return None
            outcome = await self.actions.perform_improvised(
                h, scene.id, actor_key, validated, description=text, turn_id=turn.turn_id
            )
        entry = {
            "action": outcome.request.action_key,
            "target": outcome.request.target,
            "status": outcome.status,
            "reason": outcome.reason,
            "summary": outcome.trace.summary if outcome.trace else "",
        }
        result.actions.append(entry)
        if outcome.status == "invalid":
            result.mechanical_notices.append(f"(OOC) {outcome.reason}")
        else:
            turn.mark_first_output()
            emit("mechanics", {"action": entry, "events": [e.get("type") for e in outcome.events]})
        return outcome

    async def _cached_ruling(
        self, h: CampaignHandle, actor_id: uuid.UUID, text: str, turn: Turn
    ) -> RulesAdjudicatorOut | None:
        """One ruling per attempt per turn; a resumed roll reuses the ruling it was shown."""
        from app.ai.roles import RulesAdjudicatorOut

        if text in self._ruling_cache:
            return RulesAdjudicatorOut.model_validate(self._ruling_cache[text])
        ruling = await self._adjudicate(h, actor_id, text, turn)
        if ruling is not None:
            self._ruling_cache[text] = ruling.model_dump()
        return ruling

    async def _preflight_checks(
        self,
        h: CampaignHandle,
        req: PlayRequest,
        scene: Scene,
        resolved: list[dict[str, Any]],
        channel: str,
        text: str,
        turn: Turn,
    ) -> list[dict[str, Any]]:
        """The checks this turn will call for, previewed without rolling: the player sees the
        skill, the number to reach, their bonus and what is at stake before deciding to roll."""
        checks: list[dict[str, Any]] = []
        seen: set[str] = set()
        state = None
        for step in resolved:
            kind = canonical_kind(step["intent"].action_type, channel)
            cand = step["candidate"]
            if kind in SOCIAL_SKILLS:
                key = f"{kind}:{cand.id if cand else ''}"
                if key in seen:
                    continue
                seen.add(key)
                skill, attribute, label = SOCIAL_SKILLS[kind]
                difficulty: Any = "moderate"
                stakes = SOCIAL_STAKES[kind]
            elif (
                kind not in SPEECH_TYPES
                and kind not in FREE_TYPES
                and kind not in READ_TYPES
                and ACTION_MAP.get(kind) is None
                and not (cand is not None and cand.kind == "location")
            ):
                ruling = await self._cached_ruling(h, req.actor_id, text, turn)
                if ruling is None or not ruling.requires_check or not ruling.check:
                    continue
                c = ruling.check
                skill = c.get("skill")
                attribute = c.get("attribute")
                difficulty = c.get("difficulty", "moderate")
                label = (
                    str(skill or attribute).split(".")[-1].replace("_", " ").title()
                    if (skill or attribute)
                    else "Ability"
                )
                stakes = {
                    "success": ruling.stakes.get("success") or "You get what you were trying for.",
                    "failure": ruling.stakes.get("failure") or "It doesn't work, and it costs you.",
                    "retry": ruling.stakes.get("retry") or "You may be able to try another way.",
                }
            else:
                continue
            if state is None:
                loaded = await self.actions.load_scene(h, scene.id)
                state = loaded.ctx.states[str(req.actor_id)]
            try:
                p = self.engine.preview(
                    state, "check.core", attribute=attribute, skill=skill, difficulty=difficulty
                )
            except Exception as exc:  # noqa: BLE001 - an unpreviewable check just rolls
                turn.notes.append(f"check preview failed: {exc}")
                continue
            checks.append(
                {
                    **p,
                    "label": label,
                    "kind": kind,
                    "target_known_as": cand.known_as if cand is not None else None,
                    "dc": p["target"],
                    "stakes": stakes,
                }
            )
        return checks

    async def _social(
        self,
        h: CampaignHandle,
        req: PlayRequest,
        scene: Scene,
        kind: str,
        step: dict[str, Any],
        turn: Turn,
        result: PlayResult,
        emit,
        hap: Happenings,
        text: str,
    ) -> None:
        """A social action resolved by the engine, without a ruling call: the matching skill
        against a moderate difficulty. The listener learns how convincing it was and decides
        what to do about it in character."""
        skill, attribute, label = SOCIAL_SKILLS[kind]
        ruling = {
            "requires_check": True,
            "check": {
                "check": "check.core",
                "skill": skill,
                "attribute": attribute,
                "difficulty": "moderate",
                "purpose": label,
            },
            "on_success": [],
            "on_failure": [],
            "time_cost_seconds": 6,
            "summary": f"{label}: {text[:120]}",
        }
        try:
            from app.ai.roles import RulesAdjudicatorOut

            validated = self.validate_ruling(RulesAdjudicatorOut.model_validate(ruling))
            outcome = await self.actions.perform_improvised(
                h, scene.id, str(req.actor_id), validated, description=text, turn_id=turn.turn_id
            )
        except Exception as exc:  # noqa: BLE001 - the words were still spoken
            result.dev_notes.append(f"social check not resolved: {type(exc).__name__}: {exc}")
            return
        target = step["candidate"]
        entry = {
            "action": f"social.{kind}",
            "target": target.known_as if target is not None else None,
            "status": outcome.status,
            "reason": outcome.reason,
            "summary": outcome.trace.summary if outcome.trace else "",
        }
        result.actions.append(entry)
        emit("mechanics", {"action": entry, "events": [e.get("type") for e in outcome.events]})
        if target is not None and target.kind == "actor":
            check = next((s for s in outcome.steps if s.kind == "check"), None)
            margin = 0
            if check is not None:
                margin = int(check.detail.get("total", 0)) - int(check.detail.get("target", 0))
            hap.social[uuid.UUID(target.id)] = (label, outcome.status == "succeeded", margin)

    async def _read(
        self,
        h: CampaignHandle,
        req: PlayRequest,
        cand: Candidate,
        turn: Turn,
        result: PlayResult,
        emit,
    ) -> ActionOutcome | None:
        """Reading a Document (c&k §3): an Observation whose Claims come from the stored
        `conveys[]`; the text is returned verbatim and never re-extracted."""
        try:
            r = await self.documents.read(h, req.actor_id, uuid.UUID(cand.id), turn_id=turn.turn_id)
        except WorldError as exc:
            result.actions.append(
                {"action": "read", "target": cand.id, "status": "invalid", "reason": str(exc)}
            )
            result.mechanical_notices.append(f"(OOC) {exc}")
            return None
        entry = {
            "action": "read",
            "target": cand.id,
            "status": "succeeded",
            "reason": "",
            "summary": f"read {cand.known_as}",
            "text": r.text,
            "claims": len(r.claims),
        }
        result.actions.append(entry)  # the read_document Observation renders the text
        turn.mark_first_output()
        emit("mechanics", {"action": entry, "events": ["document.read"]})
        return None

    async def _party_ids(self, actor_id: uuid.UUID) -> set[uuid.UUID]:
        from app.persistence.models import PartyMembership

        parties = select(PartyMembership.party_id).where(PartyMembership.actor_id == actor_id)
        return set(
            (
                await self.session.execute(
                    select(PartyMembership.actor_id).where(PartyMembership.party_id.in_(parties))
                )
            )
            .scalars()
            .all()
        )

    async def _companions_in_words(
        self, actor_id: uuid.UUID, cands: list[Candidate], text: str
    ) -> list[uuid.UUID]:
        """Who the player's own words take along (A9 slice: "We head to the Red Lantern, all
        three of us" moved only Alex). Party members named in the text come; "we", "us",
        "together" or "all of us" with nobody named brings every party member present. Only
        party members ever follow (the caller filters)."""
        low = text.lower()
        present = [c for c in cands if c.kind == "actor" and c.id and c.id != str(actor_id)]
        named = [
            uuid.UUID(c.id)
            for c in present
            if _tokens(c.known_as) and _tokens(c.known_as) <= set(re.findall(r"[a-z0-9]+", low))
        ]
        group = re.search(r"\b(we|us|together|all of us|all (two|three|four|five) of us)\b", low)
        with_me = re.search(r"\b(and i|with me|come with|follow me)\b", low)
        if named and (group or with_me):
            return named
        if group:
            return [uuid.UUID(c.id) for c in present]
        return []

    async def _travel(
        self,
        h: CampaignHandle,
        req: PlayRequest,
        scene: Scene,
        step: dict[str, Any],
        cands: list[Candidate],
        turn: Turn,
        result: PlayResult,
        emit,
    ) -> ActionOutcome | None:
        """Travel to a connected location (Milestone 07, time-accounting §3/§5). Companions
        the player names (intent targets / params.with) who are party members at the same
        place come along; everyone else stays, and their scene becomes offscreen."""
        cand: Candidate = step["candidate"]
        by_ref = {c.ref: c for c in cands}
        companions: list[uuid.UUID] = []
        refs = list(step["intent"].params.get("with") or []) + list(
            getattr(step["intent"], "companion_refs", []) or []
        )
        for r in refs:
            c = match_ref(cands, r) if r not in by_ref else by_ref[r]
            if c is not None and c.kind == "actor" and c.id:
                companions.append(uuid.UUID(c.id))
        for r in step.get("targets", []):  # GLM names companions here, not in params.with
            c = match_ref(cands, r) if r not in by_ref else by_ref[r]
            if c is not None and c.kind == "actor" and c.id:
                companions.append(uuid.UUID(c.id))
        companions += await self._companions_in_words(req.actor_id, cands, step.get("text", ""))
        party = await self._party_ids(req.actor_id)
        companions = list(dict.fromkeys(a for a in companions if a != req.actor_id and a in party))
        if companions:
            turn.notes.append(f"travelling with {len(companions)} companion(s)")
        try:
            tr = await self.scenes.travel(
                h,
                [req.actor_id, *companions],
                uuid.UUID(cand.id),
                created_by_type="human",
                created_by_id=req.actor_id,
            )
        except WorldError as exc:
            result.actions.append(
                {"action": "travel", "target": cand.id, "status": "invalid", "reason": str(exc)}
            )
            result.mechanical_notices.append(f"(OOC) {exc}")
            return None
        result.time_advanced_seconds += tr.travel_seconds
        entry = {
            "action": "travel",
            "target": cand.id,
            "status": "succeeded",
            "reason": "",
            "summary": f"travel to {cand.known_as}"
            + (f" with {len(companions)} companion(s)" if companions else "")
            + (" (joined the scene there)" if tr.joined_existing else ""),
            "scene_id": str(tr.scene.id),
            "companions": [str(c) for c in companions],
        }
        result.actions.append(entry)
        turn.mark_first_output()
        emit(
            "mechanics",
            {
                "action": entry,
                "events": [
                    "actor.moved",
                    "scene.started" if not tr.joined_existing else "scene.participant_joined",
                ],
            },
        )
        turn.extra.setdefault("travel", []).append(
            {
                "to": cand.id,
                "joined": tr.joined_existing,
                "merged_from": [str(x) for x in tr.merged_from],
            }
        )
        return None

    async def _catch_up_offscreen(self, h: CampaignHandle, turn: Turn, result: PlayResult) -> None:
        """time-accounting §4 (bounded form): an offscreen scene lagging the world clock by
        more than the granularity gets at most ONE AI decision (its most important AI actor,
        intentions only), applied through full mechanics; then its local_tick is set to the
        clock. At most `max_offscreen_catchups_per_turn` scenes per live turn; nothing is
        narrated and the human receives nothing (human-visibility §3)."""
        granularity = int(getattr(self.settings, "catchup_granularity_seconds", 600))
        max_scenes = int(getattr(self.settings, "max_offscreen_catchups_per_turn", 2))
        clock = await self.world.clock(h)
        done = 0
        for scene in await self.scenes.offscreen_scenes(h):
            if done >= max_scenes:
                break
            lag = clock.current_tick - scene.local_tick
            if lag <= granularity:
                continue
            # 07: only AI party members act on their own during a lull (they carry the party's
            # purpose offscreen); NPC scenes wait for plan steps and triggers (Milestone 08).
            ai = [a for a in await self.ai.ai_participants(scene) if a.actor_type == "pc"]
            calls = 0
            if ai and turn.can_make_sync_call():
                order = {"full": 0, "important": 1, "standard": 2, "background": 3}
                actor = sorted(ai, key=lambda a: order.get(a.importance_tier, 9))[0]
                minutes = max(1, lag // 60)
                situation = (
                    f"About {minutes} minutes have passed here while the others are elsewhere. "
                    "Decide what you did with that time in this place: act through intentions "
                    "(search, move, wait, speak to someone present). No narration."
                )
                decisions = await self.ai.decide_many(
                    h, scene, [actor], {actor.id: situation}, turn, kind="catch_up"
                )
                calls = len(decisions)
                for d in decisions:
                    applied = await self.ai.apply(h, scene.id, d, turn)
                    turn.extra.setdefault("offscreen", []).append(
                        {
                            "scene_id": str(scene.id),
                            "actor_id": str(actor.id),
                            "actions": applied.actions,
                            "spoke": applied.spoke,
                            "rejected": applied.rejected,
                        }
                    )
            fresh = await self.session.get(Scene, scene.id)
            if fresh is not None and fresh.status == "active":
                async with EventTransaction(self.session, h.campaign_id, h.timeline_id) as tx:
                    from_tick = fresh.local_tick
                    await tx.emit(
                        ev.SceneCaughtUp(
                            scene_id=fresh.id,
                            from_tick=from_tick,
                            to_tick=tx.clock.current_tick,
                            model_calls=calls,
                        ),
                        scene=fresh,
                    )
                    fresh.local_tick = tx.clock.current_tick
            done += 1
        if done:
            turn.extra["offscreen_catchups"] = done

    async def _speak(
        self,
        h: CampaignHandle,
        req: PlayRequest,
        scene: Scene,
        text: str,
        channel: str,
        intent: IntentInterpreterOut,
        step: dict[str, Any] | None,
        cands: list[Candidate],
        turn: Turn,
        result: PlayResult,
        emit,
        hap: Happenings | None = None,
    ) -> bool:
        by_ref = {c.ref: c for c in cands}
        known = {
            slug(name): eid
            for eid, name in (await self.perspective.known_entities(req.actor_id)).items()
        }
        quoted = QUOTE_RE.search(text)
        # quoted words first; then the interpreter's line for described speech; the whole text
        # only on an explicit say/whisper (A9 replay: "I'd like to subtly motion for Elara…"
        # was spoken aloud)
        spoken = (
            quoted[1]
            if quoted
            else (intent.utterance or "").strip()
            or (text if channel in ("say", "whisper") else text)
        )
        targets = list(req.target_actor_ids)
        if step is not None and step["candidate"] is not None and step["candidate"].kind == "actor":
            targets = targets or [uuid.UUID(step["candidate"].id)]
        elif not targets and intent.targets:
            named = [match_ref(cands, t) or actor_by_words(cands, t) for t in intent.targets]
            targets = [uuid.UUID(c.id) for c in named if c is not None and c.kind == "actor"]
        ch = (
            "whisper"
            if channel == "whisper"
            or (step is not None and step["intent"].action_type.lower() == "whisper")
            else "say"
        )
        if ch == "whisper" and not targets:
            raise WorldError("whisper needs a target")
        conveys = [
            ConveysItem(
                c.kind,
                ref_id=self._ref_to_id(c.ref_id),
                proposition=self._prop_to_ids(
                    c.proposition.model_dump() if c.proposition else None, by_ref, known
                ),
                stance=c.stance,
                fidelity=c.fidelity,
                about_speaker_self=c.about_speaker_self,
            )
            for c in intent.conveys
        ]
        try:
            r = await self.speech.utter(
                h,
                scene.id,
                req.actor_id,
                spoken,
                channel=ch,
                conveys=conveys,
                target_actor_ids=targets,
                conveyance_source="player_text",
                turn_id=turn.turn_id,
            )
        except LeakageError as exc:
            result.mechanical_notices.append(f"(OOC) speech rejected: {exc}")
            return False
        result.speakers.append(
            {
                "actor_id": str(req.actor_id),
                "channel": ch,
                "text": spoken,
                "recipients": [str(x) for x in r.recipients],
            }
        )
        if hap is not None:
            hap.note_speech(r, targets)
        turn.mark_first_output()
        emit(
            "mechanics",
            {"speech": {"channel": ch, "recipients": len(r.recipients), "claims": len(r.claims)}},
        )
        return True

    def _ref_to_id(self, ref: str | None) -> str | None:
        if not ref:
            return None
        rm = getattr(self, "_last_ref_map", {})
        return str(rm.get(ref, ref))

    @staticmethod
    def _prop_to_ids(
        prop: dict[str, Any] | None,
        by_ref: dict[str, Candidate],
        known: dict[str, uuid.UUID] | None = None,
    ) -> dict[str, Any] | None:
        """Candidate refs and the speaker's own names for entities (as the model tends to
        write them: `oric_dane`) become entity ids; anything else stays free text."""
        if not prop:
            return None
        out = dict(prop)
        by_actor_id = {c.id: c for c in by_ref.values() if c.kind == "actor" and c.entity_id}
        known_ids = {str(v) for v in (known or {}).values()}
        for key in ("subject_entity_id", "object_entity_id"):
            v = out.get(key)
            if not v:
                continue
            v = str(v)
            if v in by_ref and by_ref[v].entity_id is not None:
                out[key] = str(by_ref[v].entity_id)
            elif known and slug(v) in known:
                out[key] = str(known[slug(v)])
            elif v in by_actor_id:  # the model echoed an actor id it saw: use the entity
                out[key] = str(by_actor_id[v].entity_id)
            elif _looks_like_uuid(v) and v not in known_ids:
                out[key] = None  # an id this actor was never given: not a reference
        if isinstance(out.get("predicate"), str):
            out["predicate"] = out["predicate"].replace("_", " ").strip()
        return out

    async def _conversation_time(self, h: CampaignHandle, scene: Scene, band: str) -> int:
        seconds = TIME_BANDS.get(band or "normal", 45)
        used = int(scene.state.get("conversation_seconds", 0))
        if seconds <= 0:
            return 0
        if used >= CONVERSATION_CAP_S:
            scene.state = {**scene.state, "conversation_late": True}
            return 0
        seconds = min(seconds, CONVERSATION_CAP_S - used)
        await self.world.advance_time(h, seconds, reason=f"conversation:{band}", scene_id=scene.id)
        fresh = await self.session.get(Scene, scene.id)
        fresh.state = {**fresh.state, "conversation_seconds": used + seconds}
        return seconds

    # -- read-backs ------------------------------------------------------------------------------

    async def _last_sequence(self, h: CampaignHandle) -> int:
        return (
            await self.session.execute(
                select(Event.sequence_number)
                .where(Event.timeline_id == h.timeline_id)
                .order_by(Event.sequence_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none() or 0

    async def _events_since(self, h: CampaignHandle, seq: int) -> list[Event]:
        return list(
            (
                await self.session.execute(
                    select(Event)
                    .where(Event.timeline_id == h.timeline_id, Event.sequence_number > seq)
                    .order_by(Event.sequence_number)
                )
            )
            .scalars()
            .all()
        )

    async def _visible_rolls(self, events: list[Event]) -> list[dict[str, Any]]:
        if not events:
            return []
        rows = (
            (
                await self.session.execute(
                    select(Roll).where(
                        Roll.event_id.in_([e.id for e in events]), Roll.visibility == "public"
                    )
                )
            )
            .scalars()
            .all()
        )
        by_event = {e.id: e for e in events}
        # a check's numbers live on its check.rolled event; a roll row may be attached to the
        # action's final event instead (improvised and social checks), so pair it with its
        # actor's next check event in sequence
        checks_by_actor: dict[str, list[Event]] = {}
        for e in sorted(events, key=lambda x: x.sequence_number):
            if e.event_type == "check.rolled":
                checks_by_actor.setdefault(str((e.payload or {}).get("actor")), []).append(e)
        rows = sorted(
            rows,
            key=lambda r: by_event[r.event_id].sequence_number if r.event_id in by_event else 0,
        )
        out = []
        for r in rows:
            ev_ = by_event.get(r.event_id)
            if ev_ is None or ev_.event_type != "check.rolled":
                queue = checks_by_actor.get(str(r.actor_id), [])
                ev_ = queue.pop(0) if queue else ev_
            elif ev_ in checks_by_actor.get(str(r.actor_id), []):
                checks_by_actor[str(r.actor_id)].remove(ev_)
            p = (ev_.payload if ev_ is not None else {}) or {}
            natural = _natural(r.kept) if r.kept else _natural(r.raw)
            check_total = (
                p.get("total") if ev_ is not None and ev_.event_type == "check.rolled" else None
            )
            out.append(
                {
                    "id": str(r.id),
                    "expression": r.expression,
                    "raw": r.raw,
                    "natural": natural,
                    "modifier": r.modifier,
                    "total": check_total if check_total is not None else r.final_result,
                    "purpose": r.purpose,
                    "dc": p.get("versus"),
                    "success": p.get("success"),
                    "degree": p.get("degree"),
                    "source": "engine",
                }
            )
        return out

    async def _notices(self, actor_id: uuid.UUID, events: list[Event]) -> list[str]:
        if not events:
            return []
        rows = (
            (
                await self.session.execute(
                    select(Observation)
                    .where(
                        Observation.actor_id == actor_id,
                        Observation.source_event_id.in_([e.id for e in events]),
                    )
                    .order_by(Observation.created_at)
                )
            )
            .scalars()
            .all()
        )
        names = await self.perspective.known_entities(actor_id)
        return [PerspectiveService.render(o.observation_type, o.raw, names) for o in rows]

    async def _resources(self, actor_id: uuid.UUID) -> dict[str, int]:
        actor = await self.perspective.repo.actor(actor_id)
        if actor is None:
            return {}
        return {
            r.resource_key: r.current
            for r in (
                await self.session.execute(
                    select(ResourceStateRow).where(ResourceStateRow.entity_id == actor.entity_id)
                )
            )
            .scalars()
            .all()
        }

    async def _state_changes(
        self, actor_id: uuid.UUID, before: dict[str, int]
    ) -> list[dict[str, Any]]:
        after = await self._resources(actor_id)
        return [
            {"resource": k, "before": before.get(k), "after": v}
            for k, v in after.items()
            if before.get(k) != v
            and before.get(k) is not None  # first materialisation is not a change
        ]

    async def _versions(self, h: CampaignHandle, scene: Scene) -> dict[str, int | None]:
        campaign = await self.session.get(Campaign, h.campaign_id)
        fresh = await self.session.get(Scene, scene.id)
        return {
            "world_version": campaign.world_version if campaign else None,
            "scene_version": fresh.version if fresh else None,
        }


def _looks_like_uuid(v: str) -> bool:
    try:
        uuid.UUID(v)
        return True
    except ValueError:
        return False


def _tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", name.lower()) if t not in STOP and len(t) > 2}


# which kinds of candidate the player's words may pick for an action (none: never)
WORD_MATCH_KINDS: dict[str, tuple[str, ...]] = {
    "action.move": ("location", "zone"),
    "action.sprint": ("location", "zone"),
    "travel": ("location",),
    "action.search": ("zone", "item"),
    "action.pick_up": ("item",),
    "action.drop": ("item",),
    "action.use_item": ("item",),
    "action.take_cover": ("zone",),
}


def closer_to_words(
    cands: list[Candidate],
    picked: Candidate | None,
    text: str,
    *,
    kinds: tuple[str, ...] = ("location", "item", "zone"),
) -> Candidate | None:
    """The player's own words outrank the model's pick (A9 slice: "the shuttered warehouse with
    the merchant sign" was resolved to "Warehouse District"; "the notice on the gatepost" was
    given a ref that matched nothing; "the ledger" for "Oric's private ledger"). Another
    place/item/zone wins when it shares at least two more significant words with the input
    than the pick does; with no pick at all, one shared word is enough. Either way no other
    candidate may tie it; otherwise the pick stands."""
    if picked is not None and picked.kind not in kinds:
        return None
    words = _tokens(text)
    if not words:
        return None

    def score(c: Candidate) -> int:
        return len(_tokens(c.known_as) & words)

    base = score(picked) if picked is not None else 0
    pool = [c for c in cands if c.kind in ((picked.kind,) if picked else kinds) and c is not picked]
    scored = sorted(((score(c), c) for c in pool), key=lambda x: -x[0])
    # with no pick, one shared word is enough for an item ("the ledger"); a place needs
    # two (A9 replay: "tail this merchant" matched "…faded merchant sign" and the party left)
    need = base + 2 if picked is not None else 1
    if not scored or scored[0][0] < need:
        return None
    if picked is None and scored[0][1].kind == "location" and scored[0][0] < 2:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]


def by_ref_words(cands: list[Candidate], ref: str) -> Candidate | None:
    """The one candidate of any kind whose known name shares the most words with the model's
    ref, if no other ties it."""
    words = _tokens(ref.replace("_", " "))
    if not words:
        return None
    scored = sorted(
        ((len(_tokens(c.known_as) & words), c) for c in cands if c.known_as != "you"),
        key=lambda x: -x[0],
    )
    if not scored or scored[0][0] < 1:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]


def actor_by_words(cands: list[Candidate], text: str) -> Candidate | None:
    """The one actor (not the player) whose known name shares the most words with the input,
    when no other actor ties it."""
    words = _tokens(text)
    scored = sorted(
        (
            (len(_tokens(c.known_as) & words), c)
            for c in cands
            if c.kind == "actor" and c.known_as not in ("you",)
        ),
        key=lambda x: -x[0],
    )
    if not scored or scored[0][0] < 1:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]


def match_ref(cands: list[Candidate], ref: str | None) -> Candidate | None:
    """Exact ref first; then the model's loose spellings ("Mira", "mira_the_innkeeper",
    "Captain Renn"): a unique candidate whose name tokens all appear in the ref."""
    if not ref:
        return None
    by_ref = {c.ref: c for c in cands}
    if ref in by_ref:
        return by_ref[ref]
    slug = re.sub(r"[^a-z0-9]+", "_", ref.lower()).strip("_")
    if slug in by_ref:
        return by_ref[slug]
    want = set(slug.split("_"))
    hits = [
        c
        for c in cands
        if c.kind in ("actor", "item", "zone")
        and _tokens(c.known_as)
        and _tokens(c.known_as) <= want
    ]
    return hits[0] if len(hits) == 1 else None


_ = ObservationService  # observations are produced by the services; kept for type visibility
