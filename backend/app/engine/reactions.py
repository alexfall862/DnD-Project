"""Reaction eligibility and significance scoring (orchestration §12).

Not every actor in a scene receives a model call after every event. The orchestrator builds a
`ReactionSignals` per AI actor from what just happened (deterministic, perspective-safe
inputs), scores it here, and only the top visible reactions get a call; medium ones update
silently, low ones are ignored. Pure functions so the thresholds are testable.
"""

from __future__ import annotations

from dataclasses import dataclass

IMPORTANCE_WEIGHT = {"background": 0.4, "standard": 0.7, "important": 0.9, "full": 1.0}
HIGH = 0.55
MEDIUM = 0.3


@dataclass(frozen=True)
class ReactionSignals:
    actor_id: str
    importance: str = "standard"
    direct_target: bool = False  # addressed, whispered to, attacked
    asked: bool = False  # received a question (stance question) they could answer
    danger: bool = False  # in combat and an enemy is active / took damage
    new_information: bool = False  # received at least one Claim
    goal_relevant: bool = False  # a Claim or action touched one of the actor's goal targets
    relationship_relevant: bool = False  # the acting actor is someone they hold a relationship with
    emotional_weight: float = 0.0  # strongest active emotion intensity 0..1
    novelty: float = 0.0  # 0..1; 1 = first time this kind of thing happened in the scene
    combat_turn: bool = False  # it is this actor's initiative turn
    scene_importance: float = 0.7


def eligible(s: ReactionSignals) -> bool:
    return (
        s.direct_target
        or s.asked
        or s.danger
        or s.new_information
        or s.goal_relevant
        or s.relationship_relevant
        or s.emotional_weight >= 0.6
        or s.combat_turn
    )


def significance(s: ReactionSignals) -> float:
    if not eligible(s):
        return 0.0
    score = 0.0
    score += 0.60 if s.direct_target else 0.45 if s.asked else 0.0
    score += 0.30 if s.danger else 0.0
    score += 0.25 if s.goal_relevant else 0.0
    score += 0.15 if s.relationship_relevant else 0.0
    score += 0.15 if s.new_information else 0.0
    score += 0.15 * s.novelty
    score += 0.20 * s.emotional_weight
    score += 0.50 if s.combat_turn else 0.0
    score *= 0.5 + 0.5 * s.scene_importance
    score *= IMPORTANCE_WEIGHT.get(s.importance, 0.7)
    return round(min(score, 1.0), 3)


def tier(score: float) -> str:
    """high → visible action/dialogue (a model call); medium → internal state only (no call
    in 06b, recorded as a silent update); low → nothing."""
    if score >= HIGH:
        return "high"
    if score >= MEDIUM:
        return "medium"
    return "low"
