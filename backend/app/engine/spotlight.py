"""Spotlight governor (orchestration §13): bounded visible AI activity between two human
inputs. Pure bookkeeping; the orchestrator consults it before every visible AI turn.

Counters reset on each human input. In combat the initiative order decides who acts, so the
visible-turn cap does not apply to combat actions (combat override); it still bounds speech.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_BUDGET = {
    "max_visible_ai_turns": 3,
    "max_ai_to_ai_exchanges": 1,
    "max_unsolicited_initiatives": 2,
}


@dataclass
class SpotlightBudget:
    max_visible_ai_turns: int = 3
    max_ai_to_ai_exchanges: int = 1
    max_unsolicited_initiatives: int = 2

    @classmethod
    def from_settings(cls, settings: dict[str, Any] | None) -> SpotlightBudget:
        b = dict(DEFAULT_BUDGET)
        for k, v in ((settings or {}).get("spotlight") or {}).items():
            if k in b:
                b[k] = int(v)
        return cls(**b)


@dataclass
class SpotlightLedger:
    """Visible AI activity since the last human input (stored in `scene.state.spotlight`)."""

    visible_ai_turns: int = 0
    ai_to_ai_exchanges: int = 0
    unsolicited_initiatives: int = 0
    compressed: list[str] = field(default_factory=list)  # actors whose activity was summarised

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> SpotlightLedger:
        d = d or {}
        return cls(
            int(d.get("visible_ai_turns", 0)),
            int(d.get("ai_to_ai_exchanges", 0)),
            int(d.get("unsolicited_initiatives", 0)),
            list(d.get("compressed", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "visible_ai_turns": self.visible_ai_turns,
            "ai_to_ai_exchanges": self.ai_to_ai_exchanges,
            "unsolicited_initiatives": self.unsolicited_initiatives,
            "compressed": list(self.compressed),
        }

    def allows_visible(self, budget: SpotlightBudget, *, in_combat: bool = False) -> bool:
        return in_combat or self.visible_ai_turns < budget.max_visible_ai_turns

    def allows_ai_to_ai(self, budget: SpotlightBudget) -> bool:
        return self.ai_to_ai_exchanges < budget.max_ai_to_ai_exchanges

    def allows_unsolicited(self, budget: SpotlightBudget) -> bool:
        return self.unsolicited_initiatives < budget.max_unsolicited_initiatives

    def note_visible(self, *, ai_to_ai: bool = False, unsolicited: bool = False) -> None:
        self.visible_ai_turns += 1
        if ai_to_ai:
            self.ai_to_ai_exchanges += 1
        if unsolicited:
            self.unsolicited_initiatives += 1

    def compress(self, actor_key: str) -> None:
        if actor_key not in self.compressed:
            self.compressed.append(actor_key)
