"""SimulationService — bounded world simulation (world-memory §23; orchestration §25–§26;
implementation-plan §17; ai-contracts §14; time-accounting §6).

One `tick(from_tick, to_tick)` is a *simulation run* with an explicit interval, candidate set,
event budget and call limit (Invariant 14). Order inside a run:

1. deterministic systems — due scheduled events the clock left for us (`actor.travel`), plan
   clocks (steps with `at_tick` whose prerequisites hold), prerequisite revalidation that
   cancels what can no longer happen;
2. candidate selection — decision steps and non-deterministic scheduled events that are due;
3. at most ONE World Simulator call with the candidates, their plans/goals, the deterministic
   changes just applied and the event budget; proposals are validated against the candidate
   map and applied through the ordinary services (every change commits with an Event);
4. a `simulation.run` Event records interval, candidates, budget and what was applied.

Nothing here narrates, and nothing here runs every NPC: an idle world costs zero calls.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextCompiler
from app.ai.roles import WorldSimulatorOut
from app.ai.runner import ModelRunner
from app.config import Settings
from app.domain import events as ev
from app.engine.core import RulesEngine
from app.persistence.models import (
    Actor,
    Entity,
    Faction,
    Goal,
    Location,
    Plan,
    ScheduledEvent,
)
from app.services.events import EventTransaction
from app.services.psychology import PsychologyService
from app.services.scenes import SceneService
from app.services.schedule import DETERMINISTIC_TYPES, ScheduleService
from app.services.turns import Turn
from app.services.world import CampaignHandle, WorldError, WorldService

DAY = 86400
SIM_TRAVEL_TYPE = "actor.travel"
MAX_CANDIDATES = 6
PROPOSAL_TYPES = {"plan_advance", "plan_hold", "plan_abandon", "actor_travel", "proceed", "cancel"}


@dataclass
class Candidate:
    ref: str
    kind: str  # plan | scheduled | actor | location
    id: uuid.UUID
    label: str
    detail: str = ""


@dataclass
class SimulationRun:
    from_tick: int
    to_tick: int
    event_budget: int
    scheduled_processed: list[str] = field(default_factory=list)
    scheduled_cancelled: list[str] = field(default_factory=list)
    plan_steps_advanced: list[str] = field(default_factory=list)
    travelled: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    model_calls: int = 0
    proposals_applied: list[dict[str, Any]] = field(default_factory=list)
    proposals_rejected: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def step_info(step: Any) -> dict[str, Any]:
    """Plan steps are strings (no clock) or dicts: {title, at_tick?, kind?, prerequisites?}."""
    if isinstance(step, dict):
        return {
            "title": str(step.get("title", "")),
            "at_tick": step.get("at_tick"),
            "kind": step.get("kind", "deterministic"),
            "prerequisites": list(step.get("prerequisites", [])),
        }
    return {"title": str(step), "at_tick": None, "kind": "deterministic", "prerequisites": []}


class SimulationService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        engine: RulesEngine,
        compiler: ContextCompiler,
        runner: ModelRunner,
    ) -> None:
        self.session = session
        self.settings = settings
        self.engine = engine
        self.compiler = compiler
        self.runner = runner
        self.world = WorldService(session)
        self.schedule = ScheduleService(session)
        self.scenes = SceneService(session)
        self.psychology = PsychologyService(session)

    @property
    def granularity(self) -> int:
        return int(getattr(self.settings, "simulation_granularity_seconds", 6 * 3600))

    def crosses_boundary(self, from_tick: int, to_tick: int) -> bool:
        return to_tick // self.granularity > from_tick // self.granularity

    # -- the run ---------------------------------------------------------------------------------

    async def tick(
        self, h: CampaignHandle, *, from_tick: int, to_tick: int, turn: Turn | None = None
    ) -> SimulationRun:
        if to_tick < from_tick:
            raise WorldError("simulation interval runs backwards")
        budget_cap = int(getattr(self.settings, "simulation_event_budget", 3))
        run = SimulationRun(
            from_tick, to_tick, max(1, min(budget_cap, (to_tick - from_tick) // DAY))
        )

        # 1. deterministic systems
        await self._fire_due_deterministic(h, to_tick, run)
        await self._travel_due(h, to_tick, run)
        await self._plan_clocks(h, to_tick, run)

        # 2. candidates
        cands = await self._candidates(h, to_tick, run)
        run.candidates = [f"{c.ref}:{c.label}" for c in cands]

        # 3. one bounded model call
        if cands and (turn is None or turn.can_make_sync_call()):
            await self._decide(h, cands, run, turn)
        elif cands:
            run.notes.append("simulator call skipped: turn call cap")

        # 4. the record
        async with EventTransaction(self.session, h.campaign_id, h.timeline_id) as tx:
            await tx.emit(
                ev.SimulationRunCompleted(
                    from_tick=from_tick,
                    to_tick=to_tick,
                    event_budget=run.event_budget,
                    candidates=run.candidates,
                    model_calls=run.model_calls,
                    applied=len(run.proposals_applied),
                    rejected=len(run.proposals_rejected),
                    summary={
                        "scheduled_processed": run.scheduled_processed,
                        "scheduled_cancelled": run.scheduled_cancelled,
                        "plan_steps_advanced": run.plan_steps_advanced,
                        "travelled": run.travelled,
                        "notes": run.notes,
                    },
                ),
                game_tick=to_tick,
            )
        return run

    # -- deterministic systems ---------------------------------------------------------------------

    async def _fire_due_deterministic(
        self, h: CampaignHandle, to_tick: int, run: SimulationRun
    ) -> None:
        """The clock fires deterministic scheduled events as it moves; a tick started by the
        debug API or the worker may find some still pending (e.g. a clock moved by raw SQL)."""
        due = [
            r
            for r in await self.schedule.pending(h)
            if r.scheduled_tick <= to_tick and r.event_type in DETERMINISTIC_TYPES
        ]
        if not due:
            return
        async with EventTransaction(self.session, h.campaign_id, h.timeline_id) as tx:
            touched = await self.schedule.fire_due(tx, to_tick)
            for r in touched:
                (
                    run.scheduled_processed if r.status == "processed" else run.scheduled_cancelled
                ).append(r.payload.get("key") or r.event_type)

    async def _travel_due(self, h: CampaignHandle, to_tick: int, run: SimulationRun) -> None:
        """Important-actor travel (implementation-plan §17): a due `actor.travel` moves the actor
        through SceneService (scene join/start, arrival observations) if its prerequisites hold."""
        for r in await self.schedule.pending(h):
            if r.event_type != SIM_TRAVEL_TYPE or r.scheduled_tick > to_tick:
                continue
            failed = await self.schedule._failed_prerequisite(r.payload.get("prerequisites", []))
            key = r.payload.get("key") or "travel"
            if failed is not None:
                await self._mark(h, r, "cancelled", {"failed_prerequisite": failed})
                run.scheduled_cancelled.append(key)
                continue
            actor_id = uuid.UUID(str(r.payload["actor_id"]))
            to_loc = uuid.UUID(str(r.payload["location_id"]))
            actor = await self.session.get(Actor, actor_id)
            if actor is None or actor.current_location_id == to_loc:
                await self._mark(h, r, "skipped", {"reason": "already there or gone"})
                continue
            try:
                await self.scenes.travel(
                    h, [actor_id], to_loc, require_edge=False, created_by_type="engine"
                )
            except WorldError as exc:
                await self._mark(h, r, "cancelled", {"error": str(exc)})
                run.scheduled_cancelled.append(key)
                continue
            await self._mark(h, r, "processed", {"actor_id": str(actor_id)})
            run.travelled.append(key)
            run.scheduled_processed.append(key)

    async def _plan_clocks(self, h: CampaignHandle, to_tick: int, run: SimulationRun) -> None:
        """Deterministic plan continuation: a due step (`at_tick` ≤ now) that is not a decision
        advances when its prerequisites hold; a failing prerequisite leaves the plan waiting."""
        for plan, goal in await self._active_plans(h):
            advanced = True
            while advanced:
                advanced = False
                steps = list(plan.steps or [])
                if plan.current_step >= len(steps):
                    break
                info = step_info(steps[plan.current_step])
                if (
                    info["kind"] == "decision"
                    or info["at_tick"] is None
                    or info["at_tick"] > to_tick
                ):
                    break
                failed = await self.schedule._failed_prerequisite(info["prerequisites"])
                if failed is not None:
                    run.notes.append(
                        f"plan {plan.id} waits: prerequisite {failed.get('kind')} failed"
                    )
                    break
                async with EventTransaction(self.session, h.campaign_id, h.timeline_id) as tx:
                    await self._advance_plan(tx, plan, "plan clock", game_tick=int(info["at_tick"]))
                run.plan_steps_advanced.append(f"{goal.description[:40]} → {info['title']}")
                advanced = True

    async def _active_plans(self, h: CampaignHandle) -> list[tuple[Plan, Goal]]:
        rows = (
            await self.session.execute(
                select(Plan, Goal)
                .join(Goal, Goal.id == Plan.goal_id)
                .where(Goal.campaign_id == h.campaign_id, Plan.status == "active")
            )
        ).all()
        return [(p, g) for p, g in rows]

    async def _advance_plan(
        self, tx: EventTransaction, plan: Plan, reason: str, *, game_tick: int | None = None
    ) -> None:
        steps = list(plan.steps or [])
        before = plan.current_step
        after = min(before + 1, len(steps))
        event = await tx.emit(
            ev.PlanAdvanced(plan_id=plan.id, from_step=before, to_step=after, reason=reason),
            game_tick=game_tick,
        )
        plan.current_step, plan.updated_event_id = after, event.id
        if after >= len(steps):
            plan.status = "completed"

    async def _mark(
        self, h: CampaignHandle, row: ScheduledEvent, outcome: str, detail: dict[str, Any]
    ) -> None:
        async with EventTransaction(self.session, h.campaign_id, h.timeline_id) as tx:
            fired = await tx.emit(
                ev.ScheduledEventFired(
                    scheduled_event_id=row.id,
                    scheduled_tick=row.scheduled_tick,
                    scheduled_type=row.event_type,
                    outcome=outcome,
                    detail=detail,
                ),
                game_tick=row.scheduled_tick,
            )
            row.processed_event_id = fired.id
            row.status = {"processed": "processed", "cancelled": "cancelled"}.get(
                outcome, "processed"
            )

    # -- candidates ------------------------------------------------------------------------------

    async def _candidates(
        self, h: CampaignHandle, to_tick: int, run: SimulationRun
    ) -> list[Candidate]:
        out: list[Candidate] = []
        n = 0
        # non-deterministic scheduled events that are due: the simulator decides
        for r in await self.schedule.pending(h):
            if (
                r.scheduled_tick > to_tick
                or r.event_type in DETERMINISTIC_TYPES
                or r.event_type == SIM_TRAVEL_TYPE
            ):
                continue
            failed = await self.schedule._failed_prerequisite(r.payload.get("prerequisites", []))
            key = r.payload.get("key") or r.event_type
            if failed is not None:
                await self._mark(h, r, "cancelled", {"failed_prerequisite": failed})
                run.scheduled_cancelled.append(key)
                continue
            n += 1
            out.append(
                Candidate(
                    f"s{n}",
                    "scheduled",
                    r.id,
                    key,
                    f"{r.event_type} due at tick {r.scheduled_tick}: "
                    + str(r.payload.get("question") or "proceed, hold a day, or cancel?"),
                )
            )
        # due decision steps of active plans
        m = 0
        for plan, goal in await self._active_plans(h):
            steps = list(plan.steps or [])
            if plan.current_step >= len(steps):
                continue
            info = step_info(steps[plan.current_step])
            if info["kind"] != "decision" or (
                info["at_tick"] is not None and info["at_tick"] > to_tick
            ):
                continue
            m += 1
            owner = await self._owner_label(goal)
            out.append(
                Candidate(
                    f"p{m}",
                    "plan",
                    plan.id,
                    f"{owner}: {goal.description}",
                    f"step {plan.current_step + 1}/{len(steps)} '{info['title']}' is a decision",
                )
            )
        if len(out) > MAX_CANDIDATES:
            run.notes.append(f"{len(out) - MAX_CANDIDATES} candidate(s) deferred to the next run")
            out = out[:MAX_CANDIDATES]
        return out

    async def _owner_label(self, goal: Goal) -> str:
        if goal.owner_type == "faction":
            f = await self.session.get(Faction, goal.owner_id)
            return f.name if f else "a faction"
        a = await self.session.get(Actor, goal.owner_id)
        if a is None:
            return "someone"
        e = await self.session.get(Entity, a.entity_id)
        return (e.canonical_name if e else None) or "someone"

    # -- the one bounded call --------------------------------------------------------------------

    async def _decide(
        self, h: CampaignHandle, cands: list[Candidate], run: SimulationRun, turn: Turn | None
    ) -> None:
        locations = {
            loc.id: ent.canonical_name or "a place"
            for loc, ent in (
                await self.session.execute(
                    select(Location, Entity)
                    .join(Entity, Entity.id == Location.entity_id)
                    .where(
                        Entity.campaign_id == h.campaign_id, Location.detail_level == "materialized"
                    )
                )
            ).all()
        }
        loc_refs = {f"l{i + 1}": lid for i, lid in enumerate(locations)}
        plans_text = []
        for plan, goal in await self._active_plans(h):
            steps = [step_info(s)["title"] for s in (plan.steps or [])]
            plans_text.append(
                f"{await self._owner_label(goal)} — {goal.description}: "
                f"step {plan.current_step + 1}/"
                f"{len(steps)} ({'; '.join(steps)})"
            )
        sections = {
            "interval": f"From tick {run.from_tick} to tick {run.to_tick} "
            f"({(run.to_tick - run.from_tick) / 3600:.1f} hours).",
            "candidates": "\n".join(f"{c.ref} [{c.kind}] {c.label}: {c.detail}" for c in cands)
            + "\nLocations: "
            + ", ".join(f"{r} {locations[lid]}" for r, lid in loc_refs.items()),
            "plans": "\n".join(plans_text) or "none",
            "deterministic_changes": "; ".join(
                run.scheduled_processed + run.plan_steps_advanced + run.travelled
            )
            or "none",
            "budget": f"Event budget {run.event_budget}; "
            f"proposal types: {', '.join(sorted(PROPOSAL_TYPES))}; "
            "subject_ref must be a candidate ref; actor_travel needs target_ref = a location ref.",
        }
        ctx = await self.compiler.compile(
            h,
            "world_simulator",
            actor_id=None,
            purpose="world simulation run",
            situation="Decide the candidates' meaningful offscreen moves for this interval only.",
            extra_sections=sections,
            now_tick=run.to_tick,
        )
        res = await self.runner.run(h, ctx, turn_id=turn.turn_id if turn else None)
        run.model_calls += res.calls
        if turn is not None:
            turn.record_call(
                "world_simulator",
                calls=res.calls,
                prompt_tokens=res.prompt_tokens,
                completion_tokens=res.completion_tokens,
                context_tokens=ctx.estimated_tokens,
            )
        if not res.ok or not isinstance(res.output, WorldSimulatorOut):
            run.notes.append(
                f"simulator output unusable ({res.status}); plans continue deterministically"
            )
            return
        by_ref = {c.ref: c for c in cands}
        used = 0
        for p in res.output.proposals:
            if used >= run.event_budget:
                run.proposals_rejected.append(
                    {"subject_ref": p.subject_ref, "type": p.type, "reason": "over budget"}
                )
                continue
            c = by_ref.get(p.subject_ref)
            if c is None or p.type not in PROPOSAL_TYPES:
                run.proposals_rejected.append(
                    {
                        "subject_ref": p.subject_ref,
                        "type": p.type,
                        "reason": "unknown subject or type",
                    }
                )
                continue
            try:
                applied = await self._apply(h, c, p, loc_refs, run)
            except WorldError as exc:
                run.proposals_rejected.append(
                    {"subject_ref": p.subject_ref, "type": p.type, "reason": str(exc)}
                )
                continue
            if applied:
                used += 1
                run.proposals_applied.append(
                    {
                        "subject_ref": p.subject_ref,
                        "type": p.type,
                        "justification": p.justification[:160],
                    }
                )

    async def _apply(
        self,
        h: CampaignHandle,
        c: Candidate,
        p: Any,
        loc_refs: dict[str, uuid.UUID],
        run: SimulationRun,
    ) -> bool:
        if c.kind == "scheduled":
            row = await self.session.get(ScheduledEvent, c.id)
            if row is None or row.status != "pending":
                raise WorldError("scheduled candidate is no longer pending")
            if p.type in ("proceed", "plan_advance"):
                await self._proceed(h, row)
                run.scheduled_processed.append(c.label)
                return True
            if p.type in ("plan_hold",):
                delay = int(p.delay_seconds or DAY)
                async with EventTransaction(self.session, h.campaign_id, h.timeline_id) as tx:
                    await tx.emit(
                        ev.ScheduledEventFired(
                            scheduled_event_id=row.id,
                            scheduled_tick=row.scheduled_tick,
                            scheduled_type=row.event_type,
                            outcome="skipped",
                            detail={
                                "held_for_seconds": delay,
                                "justification": p.justification[:160],
                            },
                        ),
                        game_tick=row.scheduled_tick,
                    )
                    row.scheduled_tick = row.scheduled_tick + delay
                return True
            if p.type in ("cancel", "plan_abandon"):
                await self._mark(h, row, "cancelled", {"justification": p.justification[:160]})
                run.scheduled_cancelled.append(c.label)
                return True
            raise WorldError(f"{p.type} does not apply to a scheduled event")
        if c.kind == "plan":
            plan = await self.session.get(Plan, c.id)
            if plan is None or plan.status != "active":
                raise WorldError("plan is no longer active")
            if p.type in ("plan_advance", "proceed"):
                async with EventTransaction(self.session, h.campaign_id, h.timeline_id) as tx:
                    await self._advance_plan(tx, plan, f"simulator: {p.justification[:120]}")
                run.plan_steps_advanced.append(c.label)
                return True
            if p.type == "plan_hold":
                run.notes.append(f"plan held: {p.justification[:120]}")
                return False
            if p.type in ("plan_abandon", "cancel"):
                async with EventTransaction(self.session, h.campaign_id, h.timeline_id) as tx:
                    event = await tx.emit(
                        ev.PlanAdvanced(
                            plan_id=plan.id,
                            from_step=plan.current_step,
                            to_step=plan.current_step,
                            reason=f"abandoned: {p.justification[:120]}",
                        )
                    )
                    plan.status, plan.updated_event_id = "abandoned", event.id
                return True
            raise WorldError(f"{p.type} does not apply to a plan")
        raise WorldError("unsupported candidate kind")

    async def _proceed(self, h: CampaignHandle, row: ScheduledEvent) -> None:
        """A non-deterministic scheduled event the simulator let happen: run its `on_proceed`
        deterministic consequence (if any) and mark it processed."""
        on_proceed = dict(row.payload.get("on_proceed") or {})
        async with EventTransaction(self.session, h.campaign_id, h.timeline_id) as tx:
            fired = await tx.emit(
                ev.ScheduledEventFired(
                    scheduled_event_id=row.id,
                    scheduled_tick=row.scheduled_tick,
                    scheduled_type=row.event_type,
                    outcome="processed",
                    detail={k: v for k, v in row.payload.items() if k != "prerequisites"},
                ),
                game_tick=row.scheduled_tick,
            )
            row.status, row.processed_event_id = "processed", fired.id
            if on_proceed.get("type") in DETERMINISTIC_TYPES:
                shadow = ScheduledEvent(
                    campaign_id=row.campaign_id,
                    timeline_id=row.timeline_id,
                    scheduled_tick=row.scheduled_tick,
                    event_type=on_proceed["type"],
                    payload={k: v for k, v in on_proceed.items() if k != "type"},
                    status="processing",
                )
                await self.schedule._handle(tx, shadow, fired)
            plan_id = row.payload.get("plan_id")
            if plan_id:
                plan = await self.session.get(Plan, uuid.UUID(str(plan_id)))
                if plan is not None and plan.status == "active":
                    await self._advance_plan(
                        tx, plan, f"{row.event_type} proceeded", game_tick=row.scheduled_tick
                    )
