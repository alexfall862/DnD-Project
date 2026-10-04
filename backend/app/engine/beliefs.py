"""Deterministic belief-update rules (docs/specifications/belief-update-rules.md §3–§6).

Pure functions over small value objects so the tables in the spec are unit-testable with the
Frostbridge seed values. The Belief Processor model (§7) is gated elsewhere and may only
adjust a result produced here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STANCE_CAP = {
    "asserts_true": 0.95,
    "asserts_false": 0.95,
    "uncertain": 0.60,
    "hypothetical": 0.30,
    "question": 0.0,
}
BASE = 0.35
TRUST_COEF = 0.0035
FAMILIARITY_COEF = 0.0005
PLAUSIBLE_BONUS = 0.10
CONTRADICT_PENALTY = 0.20
SELF_REPORT_BONUS = 0.10
SUPERSEDE_MARGIN = 0.20
DOCUMENT_BASE = 0.85


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def type_for_confidence(confidence: float, *, secondhand: bool = False) -> str:
    if secondhand or confidence < 0.3:
        return "rumor"
    if confidence >= 0.6:
        return "believed"
    return "suspected"


@dataclass(frozen=True)
class Proposition:
    predicate: str
    subject: str | None = None
    object: str | None = None
    value: Any = None

    @property
    def key(self) -> str:
        value = "" if self.value is None else self.value
        return f"{self.subject or '_'}|{self.predicate}|{self.object or '_'}|{value}"

    def negated(self) -> Proposition:
        p = self.predicate
        return Proposition(
            p[4:] if p.startswith("not ") else f"not {p}", self.subject, self.object, self.value
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_entity_id": self.subject,
            "predicate": self.predicate,
            "object_entity_id": self.object,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Proposition:
        return cls(
            d["predicate"], d.get("subject_entity_id"), d.get("object_entity_id"), d.get("value")
        )


@dataclass
class ExistingBelief:
    proposition: Proposition
    belief_type: str
    confidence: float
    status: str = "active"
    ref: Any = None  # caller's handle (row id)


@dataclass(frozen=True)
class RelationshipView:
    trust: int = 0
    familiarity: int = 0


@dataclass(frozen=True)
class BeliefProposal:
    proposition: Proposition
    belief_type: str
    confidence: float
    source_type: str
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Reconciliation:
    """What to do with an incoming belief relative to the actor's existing ones."""

    new: BeliefProposal
    supersede: tuple[ExistingBelief, ...] = ()
    contest_with: tuple[ExistingBelief, ...] = ()
    weaker_alternative: bool = False
    skip: bool = False  # identical active belief already held at >= confidence


# ---------------------------------------------------------------------------------------------
# §3 direct observation / documents / mechanics
# ---------------------------------------------------------------------------------------------


def from_observation(prop: Proposition, observation_confidence: float) -> BeliefProposal:
    c = clamp(observation_confidence, 0.0, 1.0)
    if c >= 0.9:
        return BeliefProposal(prop, "known", c, "witnessed", ("clear primary sense",))
    return BeliefProposal(prop, "believed", c, "witnessed", ("partial/degraded observation",))


def from_mechanic(prop: Proposition) -> BeliefProposal:
    return BeliefProposal(prop, "known", 1.0, "mechanic", ("deterministic mechanical outcome",))


def from_document(prop: Proposition, document_trust: float = 1.0) -> BeliefProposal:
    return BeliefProposal(
        prop,
        "believed",
        round(DOCUMENT_BASE * document_trust, 3),
        "read",
        (f"document trust {document_trust}",),
    )


# ---------------------------------------------------------------------------------------------
# §4 testimony
# ---------------------------------------------------------------------------------------------


def from_testimony(
    prop: Proposition,
    stance: str,
    relationship: RelationshipView | None,
    existing: list[ExistingBelief],
    *,
    about_speaker_self: bool = False,
    speaker_secondhand: bool = False,
    contradicted_by_observation: bool = False,
) -> BeliefProposal:
    """Confidence a recipient R assigns to a Claim from speaker S."""
    rel = relationship or RelationshipView()
    reasons: list[str] = [f"base {BASE}"]
    conf = BASE
    trust_term = TRUST_COEF * rel.trust
    conf += trust_term
    reasons.append(f"trust {rel.trust} -> {trust_term:+.3f}")
    fam = FAMILIARITY_COEF * rel.familiarity
    conf += fam
    if fam:
        reasons.append(f"familiarity {rel.familiarity} -> {fam:+.3f}")
    consistent = [b for b in existing if b.status != "superseded" and b.proposition.key == prop.key]
    contradicting = [
        b for b in existing if b.status != "superseded" and b.proposition.key == prop.negated().key
    ]
    if consistent:
        conf += PLAUSIBLE_BONUS
        reasons.append("consistent with an active belief +0.10")
    elif any(b.confidence > conf for b in contradicting):
        conf -= CONTRADICT_PENALTY
        reasons.append("contradicts a stronger active belief -0.20")
    if about_speaker_self and not contradicted_by_observation:
        conf += SELF_REPORT_BONUS
        reasons.append("self-report +0.10")
    cap = STANCE_CAP.get(stance, 0.95)
    conf = clamp(round(conf, 3), 0.05, cap)
    reasons.append(f"stance {stance} cap {cap}")
    return BeliefProposal(
        prop, type_for_confidence(conf, secondhand=speaker_secondhand), conf, "told", tuple(reasons)
    )


