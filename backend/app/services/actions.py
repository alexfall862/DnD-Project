"""ActionService — runs the pure action resolver against persisted state and commits the
result through `EventTransaction` (Milestone 02b).

Flow for `perform()`:
1. load the scene: participants' mechanical state (profile + resource_states +
   condition_instances + possessed items incl. hidden properties), the scene space, the
   encounter, loose items in the scene's zones, the world tick, the scene version;
2. resolve in memory; an `invalid` outcome commits nothing;
3. inside one transaction: re-check the scene version under lock (STALE otherwise), emit one
   ledger Event per semantic mechanic event, persist the Action/steps/trace/rolls rows, write
   back resources, conditions, items, scene state, and advance the clock by the time cost.

Nothing here reads prose and nothing here is perspective-filtered: this is objective truth.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import events as ev
from app.engine.actions import (
    ActionOutcome,
    ActionRequest,
    ActionResolver,
    ReactionChooser,
    SceneContext,
    end_round,
)
from app.engine.core import RulesEngine
from app.engine.effects import apply_steps
from app.engine.encounter import Encounter
from app.engine.positioning import SceneSpace, Zone
from app.engine.stats import ActorState, ItemState
from app.persistence.models import (
    Action,
    ActionStep,
    Actor,
    ConditionInstanceRow,
    Entity,
    Event,
    Item,
    ItemHistory,
    Observation,
    ReactionWindowRecord,
    ResolutionTraceRecord,
    ResourceStateRow,
    Roll,
    Scene,
    SceneParticipant,
    WorldClock,
)
from app.persistence.repositories.perspective import PerspectiveRepository
from app.services.events import EventTransaction
from app.services.observations import ObservationInputs, ObservationService, Observer
from app.services.world import CampaignHandle, WorldError, WorldService


class StaleStateError(RuntimeError):
    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"scene version {expected} is stale; current is {actual}")
        self.expected, self.actual = expected, actual


@dataclass
class LoadedScene:
    scene: Scene
    ctx: SceneContext
    actors: dict[str, Actor]  # actor key (uuid str) -> row
    entities: dict[str, Entity]
    items: dict[str, Item]  # item key (uuid str) -> row
    resources: dict[tuple[uuid.UUID, str], ResourceStateRow]
    conditions: dict[tuple[uuid.UUID, str], ConditionInstanceRow]
    revealed: list[Item] = field(default_factory=list)  # concealed items found by this action


class ActionService:
    def __init__(self, session: AsyncSession, engine: RulesEngine) -> None:
        self.session = session
        self.engine = engine
        self.world = WorldService(session)

    # -- loading -------------------------------------------------------------------------------

    async def load_scene(
        self, h: CampaignHandle, scene_id: uuid.UUID, *, chooser: ReactionChooser | None = None
    ) -> LoadedScene:
        s = self.session
        scene = await s.get(Scene, scene_id)
        if scene is None or scene.campaign_id != h.campaign_id:
            raise WorldError(f"scene {scene_id} not found")
        clock = await s.get(WorldClock, h.timeline_id)
        parts = (
            (
                await s.execute(
                    select(SceneParticipant).where(
                        SceneParticipant.scene_id == scene_id,
                        SceneParticipant.left_event_id.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        actor_ids = [p.actor_id for p in parts]
        actors = (
            {
                str(a.id): a
                for a in (await s.execute(select(Actor).where(Actor.id.in_(actor_ids))))
                .scalars()
                .all()
            }
            if actor_ids
            else {}
        )
        entity_ids = [a.entity_id for a in actors.values()]
        entities = (
            {
                str(e.id): e
                for e in (await s.execute(select(Entity).where(Entity.id.in_(entity_ids))))
                .scalars()
                .all()
            }
            if entity_ids
            else {}
        )
        resources = {}
        conditions = {}
        if entity_ids:
            for r in (
                (
                    await s.execute(
                        select(ResourceStateRow).where(ResourceStateRow.entity_id.in_(entity_ids))
                    )
                )
                .scalars()
                .all()
            ):
                resources[(r.entity_id, r.resource_key)] = r
            for c in (
                (
                    await s.execute(
                        select(ConditionInstanceRow).where(
                            ConditionInstanceRow.target_entity_id.in_(entity_ids),
                            ConditionInstanceRow.status == "active",
                        )
                    )
                )
                .scalars()
                .all()
            ):
                conditions[(c.target_entity_id, c.instance_key)] = c
        held = (
            (
                await s.execute(
                    select(Item).where(
                        Item.possessor_entity_id.in_(entity_ids), Item.destroyed_event_id.is_(None)
                    )
                )
            )
            .scalars()
            .all()
            if entity_ids
            else []
        )
        loose = (
            (
                await s.execute(
                    select(Item).where(
                        Item.location_id == scene.location_id,
                        Item.possessor_entity_id.is_(None),
                        Item.concealed.is_(False),
                        Item.destroyed_event_id.is_(None),
                    )
                )
            )
            .scalars()
            .all()
            if scene.location_id
            else []
        )
        item_entities = {}
        all_items = list(held) + list(loose)
        if all_items:
            item_entities = {
                e.id: e
                for e in (
                    await s.execute(
                        select(Entity).where(Entity.id.in_([i.entity_id for i in all_items]))
                    )
                )
                .scalars()
                .all()
            }

        def item_state(i: Item) -> ItemState:
            return ItemState(
                instance_key=str(i.id),
                def_key=i.template_key or "item.travel_supplies",
                name=item_entities[i.entity_id].canonical_name or "",
                equipped=bool(i.mechanical_snapshot.get("equipped", False)),
                public=dict(i.public_properties),
                hidden=dict(i.hidden_properties),
            )

        states: dict[str, ActorState] = {}
        for key, a in actors.items():
            profile = dict(a.mechanical_profile)
            profile["equipment"] = [
                item_state(i).to_dict(include_hidden=True)
                for i in held
                if i.possessor_entity_id == a.entity_id
            ]
            profile["resources"] = {
                rk: {"current": r.current}
                for (eid, rk), r in resources.items()
                if eid == a.entity_id
            }
            profile["conditions"] = [
                {
                    "key": c.condition_key,
                    "intensity": c.intensity,
                    "source": c.source_ref,
                    "applied_tick": c.start_tick,
                    "expires_tick": c.expiry_tick,
                    "instance_id": c.instance_key,
                }
                for (eid, _), c in conditions.items()
                if eid == a.entity_id
            ]
            states[key] = self.engine.actor(key, profile)
        space_dict = scene.state.get("space")
        if space_dict:
            space = SceneSpace.from_dict(space_dict)
        else:
            space = SceneSpace([Zone("here")], [])
        for key in states:
            if key not in space.positions:
                space.place(key, next(iter(space.zones)))
        encounter = (
            Encounter.from_dict(scene.state["encounter"]) if scene.state.get("encounter") else None
        )
        ground: dict[str, list[ItemState]] = {}
        for i in loose:
            ground.setdefault(i.zone_key or next(iter(space.zones)), []).append(item_state(i))
        ctx = SceneContext(
            self.engine,
            states,
            space,
            encounter,
            tick=clock.current_tick if clock else 0,
            chooser=chooser,
            ground=ground,
            scene_version=scene.version,
        )
        items = {str(i.id): i for i in all_items}
        return LoadedScene(scene, ctx, actors, entities, items, resources, conditions)

    # -- actions -------------------------------------------------------------------------------

    async def perform(
        self,
        h: CampaignHandle,
        scene_id: uuid.UUID,
        request: ActionRequest,
        *,
        chooser: ReactionChooser | None = None,
        turn_id: uuid.UUID | None = None,
    ) -> ActionOutcome:
        loaded = await self.load_scene(h, scene_id, chooser=chooser)
        outcome = ActionResolver(loaded.ctx).resolve(request)
        if outcome.status == "invalid":
            return outcome  # nothing was written; the read transaction stays open for the caller
        if request.action_key == "action.search" and outcome.status == "succeeded":
            await self._reveal_concealed(loaded, outcome, request)
        await self._commit(h, loaded, outcome, request, turn_id)
        return outcome

    async def _reveal_concealed(
        self, loaded: LoadedScene, outcome: ActionOutcome, request: ActionRequest
    ) -> None:
        """A successful search of a zone uncovers the concealed items lying there whose
        concealment difficulty the check total meets (rules-engine §22: the item becomes
        visible; its hidden mechanics stay hidden). Observations and clue discoveries follow in
        `_commit` from the `item.revealed` events."""
        zone = request.target or loaded.ctx.space.position(request.actor).zone
        if loaded.scene.location_id is None:
            return
        rows = (
            (
                await self.session.execute(
                    select(Item).where(
                        Item.location_id == loaded.scene.location_id,
                        Item.zone_key == zone,
                        Item.concealed.is_(True),
                        Item.destroyed_event_id.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return
        total = outcome.check.total if outcome.check else None
        scale = self.engine.ruleset.manifest.difficulty_scale
        for row in rows:
            need = row.mechanical_snapshot.get("concealment_difficulty")
            if need is not None and total is not None and total < int(scale.get(need, need)):
                continue
            ent = await self.session.get(Entity, row.entity_id)
            name = (ent.canonical_name if ent else None) or row.template_key or "something"
            outcome.events.append(
                {
                    "type": "item.revealed",
                    "actor": request.actor,
                    "item": str(row.id),
                    "zone": zone,
                    "name": name,
                }
            )
            loaded.revealed.append(row)

    async def perform_improvised(
        self,
        h: CampaignHandle,
        scene_id: uuid.UUID,
        actor_key: str,
        ruling: dict[str, Any],
        *,
        description: str,
        chooser: ReactionChooser | None = None,
        turn_id: uuid.UUID | None = None,
    ) -> ActionOutcome:
        """Execute a Rules Adjudicator ruling (rules-engine §31): an optional check, then the
        on_success / on_failure effect compositions, all through registered primitives. The
        ruling must already be validated (`validate_ruling`). Committed like any action."""
        loaded = await self.load_scene(h, scene_id, chooser=chooser)
        ctx = loaded.ctx
        from app.engine.actions import ActionRequest as _AR

        if actor_key not in ctx.states:
            req0 = _AR(actor_key, "action.improvised", None, params={}, source="human")
            return ActionOutcome(req0, "invalid", reason="you are not there any more")
        state = ctx.states[actor_key]
        from app.engine.actions import ResolutionTrace, StepRecord

        req = _AR(
            actor_key,
            "action.improvised",
            None,
            params={"description": description, "ruling": ruling},
            source="human",
        )
        trace = ResolutionTrace(
            "action.improvised",
            actor_key,
            None,
            rules_consulted=["rules_adjudicator"],
            summary=f"{actor_key} improvises: {description}",
        )
        out = ActionOutcome(req, "resolving", trace=trace)
        if state.has_condition("condition.incapacitated"):
            out.status, out.reason = "invalid", "actor is incapacitated"
            return out
        if ctx.in_combat and ctx.encounter is not None:
            budget = ctx.encounter.budget(actor_key)
            if not budget.can_pay({"major": True}):
                out.status, out.reason = "invalid", "no major action left this turn"
                return out
            budget.pay({"major": True})
            trace.costs_paid = {"major": True}
        success = True
        check = ruling.get("check") if ruling.get("requires_check") else None
        if check:
            r = self.engine.check(
                state,
                check.get("check", "check.core"),
                attribute=check.get("attribute"),
                skill=check.get("skill"),
                difficulty=check.get("difficulty", "moderate"),
                # named after what is tested, so the player sees "persuasion", not "improvised"
                purpose=str(
                    check.get("purpose")
                    or (check.get("skill") or check.get("attribute") or "improvised").split(".")[-1]
                ),
            )
            step = StepRecord(
                "check",
                "ok",
                {"total": r.total, "target": r.target, "degree": r.degree, "success": r.success},
            )
            step.rolls.append(r.roll)
            out.steps.append(step)
            out.check = r
            trace.rules_consulted += list(r.rules_consulted)
            out.events.append(
                {
                    "type": "check.rolled",
                    "actor": actor_key,
                    "action": "action.improvised",
                    "check": r.check_key,
                    "total": r.total,
                    "versus": r.target,
                    "success": r.success,
                    "degree": r.degree,
                }
            )
            success = bool(r.success)
        steps = ruling.get("on_success" if success else "on_failure") or []
        if steps:
            step = StepRecord(
                "effects", "ok", {"branch": "on_success" if success else "on_failure"}
            )
            ectx = ctx.effect_ctx(actor_key)
            step.mutations += apply_steps(steps, state, ectx)
            step.rolls += ectx.rolls
            out.steps.append(step)
        out.status = "succeeded" if success else "failed"
        out.time_cost_seconds = 0 if ctx.in_combat else int(ruling.get("time_cost_seconds", 6))
        trace.rolls = [r for s_ in out.steps for r in s_.rolls]
        trace.mutations = out.mutations
        trace.effects_applied = [
            {"kind": m.kind, "field": m.field, "before": m.before, "after": m.after}
            for m in out.mutations
        ]
        out.events.append(
            {
                "type": "action.resolved",
                "actor": actor_key,
                "action": "action.improvised",
                "target": None,
                "status": out.status,
                "time_cost_seconds": out.time_cost_seconds,
            }
        )
        await self._commit(h, loaded, out, req, turn_id)
        return out

    async def start_encounter(
        self, h: CampaignHandle, scene_id: uuid.UUID, sides: dict[uuid.UUID, str]
    ) -> Encounter:
        loaded = await self.load_scene(h, scene_id)
        enc = Encounter(
            str(scene_id), list(loaded.ctx.states), {str(k): v for k, v in sides.items()}
        )
        enc.start(self.engine, loaded.ctx.states)
        loaded.ctx.encounter = enc
        async with self._locked(h, loaded) as tx:
            event = await tx.emit(
                ev.EncounterStarted(
                    scene_id=scene_id, order=[e.actor for e in enc.order], sides=enc.sides
                ),
                scene=loaded.scene,
            )
            await self._persist_rolls(h, loaded, event, loaded.ctx.engine.dice.history)
            self._write_scene_state(loaded)
        return enc

    async def next_turn(self, h: CampaignHandle, scene_id: uuid.UUID) -> tuple[str | None, bool]:
        """Advance the encounter; on a new round fire end-of-round triggers and advance the
        clock by one combat round."""
        loaded = await self.load_scene(h, scene_id)
        enc = loaded.ctx.encounter
        if enc is None:
            raise WorldError("no encounter in this scene")
        actor, new_round = enc.advance_turn()
        async with self._locked(h, loaded) as tx:
            if new_round:
                before = loaded.ctx.tick
                end_round(loaded.ctx)
                event = await tx.emit(
                    ev.EncounterRoundEnded(scene_id=scene_id, round=enc.round - 1),
                    scene=loaded.scene,
                )
                await self._persist_rolls(h, loaded, event, loaded.ctx.engine.dice.history)
                await self.world._advance_clock(
                    tx,
                    loaded.ctx.tick - before,
                    reason="combat_round",
                    cause=event,
                    scene=loaded.scene,
                )
            if enc.status == "ended":
                await tx.emit(
                    ev.EncounterEnded(
                        scene_id=scene_id,
                        standing=sorted(enc.living_sides(loaded.ctx.states)),
                        rounds=enc.round,
                    ),
                    scene=loaded.scene,
                )
            elif not new_round:
                tx.touch_scene(loaded.scene)
                await tx.emit(
                    ev.ActionResolved(actor=actor or "", action="turn.advance", status="succeeded"),
                    scene=loaded.scene,
                )
            await self._write_actor_states(loaded, tx)
            self._write_scene_state(loaded)
        return actor, new_round

    # -- commit --------------------------------------------------------------------------------

    def _locked(self, h: CampaignHandle, loaded: LoadedScene) -> EventTransaction:
        return _VersionCheckedTransaction(self.session, h, loaded)

    async def _commit(
        self,
        h: CampaignHandle,
        loaded: LoadedScene,
        outcome: ActionOutcome,
        request: ActionRequest,
        turn_id: uuid.UUID | None,
    ) -> None:
        actor_row = loaded.actors[request.actor]
        async with self._locked(h, loaded) as tx:
            tx.created_by_type = request.source
            tx.created_by_id = actor_row.id
            action = Action(
                campaign_id=h.campaign_id,
                actor_id=actor_row.id,
                scene_id=loaded.scene.id,
                action_key=request.action_key,
                target_ref=request.target,
                status=outcome.status,
                params=request.params,
                reason=outcome.reason or None,
                based_on_scene_version=request.based_on_scene_version,
                costs=dict(outcome.trace.costs_paid) if outcome.trace else {},
                requirements={
                    "checked": [
                        {"expr": e, "ok": ok}
                        for e, ok in (outcome.trace.requirements if outcome.trace else [])
                    ]
                },
                turn_id=turn_id,
            )
            self.session.add(action)
            await self.session.flush()
            resolved: Event | None = None
            emitted: list[tuple[Event, dict[str, Any]]] = []
            for e in outcome.events:
                payload = dict(e)
                etype = payload.pop("type")
                cls = ev.PAYLOAD_TYPES.get(etype)
                if cls is None:
                    continue
                if etype == "action.resolved":
                    payload["action_id"] = str(action.id)
                subject = loaded.actors.get(payload.get("actor", ""))
                event = await tx.emit(
                    cls.model_validate(payload),
                    scene=loaded.scene,
                    location_id=loaded.scene.location_id,
                    entities=[(subject.entity_id, "actor")] if subject else [],
                )
                emitted.append((event, payload))
                if etype == "action.resolved":
                    resolved = event
            assert resolved is not None
            action.resolution_event_id = resolved.id
            await self._observe(h, loaded, tx, emitted)
            await self._persist_reveals(loaded, tx, emitted)
            for idx, step in enumerate(outcome.steps):
                self.session.add(
                    ActionStep(
                        action_id=action.id,
                        order_index=idx,
                        kind=step.kind,
                        status=step.status,
                        payload={**step.detail, "mutations": [m.__dict__ for m in step.mutations]},
                        resolved_event_id=resolved.id,
                    )
                )
            roll_rows = await self._persist_rolls(
                h, loaded, resolved, outcome.trace.rolls if outcome.trace else []
            )
            if outcome.trace:
                for r in outcome.trace.reactions:
                    self.session.add(
                        ReactionWindowRecord(
                            action_id=action.id,
                            trigger=r.get("action", "reaction"),
                            chosen=r,
                            closed_event_id=resolved.id,
                        )
                    )
                t = outcome.trace
                self.session.add(
                    ResolutionTraceRecord(
                        action_id=action.id,
                        rules_consulted=t.rules_consulted,
                        requirements=[{"expr": e, "ok": ok} for e, ok in t.requirements],
                        modifiers=t.modifiers,
                        roll_ids=[str(r.id) for r in roll_rows],
                        effects_applied=t.effects_applied,
                        effects_rejected=t.effects_rejected,
                        summary=t.summary,
                        trace={
                            **t.to_dict(),
                            "steps": [
                                {"kind": s.kind, "status": s.status, **s.detail}
                                for s in outcome.steps
                            ],
                        },
                    )
                )
            await self._write_actor_states(loaded, tx, resolved)
            await self._write_items(loaded, outcome, resolved)
            # an encounter can end on any action (last foe surrenders, flees, falls): the
            # ledger records it here, not only on an explicit turn advance
            prev_enc = (loaded.scene.state.get("encounter") or {}).get("status")
            enc = loaded.ctx.encounter
            if prev_enc == "active" and enc is not None and enc.status == "ended":
                await tx.emit(
                    ev.EncounterEnded(
                        scene_id=loaded.scene.id,
                        standing=sorted(enc.living_sides(loaded.ctx.states)),
                        rounds=enc.round,
                    ),
                    scene=loaded.scene,
                    cause=resolved,
                )
            self._write_scene_state(loaded)
            if outcome.time_cost_seconds:
                await self.world._advance_clock(
                    tx,
                    outcome.time_cost_seconds,
                    reason=f"action:{request.action_key}",
                    cause=resolved,
                    scene=loaded.scene,
                )

    async def _observe(
        self,
        h: CampaignHandle,
        loaded: LoadedScene,
        tx: EventTransaction,
        emitted: list[tuple[Event, dict[str, Any]]],
    ) -> None:
        """Every mechanic event becomes per-observer Observations (observation-authoring §2)."""
        repo = PerspectiveRepository(self.session)
        observers: dict[str, Observer] = {}
        identity: dict[uuid.UUID, dict[uuid.UUID, str]] = {}
        hidden: set[str] = set()
        for key, st in loaded.ctx.states.items():
            a = loaded.actors[key]
            observers[key] = Observer(
                actor_id=a.id,
                entity_id=a.entity_id,
                senses={c for c in st.capabilities if c.startswith("sense:")}
                or {"sense:vision", "sense:hearing"},
                incapacitated=st.has_condition("condition.incapacitated"),
                detected=set(loaded.ctx.detected.get(key, set())),
            )
            identity[a.id] = {
                eid: row.known_name for eid, row in (await repo.identity_knowledge(a.id)).items()
            }
            if st.has_condition("condition.hidden"):
                hidden.add(key)
        actor_entity = {key: loaded.actors[key].entity_id for key in loaded.ctx.states}
        descriptors = {
            e.id: (e.metadata_ or {}).get("descriptor") or "a stranger"
            for e in loaded.entities.values()
        }
        inputs = ObservationInputs(observers, hidden, identity, actor_entity, descriptors)
        svc = ObservationService(self.session)
        for event, payload in emitted:
            await svc.observe(tx, event, payload, loaded.scene, inputs)

    async def _persist_reveals(
        self,
        loaded: LoadedScene,
        tx: EventTransaction,
        emitted: list[tuple[Event, dict[str, Any]]],
    ) -> None:
        """Concealed items found by a search become visible; everyone who observed the find
        discovers the clues the object carries (physical clues are evidence; document clues
        are only found, their content is learned by reading)."""
        if not loaded.revealed:
            return
        from app.services.mystery import MysteryService

        mystery = MysteryService(self.session)
        by_item = {str(i.id): i for i in loaded.revealed}
        await self.session.flush()
        for event, payload in emitted:
            if event.event_type != "item.revealed":
                continue
            row = by_item.get(payload.get("item", ""))
            if row is None:
                continue
            row.concealed = False
            self.session.add(
                ItemHistory(
                    item_id=row.id,
                    event_id=event.id,
                    change_type="revealed",
                    payload={"zone": payload.get("zone"), "by": payload.get("actor")},
                )
            )
            observers = list(
                (
                    await self.session.execute(
                        select(Observation.actor_id).where(Observation.source_event_id == event.id)
                    )
                )
                .scalars()
                .all()
            )
            await mystery.discover_physical(
                tx, entity_id=row.entity_id, observer_actor_ids=observers, cause=event
            )

    async def _persist_rolls(
        self, h: CampaignHandle, loaded: LoadedScene, event: Event, records
    ) -> list[Roll]:
        rows: list[Roll] = []
        for r in records:
            actor_key = r.extra.get("actor") if r.extra else None
            actor_row = loaded.actors.get(actor_key) if actor_key else None
            row = Roll(
                campaign_id=h.campaign_id,
                timeline_id=h.timeline_id,
                event_id=event.id,
                actor_id=actor_row.id if actor_row else None,
                expression=r.expression,
                seed=r.seed,
                raw=list(r.raw),
                kept=list(r.kept),
                modifier=r.modifier,
                final_result=r.total,
                purpose=r.purpose,
                visibility=r.visibility,
            )
            self.session.add(row)
            rows.append(row)
        await self.session.flush()
        loaded.ctx.engine.dice.history.clear()
        return rows

    async def _write_actor_states(
        self, loaded: LoadedScene, tx: EventTransaction, event: Event | None = None
    ) -> None:
        event_id = event.id if event else (tx.events[-1].id if tx.events else None)
        for key, st in loaded.ctx.states.items():
            a = loaded.actors[key]
            profile = st.to_profile()
            for k in ("equipment", "resources", "conditions"):
                profile.pop(k, None)
            a.mechanical_profile = profile
            a.updated_event_id = event_id
            for rk, rs in st.resources.items():
                row = loaded.resources.get((a.entity_id, rk))
                mx = self.engine.calc.resource_max(st, rk).value
                if row is None:
                    row = ResourceStateRow(
                        entity_id=a.entity_id,
                        resource_key=rk,
                        current=rs.current,
                        max_value=mx,
                        last_changed_event_id=event_id,
                    )
                    self.session.add(row)
                    loaded.resources[(a.entity_id, rk)] = row
                elif row.current != rs.current or row.max_value != mx:
                    row.current, row.max_value, row.last_changed_event_id = rs.current, mx, event_id
            live = {c.instance_id: c for c in st.conditions}
            for (eid, ikey), row in list(loaded.conditions.items()):
                if eid != a.entity_id:
                    continue
                c = live.pop(ikey, None)
                if c is None:
                    row.status, row.ended_event_id = "ended", event_id
                elif row.intensity != c.intensity or row.expiry_tick != c.expires_tick:
                    row.intensity, row.expiry_tick = c.intensity, c.expires_tick
            for ikey, c in live.items():
                row = ConditionInstanceRow(
                    target_entity_id=a.entity_id,
                    condition_key=c.key,
                    instance_key=ikey,
                    intensity=c.intensity,
                    source_ref=c.source,
                    source_event_id=event_id,
                    start_tick=c.applied_tick,
                    expiry_tick=c.expires_tick,
                )
                self.session.add(row)
                loaded.conditions[(a.entity_id, ikey)] = row

    async def _write_items(self, loaded: LoadedScene, outcome: ActionOutcome, event: Event) -> None:
        for st_key, st in loaded.ctx.states.items():
            a = loaded.actors[st_key]
            for it in st.equipment:
                row = loaded.items.get(it.instance_key)
                if row is None:
                    continue
                changed = row.possessor_entity_id != a.entity_id
                if changed:
                    row.possessor_entity_id, row.location_id, row.zone_key = a.entity_id, None, None
                    self.session.add(
                        ItemHistory(
                            item_id=row.id,
                            event_id=event.id,
                            change_type="possession",
                            payload={"to_actor": st_key, "history": it.history[-1:]},
                        )
                    )
                if row.mechanical_snapshot.get("equipped") != it.equipped:
                    row.mechanical_snapshot = {**row.mechanical_snapshot, "equipped": it.equipped}
                if row.public_properties != it.public:
                    self.session.add(
                        ItemHistory(
                            item_id=row.id,
                            event_id=event.id,
                            change_type="property_revealed",
                            payload={"public": it.public},
                        )
                    )
                    row.public_properties = dict(it.public)
        for zone, items in loaded.ctx.ground.items():
            for it in items:
                row = loaded.items.get(it.instance_key)
                if row is None or (row.possessor_entity_id is None and row.zone_key == zone):
                    continue
                row.possessor_entity_id, row.location_id, row.zone_key = (
                    None,
                    loaded.scene.location_id,
                    zone,
                )
                row.mechanical_snapshot = {**row.mechanical_snapshot, "equipped": False}
                self.session.add(
                    ItemHistory(
                        item_id=row.id,
                        event_id=event.id,
                        change_type="dropped",
                        payload={"zone": zone},
                    )
                )

    def _write_scene_state(self, loaded: LoadedScene) -> None:
        ctx = loaded.ctx
        state = dict(loaded.scene.state)
        state["space"] = ctx.space.to_dict()
        state["encounter"] = ctx.encounter.to_dict() if ctx.encounter else None
        loaded.scene.state = state
        loaded.scene.local_tick = (
            min(ctx.tick, loaded.scene.local_tick) if False else loaded.scene.local_tick
        )


class _VersionCheckedTransaction(EventTransaction):
    """EventTransaction that re-reads the scene under the campaign lock and refuses to commit
    if its version moved since the scene was loaded (optimistic revalidation, schema §18)."""

    def __init__(self, session: AsyncSession, h: CampaignHandle, loaded: LoadedScene) -> None:
        super().__init__(session, h.campaign_id, h.timeline_id)
        self.loaded = loaded

    async def __aenter__(self) -> _VersionCheckedTransaction:
        await super().__aenter__()
        scene = (
            await self.session.execute(
                select(Scene)
                .where(Scene.id == self.loaded.scene.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        actual = scene.version
        if actual != self.loaded.ctx.scene_version:
            await self.session.rollback()
            raise StaleStateError(self.loaded.ctx.scene_version, actual)
        self.loaded.scene = scene
        self.touch_scene(scene)
        return self
