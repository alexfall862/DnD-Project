"""Triggers with a hard depth/effect budget (rules-engine §15).

Triggers live on conditions and traits. `TriggerEngine.fire(state, kind, ctx)` runs every
matching trigger's effects. Nested firing (damage → trigger → damage → …) is bounded by
`MAX_TRIGGER_DEPTH`/`MAX_EFFECTS_PER_CHAIN` in `effects.py`; when the budget is hit the chain
halts with a `noop` mutation that says so instead of recursing further.
"""

from __future__ import annotations

from typing import Any

from app.engine.effects import MAX_TRIGGER_DEPTH, EffectContext, Mutation, apply_steps
from app.engine.expressions import ExpressionError, compile_expr, evaluate
from app.engine.ruleset import Ruleset, TriggerDef


class TriggerEngine:
    def __init__(self, ruleset: Ruleset) -> None:
        self.rs = ruleset

    def _triggers(self, state, kind: str) -> list[tuple[str, TriggerDef]]:
        found: list[tuple[str, TriggerDef]] = []
        for c in state.conditions:
            d = self.rs.conditions.get(c.key)
            if d:
                found += [(c.key, t) for t in d.triggers if t.event == kind]
        for t_key in state.traits:
            d = self.rs.traits.get(t_key)
            if d:
                found += [(t_key, t) for t in d.triggers if t.event == kind]
        return found

    def fire(self, state, kind: str, ctx: EffectContext) -> list[Mutation]:
        if ctx.depth > MAX_TRIGGER_DEPTH:
            ctx.budget_exhausted = True
            return [
                Mutation(
                    "noop",
                    state.actor_key,
                    kind,
                    None,
                    None,
                    ctx.source,
                    {"reason": "trigger depth exhausted", "depth": ctx.depth},
                )
            ]
        out: list[Mutation] = []
        for owner, t in self._triggers(state, kind):
            if t.condition is not None:
                try:
                    if not evaluate(
                        compile_expr(t.condition), ctx.calc.resolver(state, ctx.values)
                    ):
                        continue
                except ExpressionError:
                    continue
            out += apply_steps(t.effects, state, ctx.child(source=owner))
        return out

    def hook(self):
        """Callable for `EffectContext.fire`."""

        def _fire(state, kind: str, ctx: EffectContext) -> list[Mutation]:
            return self.fire(state, kind, ctx)

        return _fire

    def describe(self, state) -> dict[str, list[dict[str, Any]]]:
        kinds: dict[str, list[dict[str, Any]]] = {}
        for kind in {t.event for _, t in self._triggers(state, "*")} | {
            t.event for c in state.conditions for t in self.rs.conditions[c.key].triggers
        }:
            kinds[kind] = [
                {"owner": o, "effects": [e.type for e in t.effects]}
                for o, t in self._triggers(state, kind)
            ]
        return kinds
