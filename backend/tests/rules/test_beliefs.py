"""belief-update-rules.md §3–§7 as parametrised unit tests with the Frostbridge seed values."""

from __future__ import annotations

import pytest

from app.engine.beliefs import (
    BeliefProposal,
    ExistingBelief,
    GateInput,
    Proposition,
    RelationshipView,
    apply_insight,
    belief_processor_gate,
    from_document,
    from_mechanic,
    from_observation,
    from_testimony,
    meta_belief_that_asserted,
    reconcile,
    speaker_self_belief,
)

pytestmark = [pytest.mark.unit, pytest.mark.rules]

MIRA_INVOLVED = Proposition("involved in disappearance of", subject="mira", object="oric")
RENN_WEEKS = Proposition("last spoke to", subject="renn", object="oric", value="weeks ago")


def test_observation_table():
    assert from_observation(MIRA_INVOLVED, 1.0).belief_type == "known"
    partial = from_observation(MIRA_INVOLVED, 0.6)
    assert partial.belief_type == "believed" and partial.confidence == 0.6
    assert from_mechanic(MIRA_INVOLVED) == BeliefProposal(
        MIRA_INVOLVED, "known", 1.0, "mechanic", ("deterministic mechanical outcome",)
    )
    assert from_document(MIRA_INVOLVED).confidence == 0.85
    assert from_document(MIRA_INVOLVED, 0.7).confidence == 0.595  # forged/unsigned


def test_elara_from_alex_worked_value():
    """Elara ← Alex (trust 60), stance uncertain: 0.35 + 0.21 = 0.56 (cap 0.60) → suspected."""
    p = from_testimony(MIRA_INVOLVED, "uncertain", RelationshipView(trust=60, familiarity=50), [])
    assert p.confidence == pytest.approx(0.585)  # + familiarity 50 * 0.0005 = 0.025
    assert p.belief_type == "suspected"
    p0 = from_testimony(MIRA_INVOLVED, "uncertain", RelationshipView(trust=60), [])
    assert p0.confidence == pytest.approx(0.56) and p0.belief_type == "suspected"


def test_tomas_from_renn_stranger_worked_value():
    """Tomas ← Renn, no relationship: 0.35 → suspected; +0.10 if consistent with a prior."""
    p = from_testimony(RENN_WEEKS, "asserts_true", None, [])
    assert p.confidence == pytest.approx(0.35) and p.belief_type == "suspected"
    prior = ExistingBelief(RENN_WEEKS, "assumption", 0.4)
    p2 = from_testimony(RENN_WEEKS, "asserts_true", None, [prior])
    assert p2.confidence == pytest.approx(0.45)


def test_contradiction_penalty_and_caps():
    strong = ExistingBelief(RENN_WEEKS.negated(), "believed", 0.8)
    p = from_testimony(RENN_WEEKS, "asserts_true", RelationshipView(trust=100), [strong])
    assert p.confidence == pytest.approx(0.35 + 0.35 - 0.20) and p.belief_type == "suspected"
    assert (
        from_testimony(RENN_WEEKS, "hypothetical", RelationshipView(trust=100), []).confidence
        == 0.30
    )
    assert (
        from_testimony(RENN_WEEKS, "asserts_true", RelationshipView(trust=-100), []).confidence
        == 0.05
    )
    assert (
        from_testimony(
            RENN_WEEKS, "asserts_true", RelationshipView(trust=100, familiarity=100), []
        ).confidence
        == 0.75
    )


def test_self_report_and_secondhand():
    p = from_testimony(
        Proposition("was at the docks", subject="renn"),
        "asserts_true",
        None,
        [],
        about_speaker_self=True,
    )
    assert p.confidence == pytest.approx(0.45)
    p2 = from_testimony(
        RENN_WEEKS, "asserts_true", RelationshipView(trust=80), [], speaker_secondhand=True
    )
    assert p2.belief_type == "rumor" and p2.confidence == pytest.approx(0.63)


