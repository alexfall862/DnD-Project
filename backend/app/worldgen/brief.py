"""CampaignBrief (campaign-generation §3): the one structured input every generation stage
reads. Guided creation, Surprise Me and (later) imports all compile to this shape. `surprise`
fills unspecified fields from a seeded table so the same seed always gives the same brief."""

from __future__ import annotations

import random
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

GENRES = (
    "heroic fantasy",
    "dark fantasy",
    "low fantasy",
    "science fantasy",
    "post-apocalyptic",
    "weird fiction",
    "survival",
    "noir",
    "western",
    "cosmic horror",
)
TONES = ("hopeful", "grim", "wry", "melancholy", "tense", "adventurous")
PRESSURES = (
    "a disappearing caravan route",
    "a succession crisis",
    "a plague in the lower town",
    "an awakening ruin",
    "a smuggling ring buying officials",
    "a feud between two founding families",
)


class PlayerCharacterBrief(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = "the traveller"
    concept: str = "a capable newcomer with a past"
    pronouns: str = "they/them"


class CampaignBrief(BaseModel):
    model_config = ConfigDict(extra="ignore")  # e.g. the guided conversation's `_guided` state

    title: str = "Untitled campaign"
    campaign_mode: Literal["authored", "sandbox", "emergent"] = "sandbox"
    genres: list[str] = Field(default_factory=lambda: ["low fantasy"])
    tone: dict[str, float] = Field(
        default_factory=lambda: {"seriousness": 0.6, "humor": 0.3, "darkness": 0.4}
    )
    technology: str = "pre-industrial"
    supernatural: str = "rare and poorly understood"
    politics: str = "fractured local powers"
    simulation_scope: Literal["local", "regional", "world"] = "regional"
    combat_lethality: Literal["low", "medium", "high"] = "medium"
    central_pressure: str = ""
    mystery_frequency: Literal["low", "medium", "high"] = "medium"
    character_focus: Literal["low", "medium", "high"] = "high"
    expected_length: Literal["one-shot", "short", "medium", "long"] = "medium"
    party_ai_companions: int = Field(default=2, ge=0, le=4)
    player_character: PlayerCharacterBrief = Field(default_factory=PlayerCharacterBrief)
    seed: int = 0
    notes: str = ""

    def as_context(self) -> str:
        pc = self.player_character
        return (
            f"Title: {self.title}. Mode: {self.campaign_mode}. Genres: {', '.join(self.genres)}. "
            f"Tone: {', '.join(f'{k} {v}' for k, v in self.tone.items())}. "
            f"Technology: {self.technology}. Supernatural: {self.supernatural}. "
            f"Politics: {self.politics}. Simulation scope: {self.simulation_scope}. "
            f"Combat lethality: {self.combat_lethality}. Central pressure: "
            f"{self.central_pressure or 'open'}. Mystery frequency: {self.mystery_frequency}. "
            f"Expected length: {self.expected_length}. Party: the player ({pc.name}, "
            f"{pc.concept}, {pc.pronouns}) and {self.party_ai_companions} AI companion(s). "
            + (f"Notes: {self.notes}" if self.notes else "")
        ).strip()


def surprise(seed: int, **overrides: Any) -> CampaignBrief:
    """Surprise Me: minimal constraints in, a complete brief out, reproducible by seed."""
    rng = random.Random(seed)
    base = CampaignBrief(
        title=overrides.get("title") or "A new campaign",
        genres=[rng.choice(GENRES)],
        tone={
            "seriousness": round(rng.uniform(0.3, 0.9), 2),
            "humor": round(rng.uniform(0.1, 0.6), 2),
            "darkness": round(rng.uniform(0.2, 0.8), 2),
        },
        central_pressure=rng.choice(PRESSURES),
        seed=seed,
        notes=f"tone leaning {rng.choice(TONES)}",
    )
    return base.model_copy(update={k: v for k, v in overrides.items() if v is not None})
