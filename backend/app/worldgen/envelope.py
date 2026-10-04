"""The World Author's structured output envelope (ai-contracts §13; campaign-generation §5).

Every generation stage — and progressive materialization later — returns one `WorldAuthorOut`.
Content is addressed by symbolic `ref`s the model invents (`loc_harbor`, `npc_vessa`); the
engine resolves refs across stages, validates the envelope against what the stage may
propose and against established canon, and only then builds world rows from it. Nothing in
an envelope is world state by itself.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


Canon = Literal["latent", "established"]
Sensitivity = Literal["public", "private", "secret"]
Detail = Literal["outline", "latent", "materialized"]


class GenFact(_Lenient):
    """An objective truth. `known_by_refs` are actors who hold it as knowledge from the start;
    nobody else does (Invariant 2)."""

    key: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    subject_ref: str | None = None
    object_ref: str | None = None
    value: str | int | float | bool | None = None
    sensitivity: Sensitivity = "public"
    canon: Canon = "latent"
    known_by_refs: list[str] = Field(default_factory=list)
    era: str | None = None  # history: ancient | century | decade | year


class GenZone(_Lenient):
    key: str = Field(min_length=1)
    name: str = ""
    cover: Literal["none", "light", "heavy"] = "none"
    exit: bool = False
    features: list[str] = Field(default_factory=list)


class GenLocation(_Lenient):
    ref: str = Field(min_length=1)
    name: str = Field(min_length=1)
    type: str = "site"  # region | settlement | district | building | site | road | wilds
    parent_ref: str | None = None
    detail: Detail = "outline"
    descriptor: str = ""  # what a stranger sees
    features: list[str] = Field(default_factory=list)
    zones: list[GenZone] = Field(default_factory=list)
    adjacency: list[list[str]] = Field(default_factory=list)
    entry_zone: str | None = None
    simulation_state: dict[str, Any] = Field(default_factory=dict)
    settlement: bool = False


class GenRoute(_Lenient):
    from_ref: str
    to_ref: str
    travel_minutes: int = Field(default=10, ge=0)


class GenCulture(_Lenient):
    ref: str = Field(min_length=1)
    name: str = Field(min_length=1)
    homeland_ref: str | None = None
    values: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    customs: str = ""
    internal_variation: str = ""


class GenPlanStep(_Lenient):
    title: str = Field(min_length=1)
    at_day: float | None = None  # days after the campaign starts
    kind: Literal["deterministic", "decision"] = "deterministic"


class GenFaction(_Lenient):
    ref: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: Literal["polity", "faction"] = "faction"
    description: str = ""
    public: bool = True
    ideology: str = ""
    resources: dict[str, Any] = Field(default_factory=dict)
    territory_refs: list[str] = Field(default_factory=list)
    allies: list[str] = Field(default_factory=list)
    rivals: list[str] = Field(default_factory=list)
    public_goal: str = ""
    hidden_goal: str = ""
    plan_steps: list[GenPlanStep] = Field(default_factory=list)
    simulation_priority: float = Field(default=0.5, ge=0, le=1)
    scope: Literal["world", "local"] = "world"


class GenGoal(_Lenient):
    description: str = Field(min_length=1)
    priority: int = Field(default=50, ge=0, le=100)
    target_refs: list[str] = Field(default_factory=list)


class GenBelief(_Lenient):
    predicate: str = Field(min_length=1)
    subject_ref: str | None = None
    object_ref: str | None = None
    type: Literal["believed", "suspected", "rumor", "opinion"] = "believed"
    confidence: float = Field(default=0.7, ge=0, le=1)


class GenRelationship(_Lenient):
    target_ref: str
    trust: int = Field(default=0, ge=-100, le=100)
    respect: int = Field(default=0, ge=-100, le=100)
    affection: int = Field(default=0, ge=-100, le=100)
    fear: int = Field(default=0, ge=0, le=100)
    resentment: int = Field(default=0, ge=0, le=100)
    familiarity: int = Field(default=20, ge=0, le=100)


class GenEquipment(_Lenient):
    name: str = Field(min_length=1)
    template_key: str = "item.travel_supplies"


class GenActor(_Lenient):
    """A person. A later stage may repeat an earlier latent actor's ref to fill in fields the
    earlier stage left empty (truth-first: a secret names its participants, the NPC stage
    gives them a home, a sheet and goals). Conflicting values are a contradiction."""

    ref: str = Field(min_length=1)
    name: str | None = None
    role: Literal["npc", "pc_human", "pc_ai"] = "npc"
    importance: Literal["full", "important", "standard", "background"] = "standard"
    descriptor: str = ""
    occupation: str = ""
    location_ref: str | None = None
    alive: bool = True
    attributes: dict[str, int] = Field(default_factory=dict)
    skills: dict[str, int] = Field(default_factory=dict)
    traits: list[str] = Field(default_factory=list)
    equipment: list[GenEquipment] = Field(default_factory=list)
    summary: str = ""
    dimensions: dict[str, float] = Field(default_factory=dict)
    goals: list[GenGoal] = Field(default_factory=list)
    beliefs: list[GenBelief] = Field(default_factory=list)
    knows_fact_keys: list[str] = Field(default_factory=list)
    knows_refs: list[str] = Field(default_factory=list)  # names this actor knows
    core_memories: list[str] = Field(default_factory=list)
    relationships: list[GenRelationship] = Field(default_factory=list)
    faction_refs: list[str] = Field(default_factory=list)
    leads_faction_ref: str | None = None
    culture_ref: str | None = None
    autonomy: dict[str, str] = Field(default_factory=dict)


class GenConflict(_Lenient):
    ref: str = Field(min_length=1)
    title: str = Field(min_length=1)
    participant_refs: list[str] = Field(default_factory=list)
    stakes: str = ""
    status: str = "simmering"
    escalation: str = ""
    scale: Literal["world", "regional", "local"] = "regional"


class GenPressure(_Lenient):
    ref: str = Field(min_length=1)
    title: str = Field(min_length=1)
    kind: str = "pressure"
    source_refs: list[str] = Field(default_factory=list)
    clock: list[GenPlanStep] = Field(default_factory=list)


class GenMystery(_Lenient):
    """Truth first (campaign-generation §15): the question, the truth facts, participants and
    a timeline. Clues come in a later stage and must support these facts."""

    ref: str = Field(min_length=1)
    question: str = Field(min_length=1)
    truth_fact_keys: list[str] = Field(default_factory=list)
    participant_refs: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    red_herring_fact_keys: list[str] = Field(default_factory=list)


class GenClue(_Lenient):
    ref: str = Field(min_length=1)
    mystery_ref: str
    clue_type: Literal["physical", "document", "social"]
    supports_fact_key: str
    entity_ref: str | None = None  # the item (physical/document clues)
    destructible: bool = False
    reliability: float = Field(default=1.0, ge=0, le=1)


class GenDocument(_Lenient):
    text: str = Field(min_length=1)
    author_ref: str | None = None
    conveys_fact_keys: list[str] = Field(default_factory=list)
    conveys_propositions: list[str] = Field(default_factory=list)
    names_refs: list[str] = Field(default_factory=list)  # readers learn these names


class GenItem(_Lenient):
    ref: str = Field(min_length=1)
    name: str = Field(min_length=1)
    template_key: str = "item.travel_supplies"
    location_ref: str | None = None
    zone: str | None = None
    holder_ref: str | None = None
    concealed: bool = False
    concealment_difficulty: str | None = None
    public: dict[str, Any] = Field(default_factory=dict)
    hidden: dict[str, Any] = Field(default_factory=dict)
    document: GenDocument | None = None
    mechanics_key: str | None = None
    importance: Literal["important", "standard"] = "standard"


class GenEffect(_Lenient):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class GenMechanic(_Lenient):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    tier: str = "low"
    description: str = ""
    passive: GenEffect | None = None
    activated: GenEffect | None = None


class GenRoute2(_Lenient):
    kind: str = "rumor"  # rumor | notice | conversation | location | document | encounter
    via_ref: str | None = None
    detail: str = ""


class GenOpportunity(_Lenient):
    ref: str = Field(min_length=1)
    title: str = Field(min_length=1)
    pressure_ref: str | None = None
    routes: list[GenRoute2] = Field(default_factory=list)


class GenSchedule(_Lenient):
    key: str = Field(min_length=1)
    at_day: float = Field(ge=0)
    type: Literal["fact.establish", "clue.destroy", "location.state", "actor.travel", "decision"]
    fact_key: str | None = None
    clue_ref: str | None = None
    location_ref: str | None = None
    actor_ref: str | None = None
    faction_ref: str | None = None
    question: str = ""
    patch: dict[str, Any] = Field(default_factory=dict)


class GenOpening(_Lenient):
    location_ref: str
    hour: int = Field(default=16, ge=0, le=23)
    weather: str = ""
    situation: str = ""
    present_refs: list[str] = Field(default_factory=list)
    positions: dict[str, str] = Field(default_factory=dict)  # actor ref -> zone key


class WorldAuthorOut(_Lenient):
    summary: str = ""
    facts: list[GenFact] = Field(default_factory=list)
    locations: list[GenLocation] = Field(default_factory=list)
    routes: list[GenRoute] = Field(default_factory=list)
    cultures: list[GenCulture] = Field(default_factory=list)
    factions: list[GenFaction] = Field(default_factory=list)
    actors: list[GenActor] = Field(default_factory=list)
    conflicts: list[GenConflict] = Field(default_factory=list)
    pressures: list[GenPressure] = Field(default_factory=list)
    mysteries: list[GenMystery] = Field(default_factory=list)
    clues: list[GenClue] = Field(default_factory=list)
    items: list[GenItem] = Field(default_factory=list)
    mechanics: list[GenMechanic] = Field(default_factory=list)
    opportunities: list[GenOpportunity] = Field(default_factory=list)
    schedules: list[GenSchedule] = Field(default_factory=list)
    opening: GenOpening | None = None


SECTIONS = (
    "facts",
    "locations",
    "routes",
    "cultures",
    "factions",
    "actors",
    "conflicts",
    "pressures",
    "mysteries",
    "clues",
    "items",
    "mechanics",
    "opportunities",
    "schedules",
    "opening",
)
