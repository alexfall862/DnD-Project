"""Checks: simple, versus-stat and opposed, with margins and degrees (rules-engine §7;
core-adventure §2, §5). The dice service supplies every random number."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.engine.dice import DiceService, RollRecord, parse_dice
from app.engine.ruleset import CheckDef, Ruleset, RulesetError
from app.engine.stats import ActorState, ModLine, StatCalculator


class CheckError(ValueError):
    pass


@dataclass(frozen=True)
class CheckResult:
    check_key: str
    actor_key: str
    roll: RollRecord
    attribute: str | None
    attribute_value: int
    skill: str | None
    skill_value: int
    modifier_lines: tuple[ModLine, ...]
    modifier_total: int
    situational: int
    total: int
    target: int | None
    margin: int | None
    degree: str | None
    success: bool | None
    advantage: int
    critical: str | None  # "low" | "high" | None — flags only; they never override the fiction
    rules_consulted: tuple[str, ...] = field(default_factory=tuple)

    @property
    def summary(self) -> str:
        parts = [f"{self.roll.expression}={self.roll.total}"]
        if self.attribute:
            parts.append(f"{self.attribute}={self.attribute_value:+d}")
        if self.skill:
            parts.append(f"{self.skill}={self.skill_value:+d}")
        if self.modifier_total:
            parts.append(f"mods={self.modifier_total:+d}")
        if self.situational:
            parts.append(f"situational={self.situational:+d}")
        s = " ".join(parts) + f" -> {self.total}"
        if self.target is not None:
            s += f" vs {self.target} (margin {self.margin:+d}, {self.degree})"
        return s


@dataclass(frozen=True)
class OpposedResult:
    a: CheckResult
    b: CheckResult
    winner: str  # "a" | "b"
    tie: bool
    margin: int  # a.total - b.total


def _advantage_roll(base: str, net: int) -> str:
    """1d20 with net advantage → 2d20kh1; disadvantage → 2d20kl1. Other dice unchanged."""
    e = parse_dice(base)
    if net == 0 or e.count != 1 or e.keep:
        return base
    mod = f"{e.modifier:+d}" if e.modifier else ""
    return f"2d{e.sides}{'kh1' if net > 0 else 'kl1'}{mod}"


def _target_value(ruleset: Ruleset, difficulty: int | str | None) -> int | None:
    if difficulty is None:
        return None
    if isinstance(difficulty, str):
        try:
            return ruleset.manifest.difficulty_scale[difficulty]
        except KeyError:
            raise CheckError(f"unknown difficulty {difficulty!r}") from None
    return int(difficulty)


def resolve_check(
    ruleset: Ruleset,
    dice: DiceService,
    calc: StatCalculator,
    state: ActorState,
    check_key: str,
    *,
    attribute: str | None = None,
    skill: str | None = None,
    difficulty: int | str | None = None,
    target_state: ActorState | None = None,
    situational: int = 0,
    ctx: dict[str, Any] | None = None,
    visibility: str = "public",
    purpose: str = "",
) -> CheckResult:
    """Roll one check. `attribute`/`skill` override the definition's defaults (flexible pairing,
    core-adventure §4). `difficulty` is a number or a scale name; for `versus: stat` checks the
    target's stat is used instead and `target_state` is required."""
    ctx = dict(ctx or {})
    try:
        cdef: CheckDef = ruleset.checks[check_key]
    except KeyError:
        raise CheckError(f"unknown check {check_key!r}") from None
    attribute = attribute or cdef.attribute
    skill = skill or cdef.skill
    if skill and attribute is None:
        attribute = ruleset.skills[skill].default_attribute
    if attribute and not ruleset.has(attribute):
        raise CheckError(f"unknown attribute {attribute!r}")
    if skill and not ruleset.has(skill):
        raise CheckError(f"unknown skill {skill!r}")

    attr_value = calc.calculate(state, attribute, ctx).value if attribute else 0
    skill_value = calc.calculate(state, skill, ctx).value if skill else 0
    mods = calc.check_modifier(state, check_key, ctx)
    consulted = [check_key] + ([attribute] if attribute else []) + ([skill] if skill else [])

    if cdef.versus == "stat":
        if target_state is None or cdef.versus_stat is None:
            raise CheckError(f"{check_key} needs a target_state")
        target = calc.calculate(target_state, cdef.versus_stat, ctx).value
        consulted.append(cdef.versus_stat)
    elif cdef.versus == "difficulty":
        target = _target_value(ruleset, difficulty)
    else:
        target = None  # opposed: compared by the caller

    expr = _advantage_roll(cdef.roll, mods.advantage)
    roll = dice.roll(
        expr, purpose=purpose or check_key, visibility=visibility, actor=state.actor_key
    )
    total = roll.total + attr_value + skill_value + mods.value + situational

    margin = degree = success = None
    if target is not None:
        margin = total - target
        band = ruleset.degree_for_margin(margin)
        degree, success = band.degree, band.success
    critical = None
    if cdef.critical_low is not None and roll.natural == cdef.critical_low:
        critical = "low"
    elif cdef.critical_high is not None and roll.natural == cdef.critical_high:
        critical = "high"
    return CheckResult(
        check_key=check_key,
        actor_key=state.actor_key,
        roll=roll,
        attribute=attribute,
        attribute_value=attr_value,
        skill=skill,
        skill_value=skill_value,
        modifier_lines=mods.lines,
        modifier_total=mods.value,
        situational=situational,
        total=total,
        target=target,
        margin=margin,
        degree=degree,
        success=success,
        advantage=mods.advantage,
        critical=critical,
        rules_consulted=tuple(consulted),
    )


