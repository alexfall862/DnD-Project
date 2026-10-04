"""Declarative ruleset packages: definitions, loading, reference validation (rules-engine §3).

A ruleset is a directory with `manifest.yaml` listing definition files. Definitions are
Pydantic models keyed by stable ids (`attr.might`, `skill.stealth`, `resource.health`,
`condition.burning`, `check.core`, `stat.defense`, `trait.keen_observer`). Formulas are safe
expressions (`expressions.py`); effect steps use registered primitives (`effects.py`).

`Ruleset.validate()` proves every reference resolves, every expression parses, every effect
type is registered, and no condition/trigger graph can recurse without bound.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.engine.expressions import ExpressionError, compile_expr, references

Formula = str | int | float | bool | dict[str, Any]


class RulesetError(ValueError):
    pass


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    name: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class AttributeDef(Definition):
    min: int = 1
    max: int = 10
    default: int = 3


class SkillDef(Definition):
    default_attribute: str  # attr.* key
    group: str = ""
    max_rank: int = 5


class ModifierDef(BaseModel):
    """A declarative modifier granted by a trait, condition or equipment (rules-engine §9)."""

    model_config = ConfigDict(extra="forbid")
    target: (
        str  # e.g. "stat.defense", "resource.health.max", "attr.agility", "check.core", "check.*"
    )
    op: Literal["add", "subtract", "multiply", "set", "advantage", "disadvantage"]
    value: Formula = 0
    condition: Formula | None = None  # evaluated against the actor state; None = always
    priority: int = 0
    note: str = ""


class EffectStep(BaseModel):
    """One registered primitive invocation (rules-engine §13)."""

    model_config = ConfigDict(extra="forbid")
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class TriggerDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: str  # on_round_end, on_damage, on_condition_applied, on_rest, on_time_elapsed, ...
    effects: list[EffectStep]
    condition: Formula | None = None
    target: Literal["self", "source"] = "self"


class TraitDef(Definition):
    modifiers: list[ModifierDef] = Field(default_factory=list)
    triggers: list[TriggerDef] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class ResourceDef(Definition):
    max_formula: Formula
    min: int = 0
    overflow: Literal["clamp", "allow"] = "clamp"
    depletion: Literal["clamp", "allow"] = "clamp"
    visibility: Literal["public", "owner", "hidden"] = "owner"
    on_depleted: list[EffectStep] = Field(
        default_factory=list
    )  # e.g. apply_condition incapacitated
    recovery: dict[str, Formula] = Field(
        default_factory=dict
    )  # {"short_rest": "...", "long_rest": "..."}


class DerivedStatDef(Definition):
    formula: Formula


class MarginBand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    degree: str
    min: int | None = None  # inclusive; None = -inf
    max: int | None = None  # inclusive; None = +inf
    success: bool


class CheckDef(Definition):
    roll: str = "1d20"
    attribute: str | None = None  # attr.* or None (chosen per use)
    skill: str | None = None  # skill.* or None
    versus: Literal["difficulty", "stat", "opposed"] = "difficulty"
    versus_stat: str | None = None  # stat.* key when versus == "stat"
    tie: Literal["defender", "attacker", "success", "failure"] = "defender"
    critical_low: int | None = 1
    critical_high: int | None = 20
    modifier_targets: list[str] = Field(default_factory=list)  # extra modifier targets consulted


class ConditionDef(Definition):
    stacking: Literal["none", "refresh", "intensity", "independent"] = "none"
    max_intensity: int = 1
    modifiers: list[ModifierDef] = Field(default_factory=list)
    triggers: list[TriggerDef] = Field(default_factory=list)
    on_apply: list[EffectStep] = Field(default_factory=list)
    on_remove: list[EffectStep] = Field(default_factory=list)
    removed_by: list[str] = Field(default_factory=list)  # rest types / action keys / "medicine"
    default_duration_seconds: int | None = None
    blocks_targeting: bool = False  # e.g. Hidden


class DamageTypeDef(Definition):
    pass


class TargetingDef(BaseModel):
    """Declarative targeting (rules-engine §11)."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["none", "self", "actor", "zone", "item"] = "none"
    bands: list[str] | None = None  # allowed range bands; None = any
    hostile_only: bool = False
    ally_only: bool = False
    requires_los: bool = True
    count: int = 1


class ResolutionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "attack",
        "check",
        "move",
        "engage",
        "disengage",
        "take_cover",
        "rest",
        "effects",
        "surrender",
        "flee",
        "pickup",
        "drop",
        "defend",
        "protect",
        "interrupt",
        "wait",
    ] = "effects"
    check: str | None = None  # check.* key for attack/check kinds
    attribute: str | None = None
    skill: str | None = None
    difficulty: int | str | None = None
    weapon_slot: str | None = None  # equipment slot supplying damage for attacks
    on_success: list[EffectStep] = Field(default_factory=list)
    on_failure: list[EffectStep] = Field(default_factory=list)
    effects: list[EffectStep] = Field(default_factory=list)  # unconditional
    rest_kind: str | None = None
    movement_steps: int = 1
    cover_level: str | None = None


class ActionDef(Definition):
    category: str = "interaction"  # movement|attack|defense|interaction|social|exploration|...
    cost: dict[str, int | bool] = Field(
        default_factory=dict
    )  # major/movement/reaction/free, stamina, resolve_points
    time_cost_seconds: int = 6
    targeting: TargetingDef = Field(default_factory=TargetingDef)
    requirements: list[Formula] = Field(
        default_factory=list
    )  # all must hold; refs ctx.*/attr.* ...
    resolution: ResolutionDef = Field(default_factory=ResolutionDef)
    reaction_trigger: str | None = None  # attacked | ally_attacked | enemy_disengages | ...
    unsafe_movement: bool = False  # provokes opportunity attacks when leaving engagement


class EquipmentDef(Definition):
    """Equipment templates (rules-engine §21). Instances carry public/hidden properties."""

    slot: Literal["weapon", "armor", "shield", "gear"] = "gear"
    melee: bool = True
    damage: str | None = None  # dice expression
    damage_type: str = "damage.physical"
    attack_check: str | None = None  # check.melee_attack / check.ranged_attack
    attribute_bonus: Formula = 0  # added to damage (tunable, core-adventure §10)
    range_bands: dict[str, int | None] = Field(
        default_factory=dict
    )  # band -> attack modifier, None = cannot
    modifiers: list[ModifierDef] = Field(default_factory=list)  # armour: stat.defense etc.
    capabilities: list[str] = Field(default_factory=list)
    two_handed: bool = False


class RulesetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    name: str
    version: str
    engine_schema_version: int = 1
    description: str = ""
    files: list[str]
    difficulty_scale: dict[str, int] = Field(default_factory=dict)
    margins: list[MarginBand] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("margins")
    @classmethod
    def _bands_cover_line(cls, bands: list[MarginBand]) -> list[MarginBand]:
        if not bands:
            return bands
        ordered = sorted(bands, key=lambda b: b.min if b.min is not None else -(10**9))
        if ordered[0].min is not None or ordered[-1].max is not None:
            raise ValueError("margin bands must be open-ended at both ends")
        for a, b in zip(ordered, ordered[1:], strict=False):
            if a.max is None or b.min is None or b.min != a.max + 1:
                raise ValueError(f"margin bands must be contiguous: {a} / {b}")
        return ordered


DEF_TYPES: dict[str, type[Definition]] = {
    "attributes": AttributeDef,
    "skills": SkillDef,
    "traits": TraitDef,
    "resources": ResourceDef,
    "derived_stats": DerivedStatDef,
    "checks": CheckDef,
    "conditions": ConditionDef,
    "damage_types": DamageTypeDef,
    "actions": ActionDef,
    "equipment": EquipmentDef,
}
PREFIX: dict[str, str] = {
    "attributes": "attr.",
    "skills": "skill.",
    "traits": "trait.",
    "resources": "resource.",
    "derived_stats": "stat.",
    "checks": "check.",
    "conditions": "condition.",
    "damage_types": "damage.",
    "actions": "action.",
    "equipment": "item.",
}


