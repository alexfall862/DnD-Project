"""Prose roles never show structure to the player (play session 2: raw JSON in the narration
and two table-assistant answers), and the table assistant's TRY lines become suggestions."""

from __future__ import annotations

import pytest

from app.services.orchestrator import split_suggestions
from app.services.prose import prose_only

pytestmark = pytest.mark.unit


def test_plain_prose_is_untouched() -> None:
    assert prose_only("  The rain eases.  ") == "The rain eases."


def test_json_and_fences_are_unwrapped_to_their_text() -> None:
    assert prose_only('{"narration": "The guard waves you through."}') == (
        "The guard waves you through."
    )
    assert prose_only('```json\n{"answer": "You carry a coin purse."}\n```') == (
        "You carry a coin purse."
    )
    cut = '{"narration": "The wagon creaks forward and the gate swings op'
    assert prose_only(cut).startswith("The wagon creaks forward")


def test_try_lines_become_suggestions() -> None:
    body, tries = split_suggestions(
        "You could look closer.\nTRY: I search the hedge for a gap\n- TRY: I ask the guard\n"
        "TRY: I ask the guard"
    )
    assert body == "You could look closer."
    assert tries == ["I search the hedge for a gap", "I ask the guard"]


def test_described_speech_keeps_only_the_line() -> None:
    from app.services.orchestrator import described_speech

    assert (
        described_speech("I tell the older guard firmly that his captain will hear about this.")
        == "His captain will hear about this."
    )
    assert described_speech("Open the gate!") == "Open the gate!"


def test_a_consequence_written_as_an_effect_step_moves_to_its_branch() -> None:
    """A9 outcomes eval: GLM wrote reveal_feature in on_success and the whole ruling was
    rejected; an unknown primitive is still refused."""
    from app.ai.roles import RulesAdjudicatorOut
    from app.engine.core import RulesEngine
    from app.engine.effects import EffectError
    from app.services.orchestrator import SessionOrchestrator

    orch = SessionOrchestrator.__new__(SessionOrchestrator)
    orch.engine = RulesEngine.load("core_adventure", master_seed=1)
    out = orch.validate_ruling(
        RulesAdjudicatorOut.model_validate(
            {
                "requires_check": True,
                "check": {"skill": "skill.investigation", "attribute": "attr.intellect"},
                "on_success": [
                    {"type": "reveal_feature", "params": {"description": "a gap in the hedge"}}
                ],
            }
        )
    )
    assert out["on_success"] == []
    assert out["consequences"]["success"] == [
        {"kind": "reveal_feature", "description": "a gap in the hedge"}
    ]
    with pytest.raises(EffectError):
        orch.validate_ruling(
            RulesAdjudicatorOut.model_validate(
                {"requires_check": False, "on_success": [{"type": "run_python", "params": {}}]}
            )
        )


def test_a_line_from_an_earlier_turn_is_cut_even_with_full_stops_inside() -> None:
    from app.services.orchestrator import drop_repeated_quotes

    earlier = ["Just my luck. First the inspections, now false promises."]
    text = (
        "The guard waves you through. As you step into town, the merchant mutters, "
        '"Just my luck. First the inspections, now false promises." The rain eases.'
    )
    out, removed = drop_repeated_quotes(text, [], earlier)
    assert out == "The guard waves you through. The rain eases."
    assert removed
    same, none = drop_repeated_quotes(text, ['Merchant says: "' + earlier[0] + '"'], earlier)
    assert same == text and not none


def test_two_copies_of_a_consequence_are_one() -> None:
    from app.services.consequences import identity

    a = {"kind": "open_route", "label": "a gap in the town wall", "to": "warehouse_district"}
    b = {**a, "minutes": 3}
    c = {"kind": "open_route", "label": "a culvert", "to": "warehouse_district"}
    assert identity(a) == identity(b) != identity(c)