def meta_belief_that_asserted(speaker: str, prop: Proposition) -> BeliefProposal:
    """R always also gains `known 1.0` that S asserted P."""
    return BeliefProposal(
        Proposition("asserted", subject=speaker, value=prop.key),
        "known",
        1.0,
        "witnessed",
        ("the Claim itself is a fact",),
    )


def speaker_self_belief(prop: Proposition, stance: str) -> BeliefProposal | None:
    """Human speech is evidence of the speaker's own state (c&k §3): assert 0.8, uncertain 0.55."""
    if stance == "asserts_true":
        return BeliefProposal(prop, "stated", 0.8, "stated")
    if stance == "uncertain":
        return BeliefProposal(prop, "stated", 0.55, "stated")
    return None


# ---------------------------------------------------------------------------------------------
# §5 contradiction and supersession
# ---------------------------------------------------------------------------------------------


def reconcile(new: BeliefProposal, existing: list[ExistingBelief]) -> Reconciliation:
    key, neg = new.proposition.key, new.proposition.negated().key
    same = [b for b in existing if b.status != "superseded" and b.proposition.key == key]
    conflicting = [b for b in existing if b.status != "superseded" and b.proposition.key == neg]
    # identical proposition already held: keep the stronger; observation always wins over testimony
    if same:
        strongest = max(same, key=lambda b: b.confidence)
        if new.source_type != "witnessed" and strongest.confidence >= new.confidence:
            return Reconciliation(new, skip=True)
        return Reconciliation(new, supersede=tuple(same))
    if not conflicting:
        return Reconciliation(new)
    if new.belief_type == "known" and new.source_type == "witnessed":
        return Reconciliation(new, supersede=tuple(conflicting))
    strongest = max(conflicting, key=lambda b: b.confidence)
    if new.confidence >= strongest.confidence + SUPERSEDE_MARGIN:
        return Reconciliation(new, supersede=tuple(conflicting))
    if abs(new.confidence - strongest.confidence) < SUPERSEDE_MARGIN:
        return Reconciliation(new, contest_with=tuple(conflicting))
    return Reconciliation(new, weaker_alternative=True)


# ---------------------------------------------------------------------------------------------
# §6 deception and insight
# ---------------------------------------------------------------------------------------------


def apply_insight(
    proposal: BeliefProposal,
    *,
    insight_success: bool,
    deliberate_false: bool,
    speaker: str,
    truth_detection: bool = False,
) -> tuple[BeliefProposal | None, list[BeliefProposal]]:
    """Returns (possibly adjusted main belief, extra beliefs). Insight never reveals truth."""
    if not deliberate_false or not insight_success:
        return proposal, []
    if truth_detection:
        return None, [
            BeliefProposal(
                Proposition("lied about", subject=speaker, value=proposal.proposition.key),
                "known",
                1.0,
                "mechanic",
                ("truth detection",),
            )
        ]
    doubted = BeliefProposal(
        proposal.proposition,
        "doubted",
        round(proposal.confidence * 0.5, 3),
        proposal.source_type,
        proposal.reasons + ("insight: halved",),
    )
    evasive = BeliefProposal(
        Proposition("seemed evasive", subject=speaker),
        "known",
        1.0,
        "witnessed",
        ("insight success",),
    )
    return doubted, [evasive]


# ---------------------------------------------------------------------------------------------
# §7 gating (decision only; the model call itself lives in the orchestrator)
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GateInput:
    recipient_is_ai: bool
    recipient_importance: str  # background|standard|important|full
    goal_relevant: bool
    contradicts_strong_belief: bool  # contradicts an active belief with confidence >= 0.6
    contested_count: int = 0


TYPE_BOUNDARIES = (0.3, 0.6)


def near_type_boundary(confidence: float, margin: float = 0.15) -> bool:
    return any(abs(confidence - b) <= margin for b in TYPE_BOUNDARIES)


def belief_processor_gate(g: GateInput, proposal: BeliefProposal) -> bool:
    if not g.recipient_is_ai or g.recipient_importance not in ("important", "full"):
        return False
    if not (g.goal_relevant or g.contradicts_strong_belief):
        return False
    return near_type_boundary(proposal.confidence) or g.contested_count >= 2


__all__ = [n for n in dir() if not n.startswith("_")]
_ = field
