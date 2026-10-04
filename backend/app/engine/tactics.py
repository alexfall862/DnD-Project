"""Minimal tactical controller and fallback policies (orchestration §19–§20;
turn-budget-and-latency §5 step 4).

Two deterministic pieces:

- `FallbackPolicy` — what an AI combatant recorded last time it was asked ("attack X; if X is
  gone attack the nearest hostile; if none reachable take cover; flee below 30% health").
  `situation_unchanged` decides whether the policy may be reused without a fresh model call.
- `choose_action` — turns a tactical intent into ONE legal action for the current scene
  (attack if the target is in reach, otherwise close in, otherwise cover/flee). It never sees
  narrative secrets: only the mechanical scene the resolver would see anyway.
- `behavior_reaction_chooser` — a `ReactionChooser` for combat reaction windows (defend when
  attacked, opportunity attack when an enemy disengages) driven by behaviour dimensions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.engine.actions import ReactionChoice, ReactionWindow, SceneContext

HEALTH = "resource.health"


@dataclass
class FallbackPolicy:
    target: str | None = None  # preferred hostile target (actor key)
    intent: str = "attack"  # attack | protect | hold | flee
    flee_below: float = 0.3  # fraction of max health
    protect: str | None = None  # ally to stay near when intent == protect
    hp_at_decision: int | None = None
    scene_version: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "intent": self.intent,
            "flee_below": self.flee_below,
            "protect": self.protect,
            "hp_at_decision": self.hp_at_decision,
            "scene_version": self.scene_version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> FallbackPolicy | None:
        if not d:
            return None
        return cls(
            d.get("target"),
            d.get("intent", "attack"),
            float(d.get("flee_below", 0.3)),
            d.get("protect"),
            d.get("hp_at_decision"),
            d.get("scene_version"),
            dict(d.get("metadata") or {}),
        )


def _hp(ctx: SceneContext, actor: str) -> tuple[int, int]:
    st = ctx.states[actor]
    cur = st.resources[HEALTH].current if HEALTH in st.resources else 0
    try:
        mx = ctx.engine.stat(st, f"{HEALTH}.max").value
    except Exception:  # noqa: BLE001 - a build without health still gets a policy
        mx = max(cur, 1)
    return cur, int(mx) if mx else max(cur, 1)


def _standing(ctx: SceneContext, actor: str) -> bool:
    st = ctx.states.get(actor)
    return bool(
        st is not None
        and not st.has_condition("condition.incapacitated")
        and not st.has_condition("condition.surrendered")
        and actor in ctx.space.positions
        and (ctx.encounter is None or actor not in ctx.encounter.departed)
    )


def hostiles(ctx: SceneContext, actor: str) -> list[str]:
    enc = ctx.encounter
    if enc is None:
        return []
    return [
        a for a in enc.participants if a != actor and enc.hostile(actor, a) and _standing(ctx, a)
    ]


def reachable(ctx: SceneContext, actor: str, target: str) -> bool:
    """Can `actor` attack `target` with the equipped weapon from where they stand?"""
    st = ctx.states[actor]
    try:
        weapon = st.weapon(ctx.engine.ruleset)
    except Exception:  # noqa: BLE001
        return False
    wdef = ctx.engine.ruleset.equipment.get(weapon.def_key)
    if wdef is None or wdef.attack_check is None:
        return False
    band = ctx.space.band(actor, target)
    if not wdef.range_bands:
        return band == "engaged"
    return band in wdef.range_bands


def situation_unchanged(ctx: SceneContext, actor: str, policy: FallbackPolicy) -> bool:
    """turn-budget §5 step 4: same target alive and reachable (or reachable by closing in),
    own HP above the flee threshold, nothing new to react to."""
    if not ctx.in_combat or not _standing(ctx, actor):
        return False
    cur, mx = _hp(ctx, actor)
    if mx and cur / mx < policy.flee_below:
        return False
    if policy.hp_at_decision is not None and cur < policy.hp_at_decision * 0.5:
        return False  # took a beating since deciding; worth a fresh look
    if policy.intent == "attack":
        return (
            policy.target is not None
            and _standing(ctx, policy.target)
            and (policy.target in hostiles(ctx, actor))
        )
    return True


def choose_action(
    ctx: SceneContext, actor: str, policy: FallbackPolicy
) -> tuple[str, str | None, str]:
    """One legal action for this turn: (action_key, target, reason)."""
    enc = ctx.encounter
    budget = enc.budget(actor) if enc else None
    cur, mx = _hp(ctx, actor)
    if mx and cur / mx < policy.flee_below:
        return "action.flee", None, "health below flee threshold"
    foes = hostiles(ctx, actor)
    if policy.intent == "flee":
        return "action.flee", None, "policy: flee"
    if not foes:
        return "action.wait", None, "no standing hostiles"
    target = policy.target if policy.target in foes else None
    if target is None:
        # nearest hostile: engaged < close < far
        order = {"engaged": 0, "close": 1, "far": 2, "distant": 3}
        target = min(foes, key=lambda f: order.get(ctx.space.band(actor, f), 9))
    has_major = budget is None or budget.major >= 1
    has_move = budget is None or budget.movement >= 1
    if reachable(ctx, actor, target) and has_major:
        return "action.attack", target, f"attack {target}"
    band = ctx.space.band(actor, target)
    if band == "close" and has_move:
        return "action.engage", target, f"close to melee with {target}"
    if band in ("near", "far", "distant") and has_move:
        here = ctx.space.position(actor).zone
        path = ctx.space.path(here, ctx.space.position(target).zone)
        if path and len(path) > 1:
            steps = ctx.engine.ruleset.actions["action.move"].resolution.movement_steps or 1
            return "action.move", path[min(steps, len(path) - 1)], f"move toward {target}"
    if has_major and ctx.space.position(actor).cover == "none":
        return "action.take_cover", None, "no reachable target; take cover"
    return "action.wait", None, "nothing useful to do"


def behavior_reaction_chooser(ctx_dims: dict[str, dict[str, float]]):
    """A `ReactionChooser` for AI combatants. `ctx_dims` maps actor key -> behaviour
    dimensions. Defend when attacked (always); opportunity attack when an enemy disengages if
    aggression >= 0.4; protect an engaged ally if loyalty >= 0.6."""

    def choose(w: ReactionWindow) -> ReactionChoice | None:
        for reactor, key in w.eligible:
            dims = ctx_dims.get(reactor, {})
            if w.trigger == "attacked" and key == "action.defend" and reactor == w.target:
                return ReactionChoice(reactor, key, None)
            if (
                w.trigger == "enemy_disengages"
                and key == "action.opportunity_attack"
                and dims.get("aggression", 0.5) >= 0.4
            ):
                return ReactionChoice(reactor, key, w.acting_actor)
            if (
                w.trigger == "ally_attacked"
                and key == "action.protect"
                and dims.get("loyalty", 0.5) >= 0.6
                and w.target is not None
            ):
                return ReactionChoice(reactor, key, w.target)
        return None

    return choose
