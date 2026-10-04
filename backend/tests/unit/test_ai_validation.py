"""Structured output: lenient extraction, conveys normalisation, Pydantic validation."""

from __future__ import annotations

import json

import pytest

from app.ai.roles import AIPlayerOut, IntentInterpreterOut, NPCActorOut
from app.ai.validation import extract_json, normalize_conveys, validate_output

pytestmark = pytest.mark.unit

GOOD = {
    "decision_summary": "Agree quietly.",
    "spoken_text": "She looked at the guards.",
    "speech_channel": "whisper",
    "speech_target_ref": "alex",
    "conveys": [{"kind": "belief_ref", "ref_id": "b_12345678", "stance": "asserts_true"}],
    "intentions": [
        {"action_type": "observe", "target_ref": "mira", "description": "watch", "private": True}
    ],
    "belief_proposals": [],
    "emotion_proposals": [],
}


def test_extract_json_handles_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```')[0] == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": {"b": 2}} hope that helps')[0] == {"a": {"b": 2}}
    assert extract_json("[1,2]")[0] is None and extract_json("nope")[1]


def test_stray_predicate_moves_into_proposition_and_kind_follows_the_id():
    obj = {
        "conveys": [
            {
                "kind": "proposition",
                "predicate": "met Oric",
                "subject_entity_id": "renn",
                "stance": "asserts_false",
            },
            {
                "kind": "fact_ref",
                "ref_id": "b_elara_5",
                "stance": "asserts_true",
            },  # belief id tagged as fact (04b finding 3)
            {"kind": "belief_ref", "ref_id": "f_renn_1"},
            {
                "kind": "belief_ref",
                "stance": "uncertain",
                "proposition": {"predicate": "x"},
            },  # ref kind without a ref
        ]
    }
    out = normalize_conveys(obj)["conveys"]
    assert (
        out[0]["proposition"] == {"predicate": "met Oric", "subject_entity_id": "renn"}
        and "predicate" not in out[0]
    )
    assert (
        out[1]["kind"] == "belief_ref"
        and out[2]["kind"] == "fact_ref"
        and out[3]["kind"] == "proposition"
    )
    assert all("fidelity" in c and "about_speaker_self" in c for c in out)


def test_validate_output_roundtrip_and_errors():
    model, obj, errors = validate_output(json.dumps(GOOD), AIPlayerOut)
    assert model is not None and not errors and model.conveys[0].ref_id == "b_12345678"
    bad = dict(GOOD, decision_summary="", intentions=[{"description": "no type"}])
    model, obj, errors = validate_output(json.dumps(bad), AIPlayerOut)
    assert (
        model is None
        and any("decision_summary" in e for e in errors)
        and any("action_type" in e for e in errors)
    )
    model, obj, errors = validate_output("not json at all", AIPlayerOut)
    assert model is None and errors[0].startswith("json:")


def test_intent_and_npc_schemas_accept_spike_shaped_output():
    intent = {
        "channel": "whisper",
        "confidence": 0.9,
        "targets": ["elara"],
        "intents": [{"order": 1, "action_type": "whisper", "target_ref": "elara"}],
        "ambiguities": [],
        "requires_clarification": False,
        "clarification_question": None,
        "conveys": [
            {
                "kind": "proposition",
                "proposition": {"subject_entity_id": "mira", "predicate": "involved"},
                "stance": "uncertain",
            }
        ],
        "asserted_facts": [
            {
                "proposition": {"predicate": "has a compass"},
                "class": "self_minor",
                "mechanical_weight": "none",
            }
        ],
        "conversation_time_band": "brief",
    }
    m, _, errs = validate_output(json.dumps(intent), IntentInterpreterOut)
    assert m is not None and m.asserted_facts[0].class_ == "self_minor", errs
    npc = {
        "decision_summary": "Deflect.",
        "speech_act": {"type": "evade"},
        "spoken_text": "People come and go.",
        "conveys": [],
        "intentions": [],
        "emotion_proposals": [{"emotion": "anxious", "intensity": 0.5}],
    }
    m, _, errs = validate_output(json.dumps(npc), NPCActorOut)
    assert m is not None and m.speech_act.type == "evade", errs


def test_a_cut_off_answer_is_repaired_in_the_role_s_own_shape() -> None:
    """A9 generation runs: the actor-specific truncation instruction turned a World Author
    stage into an NPC speech. Only actor roles get it."""
    from app.ai.runner import TRUNCATED_GENERIC, TRUNCATED_INSTRUCTION, truncated_instruction

    assert truncated_instruction("npc_actor") == TRUNCATED_INSTRUCTION
    assert truncated_instruction("ai_player") == TRUNCATED_INSTRUCTION
    for role in ("world_author", "world_simulator", "brief_interviewer", "memory_processor"):
        text = truncated_instruction(role)
        assert text == TRUNCATED_GENERIC and "spoken_text" not in text and "conveys" not in text


def test_a_cut_off_list_keeps_its_complete_items() -> None:
    from app.ai.validation import salvage_truncated_json

    cut = (
        '```json\n{"summary": "x", "actors": [{"ref": "a", "name": "A"}, {"ref": "b", '
        '"name": "B", "goals": [{"description": "q"}]}, {"ref": "c", "name": "C, the \\"tall'
    )
    fixed = salvage_truncated_json(cut)
    data = json.loads(fixed)
    assert [a["ref"] for a in data["actors"]] == ["a", "b"]  # c was incomplete: dropped
    nested = '{"actors": [{"ref": "a"}, {"ref": "b", "goals": [{"d": "x"}, {"d": "y"}], "na'
    assert [a["ref"] for a in json.loads(salvage_truncated_json(nested))["actors"]] == ["a"]
    assert salvage_truncated_json('{"a": 1}') == '{"a": 1}'
    assert salvage_truncated_json("no json here") is None