class Ruleset:
    def __init__(self, manifest: RulesetManifest, source_dir: Path | None = None) -> None:
        self.manifest = manifest
        self.source_dir = source_dir
        self.defs: dict[str, dict[str, Definition]] = {k: {} for k in DEF_TYPES}
        self.content_hash = ""

    # -- access ---------------------------------------------------------------------------------

    @property
    def key(self) -> str:
        return self.manifest.key

    def add(self, section: str, definition: Definition) -> None:
        prefix = PREFIX[section]
        if not definition.key.startswith(prefix):
            raise RulesetError(f"{section} key {definition.key!r} must start with {prefix!r}")
        if definition.key in self.defs[section]:
            raise RulesetError(f"duplicate definition {definition.key!r}")
        self.defs[section][definition.key] = definition

    def get(self, key: str) -> Definition:
        for section, prefix in PREFIX.items():
            if key.startswith(prefix):
                try:
                    return self.defs[section][key]
                except KeyError:
                    raise RulesetError(f"unknown definition {key!r}") from None
        raise RulesetError(f"unknown definition family for {key!r}")

    def has(self, key: str) -> bool:
        try:
            self.get(key)
            return True
        except RulesetError:
            return False

    def section(self, name: str) -> dict[str, Any]:
        return self.defs[name]

    @property
    def attributes(self) -> dict[str, AttributeDef]:
        return self.defs["attributes"]  # type: ignore[return-value]

    @property
    def skills(self) -> dict[str, SkillDef]:
        return self.defs["skills"]  # type: ignore[return-value]

    @property
    def resources(self) -> dict[str, ResourceDef]:
        return self.defs["resources"]  # type: ignore[return-value]

    @property
    def conditions(self) -> dict[str, ConditionDef]:
        return self.defs["conditions"]  # type: ignore[return-value]

    @property
    def traits(self) -> dict[str, TraitDef]:
        return self.defs["traits"]  # type: ignore[return-value]

    @property
    def checks(self) -> dict[str, CheckDef]:
        return self.defs["checks"]  # type: ignore[return-value]

    @property
    def derived_stats(self) -> dict[str, DerivedStatDef]:
        return self.defs["derived_stats"]  # type: ignore[return-value]

    @property
    def actions(self) -> dict[str, ActionDef]:
        return self.defs["actions"]  # type: ignore[return-value]

    @property
    def equipment(self) -> dict[str, EquipmentDef]:
        return self.defs["equipment"]  # type: ignore[return-value]

    def degree_for_margin(self, margin: int) -> MarginBand:
        for band in self.manifest.margins:
            lo = band.min if band.min is not None else -(10**9)
            hi = band.max if band.max is not None else 10**9
            if lo <= margin <= hi:
                return band
        raise RulesetError("no margin band matched")  # unreachable after validation

    # -- validation -----------------------------------------------------------------------------

    def validate(self, effect_types: set[str]) -> None:
        problems: list[str] = []
        if True:
            for d in self.skills.values():
                if not self.has(d.default_attribute):
                    problems.append(f"{d.key}: default_attribute {d.default_attribute!r} unknown")
        for d in self.resources.values():
            problems += self._check_formula(d.key, "max_formula", d.max_formula)
            for k, f in d.recovery.items():
                problems += self._check_formula(d.key, f"recovery.{k}", f)
            problems += self._check_steps(d.key, d.on_depleted, effect_types)
        for d in self.derived_stats.values():
            problems += self._check_formula(d.key, "formula", d.formula)
        for d in self.checks.values():
            if d.attribute and not self.has(d.attribute):
                problems.append(f"{d.key}: attribute {d.attribute!r} unknown")
            if d.skill and not self.has(d.skill):
                problems.append(f"{d.key}: skill {d.skill!r} unknown")
            if d.versus == "stat" and (not d.versus_stat or not self.has(d.versus_stat)):
                problems.append(f"{d.key}: versus_stat {d.versus_stat!r} unknown")
        for items in (self.traits, self.conditions):
            for d in items.values():
                for m in d.modifiers:
                    problems += self._check_modifier(d.key, m)
                for t in d.triggers:
                    problems += self._check_steps(d.key, t.effects, effect_types)
                    if t.condition is not None:
                        problems += self._check_formula(d.key, "trigger.condition", t.condition)
                if isinstance(d, ConditionDef):
                    problems += self._check_steps(d.key, d.on_apply, effect_types)
                    problems += self._check_steps(d.key, d.on_remove, effect_types)
        for d in self.actions.values():
            for f in d.requirements:
                problems += self._check_formula(d.key, "requirement", f)
            r = d.resolution
            if r.check and not self.has(r.check):
                problems.append(f"{d.key}: resolution.check {r.check!r} unknown")
            if r.attribute and not self.has(r.attribute):
                problems.append(f"{d.key}: resolution.attribute {r.attribute!r} unknown")
            if r.skill and not self.has(r.skill):
                problems.append(f"{d.key}: resolution.skill {r.skill!r} unknown")
            if isinstance(r.difficulty, str) and r.difficulty not in self.manifest.difficulty_scale:
                problems.append(f"{d.key}: unknown difficulty {r.difficulty!r}")
            if d.targeting.bands:
                known = set(self.manifest.settings.get("range_bands", []))
                bad = [b for b in d.targeting.bands if known and b not in known]
                problems += [f"{d.key}: unknown range band {b!r}" for b in bad]
            for steps in (r.on_success, r.on_failure, r.effects):
                problems += self._check_steps(d.key, steps, effect_types)
            for ck in ("major", "movement", "reaction", "free"):
                v = d.cost.get(ck)
                if v is not None and not isinstance(v, bool):
                    problems.append(f"{d.key}: cost.{ck} must be boolean")
            for rk in d.cost:
                if rk.startswith("resource.") and not self.has(rk):
                    problems.append(f"{d.key}: cost resource {rk!r} unknown")
        for d in self.equipment.values():
            if d.damage:
                try:
                    from app.engine.dice import parse_dice

                    parse_dice(d.damage)
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"{d.key}: damage {d.damage!r}: {exc}")
            if not self.has(d.damage_type):
                problems.append(f"{d.key}: damage_type {d.damage_type!r} unknown")
            if d.attack_check and not self.has(d.attack_check):
                problems.append(f"{d.key}: attack_check {d.attack_check!r} unknown")
            problems += self._check_formula(d.key, "attribute_bonus", d.attribute_bonus)
            for m in d.modifiers:
                problems += self._check_modifier(d.key, m)
            known = set(self.manifest.settings.get("range_bands", []))
            problems += [
                f"{d.key}: unknown range band {b!r}"
                for b in d.range_bands
                if known and b not in known
            ]
        if not self.manifest.margins:
            problems.append("manifest: margins table is required")
        problems += self._check_trigger_cycles()
        if problems:
            raise RulesetError(f"ruleset {self.key!r} invalid:\n  - " + "\n  - ".join(problems))

    def _check_formula(self, owner: str, field: str, formula: Formula) -> list[str]:
        try:
            expr = compile_expr(formula)
        except ExpressionError as exc:
            return [f"{owner}.{field}: {exc}"]
        bad = [r for r in references(expr) if not self._ref_known(r)]
        return [f"{owner}.{field}: unknown reference {r!r}" for r in bad]

    def _ref_known(self, ref: str) -> bool:
        """References allowed in formulas: attr.*, skill.*, stat.*, trait.*, condition.*,
        resource.<key>.current / .max, and engine-provided ctx.* values."""
        if ref.startswith("ctx."):
            return True
        if ref.startswith("resource."):
            parts = ref.split(".")
            return (
                len(parts) == 3 and parts[2] in ("current", "max") and self.has(".".join(parts[:2]))
            )
        return self.has(ref)

    def _check_modifier(self, owner: str, m: ModifierDef) -> list[str]:
        out: list[str] = []
        t = m.target
        if t == "check.*" or t.startswith("check."):
            if t != "check.*" and not self.has(t):
                out.append(f"{owner}: modifier target {t!r} unknown")
        elif t.startswith("resource."):
            parts = t.split(".")
            if len(parts) != 3 or parts[2] != "max" or not self.has(".".join(parts[:2])):
                out.append(f"{owner}: modifier target {t!r} must be resource.<key>.max")
        elif not (
            t.startswith("stat.") or t.startswith("attr.") or t.startswith("skill.")
        ) or not self.has(t):
            out.append(f"{owner}: modifier target {t!r} unknown")
        out += self._check_formula(owner, "modifier.value", m.value)
        if m.condition is not None:
            out += self._check_formula(owner, "modifier.condition", m.condition)
        if m.op in ("advantage", "disadvantage") and not t.startswith("check."):
            out.append(f"{owner}: {m.op} only applies to check.* targets")
        return out

    def _check_steps(
        self, owner: str, steps: list[EffectStep], effect_types: set[str]
    ) -> list[str]:
        out: list[str] = []
        for s in steps:
            if s.type not in effect_types:
                out.append(f"{owner}: unknown effect primitive {s.type!r}")
                continue
            for pk in ("condition", "resource", "attribute", "damage_type"):
                v = s.params.get(pk)
                if isinstance(v, str) and not self.has(v):
                    out.append(f"{owner}: effect {s.type} references unknown {pk} {v!r}")
            for pk in ("amount", "value"):
                v = s.params.get(pk)
                if v is not None and not isinstance(v, str | int | float | dict):
                    out.append(f"{owner}: effect {s.type} param {pk} has bad type")
        return out

    def _check_trigger_cycles(self) -> list[str]:
        """A condition whose triggers (transitively) apply itself is an unbounded loop at
        definition level. Detect condition → trigger → apply_condition → condition cycles."""
        graph: dict[str, set[str]] = {}
        for d in self.conditions.values():
            targets: set[str] = set()
            for t in d.triggers:
                for s in t.effects:
                    if s.type == "apply_condition" and isinstance(s.params.get("condition"), str):
                        targets.add(s.params["condition"])
            for s in d.on_apply:
                if s.type == "apply_condition" and isinstance(s.params.get("condition"), str):
                    targets.add(s.params["condition"])
            graph[d.key] = targets
        problems: list[str] = []
        state: dict[str, int] = {}

        def visit(node: str, path: list[str]) -> None:
            if state.get(node) == 1:
                problems.append("condition trigger cycle: " + " -> ".join(path + [node]))
                return
            if state.get(node) == 2:
                return
            state[node] = 1
            for nxt in graph.get(node, ()):
                visit(nxt, path + [node])
            state[node] = 2

        for node in graph:
            if state.get(node) is None:
                visit(node, [])
        return problems


