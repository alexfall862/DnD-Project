"""RulesEngine facade: one object that ties ruleset, dice, stats, checks, effects and
triggers together, plus deterministic state hashing for replay tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.engine import checks as _checks
from app.engine.dice import DiceService, SeedStream
from app.engine.effects import EffectContext, Mutation, apply_steps, expire
from app.engine.ruleset import Ruleset, load_ruleset
from app.engine.stats import ActorState, StatCalculator, StatResult
from app.engine.triggers import TriggerEngine

RULESETS_DIR = Path(__file__).resolve().parents[2] / "rulesets"


class RulesEngine:
    def __init__(self, ruleset: Ruleset, dice: DiceService | None = None) -> None:
        self.ruleset = ruleset
        self.dice = dice or DiceService(SeedStream())
        self.calc = StatCalculator(ruleset)
        self.triggers = TriggerEngine(ruleset)

    @classmethod
    def load(cls, ruleset_key: str, *, master_seed: int | None = None) -> RulesEngine:
        rs = load_ruleset(RULESETS_DIR / ruleset_key)
        return cls(rs, DiceService(SeedStream(master_seed)))

    # -- state ---------------------------------------------------------------------------------

    def actor(self, actor_key: str, profile: dict[str, Any]) -> ActorState:
        return ActorState.from_profile(self.ruleset, actor_key, profile)

    def stat(self, state: ActorState, target: str, ctx: dict[str, Any] | None = None) -> StatResult:
        return self.calc.calculate(state, target, ctx)

    def context(self, *, tick: int = 0, source: str | None = None, **values: Any) -> EffectContext:
        return EffectContext(
            ruleset=self.ruleset,
            dice=self.dice,
            calc=self.calc,
            tick=tick,
            source=source,
            values=values,
            fire=self.triggers.hook(),
        )

    # -- mechanics -----------------------------------------------------------------------------

    def check(self, state: ActorState, check_key: str, **kw: Any) -> _checks.CheckResult:
        return _checks.resolve_check(self.ruleset, self.dice, self.calc, state, check_key, **kw)

    def opposed(
        self, attacker: ActorState, defender: ActorState, **kw: Any
    ) -> _checks.OpposedResult:
        return _checks.resolve_opposed(self.ruleset, self.dice, self.calc, attacker, defender, **kw)

    def apply(
        self, state: ActorState, steps: list[dict[str, Any]], ctx: EffectContext | None = None
    ) -> list[Mutation]:
        return apply_steps(steps, state, ctx or self.context())

    def fire(
        self, state: ActorState, kind: str, ctx: EffectContext | None = None
    ) -> list[Mutation]:
        return self.triggers.fire(state, kind, ctx or self.context())

    def advance(self, state: ActorState, tick: int) -> list[Mutation]:
        return expire(state, tick, self.context(tick=tick))

    # -- replay --------------------------------------------------------------------------------

    @staticmethod
    def state_hash(*states: ActorState) -> str:
        """Canonical hash of mechanical state (ignores instance/modifier ids and timestamps)."""
        payload = []
        for s in states:
            p = s.to_profile(include_hidden=True)
            for c in p["conditions"]:
                c.pop("instance_id", None)
            for m in p["temp_modifiers"]:
                m.pop("modifier_id", None)
            payload.append({"actor": s.actor_key, **p})
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
