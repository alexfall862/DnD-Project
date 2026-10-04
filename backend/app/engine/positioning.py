"""Theater-of-the-mind positioning (rules-engine §11, §14; core-adventure §9).

A scene's space is a small graph of named zones. Each actor has a `Position`: a zone, the set
of actors it is engaged with (melee), its cover level and whether it holds high ground.

Range band between two actors:
- same zone and engaged with each other → `engaged`
- same zone, not engaged → `close`
- zones 1 step apart → `near`, 2 → `far`, 3+ (or unreachable) → `distant`

Movement changes one step at a time: engage/disengage within a zone, or move to an adjacent
zone (which also drops any engagement). The engine owns spatial truth; narration describes it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

BANDS = ["engaged", "close", "near", "far", "distant"]
COVER_LEVELS = {"none": 0, "partial": 1, "strong": 2, "total": 3}


class PositionError(ValueError):
    pass


@dataclass
class Zone:
    key: str
    name: str = ""
    cover: str = "none"  # best cover available to someone standing here
    elevated: bool = False
    exit: bool = False  # leaving the encounter is possible from here
    features: list[str] = field(default_factory=list)


@dataclass
class Position:
    zone: str
    engaged_with: set[str] = field(default_factory=set)
    cover: str = "none"
    elevated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone": self.zone,
            "engaged_with": sorted(self.engaged_with),
            "cover": self.cover,
            "elevated": self.elevated,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Position:
        return cls(
            d["zone"],
            set(d.get("engaged_with", [])),
            d.get("cover", "none"),
            bool(d.get("elevated")),
        )


class SceneSpace:
    def __init__(self, zones: list[Zone], adjacency: list[tuple[str, str]]) -> None:
        self.zones: dict[str, Zone] = {z.key: z for z in zones}
        self.adjacent: dict[str, set[str]] = {k: set() for k in self.zones}
        for a, b in adjacency:
            if a not in self.zones or b not in self.zones:
                raise PositionError(f"adjacency references unknown zone: {a}-{b}")
            self.adjacent[a].add(b)
            self.adjacent[b].add(a)
        self.positions: dict[str, Position] = {}

    # -- setup -------------------------------------------------------------------------------

    def place(
        self, actor: str, zone: str, *, cover: str = "none", elevated: bool = False
    ) -> Position:
        if zone not in self.zones:
            raise PositionError(f"unknown zone {zone!r}")
        if cover not in COVER_LEVELS:
            raise PositionError(f"unknown cover {cover!r}")
        self.positions[actor] = Position(zone, set(), cover, elevated or self.zones[zone].elevated)
        return self.positions[actor]

    def remove(self, actor: str) -> None:
        pos = self.positions.pop(actor, None)
        if pos:
            for other in pos.engaged_with:
                self.positions[other].engaged_with.discard(actor)

    def position(self, actor: str) -> Position:
        try:
            return self.positions[actor]
        except KeyError:
            raise PositionError(f"{actor} is not in the scene") from None

    # -- queries -----------------------------------------------------------------------------

    def zone_distance(self, a: str, b: str) -> int | None:
        if a == b:
            return 0
        seen = {a}
        q = deque([(a, 0)])
        while q:
            z, d = q.popleft()
            for n in self.adjacent[z]:
                if n == b:
                    return d + 1
                if n not in seen:
                    seen.add(n)
                    q.append((n, d + 1))
        return None

    def band(self, a: str, b: str) -> str:
        pa, pb = self.position(a), self.position(b)
        if pa.zone == pb.zone:
            return "engaged" if b in pa.engaged_with else "close"
        d = self.zone_distance(pa.zone, pb.zone)
        if d is None or d >= 3:
            return "distant"
        return "near" if d == 1 else "far"

    def band_index(self, band: str) -> int:
        return BANDS.index(band)

    def engaged(self, a: str, b: str) -> bool:
        return b in self.position(a).engaged_with

    def actors_in_zone(self, zone: str) -> list[str]:
        return sorted(k for k, p in self.positions.items() if p.zone == zone)

    def engaged_partners(self, actor: str) -> set[str]:
        return set(self.position(actor).engaged_with)

    def cover_against(self, target: str, attacker: str) -> str:
        """Cover only helps against attackers outside the target's engagement."""
        if self.engaged(target, attacker):
            return "none"
        return self.position(target).cover

    def has_line_of_sight(self, a: str, b: str) -> bool:
        return (
            self.band(a, b) != "distant"
            or self.zone_distance(self.position(a).zone, self.position(b).zone) is not None
        )

    # -- movement ----------------------------------------------------------------------------

    def engage(self, actor: str, target: str) -> None:
        pa, pt = self.position(actor), self.position(target)
        if pa.zone != pt.zone:
            raise PositionError(f"{actor} must be in the same zone as {target} to engage")
        pa.engaged_with.add(target)
        pt.engaged_with.add(actor)
        pa.cover = "none"  # stepping into melee leaves cover

    def disengage(self, actor: str) -> set[str]:
        pa = self.position(actor)
        partners = set(pa.engaged_with)
        for other in partners:
            self.positions[other].engaged_with.discard(actor)
        pa.engaged_with.clear()
        return partners

    def move_to(self, actor: str, zone: str) -> tuple[str, set[str]]:
        """Move one step to an adjacent zone. Returns (previous zone, partners left behind)."""
        pa = self.position(actor)
        if zone not in self.zones:
            raise PositionError(f"unknown zone {zone!r}")
        if zone == pa.zone:
            raise PositionError("already in that zone")
        if zone not in self.adjacent[pa.zone]:
            raise PositionError(f"{zone!r} is not adjacent to {pa.zone!r}")
        left = self.disengage(actor)
        prev = pa.zone
        pa.zone = zone
        pa.cover = "none"
        pa.elevated = self.zones[zone].elevated
        return prev, left

    def take_cover(self, actor: str) -> str:
        pa = self.position(actor)
        if pa.engaged_with:
            raise PositionError("cannot take cover while engaged")
        available = self.zones[pa.zone].cover
        if available == "none":
            raise PositionError("no cover here")
        pa.cover = available
        return available

    def path(self, a_zone: str, b_zone: str) -> list[str] | None:
        if a_zone == b_zone:
            return [a_zone]
        prev: dict[str, str | None] = {a_zone: None}
        q = deque([a_zone])
        while q:
            z = q.popleft()
            for n in self.adjacent[z]:
                if n not in prev:
                    prev[n] = z
                    if n == b_zone:
                        out = [n]
                        while prev[out[-1]] is not None:
                            out.append(prev[out[-1]])  # type: ignore[arg-type]
                        return list(reversed(out))
                    q.append(n)
        return None

    # -- (de)serialisation -------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "zones": [z.__dict__ for z in self.zones.values()],
            "adjacency": sorted(
                {tuple(sorted((a, b))) for a, ns in self.adjacent.items() for b in ns}
            ),
            "positions": {k: p.to_dict() for k, p in sorted(self.positions.items())},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SceneSpace:
        space = cls([Zone(**z) for z in d["zones"]], [tuple(p) for p in d.get("adjacency", [])])
        for k, p in d.get("positions", {}).items():
            space.positions[k] = Position.from_dict(p)
        return space