# ---------------------------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------------------------


def _iter_defs(doc: Any, file: str) -> Iterator[tuple[str, dict[str, Any]]]:
    if not isinstance(doc, dict):
        raise RulesetError(f"{file}: top level must be a mapping of section -> list")
    for section, items in doc.items():
        if section not in DEF_TYPES:
            raise RulesetError(f"{file}: unknown section {section!r}")
        if not isinstance(items, list):
            raise RulesetError(f"{file}: section {section!r} must be a list")
        for item in items:
            yield section, item


def load_ruleset(path: str | Path, *, effect_types: set[str] | None = None) -> Ruleset:
    """Load and validate a ruleset package directory. `effect_types` defaults to the engine's
    registered primitives."""
    from app.engine.effects import REGISTRY  # local import: effects imports nothing from here

    root = Path(path)
    manifest_path = root / "manifest.yaml"
    if not manifest_path.exists():
        raise RulesetError(f"no manifest.yaml in {root}")
    try:
        manifest = RulesetManifest.model_validate(
            yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        )
    except Exception as exc:  # noqa: BLE001
        raise RulesetError(f"manifest.yaml invalid: {exc}") from exc
    rs = Ruleset(manifest, root)
    hasher = hashlib.sha256(manifest_path.read_bytes())
    for file in manifest.files:
        fp = root / file
        if not fp.exists():
            raise RulesetError(f"manifest lists missing file {file!r}")
        raw = fp.read_bytes()
        hasher.update(raw)
        doc = yaml.safe_load(raw.decode("utf-8"))
        for section, item in _iter_defs(doc, file):
            try:
                d = DEF_TYPES[section].model_validate(item)
            except Exception as exc:  # noqa: BLE001 - surface pydantic detail with file context
                ident = item.get("key") if isinstance(item, dict) else repr(item)
                raise RulesetError(f"{file}: invalid {section} entry {ident}: {exc}") from exc
            rs.add(section, d)
    rs.content_hash = hasher.hexdigest()
    rs.validate(effect_types if effect_types is not None else set(REGISTRY))
    return rs


def ruleset_summary(rs: Ruleset) -> dict[str, Any]:
    return {
        "key": rs.key,
        "version": rs.manifest.version,
        "content_hash": rs.content_hash,
        "counts": {k: len(v) for k, v in rs.defs.items()},
    }


def dump_definition(d: Definition) -> str:
    return json.dumps(d.model_dump(), sort_keys=True)
