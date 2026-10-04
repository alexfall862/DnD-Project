"""Registered effect primitives (rules-engine §13–§15). Every mechanical mutation goes
through one of these; rulesets and models compose them but can never add new ones.

Milestone 02a primitives: modify_resource, deal_damage, restore_resource, modify_attribute,
modify_check, apply_condition, remove_condition. The remaining primitives (move_entity,
transfer_item, …) land in 02b and register here the same way.

Each primitive is `fn(state, params, ctx) -> list[Mutation]`. `Mutation` is an auditable
before/after record; the caller turns mutations into Events and projection updates.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.engine.dice import DICE_RE, DiceService, RollRecord
from app.engine.expressions import ExpressionError, compile_expr, evaluate_int
from app.engine.ruleset import EffectStep, Ruleset
from app.engine.stats import ActorState, ConditionInstance, ItemState, Modifier, StatCalculator

MAX_TRIGGER_DEPTH = 4
MAX_EFFECTS_PER_CHAIN = 32


class EffectError(ValueError):
    pass


@dataclass(frozen=True)
class Mutation:
    kind: str  # resource | condition_* | modifier_added | modifier_expired | attribute | noop
    actor_key: str
    field: str
    before: Any
    after: Any
    source: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class EffectContext:
    ruleset: Ruleset
    dice: DiceService
    calc: StatCalculator
    tick: int = 0
    source: str | None = None  # who/what caused the effect (actor key, condition key, item key)
    values: dict[str, Any] = field(default_factory=dict)  # ctx.* for formulas (situational facts)
    fire: Callable[[ActorState, str, EffectContext], list[Mutation]] | None = None  # trigger hook
    depth: int = 0
    rolls: list[RollRecord] = field(default_factory=list)
    # Shared across the whole effect chain (parent and every child context).
    budget: dict[str, Any] = field(default_factory=lambda: {"effects": 0, "exhausted": False})

    @property
    def effects_applied(self) -> int:
        return self.budget["effects"]

    @effects_applied.setter
    def effects_applied(self, n: int) -> None:
        self.budget["effects"] = n

    @property
    def budget_exhausted(self) -> bool:
        return self.budget["exhausted"]

    @budget_exhausted.setter
    def budget_exhausted(self, v: bool) -> None:
        self.budget["exhausted"] = v

    def child(self, **changes: Any) -> EffectContext:
        return EffectContext(
            ruleset=self.ruleset,
            dice=self.dice,
            calc=self.calc,
            tick=self.tick,
            source=changes.get("source", self.source),
            values=dict(self.values),
            fire=self.fire,
            depth=self.depth + 1,
            rolls=self.rolls,
            budget=self.budget,
        )


EffectFn = Callable[[ActorState, dict[str, Any], EffectContext], list[Mutation]]
REGISTRY: dict[str, EffectFn] = {}


def primitive(name: str) -> Callable[[EffectFn], EffectFn]:
    def deco(fn: EffectFn) -> EffectFn:
        REGISTRY[name] = fn
        return fn

    return deco


# ---------------------------------------------------------------------------------------------
# Amount resolution: int, dice expression, or safe formula over the actor state
# ---------------------------------------------------------------------------------------------


def resolve_amount(amount: Any, state: ActorState, ctx: EffectContext, *, purpose: str) -> int:
    if isinstance(amount, bool):
        raise EffectError("amount cannot be boolean")
    if isinstance(amount, int):
        return amount
    if isinstance(amount, float):
        return int(amount)
    if isinstance(amount, str) and DICE_RE.match(amount):
        roll = ctx.dice.roll(amount, purpose=purpose, visibility="public", actor=state.actor_key)
        ctx.rolls.append(roll)
        return roll.total
    if isinstance(amount, str) and re.match(r"^-\s*\d*d\d+", amount):  # "-1d4" style
        roll = ctx.dice.roll(amount[1:].strip(), purpose=purpose, actor=state.actor_key)
        ctx.rolls.append(roll)
        return -roll.total
    try:
        return evaluate_int(compile_expr(amount), ctx.calc.resolver(state, ctx.values))
    except ExpressionError as exc:
        raise EffectError(f"bad amount {amount!r}: {exc}") from exc


# ---------------------------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------------------------


def _set_resource(
    state: ActorState,
    key: str,
    new: int,
    ctx: EffectContext,
    source: str | None,
    detail: dict[str, Any],
) -> list[Mutation]:
    rdef = ctx.ruleset.resources.get(key)
    if rdef is None:
        raise EffectError(f"unknown resource {key!r}")
    res = state.resources[key]
    before = res.current
    mx = ctx.calc.resource_max(state, key, ctx.values).value
    if rdef.overflow == "clamp":
        new = min(new, mx)
    if rdef.depletion == "clamp":
        new = max(new, rdef.min)
    else:
        new = max(new, rdef.min)  # `min` is the floor even when depletion is "allow"
    res.current = new
    out = [Mutation("resource", state.actor_key, key, before, new, source, {**detail, "max": mx})]
    if before > 0 >= new and rdef.on_depleted:
        out += apply_steps(rdef.on_depleted, state, ctx.child(source=key))
    return out


@primitive("modify_resource")
def modify_resource(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    key = p["resource"]
    amount = resolve_amount(p["amount"], state, ctx, purpose=f"modify {key}")
    return _set_resource(
        state, key, state.resources[key].current + amount, ctx, ctx.source, {"amount": amount}
    )


@primitive("restore_resource")
def restore_resource(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    key = p["resource"]
    amount = abs(resolve_amount(p["amount"], state, ctx, purpose=f"restore {key}"))
    return _set_resource(
        state,
        key,
        state.resources[key].current + amount,
        ctx,
        ctx.source,
        {"amount": amount, "restore": True},
    )


@primitive("deal_damage")
def deal_damage(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    """raw → source modifiers → resistance/vulnerability/immunity → armour → min 0 → resource →
    damage triggers. Every stage is recorded (rules-engine §14)."""
    dtype = p.get("damage_type", "damage.physical")
    if not ctx.ruleset.has(dtype):
        raise EffectError(f"unknown damage type {dtype!r}")
    resource = p.get("resource", "resource.health")
    raw = max(0, resolve_amount(p["amount"], state, ctx, purpose=f"damage {dtype}"))
    stages: list[tuple[str, int]] = [("raw", raw)]
    amount = raw + int(p.get("bonus", 0)) + int(ctx.values.get("damage_bonus", 0))
    stages.append(("source_modifiers", amount))
    short = dtype.split(".", 1)[1]
    if f"immune:{short}" in state.capabilities:
        amount = 0
    elif f"resist:{short}" in state.capabilities:
        amount //= 2
    elif f"vulnerable:{short}" in state.capabilities:
        amount *= 2
    stages.append(("resistance", amount))
    armor = int(ctx.values.get("armor_dr", 0)) if not p.get("ignores_armor") else 0
    amount = max(0, amount - armor)
    stages.append(("armor", amount))
    amount = max(0, amount)
    stages.append(("final", amount))
    out = _set_resource(
        state,
        resource,
        state.resources[resource].current - amount,
        ctx,
        ctx.source,
        {"damage_type": dtype, "stages": stages, "amount": -amount},
    )
    out[0] = Mutation(
        out[0].kind,
        out[0].actor_key,
        out[0].field,
        out[0].before,
        out[0].after,
        out[0].source,
        {**out[0].detail, "damage": amount},
    )
    if amount > 0 and ctx.fire is not None:
        out += ctx.fire(state, "on_damage", ctx.child(source=p.get("source", ctx.source)))
    return out


def _temp_modifier(
    state: ActorState, target: str, op: str, value: Any, ctx: EffectContext, p: dict[str, Any]
) -> list[Mutation]:
    duration = p.get("duration_seconds")
    mod = Modifier(
        target=target,
        op=op,
        value=compile_expr(value),
        source=p.get("source") or ctx.source or "effect",
        priority=int(p.get("priority", 0)),
        note=p.get("note", ""),
        expires_tick=(ctx.tick + int(duration)) if duration is not None else None,
        value_src=value,
    )
    state.temp_modifiers.append(mod)
    return [
        Mutation(
            "modifier_added",
            state.actor_key,
            target,
            None,
            {"op": op, "value": value, "expires_tick": mod.expires_tick},
            mod.source,
            {"modifier_id": mod.modifier_id},
        )
    ]


@primitive("modify_attribute")
def modify_attribute(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    key = p["attribute"]
    if key not in ctx.ruleset.attributes:
        raise EffectError(f"unknown attribute {key!r}")
    if p.get("permanent"):
        amount = resolve_amount(p["amount"], state, ctx, purpose=f"modify {key}")
        d = ctx.ruleset.attributes[key]
        before = state.attributes[key]
        after = max(d.min, min(d.max, before + amount))
        state.attributes[key] = after
        return [
            Mutation(
                "attribute", state.actor_key, key, before, after, ctx.source, {"permanent": True}
            )
        ]
    return _temp_modifier(state, key, "add", p["amount"], ctx, p)


@primitive("modify_check")
def modify_check(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    target = p.get("check", "check.*")
    if target != "check.*" and target not in ctx.ruleset.checks:
        raise EffectError(f"unknown check {target!r}")
    op = p.get("op", "add")
    if op not in ("add", "subtract", "advantage", "disadvantage"):
        raise EffectError(f"bad op {op!r}")
    return _temp_modifier(state, target, op, p.get("amount", 0), ctx, p)


@primitive("apply_condition")
def apply_condition(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    key = p["condition"]
    cdef = ctx.ruleset.conditions.get(key)
    if cdef is None:
        raise EffectError(f"unknown condition {key!r}")
    intensity = int(p.get("intensity", 1))
    duration = p.get("duration_seconds", cdef.default_duration_seconds)
    expires = (ctx.tick + int(duration)) if duration is not None else None
    source = p.get("source") or ctx.source
    existing = [c for c in state.conditions if c.key == key]
    out: list[Mutation] = []
    if existing and cdef.stacking == "none":
        return [
            Mutation(
                "noop",
                state.actor_key,
                key,
                existing[0].intensity,
                existing[0].intensity,
                source,
                {"reason": "already present"},
            )
        ]
    if existing and cdef.stacking == "refresh":
        inst = existing[0]
        before = inst.expires_tick
        inst.expires_tick = expires
        inst.source = source
        return [Mutation("condition_refreshed", state.actor_key, key, before, expires, source)]
    if existing and cdef.stacking == "intensity":
        inst = existing[0]
        before = inst.intensity
        inst.intensity = min(cdef.max_intensity, inst.intensity + intensity)
        inst.expires_tick = expires or inst.expires_tick
        return [
            Mutation("condition_intensified", state.actor_key, key, before, inst.intensity, source)
        ]
    inst = ConditionInstance(
        key=key,
        intensity=min(intensity, cdef.max_intensity),
        source=source,
        applied_tick=ctx.tick,
        expires_tick=expires,
    )
    state.conditions.append(inst)
    out.append(
        Mutation(
            "condition_applied",
            state.actor_key,
            key,
            None,
            inst.intensity,
            source,
            {"instance_id": inst.instance_id, "expires_tick": expires},
        )
    )
    if cdef.on_apply:
        out += apply_steps(cdef.on_apply, state, ctx.child(source=key))
    if ctx.fire is not None:
        out += ctx.fire(state, "on_condition_applied", ctx.child(source=key))
    return out


@primitive("remove_condition")
def remove_condition(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    key = p["condition"]
    cdef = ctx.ruleset.conditions.get(key)
    if cdef is None:
        raise EffectError(f"unknown condition {key!r}")
    instance_id = p.get("instance_id")
    reduce_by = p.get("intensity")
    out: list[Mutation] = []
    keep: list[ConditionInstance] = []
    for c in state.conditions:
        if c.key != key or (instance_id and c.instance_id != instance_id):
            keep.append(c)
            continue
        if reduce_by and c.intensity > int(reduce_by):
            before = c.intensity
            c.intensity -= int(reduce_by)
            out.append(
                Mutation(
                    "condition_intensified",
                    state.actor_key,
                    key,
                    before,
                    c.intensity,
                    ctx.source,
                    {"reduced": True},
                )
            )
            keep.append(c)
            continue
        out.append(
            Mutation(
                "condition_removed",
                state.actor_key,
                key,
                c.intensity,
                None,
                ctx.source,
                {"instance_id": c.instance_id},
            )
        )
        if not p.get("all") and instance_id is None and cdef.stacking == "independent":
            keep += [x for x in state.conditions if x is not c and x.key == key and x not in keep]
            # remove only one instance for independent stacks
            state.conditions = [x for x in state.conditions if x is not c]
            if cdef.on_remove:
                out += apply_steps(cdef.on_remove, state, ctx.child(source=key))
            return out
    if not out:
        return [
            Mutation(
                "noop", state.actor_key, key, None, None, ctx.source, {"reason": "not present"}
            )
        ]
    state.conditions = keep
    if cdef.on_remove and any(m.kind == "condition_removed" for m in out):
        out += apply_steps(cdef.on_remove, state, ctx.child(source=key))
    return out


# ---------------------------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------------------------


def validate_step(ruleset: Ruleset, step: EffectStep) -> None:
    if step.type not in REGISTRY:
        raise EffectError(f"unknown effect primitive {step.type!r}")
    for pk in ("condition", "resource", "attribute", "damage_type"):
        v = step.params.get(pk)
        if isinstance(v, str) and not ruleset.has(v):
            raise EffectError(f"{step.type}: unknown {pk} {v!r}")


def apply_steps(
    steps: list[EffectStep] | list[dict[str, Any]], state: ActorState, ctx: EffectContext
) -> list[Mutation]:
    """Apply a list of effect steps in order, within the trigger/effect budget."""
    out: list[Mutation] = []
    for raw in steps:
        step = raw if isinstance(raw, EffectStep) else EffectStep.model_validate(raw)
        validate_step(ctx.ruleset, step)
        if ctx.depth > MAX_TRIGGER_DEPTH or ctx.effects_applied >= MAX_EFFECTS_PER_CHAIN:
            ctx.budget_exhausted = True
            out.append(
                Mutation(
                    "noop",
                    state.actor_key,
                    step.type,
                    None,
                    None,
                    ctx.source,
                    {"reason": "effect budget exhausted", "depth": ctx.depth},
                )
            )
            break
        ctx.effects_applied += 1
        out += REGISTRY[step.type](state, step.params, ctx)
    return out


def expire(state: ActorState, tick: int, ctx: EffectContext) -> list[Mutation]:
    """Remove conditions and temporary modifiers whose expiry tick has passed."""
    out: list[Mutation] = []
    for c in [c for c in state.conditions if c.expires_tick is not None and c.expires_tick <= tick]:
        out += remove_condition(
            state, {"condition": c.key, "instance_id": c.instance_id}, ctx.child(source="expiry")
        )
    before = len(state.temp_modifiers)
    state.temp_modifiers = [
        m for m in state.temp_modifiers if m.expires_tick is None or m.expires_tick > tick
    ]
    if len(state.temp_modifiers) != before:
        out.append(
            Mutation(
                "modifier_expired",
                state.actor_key,
                "temp_modifiers",
                before,
                len(state.temp_modifiers),
                "expiry",
            )
        )
    return out


# ---------------------------------------------------------------------------------------------
# Milestone 02b primitives. Those that touch the world beyond one actor's state return
# request-style mutations the owning service turns into events/projections.
# ---------------------------------------------------------------------------------------------


@primitive("grant_capability")
def grant_capability(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    cap = p["capability"]
    before = cap in state.capabilities
    state.capabilities.add(cap)
    return [Mutation("capability", state.actor_key, cap, before, True, ctx.source)]


@primitive("remove_capability")
def remove_capability(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    cap = p["capability"]
    before = cap in state.capabilities
    state.capabilities.discard(cap)
    return [Mutation("capability", state.actor_key, cap, before, False, ctx.source)]


@primitive("transfer_item")
def transfer_item(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    """Move an item instance from this actor to another actor state in `ctx.values['states']`
    (or to the ground: `to=None` with a `zone`)."""
    key = p["item"]
    item = state.item(key)
    if item is None:
        raise EffectError(f"{state.actor_key} does not hold {key!r}")
    to_key = p.get("to")
    state.equipment = [i for i in state.equipment if i.instance_key != key]
    item.equipped = False
    if to_key:
        states: dict[str, ActorState] = ctx.values.get("states", {})
        if to_key not in states:
            raise EffectError(f"unknown recipient {to_key!r}")
        states[to_key].equipment.append(item)
    else:
        ground: dict[str, list[ItemState]] = ctx.values.setdefault("ground", {})
        ground.setdefault(p.get("zone", "here"), []).append(item)
    item.history.append(f"transfer:{state.actor_key}->{to_key or 'ground'}")
    return [
        Mutation(
            "item_transfer",
            state.actor_key,
            key,
            state.actor_key,
            to_key,
            ctx.source,
            {"zone": p.get("zone")},
        )
    ]


@primitive("move_entity")
def move_entity(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    """Forced movement within the scene space (`ctx.values['space']`), e.g. a shove."""
    space = ctx.values.get("space")
    if space is None:
        return [
            Mutation(
                "move_request", state.actor_key, "zone", None, p.get("zone"), ctx.source, dict(p)
            )
        ]
    before = space.position(state.actor_key).zone
    if p.get("disengage"):
        space.disengage(state.actor_key)
    if p.get("zone"):
        space.move_to(state.actor_key, p["zone"])
    return [
        Mutation(
            "position",
            state.actor_key,
            "zone",
            before,
            space.position(state.actor_key).zone,
            ctx.source,
        )
    ]


@primitive("create_entity")
def create_entity(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    return [
        Mutation(
            "entity_create",
            state.actor_key,
            p.get("entity_type", "item"),
            None,
            p.get("name"),
            ctx.source,
            dict(p),
        )
    ]


@primitive("destroy_entity")
def destroy_entity(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    key = p.get("item")
    if key and state.item(key):
        state.equipment = [i for i in state.equipment if i.instance_key != key]
    return [
        Mutation(
            "entity_destroy",
            state.actor_key,
            key or p.get("entity", ""),
            True,
            False,
            ctx.source,
            dict(p),
        )
    ]


@primitive("trigger_event")
def trigger_event(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    return [
        Mutation(
            "event_request",
            state.actor_key,
            p.get("event_type", "custom"),
            None,
            None,
            ctx.source,
            dict(p),
        )
    ]


@primitive("schedule_event")
def schedule_event(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    return [
        Mutation(
            "schedule_request",
            state.actor_key,
            p.get("event_type", "custom"),
            None,
            ctx.tick + int(p.get("delay_seconds", 0)),
            ctx.source,
            dict(p),
        )
    ]


@primitive("reveal_information")
def reveal_information(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    """A structured 'tell' or discovery for the perspective layer (Milestone 03) to record."""
    if p.get("item_property") and p.get("item"):
        item = state.item(p["item"])
        if item and p["item_property"] in item.hidden:
            item.public[p["item_property"]] = item.hidden[p["item_property"]]
            return [
                Mutation(
                    "item_property_revealed",
                    state.actor_key,
                    p["item"],
                    None,
                    p["item_property"],
                    ctx.source,
                )
            ]
    return [
        Mutation(
            "reveal",
            state.actor_key,
            p.get("kind", "tell"),
            None,
            p.get("text") or p.get("fact"),
            ctx.source,
            dict(p),
        )
    ]


@primitive("change_relationship")
def change_relationship(state: ActorState, p: dict[str, Any], ctx: EffectContext) -> list[Mutation]:
    """Stub: records a relationship delta request; the relationships service (Milestone 06b)
    applies it with event provenance."""
    return [
        Mutation(
            "relationship_delta",
            state.actor_key,
            p.get("target", ""),
            None,
            {p.get("dimension", "trust"): p.get("delta", 0)},
            ctx.source,
            dict(p),
        )
    ]
