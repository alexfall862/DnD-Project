"""Action state machine and resolution (rules-engine §10–§12, §16–§20, §27, §33;
core-adventure §8–§11).

`ActionResolver` turns an `ActionRequest` into an `ActionOutcome`:

    proposed → validated (targeting, range, requirements, economy, costs) → resolving
    (ordered steps; reaction windows between them) → succeeded | failed | partial | interrupted
    | cancelled | invalid

Everything the resolver decides is written into a `ResolutionTrace`. The resolver is pure: it
mutates in-memory `ActorState`s and the `SceneSpace`, and returns semantic `events` the owning
service commits as ledger Events in one transaction. Reactions are chosen by a caller-supplied
`ReactionChooser` (scripted in tests, AI/orchestrator-driven later); the resolver only ever
offers reactions the rules permit and charges the reaction budget.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.engine.checks import CheckResult
from app.engine.dice import RollRecord
from app.engine.effects import EffectContext, EffectError, Mutation, apply_steps
from app.engine.encounter import Encounter
from app.engine.expressions import ExpressionError, compile_expr, evaluate, evaluate_int
from app.engine.positioning import COVER_LEVELS, PositionError, SceneSpace
from app.engine.ruleset import ActionDef, EquipmentDef
from app.engine.stats import ActorState, ItemState

if TYPE_CHECKING:
    from app.engine.core import RulesEngine

STATUSES = (
    "proposed",
    "validated",
    "resolving",
    "succeeded",
    "failed",
    "partial",
    "interrupted",
    "cancelled",
    "invalid",
)
REACTION_ONLY_KINDS = {"defend", "protect"}


class ActionError(ValueError):
    pass


# ---------------------------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------------------------


@dataclass
class ActionRequest:
    actor: str
    action_key: str
    target: str | None = None  # actor key | zone key | item instance key, per targeting.type
    params: dict[str, Any] = field(default_factory=dict)
    based_on_scene_version: int | None = None
    source: str = "engine"  # human | ai | scripted | engine


@dataclass
class ReactionWindow:
    trigger: str  # attacked | ally_attacked | enemy_disengases
    acting_actor: str
    target: str | None
    eligible: list[tuple[str, str]]  # (reactor, action key)
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReactionChoice:
    reactor: str
    action_key: str
    target: str | None = None


ReactionChooser = Callable[[ReactionWindow], ReactionChoice | None]


@dataclass
class StepRecord:
    kind: str
    status: str
    detail: dict[str, Any] = field(default_factory=dict)
    mutations: list[Mutation] = field(default_factory=list)
    rolls: list[RollRecord] = field(default_factory=list)


@dataclass
class ResolutionTrace:
    action_key: str
    actor: str
    target: str | None
    rules_consulted: list[str] = field(default_factory=list)
    requirements: list[tuple[str, bool]] = field(default_factory=list)
    costs_paid: dict[str, Any] = field(default_factory=dict)
    modifiers: list[dict[str, Any]] = field(default_factory=list)
    rolls: list[RollRecord] = field(default_factory=list)
    effects_applied: list[dict[str, Any]] = field(default_factory=list)
    effects_rejected: list[dict[str, Any]] = field(default_factory=list)
    mutations: list[Mutation] = field(default_factory=list)
    reactions: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_key": self.action_key,
            "actor": self.actor,
            "target": self.target,
            "rules_consulted": self.rules_consulted,
            "requirements": [{"expr": e, "ok": ok} for e, ok in self.requirements],
            "costs_paid": self.costs_paid,
            "modifiers": self.modifiers,
            "rolls": [r.__dict__ for r in self.rolls],
            "effects_applied": self.effects_applied,
            "effects_rejected": self.effects_rejected,
            "mutations": [m.__dict__ for m in self.mutations],
            "reactions": self.reactions,
            "summary": self.summary,
        }


@dataclass
class ActionOutcome:
    request: ActionRequest
    status: str
    reason: str = ""
    steps: list[StepRecord] = field(default_factory=list)
    trace: ResolutionTrace | None = None
    check: CheckResult | None = None
    time_cost_seconds: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in ("succeeded", "partial")

    @property
    def mutations(self) -> list[Mutation]:
        return [m for s in self.steps for m in s.mutations]


# ---------------------------------------------------------------------------------------------
# Combat / scene context
# ---------------------------------------------------------------------------------------------


@dataclass
class SceneContext:
    engine: RulesEngine
    states: dict[str, ActorState]
    space: SceneSpace
    encounter: Encounter | None = None
    tick: int = 0
    chooser: ReactionChooser | None = None
    ground: dict[str, list[ItemState]] = field(default_factory=dict)  # zone -> loose items
    scene_version: int = 0
    detected: dict[str, set[str]] = field(
        default_factory=dict
    )  # observer -> hidden actors it has detected

    @property
    def in_combat(self) -> bool:
        return self.encounter is not None and self.encounter.status == "active"

    def effect_ctx(self, source: str | None, **values: Any) -> EffectContext:
        merged = {"states": self.states, "space": self.space, "ground": self.ground, **values}
        return self.engine.context(tick=self.tick, source=source, **merged)


# ---------------------------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------------------------


class ActionResolver:
    def __init__(self, ctx: SceneContext) -> None:
        self.ctx = ctx
        self.engine = ctx.engine
        self.rs = ctx.engine.ruleset

    # -- entry -------------------------------------------------------------------------------

    def resolve(self, req: ActionRequest, *, as_reaction: bool = False) -> ActionOutcome:
        trace = ResolutionTrace(req.action_key, req.actor, req.target)
        out = ActionOutcome(req, "proposed", trace=trace)
        try:
            adef = self._validate(req, trace, as_reaction)
        except ActionError as exc:
            out.status = "invalid"
            out.reason = str(exc)
            trace.summary = f"invalid: {exc}"
            return out
        out.status = "resolving"
        self._pay_costs(req, adef, trace)
        try:
            self._dispatch(req, adef, out)
        except (EffectError, PositionError, ActionError) as exc:
            # costs were paid and partial mutations may stand: a failed action is still an
            # action that resolved, so it gets its ledger event like any other
            out.status = "failed"
            out.reason = str(exc)
            trace.summary = f"failed: {exc}"
        if out.status == "resolving":
            out.status = "succeeded"
        out.time_cost_seconds = 0 if self.ctx.in_combat else adef.time_cost_seconds
        trace.rolls = [r for s in out.steps for r in s.rolls]
        trace.mutations = out.mutations
        trace.effects_applied = [
            {"kind": m.kind, "field": m.field, "before": m.before, "after": m.after}
            for m in out.mutations
        ]
        if not trace.summary:
            trace.summary = (
                f"{req.actor} {adef.name.lower()}"
                + (f" -> {req.target}" if req.target else "")
                + f": {out.status}"
            )
        out.events.append(
            {
                "type": "action.resolved",
                "actor": req.actor,
                "action": req.action_key,
                "target": req.target,
                "status": out.status,
                "time_cost_seconds": out.time_cost_seconds,
            }
        )
        if self.ctx.encounter is not None:
            self.ctx.encounter.maybe_end(self.ctx.states)
        return out

    # -- validation --------------------------------------------------------------------------

    def _state(self, key: str) -> ActorState:
        try:
            return self.ctx.states[key]
        except KeyError:
            raise ActionError(f"unknown actor {key!r}") from None

    def _facts(self, actor: str, state: ActorState) -> dict[str, Any]:
        weapon = state.weapon(self.rs)
        wdef = self.rs.equipment[weapon.def_key]
        in_scene = actor in self.ctx.space.positions
        pos = self.ctx.space.position(actor) if in_scene else None
        return {
            "has_weapon": True,
            "has_melee_weapon": wdef.melee,
            "has_ranged_weapon": not wdef.melee,
            "is_engaged": bool(pos and pos.engaged_with),
            "cover_available": bool(
                pos and self.ctx.space.zones[pos.zone].cover != "none" and not pos.engaged_with
            ),
            "in_combat": self.ctx.in_combat,
            "incapacitated": state.has_condition("condition.incapacitated"),
        }

    def _validate(self, req: ActionRequest, trace: ResolutionTrace, as_reaction: bool) -> ActionDef:
        adef = self.rs.actions.get(req.action_key)
        if adef is None:
            raise ActionError(f"unknown action {req.action_key!r}")
        trace.rules_consulted.append(req.action_key)
        if (
            req.based_on_scene_version is not None
            and req.based_on_scene_version != self.ctx.scene_version
        ):
            raise ActionError(
                f"stale: scene version {req.based_on_scene_version} != {self.ctx.scene_version}"
            )
        state = self._state(req.actor)
        if state.has_condition("condition.incapacitated"):
            raise ActionError(f"{req.actor} is incapacitated")
        if adef.reaction_trigger and not as_reaction:
            raise ActionError(f"{req.action_key} can only be used as a reaction")
        if self.ctx.in_combat and not as_reaction and self.ctx.encounter.current_actor != req.actor:  # type: ignore[union-attr]
            raise ActionError(f"not {req.actor}'s turn")
        # targeting
        t = adef.targeting
        if t.type == "none":
            if req.target is not None:
                raise ActionError("action takes no target")
        elif t.type == "self":
            if req.target not in (None, req.actor):
                raise ActionError("self-targeted action")
        elif t.type == "actor":
            if req.target is None:
                raise ActionError("target required")
            target = self._state(req.target)
            if req.target == req.actor:
                raise ActionError("cannot target self")
            if req.target not in self.ctx.space.positions:
                raise ActionError(f"{req.target} is not in the scene")
            if target.has_condition("condition.hidden") and req.target not in self.ctx.detected.get(
                req.actor, set()
            ):
                raise ActionError(f"{req.target} is hidden from {req.actor}")
            if self.ctx.space.position(req.target).cover == "total" and not self.ctx.space.engaged(
                req.target, req.actor
            ):
                raise ActionError(f"{req.target} is in total cover")
            band = self.ctx.space.band(req.actor, req.target)
            if t.bands and band not in t.bands:
                raise ActionError(f"target is {band}; allowed {t.bands}")
            enc = self.ctx.encounter
            if enc is not None:
                if t.hostile_only and not enc.hostile(req.actor, req.target):
                    raise ActionError("target is not hostile")
                if t.ally_only and enc.hostile(req.actor, req.target):
                    raise ActionError("target is not an ally")
            trace.rules_consulted.append(f"band:{band}")
        elif t.type == "zone":
            if req.target is None or req.target not in self.ctx.space.zones:
                raise ActionError(f"unknown zone {req.target!r}")
        elif t.type == "item":
            if req.target is None:
                raise ActionError("item required")
        # requirements
        facts = self._facts(req.actor, state)
        resolver = self.engine.calc.resolver(state, facts)
        for f in adef.requirements:
            try:
                ok = bool(evaluate(compile_expr(f), resolver))
            except ExpressionError as exc:
                raise ActionError(f"requirement {f!r}: {exc}") from exc
            trace.requirements.append((str(f), ok))
            if not ok:
                raise ActionError(f"requirement not met: {f}")
        # economy + resource costs
        if self.ctx.in_combat:
            budget = self.ctx.encounter.budget(req.actor)  # type: ignore[union-attr]
            if not budget.can_pay(adef.cost):
                raise ActionError(
                    "no "
                    + ", ".join(
                        k
                        for k, v in adef.cost.items()
                        if v and k in ("major", "movement", "reaction")
                    )
                    + " left this turn"
                )
        for rk, amount in adef.cost.items():
            if rk.startswith("resource.") and state.resources[rk].current < int(amount):
                raise ActionError(f"not enough {rk}")
        return adef

    def _pay_costs(self, req: ActionRequest, adef: ActionDef, trace: ResolutionTrace) -> None:
        state = self._state(req.actor)
        if self.ctx.in_combat:
            self.ctx.encounter.budget(req.actor).pay(adef.cost)  # type: ignore[union-attr]
        for rk, amount in adef.cost.items():
            if rk.startswith("resource."):
                state.resources[rk].current -= int(amount)
        trace.costs_paid = {k: v for k, v in adef.cost.items() if v}

    # -- dispatch ----------------------------------------------------------------------------

    def _dispatch(self, req: ActionRequest, adef: ActionDef, out: ActionOutcome) -> None:
        kind = adef.resolution.kind
        handler = {
            "attack": self._attack,
            "move": self._move,
            "engage": self._engage,
            "disengage": self._disengage,
            "take_cover": self._take_cover,
            "rest": self._rest,
            "check": self._check,
            "effects": self._effects,
            "surrender": self._effects,
            "flee": self._flee,
            "pickup": self._pickup,
            "drop": self._drop,
            "wait": self._wait,
            "defend": self._wait,
            "protect": self._wait,
        }.get(kind)
        if handler is None:
            raise ActionError(f"unsupported resolution kind {kind!r}")
        handler(req, adef, out)

    def _clear_cover(self, out: ActionOutcome, step: StepRecord, actor: str) -> None:
        if self._state(actor).has_condition("condition.in_cover"):
            self._apply(
                out,
                step,
                actor,
                [
                    {
                        "type": "remove_condition",
                        "params": {"condition": "condition.in_cover", "all": True},
                    }
                ],
            )

    def _step(
        self, out: ActionOutcome, step_kind: str, status: str = "ok", **detail: Any
    ) -> StepRecord:
        s = StepRecord(step_kind, status, detail)
        out.steps.append(s)
        return s

    def _apply(
        self, out: ActionOutcome, step: StepRecord, actor: str, steps: list, **values: Any
    ) -> list[Mutation]:
        if not steps:
            return []
        ectx = self.ctx.effect_ctx(actor, **values)
        muts = apply_steps(steps, self._state(actor), ectx)
        step.mutations += muts
        step.rolls += ectx.rolls
        return muts

    # -- reactions ---------------------------------------------------------------------------

    def _offer_reaction(
        self, trigger: str, acting: str, target: str | None, candidates: list[str], **detail: Any
    ) -> ActionOutcome | None:
        """Offer a reaction window to `candidates`; resolve whatever the chooser picks."""
        if self.ctx.chooser is None or not self.ctx.in_combat:
            return None
        eligible: list[tuple[str, str]] = []
        for reactor in candidates:
            st = self.ctx.states.get(reactor)
            if st is None or st.has_condition("condition.incapacitated"):
                continue
            if self.ctx.encounter.budget(reactor).reaction < 1:  # type: ignore[union-attr]
                continue
            for key, adef in self.rs.actions.items():
                if adef.reaction_trigger == trigger:
                    eligible.append((reactor, key))
        if not eligible:
            return None
        window = ReactionWindow(trigger, acting, target, eligible, detail)
        choice = self.ctx.chooser(window)
        if choice is None or (choice.reactor, choice.action_key) not in eligible:
            return None
        sub = self.resolve(
            ActionRequest(choice.reactor, choice.action_key, choice.target, source="reaction"),
            as_reaction=True,
        )
        return sub

    # -- handlers ----------------------------------------------------------------------------

    def _attack(self, req: ActionRequest, adef: ActionDef, out: ActionOutcome) -> None:
        actor, target_key = req.actor, req.target
        assert target_key is not None
        state, target = self._state(actor), self._state(target_key)
        weapon = state.weapon(self.rs)
        wdef: EquipmentDef = self.rs.equipment[weapon.def_key]
        if wdef.attack_check is None:
            raise ActionError(f"{weapon.name} cannot attack")
        band = self.ctx.space.band(actor, target_key)
        range_mod = wdef.range_bands.get(band, None if wdef.range_bands else 0)
        if range_mod is None:
            raise ActionError(f"{weapon.name} cannot reach a {band} target")
        trace = out.trace
        assert trace is not None
        trace.rules_consulted += [weapon.def_key, wdef.attack_check]
        situational = range_mod
        notes = []
        if range_mod:
            notes.append({"source": f"range:{band}", "value": range_mod})
        pa, pt = self.ctx.space.position(actor), self.ctx.space.position(target_key)
        if pa.elevated and not pt.elevated:
            hg = int(self.rs.manifest.settings.get("high_ground_bonus", 1))
            situational += hg
            notes.append({"source": "high_ground", "value": hg})
        engaged = self.ctx.space.engaged(actor, target_key)
        cover = self.ctx.space.cover_against(target_key, actor)  # applied via condition.in_cover
        # reaction windows: the target may Defend; an engaged/adjacent ally may Protect
        defend_bonus = 0
        actual_target_key = target_key
        enc = self.ctx.encounter
        if enc is not None:
            allies = [
                a
                for a in enc.participants
                if a != target_key
                and not enc.hostile(a, target_key)
                and a in self.ctx.space.positions
                and self.ctx.space.band(a, target_key) in ("engaged", "close")
            ]
            protect = self._offer_reaction(
                "ally_attacked", actor, target_key, allies, attacker=actor
            )
            if (
                protect is not None
                and protect.ok
                and protect.request.action_key == "action.protect"
            ):
                actual_target_key = protect.request.actor
                target = self._state(actual_target_key)
                trace.reactions.append(
                    {
                        "reactor": actual_target_key,
                        "action": "action.protect",
                        "intercepted_for": target_key,
                    }
                )
                cover = "none"
            defend = self._offer_reaction(
                "attacked", actor, actual_target_key, [actual_target_key], attacker=actor
            )
            if defend is not None and defend.ok and defend.request.action_key == "action.defend":
                defend_bonus = 2
                trace.reactions.append(
                    {"reactor": actual_target_key, "action": "action.defend", "defense_bonus": 2}
                )
        situational -= defend_bonus
        if cover != "none":
            notes.append(
                {
                    "source": f"cover:{cover}",
                    "value": "via condition.in_cover on the target's Defense",
                }
            )
        if defend_bonus:
            notes.append({"source": "defend", "value": -defend_bonus})
        step = self._step(
            out, "attack_roll", target=actual_target_key, band=band, weapon=weapon.def_key
        )
        check = self.engine.check(
            state,
            wdef.attack_check,
            target_state=target,
            situational=situational,
            ctx={"attacker_engaged": engaged},
            purpose=f"{weapon.def_key} attack",
        )
        step.rolls.append(check.roll)
        out.check = check
        trace.modifiers = notes + [
            {"source": ln.source, "op": ln.op, "value": ln.value} for ln in check.modifier_lines
        ]
        trace.rules_consulted += list(check.rules_consulted)
        step.detail.update(
            total=check.total,
            target_value=check.target,
            margin=check.margin,
            degree=check.degree,
            success=check.success,
            critical=check.critical,
        )
        out.events.append(
            {
                "type": "attack.rolled",
                "actor": actor,
                "target": actual_target_key,
                "weapon": weapon.def_key,
                "roll": check.roll.__dict__,
                "total": check.total,
                "versus": check.target,
                "success": check.success,
                "degree": check.degree,
            }
        )
        if not check.success:
            step.status = "miss"
            out.status = "failed"
            out.trace.summary = (
                f"{actor} attacks {actual_target_key} with {weapon.name}: miss ({check.summary})"  # type: ignore[union-attr]
            )
            self._apply(out, step, actual_target_key, adef.resolution.on_failure)
            return
        # damage: weapon dice + attribute contribution + hidden bonuses that apply
        dmg_step = self._step(out, "damage", target=actual_target_key)
        bonus = evaluate_int(
            compile_expr(wdef.attribute_bonus), self.engine.calc.resolver(state, {})
        )
        hidden_bonus = 0
        for tag, extra in (weapon.hidden.get("bonus_damage_vs_tags") or {}).items():
            if tag in target.tags:
                hidden_bonus += int(extra)
        for tag, extra in (weapon.public.get("bonus_damage_vs_tags") or {}).items():
            if tag in target.tags:
                hidden_bonus += int(extra)
        if check.degree in ("strong_success", "exceptional_success"):
            pass  # degrees reach the narrator; no automatic extra damage in Core Adventure v0.1
        ectx = self.ctx.effect_ctx(actor, damage_bonus=bonus + hidden_bonus)
        muts = apply_steps(
            [
                {
                    "type": "deal_damage",
                    "params": {
                        "amount": wdef.damage or "1d2",
                        "damage_type": wdef.damage_type,
                        "source": actor,
                    },
                }
            ],
            target,
            ectx,
        )
        dmg_step.mutations += muts
        dmg_step.rolls += ectx.rolls
        dealt = muts[0].detail.get("damage", 0) if muts else 0
        dmg_step.detail.update(dealt=dealt, attribute_bonus=bonus, hidden_bonus=hidden_bonus)
        out.events.append(
            {
                "type": "damage.dealt",
                "actor": actor,
                "target": actual_target_key,
                "amount": dealt,
                "damage_type": wdef.damage_type,
                "remaining": target.resources["resource.health"].current,
            }
        )
        if target.has_condition("condition.incapacitated"):
            out.events.append(
                {"type": "actor.incapacitated", "actor": actual_target_key, "by": actor}
            )
            self.ctx.space.disengage(actual_target_key)
        self._apply(out, dmg_step, actual_target_key, adef.resolution.on_success)
        out.trace.summary = (
            f"{actor} hits {actual_target_key} with {weapon.name} for {dealt} ({check.summary})"  # type: ignore[union-attr]
        )

    def _move(self, req: ActionRequest, adef: ActionDef, out: ActionOutcome) -> None:
        actor, zone = req.actor, req.target
        assert zone is not None
        space = self.ctx.space
        start = space.position(actor).zone
        path = space.path(start, zone)
        if path is None:
            raise ActionError(f"no route from {start} to {zone}")
        steps_needed = len(path) - 1
        if steps_needed == 0:
            raise ActionError("already there")
        if steps_needed > adef.resolution.movement_steps:
            raise ActionError(
                f"{zone} is {steps_needed} steps away; "
                f"this action allows {adef.resolution.movement_steps}"
            )
        for nxt in path[1:]:
            partners = space.engaged_partners(actor)
            if partners:
                oa = self._opportunity(actor, partners, out)
                if oa and self._state(actor).has_condition("condition.incapacitated"):
                    out.status = "interrupted"
                    out.trace.summary = f"{actor} was cut down while disengaging"  # type: ignore[union-attr]
                    return
            prev, left = space.move_to(actor, nxt)
            step = self._step(out, "move", frm=prev, to=nxt, disengaged_from=sorted(left))
            step.mutations.append(Mutation("position", actor, "zone", prev, nxt, actor))
            self._clear_cover(out, step, actor)
            out.events.append(
                {
                    "type": "actor.repositioned",
                    "actor": actor,
                    "from_zone": prev,
                    "to_zone": nxt,
                    "disengaged_from": sorted(left),
                }
            )

    def _opportunity(
        self, actor: str, partners: set[str], out: ActionOutcome
    ) -> ActionOutcome | None:
        enc = self.ctx.encounter
        hostile = [p for p in sorted(partners) if enc is None or enc.hostile(p, actor)]
        sub = self._offer_reaction("enemy_disengages", actor, None, hostile, mover=actor)
        if sub is not None:
            out.trace.reactions.append(
                {
                    "reactor": sub.request.actor,
                    "action": sub.request.action_key,
                    "status": sub.status,
                    "summary": sub.trace.summary if sub.trace else "",
                }
            )  # type: ignore[union-attr]
            out.steps += sub.steps
            out.events += sub.events
        return sub

    def _engage(self, req: ActionRequest, adef: ActionDef, out: ActionOutcome) -> None:
        self.ctx.space.engage(req.actor, req.target)  # type: ignore[arg-type]
        step = self._step(out, "engage", target=req.target)
        step.mutations.append(
            Mutation("position", req.actor, "engaged_with", None, req.target, req.actor)
        )
        self._clear_cover(out, step, req.actor)
        self._clear_cover(out, step, req.target)  # type: ignore[arg-type]
        out.events.append({"type": "actor.engaged", "actor": req.actor, "target": req.target})

    def _disengage(self, req: ActionRequest, adef: ActionDef, out: ActionOutcome) -> None:
        partners = self.ctx.space.engaged_partners(req.actor)
        if adef.unsafe_movement:
            oa = self._opportunity(req.actor, partners, out)
            if oa and self._state(req.actor).has_condition("condition.incapacitated"):
                out.status = "interrupted"
                return
        left = self.ctx.space.disengage(req.actor)
        step = self._step(out, "disengage", left=sorted(left), unsafe=adef.unsafe_movement)
        step.mutations.append(
            Mutation("position", req.actor, "engaged_with", sorted(left), [], req.actor)
        )
        out.events.append(
            {
                "type": "actor.disengaged",
                "actor": req.actor,
                "from": sorted(left),
                "unsafe": adef.unsafe_movement,
            }
        )

    def _take_cover(self, req: ActionRequest, adef: ActionDef, out: ActionOutcome) -> None:
        level = self.ctx.space.take_cover(req.actor)
        step = self._step(out, "take_cover", level=level)
        intensity = min(2, COVER_LEVELS[level])
        self._apply(
            out,
            step,
            req.actor,
            [
                {
                    "type": "apply_condition",
                    "params": {"condition": "condition.in_cover", "intensity": intensity},
                }
            ],
        )
        out.events.append({"type": "actor.took_cover", "actor": req.actor, "level": level})

    def _rest(self, req: ActionRequest, adef: ActionDef, out: ActionOutcome) -> None:
        kind = adef.resolution.rest_kind or "short_rest"
        state = self._state(req.actor)
        step = self._step(out, "rest", kind=kind)
        for cdef in list(self.rs.conditions.values()):
            if kind in cdef.removed_by and state.has_condition(cdef.key):
                self._apply(
                    out,
                    step,
                    req.actor,
                    [{"type": "remove_condition", "params": {"condition": cdef.key, "all": True}}],
                )
        resolver = self.engine.calc.resolver(state, {})
        for rkey, rdef in self.rs.resources.items():
            formula = rdef.recovery.get(kind)
            if formula is None:
                continue
            amount = evaluate_int(compile_expr(formula), resolver)
            self._apply(
                out,
                step,
                req.actor,
                [{"type": "restore_resource", "params": {"resource": rkey, "amount": amount}}],
            )
        out.trace.rules_consulted.append(f"rest:{kind}")  # type: ignore[union-attr]
        self.engine.fire(state, "on_rest", self.ctx.effect_ctx(req.actor))
        out.events.append({"type": "actor.rested", "actor": req.actor, "kind": kind})

    def _check(self, req: ActionRequest, adef: ActionDef, out: ActionOutcome) -> None:
        r = adef.resolution
        state = self._state(req.actor)
        difficulty = req.params.get("difficulty", r.difficulty)
        check = self.engine.check(
            state,
            r.check or "check.core",
            attribute=req.params.get("attribute", r.attribute),
            skill=req.params.get("skill", r.skill),
            difficulty=difficulty,
            situational=int(req.params.get("situational", 0)),
            purpose=req.action_key,
        )
        step = self._step(
            out,
            "check",
            total=check.total,
            target=check.target,
            degree=check.degree,
            success=check.success,
        )
        step.rolls.append(check.roll)
        out.check = check
        out.trace.rules_consulted += list(check.rules_consulted)  # type: ignore[union-attr]
        out.events.append(
            {
                "type": "check.rolled",
                "actor": req.actor,
                "action": req.action_key,
                "check": check.check_key,
                "total": check.total,
                "versus": check.target,
                "success": check.success,
                "degree": check.degree,
            }
        )
        if check.success is False:
            out.status = "failed"
            self._apply(out, step, req.actor, r.on_failure)
        else:
            self._apply(out, step, req.actor, r.on_success)

    def _effects(self, req: ActionRequest, adef: ActionDef, out: ActionOutcome) -> None:
        step = self._step(out, adef.resolution.kind)
        self._apply(out, step, req.actor, adef.resolution.effects)
        if adef.resolution.kind == "surrender":
            self.ctx.space.disengage(req.actor)
            out.events.append({"type": "actor.surrendered", "actor": req.actor})

    def _flee(self, req: ActionRequest, adef: ActionDef, out: ActionOutcome) -> None:
        space = self.ctx.space
        pos = space.position(req.actor)
        if pos.engaged_with:
            raise ActionError("cannot flee while engaged; disengage first")
        zone = req.target
        assert zone is not None
        if not space.zones[zone].exit:
            raise ActionError(f"{zone} is not an exit")
        if pos.zone != zone:
            self._move(req, adef, out)
            if out.status == "interrupted":
                return
        step = self._step(out, "flee", via=zone)
        self._apply(
            out,
            step,
            req.actor,
            [{"type": "apply_condition", "params": {"condition": "condition.fleeing"}}],
        )
        space.remove(req.actor)
        if self.ctx.encounter is not None:
            self.ctx.encounter.remove(req.actor, "fled")
        out.events.append({"type": "actor.fled", "actor": req.actor, "via": zone})

    def _pickup(self, req: ActionRequest, adef: ActionDef, out: ActionOutcome) -> None:
        zone = self.ctx.space.position(req.actor).zone
        items = self.ctx.ground.get(zone, [])
        item = next((i for i in items if i.instance_key == req.target), None)
        if item is None:
            raise ActionError(f"{req.target} is not here")
        items.remove(item)
        item.equipped = False
        item.history.append(f"picked_up:{req.actor}")
        self._state(req.actor).equipment.append(item)
        step = self._step(out, "pickup", item=item.instance_key)
        step.mutations.append(
            Mutation(
                "item_transfer", req.actor, item.instance_key, f"zone:{zone}", req.actor, req.actor
            )
        )
        out.events.append(
            {"type": "item.picked_up", "actor": req.actor, "item": item.instance_key, "zone": zone}
        )

    def _drop(self, req: ActionRequest, adef: ActionDef, out: ActionOutcome) -> None:
        state = self._state(req.actor)
        item = state.item(req.target or "")
        if item is None:
            raise ActionError(f"{req.actor} does not hold {req.target!r}")
        zone = self.ctx.space.position(req.actor).zone
        state.equipment.remove(item)
        item.equipped = False
        item.history.append(f"dropped:{req.actor}")
        self.ctx.ground.setdefault(zone, []).append(item)
        step = self._step(out, "drop", item=item.instance_key)
        step.mutations.append(
            Mutation(
                "item_transfer", req.actor, item.instance_key, req.actor, f"zone:{zone}", req.actor
            )
        )
        out.events.append(
            {"type": "item.dropped", "actor": req.actor, "item": item.instance_key, "zone": zone}
        )

    def _wait(self, req: ActionRequest, adef: ActionDef, out: ActionOutcome) -> None:
        self._step(out, adef.resolution.kind)


# ---------------------------------------------------------------------------------------------
# Round bookkeeping
# ---------------------------------------------------------------------------------------------


def end_round(ctx: SceneContext) -> list[Mutation]:
    """Fire on_round_end for everyone present, expire timed effects, advance the tick by one
    combat round (ruleset setting)."""
    muts: list[Mutation] = []
    for key, st in ctx.states.items():
        if key in ctx.space.positions:
            muts += ctx.engine.fire(
                st,
                "on_round_end",
                ctx.effect_ctx(f"round:{ctx.encounter.round if ctx.encounter else 0}"),
            )
    ctx.tick += int(
        ctx.engine.ruleset.manifest.settings.get("time_costs", {}).get("combat_round", 6)
    )
    for st in ctx.states.values():
        muts += ctx.engine.advance(st, ctx.tick)
    if ctx.encounter is not None:
        ctx.encounter.maybe_end(ctx.states)
    return muts
