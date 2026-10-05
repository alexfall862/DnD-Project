"""Role registry (orchestration §3; ai-contracts §3–§15, §21).

Each role declares: default profile, prompt id, allowed/forbidden context types, output model
(or None for prose), output budget, temperature, and the authority its proposals may carry.
Permissions and typed contracts enforce behaviour; prompts only guide it (orchestration §40).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.worldgen.envelope import WorldAuthorOut

Stance = Literal["asserts_true", "asserts_false", "uncertain", "question", "hypothetical"]
Fidelity = Literal["full", "partial", "distorted"]
BeliefType = Literal[
    "known",
    "believed",
    "suspected",
    "rumor",
    "opinion",
    "assumption",
    "inference",
    "false_memory",
    "stated",
    "doubted",
]


class Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class PropositionOut(Lenient):
    subject_entity_id: str | None = None
    predicate: str = Field(min_length=1)
    object_entity_id: str | None = None
    value: str | int | float | bool | None = None


class ConveysItemOut(Lenient):
    kind: Literal["belief_ref", "fact_ref", "proposition"]
    ref_id: str | None = None
    proposition: PropositionOut | None = None
    stance: Stance = "asserts_true"
    fidelity: Fidelity = "full"
    about_speaker_self: bool = False
    contradicts_ref: str | None = (
        None  # the engine derives deliberate_false from this (04b finding)
    )


class IntentionOut(Lenient):
    action_type: str = Field(min_length=1)
    target_ref: str | None = None
    description: str = ""
    private: bool = False


class BeliefProposalOut(Lenient):
    proposition: PropositionOut
    belief_type: BeliefType
    confidence: float = Field(ge=0, le=1)


class EmotionProposalOut(Lenient):
    emotion: str = Field(min_length=1)
    intensity: float = Field(ge=0, le=1)


class RelationshipProposalOut(Lenient):
    """Bounded, event-linked relationship change proposed by the actor's own decision
    (world-memory §11). The engine clamps the delta and records provenance."""

    target_ref: str
    dimension: Literal[
        "trust", "affection", "respect", "fear", "resentment", "obligation", "familiarity"
    ]
    delta: int = Field(ge=-10, le=10)
    reason: str = ""


class GoalUpdateOut(Lenient):
    goal_ref: str | None = None  # g1, g2 ... from context; None = new goal
    status: Literal["active", "succeeded", "failed", "abandoned"] | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    description: str | None = None


class FallbackPolicyOut(Lenient):
    target_ref: str | None = None
    intent: Literal["attack", "protect", "hold", "flee"] = "attack"
    flee_below: float = Field(default=0.3, ge=0, le=1)
    protect_ref: str | None = None


class AIPlayerOut(Lenient):
    decision_summary: str = Field(min_length=1, max_length=600)
    spoken_text: str | None = None
    speech_channel: Literal["say", "whisper", "none"] = "none"
    speech_target_ref: str | None = None
    conveys: list[ConveysItemOut] = Field(default_factory=list)
    intentions: list[IntentionOut] = Field(default_factory=list)
    belief_proposals: list[BeliefProposalOut] = Field(default_factory=list)
    emotion_proposals: list[EmotionProposalOut] = Field(default_factory=list)
    goal_updates: list[GoalUpdateOut] = Field(default_factory=list)
    relationship_proposals: list[RelationshipProposalOut] = Field(default_factory=list)
    fallback_policy: FallbackPolicyOut | None = None


class SpeechActOut(Lenient):
    type: Literal["answer", "evade", "refuse", "lie", "bargain", "silence", "other"] = "answer"
    knowingly_false: bool = (
        False  # speaker-private; the engine also derives it from contradicts_ref
    )


class NPCActorOut(Lenient):
    decision_summary: str = Field(min_length=1, max_length=600)
    speech_act: SpeechActOut = Field(default_factory=SpeechActOut)
    spoken_text: str | None = None
    speech_channel: Literal["say", "whisper", "none"] = "say"  # whisper needs a target
    speech_target_ref: str | None = None
    conveys: list[ConveysItemOut] = Field(default_factory=list)
    intentions: list[IntentionOut] = Field(default_factory=list)
    belief_proposals: list[BeliefProposalOut] = Field(default_factory=list)
    emotion_proposals: list[EmotionProposalOut] = Field(default_factory=list)
    relationship_proposals: list[RelationshipProposalOut] = Field(default_factory=list)
    fallback_policy: FallbackPolicyOut | None = None


class IntentItemOut(Lenient):
    order: int = Field(ge=1)
    action_type: str = Field(min_length=1)
    target_ref: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class AssertedFactOut(Lenient):
    proposition: PropositionOut
    class_: Literal["self_minor", "self_major", "world_minor", "world_major", "contradiction"] = (
        Field(alias="class")
    )
    mechanical_weight: Literal["none", "minor", "significant"] = "none"
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class IntentInterpreterOut(Lenient):
    channel: Literal["do", "say", "whisper", "private", "ooc"]
    confidence: float = Field(ge=0, le=1)
    targets: list[str] = Field(default_factory=list)
    intents: list[IntentItemOut] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    requires_clarification: bool = False
    clarification_question: str | None = None
    conveys: list[ConveysItemOut] = Field(default_factory=list)
    asserted_facts: list[AssertedFactOut] = Field(default_factory=list)
    conversation_time_band: Literal["brief", "normal", "long", "extended", "none"] = "none"
    # the exact words the character says aloud, when the player describes speech instead of
    # quoting it ("I want to ask him where he's from" -> "Where are you coming from?")
    utterance: str | None = None


class MaterializedGoalOut(Lenient):
    description: str = Field(min_length=1)
    priority: int = Field(default=50, ge=1, le=100)


class MaterializedMemoryOut(Lenient):
    summary: str = Field(min_length=1)
    salience: float = Field(default=0.6, ge=0, le=1)


class AttitudeOut(Lenient):
    trust: int = Field(default=30, ge=0, le=100)
    respect: int = Field(default=30, ge=0, le=100)
    affection: int = Field(default=10, ge=0, le=100)
    fear: int = Field(default=0, ge=0, le=100)
    resentment: int = Field(default=0, ge=0, le=100)
    familiarity: int = Field(default=10, ge=0, le=100)


class NPCMaterializerOut(Lenient):
    """A background extra made into a living character: psychology and the memory of what
    they witnessed. No world facts: what they claim stays a claim."""

    summary: str = Field(min_length=1, max_length=400)
    occupation: str = ""
    temperament: str = ""
    dimensions: dict[str, float] = Field(default_factory=dict)
    goals: list[MaterializedGoalOut] = Field(default_factory=list, max_length=3)
    attitude_to_party: AttitudeOut = Field(default_factory=AttitudeOut)
    memories: list[MaterializedMemoryOut] = Field(default_factory=list, max_length=5)


class IncidentalDetailOut(Lenient):
    classification: Literal["furnishing", "condition", "appearance", "extra", "other"]
    description: str


class NarratorOut(Lenient):
    narration: str = Field(min_length=1)
    incidental_detail_candidates: list[IncidentalDetailOut] = Field(default_factory=list)


class ClaimExtractorOut(Lenient):
    conveys: list[ConveysItemOut] = Field(default_factory=list)


class EntityResolverOut(Lenient):
    resolved: bool
    entity_id: str | None = None
    confidence: float = Field(ge=0, le=1)
    reason: str = ""


class RulesAdjudicatorOut(Lenient):
    requires_check: bool
    check: dict[str, Any] | None = None
    on_success: list[dict[str, Any]] = Field(default_factory=list)
    on_failure: list[dict[str, Any]] = Field(default_factory=list)
    time_cost_seconds: int = 6
    precedent_tags: list[str] = Field(default_factory=list)
    scope: Literal["single_use", "scene", "campaign"] = "single_use"
    summary: str = ""
    # what is at stake, in the player's terms: {"success": ..., "failure": ..., "retry": ...}
    stakes: dict[str, str] = Field(default_factory=dict)


class MemoryCandidateOut(Lenient):
    summary: str = Field(min_length=1)
    emotional_interpretation: str | None = None
    salience: float = Field(ge=0, le=1)
    emotional_weight: float = Field(ge=0, le=1, default=0)
    is_core: bool = False
    source_observation_ids: list[str] = Field(default_factory=list)


class MemoryProcessorOut(Lenient):
    memories: list[MemoryCandidateOut] = Field(default_factory=list)
    belief_proposals: list[BeliefProposalOut] = Field(default_factory=list)
    emotion_proposals: list[EmotionProposalOut] = Field(default_factory=list)


class BeliefProcessorOut(Lenient):
    confidence_adjustment: float = Field(ge=-0.25, le=0.25, default=0)
    inferences: list[BeliefProposalOut] = Field(default_factory=list)
    reason: str = ""


class CanonExtractorOut(Lenient):
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class SimulationProposalOut(Lenient):
    """One meaningful offscreen decision (ai-contracts §14). `subject_ref` is a candidate ref
    from the request; the engine validates and applies it, or rejects it."""

    subject_ref: str = Field(min_length=1)
    type: Literal["plan_advance", "plan_hold", "plan_abandon", "actor_travel", "proceed", "cancel"]
    target_ref: str | None = None  # actor_travel: a location ref
    delay_seconds: int | None = Field(default=None, ge=0)
    justification: str = ""


class WorldSimulatorOut(Lenient):
    proposals: list[SimulationProposalOut] = Field(default_factory=list)
    budget_used: int = Field(default=0, ge=0)


class BriefInterviewOut(Lenient):
    """Guided creation (campaign-generation §2): settings inferred from one answer."""

    brief_patch: dict[str, Any] = Field(default_factory=dict)
    next_question: str | None = None
    done: bool = False


class JournalWriterOut(Lenient):
    title: str = ""
    body: str = Field(min_length=1)


# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RoleSpec:
    name: str
    profile: str  # fast_structured | balanced_reasoning | creative_narrative | deep_world_author
    prompt_id: str
    output_model: type[BaseModel] | None
    max_tokens: int
    temperature: float
    actor_scoped: bool  # context is one actor's perspective (vs. objective roles)
    allowed_context: frozenset[str]
    forbidden_context: frozenset[str] = frozenset()
    authority: frozenset[str] = frozenset()  # what its proposals may touch
    repair: bool = True  # one bounded repair call on invalid JSON
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


ACTOR_CONTEXT = frozenset(
    {
        "identity",
        "known_entities",
        "behavior",
        "mechanics_player_layer",
        "core_memories",
        "beliefs",
        "heard_claims",
        "observations",
        "scene",
        "inventory_public",
        "relationships_own",
        "goals_own",
        "emotions_own",
        "memories",
        "available_actions",
        "situation",
        "rules_public",
        # built from this actor's own perspective (build_candidates): the refs it may target.
        # Missing until 2026-10-05, so the interpreter and AI actors guessed every ref.
        "candidates",
    }
)
OBJECTIVE = frozenset(
    {"facts", "hidden_properties", "other_actor_beliefs", "mystery_truth", "offscreen"}
)

ROLES: dict[str, RoleSpec] = {
    spec.name: spec
    for spec in (
        RoleSpec(
            "intent_interpreter",
            "fast_structured",
            "intent_interpreter",
            IntentInterpreterOut,
            1024,
            0.2,
            True,
            (ACTOR_CONTEXT - {"memories"}) | {"recent_turns"},
            OBJECTIVE,
            frozenset({"intent"}),
        ),
        RoleSpec(
            "entity_resolver",
            "fast_structured",
            "entity_resolver",
            EntityResolverOut,
            300,
            0.1,
            True,
            frozenset({"candidates", "situation"}),
            OBJECTIVE,
            frozenset(),
        ),
        RoleSpec(
            "ai_player",
            "balanced_reasoning",
            "ai_player",
            AIPlayerOut,
            900,
            0.6,
            True,
            ACTOR_CONTEXT,
            OBJECTIVE,
            frozenset({"intent", "speech", "belief", "emotion", "goal"}),
        ),
        RoleSpec(
            "npc_actor",
            "balanced_reasoning",
            "npc_actor",
            NPCActorOut,
            900,
            0.6,
            True,
            ACTOR_CONTEXT,
            OBJECTIVE,
            frozenset({"intent", "speech", "belief", "emotion"}),
        ),
        RoleSpec(
            "npc_tactical",
            "fast_structured",
            "npc_tactical",
            IntentionOut,
            300,
            0.3,
            True,
            frozenset({"mechanics_player_layer", "available_actions", "situation"}),
            OBJECTIVE,
            frozenset({"intent"}),
        ),
        RoleSpec(
            "rules_adjudicator",
            "balanced_reasoning",
            "rules_adjudicator",
            RulesAdjudicatorOut,
            900,
            0.2,
            False,
            frozenset({"rules_public", "situation", "scene", "mechanics_player_layer"}),
            OBJECTIVE,
            frozenset({"ruling"}),
        ),
        RoleSpec(
            "narrator",
            "creative_narrative",
            "narrator",
            None,  # prose: streamed verbatim; decoration is extracted by the canon pass
            700,
            0.8,
            True,
            frozenset(
                {
                    "observations",
                    "heard_claims",
                    "scene",
                    "style",
                    "resolved_mechanics",
                    "situation",
                    "recent_turns",
                }
            ),
            OBJECTIVE | {"beliefs", "memories"},
            frozenset(),
            repair=False,
            notes="streamed; focus actor's rendered observations only",
        ),
        RoleSpec(
            "claim_extractor",
            "fast_structured",
            "claim_extractor",
            ClaimExtractorOut,
            700,
            0.1,
            True,
            frozenset({"situation", "candidates"}),
            OBJECTIVE,
            frozenset({"claim"}),
        ),
        RoleSpec(
            "canon_extractor",
            "fast_structured",
            "canon_extractor",
            CanonExtractorOut,
            500,
            0.2,
            True,
            frozenset({"situation", "scene"}),
            OBJECTIVE,
            frozenset({"decoration"}),
        ),
        RoleSpec(
            "memory_processor",
            "fast_structured",
            "memory_processor",
            MemoryProcessorOut,
            700,
            0.4,
            True,
            frozenset(
                {
                    "observations",
                    "heard_claims",
                    "beliefs",
                    "goals_own",
                    "relationships_own",
                    "emotions_own",
                    "memories",
                }
            ),
            OBJECTIVE | {"narration"},
            frozenset({"memory", "belief", "emotion"}),
        ),
        RoleSpec(
            "belief_processor",
            "fast_structured",
            "belief_processor",
            BeliefProcessorOut,
            400,
            0.3,
            True,
            frozenset({"beliefs", "relationships_own", "situation"}),
            OBJECTIVE,
            frozenset({"belief_adjust"}),
        ),
        RoleSpec(
            "journal_writer",
            "fast_structured",
            "journal_writer",
            JournalWriterOut,
            700,
            0.5,
            True,
            frozenset({"observations", "heard_claims", "beliefs", "scene"}),
            OBJECTIVE,
            frozenset(),
        ),
        RoleSpec(
            "table_assistant",
            "fast_structured",
            "table_assistant",
            None,  # prose: an answer to the player, out of character
            600,
            0.3,
            True,
            frozenset(
                {
                    "identity",
                    "known_entities",
                    "mechanics_player_layer",
                    "beliefs",
                    "heard_claims",
                    "observations",
                    "scene",
                    "inventory_public",
                    "goals_own",
                    "relationships_own",
                    "memories",
                    "core_memories",
                    "rules_public",
                    "recent_turns",
                    "situation",
                }
            ),
            OBJECTIVE,
            frozenset(),
            repair=False,
            notes="OOC questions answered from the focus character's perspective only",
        ),
        RoleSpec(
            "npc_materializer",
            "balanced_reasoning",
            "npc_materializer",
            NPCMaterializerOut,
            900,
            0.6,
            False,
            frozenset({"person", "witnessed", "scene", "task"}),
            OBJECTIVE,
            frozenset({"npc_profile"}),
            notes="promotes a background extra; psychology and witnessed memory, never facts",
        ),
        RoleSpec(
            "brief_interviewer",
            "fast_structured",
            "brief_interviewer",
            BriefInterviewOut,
            600,
            0.5,
            False,
            frozenset({"brief", "conversation", "task"}),
            frozenset(),
            frozenset({"campaign_brief"}),
            notes="pre-play only; proposes brief fields, never world content",
        ),
        RoleSpec(
            "world_author",
            "deep_world_author",
            "world_author",
            WorldAuthorOut,
            4096,
            0.7,
            False,
            frozenset({"brief", "established_canon", "latent_canon", "task", "rules_public"}),
            frozenset(),
            frozenset({"world_content"}),
            notes="objective role; may know mystery truth",
        ),
        RoleSpec(
            "world_simulator",
            "balanced_reasoning",
            "world_simulator",
            WorldSimulatorOut,
            900,
            0.5,
            False,
            frozenset(
                {"interval", "candidates", "goals", "plans", "deterministic_changes", "budget"}
            ),
            frozenset(),
            frozenset({"simulation"}),
        ),
    )
}

PROFILES = (
    "fast_structured",
    "balanced_reasoning",
    "creative_narrative",
    "deep_world_author",
    "embedding",
    "rerank",
)


def role(name: str) -> RoleSpec:
    try:
        return ROLES[name]
    except KeyError:
        raise KeyError(f"unknown role {name!r}") from None
