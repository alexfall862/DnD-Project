"""Actor mechanical state and stat calculation with modifier provenance (rules-engine §5–§9).

`ActorState` is the in-memory, ruleset-shaped view of `actors.mechanical_profile` plus live
resources/conditions. `StatCalculator` resolves any reference (`attr.*`, `skill.*`, `stat.*`,
`resource.<k>.max`, `check.*`) by applying every applicable modifier — from traits, active
conditions and temporary effects — and records each one as a provenance line.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.engine.expressions import Expr, ExpressionError, compile_expr, evaluate, evaluate_int
from app.engine.ruleset import ModifierDef, Ruleset, RulesetError

MAX_DERIVATION_DEPTH = 16


class StatError(ValueError):
    pass


# ---------------------------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------------------------


@dataclass
class ConditionInstance:
    key: str
    intensity: int = 1
    source: str | None = None
    applied_tick: int | None = None
    expires_tick: int | None = None
    instance_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class ResourceState:
    current: int


@dataclass
class Modifier:
    """A runtime modifier with provenance (traits/conditions are expanded into these)."""

    target: str
    op: str
    value: Expr
    source: str
    condition: Expr | None = None
    priority: int = 0
    note: str = ""
    expires_tick: int | None = None
    modifier_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @classmethod
    def from_def(cls, d: ModifierDef, source: str) -> Modifier:
        return cls(
            target=d.target,
            op=d.op,
            value=compile_expr(d.value),
            source=source,
            condition=compile_expr(d.condition) if d.condition is not None else None,
            priority=d.priority,
            note=d.note,
        )


@dataclass
class ActorState:
    actor_key: str
    attributes: dict[str, int]
    skills: dict[str, int] = field(default_factory=dict)
    traits: list[str] = field(default_factory=list)
    resources: dict[str, ResourceState] = field(default_factory=dict)
    conditions: list[ConditionInstance] = field(default_factory=list)
    temp_modifiers: list[Modifier] = field(default_factory=list)
    capabilities: set[str] = field(default_factory=set)
    equipment: list[dict[str, Any]] = field(default_factory=list)  # Milestone 02b

    def condition_intensity(self, key: str) -> int:
        return sum(c.intensity for c in self.conditions if c.key == key)

    def has_condition(self, key: str) -> bool:
        return any(c.key == key for c in self.conditions)

    @classmethod
    def from_profile(cls, ruleset: Ruleset, actor_key: str, profile: dict[str, Any]) -> ActorState:
        """Build from a `mechanical_profile` dict. Unknown keys are rejected; resources missing
        from the profile start at their computed maximum."""
        attrs: dict[str, int] = {}
        for k, d in ruleset.attributes.items():
            v = profile.get("attributes", {}).get(k, d.default)
            if not isinstance(v, int) or not d.min <= v <= d.max:
                raise StatError(f"{actor_key}: {k}={v!r} outside {d.min}..{d.max}")
            attrs[k] = v
        for k in profile.get("attributes", {}):
            if k not in ruleset.attributes:
                raise StatError(f"{actor_key}: unknown attribute {k!r}")
        skills: dict[str, int] = {}
        for k, v in profile.get("skills", {}).items():
            d = ruleset.skills.get(k)
            if d is None:
                raise StatError(f"{actor_key}: unknown skill {k!r}")
            if not isinstance(v, int) or not 0 <= v <= d.max_rank:
                raise StatError(f"{actor_key}: {k}={v!r} outside 0..{d.max_rank}")
            skills[k] = v
        traits = list(profile.get("traits", []))
        for t in traits:
            if t not in ruleset.traits:
                raise StatError(f"{actor_key}: unknown trait {t!r}")
        caps: set[str] = set(profile.get("capabilities", []))
        for t in traits:
            caps |= set(ruleset.traits[t].capabilities)
        state = cls(
            actor_key=actor_key, attributes=attrs, skills=skills, traits=traits, capabilities=caps
        )
        for c in profile.get("conditions", []):
            if c["key"] not in ruleset.conditions:
                raise StatError(f"{actor_key}: unknown condition {c['key']!r}")
            state.conditions.append(ConditionInstance(**c))
        calc = StatCalculator(ruleset)
        for k in ruleset.resources:
            given = profile.get("resources", {}).get(k)
            if given is None:
                state.resources[k] = ResourceState(current=calc.resource_max(state, k).value)
            else:
                state.resources[k] = ResourceState(current=int(given["current"]))
        for k in profile.get("resources", {}):
            if k not in ruleset.resources:
                raise StatError(f"{actor_key}: unknown resource {k!r}")
        return state

    def to_profile(self) -> dict[str, Any]:
        return {
            "attributes": dict(sorted(self.attributes.items())),
            "skills": dict(sorted(self.skills.items())),
            "traits": sorted(self.traits),
            "capabilities": sorted(self.capabilities),
            "resources": {k: {"current": r.current} for k, r in sorted(self.resources.items())},
            "conditions": [
                {
                    "key": c.key,
                    "intensity": c.intensity,
                    "source": c.source,
                    "applied_tick": c.applied_tick,
                    "expires_tick": c.expires_tick,
                    "instance_id": c.instance_id,
                }
                for c in self.conditions
            ],
            "temp_modifiers": [
                {
                    "target": m.target,
                    "op": m.op,
                    "source": m.source,
                    "priority": m.priority,
                    "note": m.note,
                    "expires_tick": m.expires_tick,
                    "modifier_id": m.modifier_id,
                }
                for m in self.temp_modifiers
            ],
        }


# ---------------------------------------------------------------------------------------------
# Calculation
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ModLine:
    source: str
    op: str
    value: int | float | bool
    note: str = ""


@dataclass(frozen=True)
class StatResult:
    target: str
    base: int
    value: int
    lines: tuple[ModLine, ...]
    advantage: int = 0  # net advantage count (>0 adv, <0 dis) for check.* targets

    @property
    def explanation(self) -> str:
        parts = [f"{self.target}: base {self.base}"]
        parts += [
            f"{ln.op} {ln.value} ({ln.source}{': ' + ln.note if ln.note else ''})"
            for ln in self.lines
        ]
        return " ; ".join(parts) + f" = {self.value}"


def _matches(mod_target: str, target: str) -> bool:
    if mod_target == target:
        return True
    return mod_target == "check.*" and target.startswith("check.")


class StatCalculator:
    def __init__(self, ruleset: Ruleset) -> None:
        self.rs = ruleset
        self._formula_cache: dict[tuple[str, str], Expr] = {}

    # -- modifiers --------------------------------------------------------------------------

    def active_modifiers(self, state: ActorState) -> list[Modifier]:
        mods: list[Modifier] = []
        for t in state.traits:
            d = self.rs.traits.get(t)
            if d:
                mods += [Modifier.from_def(m, source=t) for m in d.modifiers]
        for c in state.conditions:
            d = self.rs.conditions.get(c.key)
            if d:
                mods += [Modifier.from_def(m, source=c.key) for m in d.modifiers]
        mods += state.temp_modifiers
        return mods

    # -- resolution -------------------------------------------------------------------------

    def resolver(self, state: ActorState, ctx: dict[str, Any] | None = None, _depth: int = 0):
        ctx = ctx or {}

        def resolve(name: str):
            if name.startswith("ctx."):
                return ctx.get(name[4:], 0)
            if name.startswith("trait."):
                return name in state.traits
            if name.startswith("condition."):
                return state.condition_intensity(name)
            if name.startswith("resource."):
                parts = name.split(".")
                key = ".".join(parts[:2])
                if parts[2] == "current":
                    return state.resources[key].current
                return self.calculate(state, f"{key}.max", ctx, _depth + 1).value
            if name.startswith(("attr.", "skill.", "stat.")):
                return self.calculate(state, name, ctx, _depth + 1).value
            raise KeyError(name)

        return resolve

    def _formula(self, key: str, kind: str, src) -> Expr:
        ck = (key, kind)
        if ck not in self._formula_cache:
            self._formula_cache[ck] = compile_expr(src)
        return self._formula_cache[ck]

    def _base(self, state: ActorState, target: str, ctx: dict[str, Any], depth: int) -> int:
        if target.startswith("attr."):
            return state.attributes.get(target, self.rs.attributes[target].default)
        if target.startswith("skill."):
            if target not in self.rs.skills:
                raise StatError(f"unknown skill {target!r}")
            return state.skills.get(target, 0)
        if target.startswith("stat."):
            d = self.rs.derived_stats.get(target)
            if d is None:
                raise StatError(f"unknown derived stat {target!r}")
            return evaluate_int(
                self._formula(target, "stat", d.formula), self.resolver(state, ctx, depth)
            )
        if target.startswith("resource.") and target.endswith(".max"):
            key = target[: -len(".max")]
            d = self.rs.resources.get(key)
            if d is None:
                raise StatError(f"unknown resource {key!r}")
            return evaluate_int(
                self._formula(key, "max", d.max_formula), self.resolver(state, ctx, depth)
            )
        if target.startswith("check."):
            return 0
        raise StatError(f"cannot calculate {target!r}")

    def calculate(
        self, state: ActorState, target: str, ctx: dict[str, Any] | None = None, _depth: int = 0
    ) -> StatResult:
        if _depth > MAX_DERIVATION_DEPTH:
            raise StatError(f"derivation too deep resolving {target!r} (cycle?)")
        ctx = ctx or {}
        base = self._base(state, target, ctx, _depth)
        resolve = self.resolver(state, ctx, _depth)
        lines: list[ModLine] = []
        adds: list[tuple[int, Modifier, int | float]] = []
        muls: list[tuple[int, Modifier, int | float]] = []
        sets: list[tuple[int, Modifier, int | float]] = []
        advantage = 0
        for m in self.active_modifiers(state):
            if not _matches(m.target, target):
                continue
            if m.condition is not None:
                try:
                    if not evaluate(m.condition, resolve):
                        continue
                except ExpressionError:
                    continue
            if m.op in ("advantage", "disadvantage"):
                advantage += 1 if m.op == "advantage" else -1
                lines.append(ModLine(m.source, m.op, True, m.note))
                continue
            try:
                v = evaluate(m.value, resolve)
            except ExpressionError as exc:
                raise StatError(f"modifier from {m.source} on {target}: {exc}") from exc
            if isinstance(v, bool):
                v = int(v)
            bucket = {"add": adds, "subtract": adds, "multiply": muls, "set": sets}[m.op]
            bucket.append((m.priority, m, -v if m.op == "subtract" else v))
        value: int | float = base
        for _, m, v in sorted(adds, key=lambda t: t[0]):
            value += v
            lines.append(ModLine(m.source, m.op, abs(v), m.note))
        for _, m, v in sorted(muls, key=lambda t: t[0]):
            value *= v
            lines.append(ModLine(m.source, m.op, v, m.note))
        for _, m, v in sorted(sets, key=lambda t: t[0]):
            value = v
            lines.append(ModLine(m.source, m.op, v, m.note))
        value = int(value // 1) if isinstance(value, float) else value
        if target.startswith("attr."):
            d = self.rs.attributes[target]
            value = max(d.min, min(d.max, value))
        return StatResult(target, base, int(value), tuple(lines), advantage)

    def resource_max(
        self, state: ActorState, resource_key: str, ctx: dict[str, Any] | None = None
    ) -> StatResult:
        return self.calculate(state, f"{resource_key}.max", ctx)

    def check_modifier(
        self, state: ActorState, check_key: str, ctx: dict[str, Any] | None = None
    ) -> StatResult:
        """Flat modifier + advantage count for a check (`check.<key>` and `check.*` targets)."""
        return self.calculate(state, check_key, ctx)

    def validate_profile(self, state: ActorState) -> None:
        for key in self.rs.resources:
            if key not in state.resources:
                raise RulesetError(f"missing resource state {key!r}")
