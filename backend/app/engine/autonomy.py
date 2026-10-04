"""Autonomy profiles and enforcement gates (world-memory §4 "AI autonomy"; ai-contracts §5
"Autonomy enforcement"). Pure functions: the service decides what a gate result means.

Each domain is configured as `blocked | suggest_only | ask | autonomous`. The model may
propose anything; the engine classifies the proposal's domain and applies the gate after
generation, so a forgotten setting in the prompt changes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LEVELS = ("blocked", "suggest_only", "ask", "autonomous")
DOMAINS = (
    "conversation",
    "exploration",
    "combat",
    "spending",
    "item_transfer",
    "advancement",
    "party_departure",
    "romance",
    "major_irreversible",
)
DEFAULT_LEVELS: dict[str, str] = {
    "conversation": "autonomous",
    "exploration": "autonomous",
    "combat": "autonomous",
    "spending": "ask",
    "item_transfer": "ask",
    "advancement": "ask",
    "party_departure": "ask",
    "romance": "ask",
    "major_irreversible": "ask",
}

# action key -> domain. Anything not listed is exploration (movement, searching, waiting).
ACTION_DOMAINS: dict[str, str] = {
    "action.attack": "combat",
    "action.engage": "combat",
    "action.disengage": "combat",
    "action.withdraw": "combat",
    "action.take_cover": "combat",
    "action.defend": "combat",
    "action.flee": "combat",
    "action.surrender": "major_irreversible",
    "action.pick_up": "item_transfer",
    "action.drop": "item_transfer",
    "action.give": "item_transfer",
    "action.trade": "spending",
    "action.leave_party": "party_departure",
    "speech": "conversation",
}


@dataclass(frozen=True)
class AutonomyProfile:
    levels: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict | None) -> AutonomyProfile:
        levels = dict(DEFAULT_LEVELS)
        for k, v in (d or {}).items():
            if k in DOMAINS and v in LEVELS:
                levels[k] = v
        return cls(levels)

    def level(self, domain: str) -> str:
        return self.levels.get(domain, "autonomous")


def domain_of(action_key: str, *, params: dict | None = None) -> str:
    """Classify an intention. A `pick_up` of something another actor owns, or a `drop` of a
    unique item, is still item_transfer; anything irreversible is flagged by the ruleset's
    `irreversible` param when it exists."""
    if params and params.get("irreversible"):
        return "major_irreversible"
    return ACTION_DOMAINS.get(action_key, "exploration")


@dataclass(frozen=True)
class GateResult:
    domain: str
    level: str

    @property
    def execute(self) -> bool:
        return self.level == "autonomous"

    @property
    def paused(self) -> bool:
        return self.level == "ask"

    @property
    def suggestion(self) -> bool:
        return self.level == "suggest_only"

    @property
    def blocked(self) -> bool:
        return self.level == "blocked"


def gate(profile: AutonomyProfile, action_key: str, *, params: dict | None = None) -> GateResult:
    domain = domain_of(action_key, params=params)
    return GateResult(domain, profile.level(domain))
