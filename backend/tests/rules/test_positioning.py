"""Theater-of-the-mind zones, bands, engagement, cover, movement."""

from __future__ import annotations

import pytest

from app.engine.positioning import PositionError, SceneSpace, Zone

pytestmark = [pytest.mark.unit, pytest.mark.rules]


def warehouse() -> SceneSpace:
    """Oric's Warehouse (frostbridge-demo §31): door-floor-crates-shelf; window off the floor."""
    space = SceneSpace(
        [
            Zone("door", exit=True),
            Zone("floor", cover="none"),
            Zone("crates", cover="strong"),
            Zone("shelf", cover="partial", elevated=True),
            Zone("window", exit=True),
        ],
        [
            ("door", "floor"),
            ("floor", "crates"),
            ("floor", "shelf"),
            ("floor", "window"),
            ("crates", "shelf"),
        ],
    )
    space.place("elara", "floor")
    space.place("thief_1", "crates")
    space.place("thief_2", "door")
    return space


def test_bands_follow_zone_distance_and_engagement():
    s = warehouse()
    assert s.band("elara", "thief_1") == "near"  # adjacent zone
    assert s.band("thief_1", "thief_2") == "far"  # crates-floor-door
    s.place("far_one", "window")
    assert s.band("thief_1", "far_one") == "far"
    s.move_to("thief_1", "floor")
    assert s.band("elara", "thief_1") == "close"
    s.engage("thief_1", "elara")
    assert s.band("elara", "thief_1") == "engaged" and s.engaged("elara", "thief_1")
    assert s.band("thief_2", "elara") == "near"


def test_distant_when_three_or_more_steps_or_unreachable():
    s = SceneSpace([Zone(k) for k in "abcde"], [("a", "b"), ("b", "c"), ("c", "d")])
    s.place("x", "a")
    s.place("y", "d")
    s.place("z", "e")
    assert s.band("x", "y") == "distant" and s.band("x", "z") == "distant"
    assert s.path("a", "d") == ["a", "b", "c", "d"] and s.path("a", "e") is None


def test_movement_rules():
    s = warehouse()
    with pytest.raises(PositionError, match="not adjacent"):
        s.move_to("thief_2", "crates")
    prev, left = s.move_to("elara", "shelf")
    assert prev == "floor" and left == set() and s.position("elara").elevated
    with pytest.raises(PositionError, match="already"):
        s.move_to("elara", "shelf")
    s.move_to("thief_1", "shelf")
    s.engage("thief_1", "elara")
    prev, left = s.move_to("elara", "floor")
    assert left == {"thief_1"} and not s.position("thief_1").engaged_with
    assert not s.position("elara").elevated


def test_cover_only_counts_outside_engagement():
    s = warehouse()
    assert s.take_cover("thief_1") == "strong"
    assert s.cover_against("thief_1", "elara") == "strong"
    s.move_to("elara", "crates")
    s.engage("elara", "thief_1")
    assert s.cover_against("thief_1", "elara") == "none"
    assert s.position("elara").cover == "none"
    with pytest.raises(PositionError, match="while engaged"):
        s.take_cover("thief_1")
    s.disengage("thief_1")
    with pytest.raises(PositionError, match="no cover"):
        s.take_cover("thief_2")


def test_round_trips_through_dict():
    s = warehouse()
    s.engage("thief_1", "elara") if s.position("thief_1").zone == s.position("elara").zone else None
    s.take_cover("thief_1")
    again = SceneSpace.from_dict(s.to_dict())
    assert again.to_dict() == s.to_dict()
    assert again.band("elara", "thief_2") == "near"
