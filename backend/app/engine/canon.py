"""Canon extraction allowlist validator (canon-extraction-allowlist.md). The one place model
prose can become persistent state: decoration only, checked structurally here, never by the
prompt. Rejections are returned with reasons so the caller can log them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ALLOWED_CLASSES = {
    "furnishing": "location_feature",  # bench, cracked window, barrels
    "condition": "location_condition",  # weather, smell, noise, crowding
    "appearance": "entity_descriptor",  # grey cloak, limp, scar — entity already present
    "extra": "background_extra",  # background people present in the scene
    "availability": "trade_flavour",  # price/availability of goods already traded here
}
MECHANICS_FIELDS = {
    "effect",
    "effects",
    "mechanics",
    "damage",
    "bonus",
    "modifier",
    "properties",
    "stats",
    "attack",
    "defense",
}
STRUCTURE_WORDS = {
    "door",
    "exit",
    "passage",
    "tunnel",
    "stairs",
    "staircase",
    "corridor",
    "room",
    "cellar",
    "trapdoor",
    "hatch",
    "window leads",
    "gate",
}
ITEM_WORDS = {
    "key",
    "coin",
    "coins",
    "purse",
    "dagger",
    "sword",
    "blade",
    "potion",
    "scroll",
    "letter",
    "note",
    "ring",
    "amulet",
    "book",
    "ledger",
    "map",
}
SECRET_WORDS = {
    "secret",
    "secretly",
    "hidden motive",
    "plots",
    "plans to",
    "intends",
    "wants to",
    "fears",
    "hates",
    "loves",
    "rumour",
    "rumor",
    "prophecy",
    "legend",
    "history",
    "once",
    "years ago",
}


@dataclass(frozen=True)
class CanonCandidate:
    classification: str
    description: str
    target_ref: str | None = None  # location key / entity id the detail belongs to
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CanonCandidate:
        known = {"classification", "description", "target_ref", "entity_id", "location"}
        return cls(
            str(d.get("classification", "")).lower().strip(),
            str(d.get("description", "")).strip(),
            d.get("target_ref") or d.get("entity_id") or d.get("location"),
            {k: v for k, v in d.items() if k not in known},
        )


@dataclass(frozen=True)
class Validation:
    accepted: list[tuple[CanonCandidate, str]]  # (candidate, persistence action)
    rejected: list[tuple[CanonCandidate, str]]  # (candidate, reason)


def validate(
    candidates: list[CanonCandidate],
    *,
    present_entity_ids: set[str],
    current_location_id: str | None,
    existing_feature_texts: set[str] = frozenset(),
) -> Validation:
    accepted: list[tuple[CanonCandidate, str]] = []
    rejected: list[tuple[CanonCandidate, str]] = []
    for c in candidates:
        action = ALLOWED_CLASSES.get(c.classification)
        if action is None:
            rejected.append((c, f"class {c.classification!r} not in allowlist"))
            continue
        if not c.description or len(c.description) > 200:
            rejected.append((c, "description missing or too long"))
            continue
        low = c.description.lower()
        if any(k in MECHANICS_FIELDS for k in c.extra):
            rejected.append((c, "mechanical fields are never persisted"))
            continue
        words = set(low.replace(",", " ").replace(".", " ").split())
        if words & ITEM_WORDS:
            rejected.append((c, "items are never persisted by extraction"))
            continue
        if any(w in low for w in STRUCTURE_WORDS):
            rejected.append((c, "topology (exits, passages, rooms) is never persisted"))
            continue
        if any(w in low for w in SECRET_WORDS):
            rejected.append((c, "history, secrets, motives and rumours are never persisted"))
            continue
        if action == "entity_descriptor":
            if not c.target_ref or str(c.target_ref) not in present_entity_ids:
                rejected.append((c, "appearance detail must name an entity present in the scene"))
                continue
        elif action in ("location_feature", "location_condition", "trade_flavour"):
            if c.target_ref and current_location_id and str(c.target_ref) != current_location_id:
                rejected.append((c, "details belong to the current location only"))
                continue
        if low in existing_feature_texts:
            rejected.append((c, "already recorded"))
            continue
        accepted.append((c, action))
    return Validation(accepted, rejected)
