"""JSON schemas for the spike — the *intended* contracts from ai-contracts.md / c&k.md §2.

Kept as close to the specified shapes as possible (nested `proposition` objects) so the spike
measures the real thing; if schema-valid rates are poor, option (b) in the milestone is to
flatten these before Milestone 05.
"""

from __future__ import annotations

from typing import Any

STANCES = ["asserts_true", "asserts_false", "uncertain", "question", "hypothetical"]
FIDELITY = ["full", "partial", "distorted"]
BELIEF_TYPES = [
    "known", "believed", "suspected", "rumor", "opinion", "assumption", "inference",
    "false_memory", "stated", "doubted",
]

PROPOSITION: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subject_entity_id": {"type": ["string", "null"]},
        "predicate": {"type": "string", "minLength": 1},
        "object_entity_id": {"type": ["string", "null"]},
        "value": {"type": ["string", "number", "boolean", "null"]},
    },
    "required": ["predicate"],
    "additionalProperties": False,
}

CONVEYS_ITEM: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {"enum": ["belief_ref", "fact_ref", "proposition"]},
        "ref_id": {"type": ["string", "null"]},
        "proposition": {"anyOf": [PROPOSITION, {"type": "null"}]},
        "stance": {"enum": STANCES},
        "fidelity": {"enum": FIDELITY},
        "deliberate_false": {"type": "boolean"},
        "about_speaker_self": {"type": "boolean"},
    },
    "required": ["kind", "stance", "fidelity", "deliberate_false", "about_speaker_self"],
    "additionalProperties": False,
}

CONVEYS: dict[str, Any] = {"type": "array", "items": CONVEYS_ITEM}

INTENTION: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action_type": {"type": "string", "minLength": 1},
        "target_ref": {"type": ["string", "null"]},
        "description": {"type": "string"},
        "private": {"type": "boolean"},
    },
    "required": ["action_type", "description", "private"],
    "additionalProperties": False,
}

BELIEF_PROPOSAL: dict[str, Any] = {
    "type": "object",
    "properties": {
        "proposition": PROPOSITION,
        "belief_type": {"enum": BELIEF_TYPES},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["proposition", "belief_type", "confidence"],
    "additionalProperties": False,
}

EMOTION_PROPOSAL: dict[str, Any] = {
    "type": "object",
    "properties": {
        "emotion": {"type": "string", "minLength": 1},
        "intensity": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["emotion", "intensity"],
    "additionalProperties": False,
}

AI_PLAYER: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision_summary": {"type": "string", "minLength": 1, "maxLength": 600},
        "spoken_text": {"type": ["string", "null"]},
        "speech_channel": {"enum": ["say", "whisper", "none"]},
        "speech_target_ref": {"type": ["string", "null"]},
        "conveys": CONVEYS,
        "intentions": {"type": "array", "items": INTENTION},
        "belief_proposals": {"type": "array", "items": BELIEF_PROPOSAL},
        "emotion_proposals": {"type": "array", "items": EMOTION_PROPOSAL},
    },
    "required": [
        "decision_summary", "spoken_text", "speech_channel", "conveys", "intentions",
        "belief_proposals", "emotion_proposals",
    ],
    "additionalProperties": False,
}

NPC_ACTOR: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision_summary": {"type": "string", "minLength": 1, "maxLength": 600},
        "speech_act": {
            "type": "object",
            "properties": {
                "type": {"enum": ["answer", "evade", "refuse", "lie", "bargain", "silence", "other"]},
                "knowingly_false": {"type": "boolean"},
            },
            "required": ["type", "knowingly_false"],
            "additionalProperties": False,
        },
        "spoken_text": {"type": ["string", "null"]},
        "conveys": CONVEYS,
        "intentions": {"type": "array", "items": INTENTION},
        "emotion_proposals": {"type": "array", "items": EMOTION_PROPOSAL},
    },
    "required": ["decision_summary", "speech_act", "spoken_text", "conveys", "intentions",
                 "emotion_proposals"],
    "additionalProperties": False,
}

NARRATOR: dict[str, Any] = {
    "type": "object",
    "properties": {
        "narration": {"type": "string", "minLength": 40},
        "incidental_detail_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "classification": {"enum": ["furnishing", "condition", "appearance", "extra", "other"]},
                    "description": {"type": "string"},
                },
                "required": ["classification", "description"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["narration", "incidental_detail_candidates"],
    "additionalProperties": False,
}

ASSERTED_FACT: dict[str, Any] = {
    "type": "object",
    "properties": {
        "proposition": PROPOSITION,
        "class": {"enum": ["self_minor", "self_major", "world_minor", "world_major", "contradiction"]},
        "mechanical_weight": {"enum": ["none", "minor", "significant"]},
    },
    "required": ["proposition", "class", "mechanical_weight"],
    "additionalProperties": False,
}

INTENT_ITEM: dict[str, Any] = {
    "type": "object",
    "properties": {
        "order": {"type": "integer", "minimum": 1},
        "action_type": {"type": "string", "minLength": 1},
        "target_ref": {"type": ["string", "null"]},
        "params": {"type": "object"},
    },
    "required": ["order", "action_type", "target_ref"],
    "additionalProperties": False,
}

INTENT_INTERPRETER: dict[str, Any] = {
    "type": "object",
    "properties": {
        "channel": {"enum": ["do", "say", "whisper", "private", "ooc"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "targets": {"type": "array", "items": {"type": "string"}},
        "intents": {"type": "array", "items": INTENT_ITEM},
        "ambiguities": {"type": "array", "items": {"type": "string"}},
        "requires_clarification": {"type": "boolean"},
        "clarification_question": {"type": ["string", "null"]},
        "conveys": CONVEYS,
        "asserted_facts": {"type": "array", "items": ASSERTED_FACT},
        "conversation_time_band": {"enum": ["brief", "normal", "long", "extended", "none"]},
    },
    "required": [
        "channel", "confidence", "targets", "intents", "ambiguities", "requires_clarification",
        "clarification_question", "conveys", "asserted_facts", "conversation_time_band",
    ],
    "additionalProperties": False,
}