def resolve_opposed(
    ruleset: Ruleset,
    dice: DiceService,
    calc: StatCalculator,
    attacker: ActorState,
    defender: ActorState,
    *,
    check_key: str = "check.opposed",
    attacker_attribute: str | None = None,
    attacker_skill: str | None = None,
    defender_attribute: str | None = None,
    defender_skill: str | None = None,
    ctx: dict[str, Any] | None = None,
    purpose: str = "",
) -> OpposedResult:
    cdef = ruleset.checks.get(check_key)
    if cdef is None:
        raise CheckError(f"unknown check {check_key!r}")
    if cdef.versus != "opposed":
        raise RulesetError(f"{check_key} is not an opposed check")
    a = resolve_check(
        ruleset,
        dice,
        calc,
        attacker,
        check_key,
        attribute=attacker_attribute,
        skill=attacker_skill,
        ctx=ctx,
        purpose=purpose or f"{check_key}:attacker",
    )
    b = resolve_check(
        ruleset,
        dice,
        calc,
        defender,
        check_key,
        attribute=defender_attribute,
        skill=defender_skill,
        ctx=ctx,
        purpose=purpose or f"{check_key}:defender",
    )
    margin = a.total - b.total
    tie = margin == 0
    if margin > 0:
        winner = "a"
    elif margin < 0:
        winner = "b"
    else:
        winner = {"defender": "b", "attacker": "a", "success": "a", "failure": "b"}[cdef.tie]
    return OpposedResult(a=a, b=b, winner=winner, tie=tie, margin=margin)


def preview_check(
    ruleset: Ruleset,
    calc: StatCalculator,
    state: ActorState,
    check_key: str,
    *,
    attribute: str | None = None,
    skill: str | None = None,
    difficulty: int | str | None = None,
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """What a check will be, without rolling (dice step, play session 2026-10-05): the die,
    the bonus the actor brings and the number to reach. The same arithmetic as
    `resolve_check`, so the card the player sees matches what resolution will use."""
    ctx = dict(ctx or {})
    cdef: CheckDef = ruleset.checks[check_key]
    attribute = attribute or cdef.attribute
    skill = skill or cdef.skill
    if skill and attribute is None:
        attribute = ruleset.skills[skill].default_attribute
    attr_value = calc.calculate(state, attribute, ctx).value if attribute else 0
    skill_value = calc.calculate(state, skill, ctx).value if skill else 0
    mods = calc.check_modifier(state, check_key, ctx)
    target = _target_value(ruleset, difficulty) if cdef.versus == "difficulty" else None
    return {
        "check": check_key,
        "die": _advantage_roll(cdef.roll, mods.advantage),
        "attribute": attribute,
        "attribute_value": attr_value,
        "skill": skill,
        "skill_value": skill_value,
        "modifier_total": mods.value,
        "modifier_lines": [str(x) for x in mods.lines],
        "bonus": attr_value + skill_value + mods.value,
        "target": target,
        "advantage": mods.advantage,
    }
