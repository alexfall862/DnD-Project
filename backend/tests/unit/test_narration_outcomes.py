"""A9 Frostbridge slice (Milestone 10 run): the narrator was given only the player's words, so an
invalid pick-up and a rejected read were narrated as successes. It now receives the outcome of
each attempt, and the outcome lines are binding."""

from __future__ import annotations

import uuid

from app.services.narration import STYLE_PRESETS, NarrativeBundle
from app.services.orchestrator import PlayResult, narration_outcomes


def result(**kw) -> PlayResult:
    return PlayResult(uuid.uuid4(), **kw)


def test_each_attempt_reaches_the_narrator_with_its_outcome() -> None:
    r = result(
        actions=[
            {"action": "action.search", "target": "office", "status": "succeeded"},
            {
                "action": "action.pick_up",
                "target": None,
                "status": "invalid",
                "reason": "item required",
            },
            {"action": "action.attack", "target": "thief", "status": "failed"},
        ]
    )
    lines = narration_outcomes(r)
    assert lines[0] == "search (office): succeeded"
    assert "pick up: did NOT happen" in lines[1] and "item required" in lines[1]
    assert "FAILED" in lines[2]


def test_a_rejected_ruling_is_an_attempt_without_effect() -> None:
    r = result(mechanical_notices=["(OOC) ruling rejected: 2 validation errors for EffectStep"])
    (line,) = narration_outcomes(r)
    assert "no effect" in line and "validation" not in line  # no engine internals
    assert narration_outcomes(result()) == []  # plain speech: nothing to report


def test_outcomes_lead_the_narrators_situation() -> None:
    b = NarrativeBundle(
        uuid.uuid4(),
        observations=[],
        dialogue=[],
        mechanics=[],
        scene_line="",
        style={},
        own_input="I pick up the dagger.",
        outcomes=["pick up: did NOT happen (not possible right now); do not narrate it happening"],
    )
    text = b.situation()
    assert text.index("I pick up the dagger.") < text.index("Outcome of what you attempted")
    assert "did NOT happen" in text


def test_narration_style_presets_are_known() -> None:
    assert set(STYLE_PRESETS) == {"terse", "standard", "rich"}