def test_meta_belief_and_speaker_self_belief():
    m = meta_belief_that_asserted("alex", MIRA_INVOLVED)
    assert m.belief_type == "known" and m.confidence == 1.0 and m.proposition.subject == "alex"
    s = speaker_self_belief(MIRA_INVOLVED, "uncertain")
    assert s is not None and s.belief_type == "stated" and s.confidence == 0.55
    assert speaker_self_belief(MIRA_INVOLVED, "asserts_true").confidence == 0.8
    assert speaker_self_belief(MIRA_INVOLVED, "question") is None


def test_reconcile_supersede_contest_weaker_and_observation_wins():
    held = ExistingBelief(RENN_WEEKS, "believed", 0.5)
    stronger = BeliefProposal(RENN_WEEKS.negated(), "believed", 0.75, "told")
    r = reconcile(stronger, [held])
    assert r.supersede == (held,) and not r.contest_with
    close = BeliefProposal(RENN_WEEKS.negated(), "believed", 0.6, "told")
    r = reconcile(close, [held])
    assert r.contest_with == (held,) and not r.supersede
    weak = BeliefProposal(RENN_WEEKS.negated(), "rumor", 0.2, "told")
    r = reconcile(weak, [held])
    assert r.weaker_alternative and not r.supersede and not r.contest_with
    seen = BeliefProposal(RENN_WEEKS.negated(), "known", 1.0, "witnessed")
    assert reconcile(seen, [ExistingBelief(RENN_WEEKS, "believed", 0.95)]).supersede
    # identical proposition already held at least as strongly from testimony: skip
    assert reconcile(BeliefProposal(RENN_WEEKS, "suspected", 0.4, "told"), [held]).skip
    assert reconcile(BeliefProposal(RENN_WEEKS, "known", 1.0, "witnessed"), [held]).supersede == (
        held,
    )


def test_insight_halves_confidence_and_never_reveals_truth():
    p = from_testimony(RENN_WEEKS, "asserts_true", None, [])
    unchanged, extra = apply_insight(
        p, insight_success=False, deliberate_false=True, speaker="renn"
    )
    assert unchanged is p and extra == []
    doubted, extra = apply_insight(p, insight_success=True, deliberate_false=True, speaker="renn")
    assert doubted.belief_type == "doubted" and doubted.confidence == pytest.approx(0.175)
    assert extra[0].proposition.predicate == "seemed evasive" and extra[0].belief_type == "known"
    assert "lied" not in doubted.proposition.predicate
    gone, extra = apply_insight(
        p, insight_success=True, deliberate_false=True, speaker="renn", truth_detection=True
    )
    assert gone is None and extra[0].proposition.predicate == "lied about"
    honest, extra = apply_insight(p, insight_success=True, deliberate_false=False, speaker="mira")
    assert honest is p and extra == []


@pytest.mark.parametrize(
    "gate, conf, expected",
    [
        (GateInput(True, "full", True, False), 0.56, True),  # Elara, goal-relevant, near 0.6
        (GateInput(True, "full", True, False), 0.45, True),  # near 0.3/0.6 both within 0.15
        (GateInput(True, "full", True, False), 0.80, False),  # not near a boundary
        (GateInput(True, "full", False, False), 0.56, False),  # not goal relevant
        (GateInput(True, "background", True, False), 0.56, False),
        (GateInput(False, "full", True, False), 0.56, False),  # human recipient
        (GateInput(True, "important", False, True), 0.80, False),
        (GateInput(True, "important", False, True, contested_count=2), 0.80, True),
    ],
)
def test_belief_processor_gate(gate, conf, expected):
    assert (
        belief_processor_gate(gate, BeliefProposal(RENN_WEEKS, "believed", conf, "told"))
        is expected
    )


def test_proposition_key_and_negation_round_trip():
    p = Proposition("met", subject="renn", object="oric")
    assert p.negated().predicate == "not met" and p.negated().negated() == p
    assert Proposition.from_dict(p.to_dict()) == p and p.key == "renn|met|oric|"
