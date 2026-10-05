"""The closed consequence vocabulary (DECISIONS 10d).

A consequence is what an attempt *changes in the world*: a guard lets the party through, a gap
in the hedge becomes a way in, the merchant promises a deal, the party is now "inspected".
Models propose consequences from this list; `ConsequenceService` validates and applies them
with events. Nothing outside the list can be proposed.

Models write one flat object per consequence: `{"kind": "grant_passage", "obstacle":
"s_1a2b3c"}`. Parameter values are refs from the request (people, places, items, situations)
or short plain text where the spec says so.

`actor_may`: an NPC or AI player may propose this kind for itself in a reaction. `self_param`
names the parameter that must then be the proposer ("self"); for obstacles, the proposer must
hold the obstacle.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConsequenceSpec:
    kind: str
    group: str
    summary: str
    params: dict[str, str]
    required: tuple[str, ...] = ()
    actor_may: bool = False
    self_param: str | None = None
    examples: list[str] = field(default_factory=list)


def _s(
    kind: str,
    group: str,
    summary: str,
    params: dict[str, str],
    required: tuple[str, ...] = (),
    *,
    actor_may: bool = False,
    self_param: str | None = None,
) -> ConsequenceSpec:
    return ConsequenceSpec(kind, group, summary, params, required, actor_may, self_param)


PERSON = "a person ref, or self / party"
SPECS: dict[str, ConsequenceSpec] = {
    s.kind: s
    for s in (
        # -- access and movement
        _s(
            "grant_passage",
            "access",
            "an obstacle lets someone through",
            {"obstacle": "situation ref", "who": "actor (the one acting) or party (default)"},
            ("obstacle",),
            actor_may=True,
        ),
        _s(
            "remove_obstacle",
            "access",
            "an obstacle is gone for everyone",
            {"obstacle": "situation ref"},
            ("obstacle",),
            actor_may=True,
        ),
        _s(
            "add_obstacle",
            "access",
            "something now stands in the way (must leave a way past)",
            {
                "label": "what blocks, short text",
                "blocks": "place ref it bars, or all",
                "held_by": "person ref who enforces it (optional)",
                "ways_past": "list of 1-3 short ways around it",
                "minutes": "how long it lasts (max 360)",
            },
            ("label",),
            actor_may=True,
            self_param="held_by",
        ),
        _s(
            "open_route",
            "access",
            "a new way through opens (a gap, a back door, a path)",
            {
                "label": "the way, short text (a gap in the hedgerow)",
                "to": "place ref it leads to",
                "minutes": "travel time through it (default 2)",
            },
            ("label", "to"),
        ),
        _s(
            "close_route",
            "access",
            "a way is shut (a door barred, a bridge out)",
            {"to": "place ref", "label": "short text", "ways_past": "list of short ways around"},
            ("to", "label"),
        ),
        _s(
            "escort",
            "access",
            "someone takes the party to a place now",
            {"to": "place ref", "by": "person ref who leads (optional)"},
            ("to",),
        ),
        _s(
            "reposition",
            "access",
            "someone ends up in another spot of this scene",
            {"who": PERSON, "zone": "zone ref"},
            ("who", "zone"),
        ),
        # -- discovery
        _s(
            "reveal_feature",
            "discovery",
            "a detail of the place is established (a loose grate, fresh tracks)",
            {"description": "short text", "zone": "zone ref (optional)"},
            ("description",),
        ),
        _s(
            "learn",
            "discovery",
            "the one acting learns something (what they now believe)",
            {"text": "one sentence, from the character's point of view"},
            ("text",),
        ),
        _s(
            "reveal_clue",
            "discovery",
            "a listed clue is found",
            {"clue": "clue key from the request"},
            ("clue",),
        ),
        _s(
            "reveal_item",
            "discovery",
            "something concealed where the actor stands is found",
            {},
        ),
        _s(
            "introduce",
            "discovery",
            "someone tells their name",
            {"person": "person ref (self when an actor introduces themself)"},
            ("person",),
            actor_may=True,
            self_param="person",
        ),
        # -- people
        _s(
            "change_attitude",
            "people",
            "someone's feeling toward another shifts",
            {
                "person": "person ref whose feeling changes",
                "toward": "person ref, or party (default: the one acting)",
                "dimension": "trust | respect | affection | fear",
                "delta": "-2..2 (steps)",
            },
            ("person", "dimension", "delta"),
            actor_may=True,
            self_param="person",
        ),
        _s(
            "agree",
            "people",
            "someone promises to do something",
            {
                "person": "person ref who promises",
                "request": "what they promise, short text",
                "lets_pass": "situation ref of an obstacle they hold (optional)",
            },
            ("person", "request"),
            actor_may=True,
            self_param="person",
        ),
        _s(
            "refuse",
            "people",
            "someone firmly refuses (remembered)",
            {"person": "person ref", "request": "what they refuse, short text"},
            ("person", "request"),
            actor_may=True,
            self_param="person",
        ),
        _s(
            "accompany",
            "people",
            "someone goes along with the party for a while",
            {"person": "person ref", "minutes": "how long (optional)"},
            ("person",),
            actor_may=True,
            self_param="person",
        ),
        _s(
            "leave",
            "people",
            "someone leaves for another place",
            {"person": "person ref", "to": "place ref (optional)"},
            ("person",),
            actor_may=True,
            self_param="person",
        ),
        _s(
            "distract",
            "people",
            "someone's attention is elsewhere for a while",
            {"person": "person ref", "minutes": "1-60"},
            ("person",),
        ),
        _s(
            "turn_hostile",
            "people",
            "someone becomes an open enemy",
            {"person": "person ref", "toward": "person ref or party (default party)"},
            ("person",),
            actor_may=True,
            self_param="person",
        ),
        _s(
            "raise_alarm",
            "people",
            "an alarm is raised here",
            {"text": "short text (shouts for the watch)"},
            ("text",),
            actor_may=True,
        ),
        _s(
            "owe_favor",
            "people",
            "someone owes someone a favour",
            {"debtor": "person ref", "creditor": "person ref", "what": "short text"},
            ("debtor", "creditor", "what"),
            actor_may=True,
            self_param="debtor",
        ),
        # -- status
        _s(
            "set_status",
            "status",
            "someone now has a status (inspected, welcome, wanted, soaked)",
            {"who": PERSON, "status": "1-4 words", "minutes": "how long (optional)"},
            ("who", "status"),
            actor_may=True,
        ),
        _s(
            "clear_status",
            "status",
            "a status ends",
            {"who": PERSON, "status": "the status text"},
            ("who", "status"),
            actor_may=True,
        ),
        _s(
            "advance_clock",
            "status",
            "pressure builds (Suspicion, The fire spreads)",
            {"name": "short name", "by": "1 or 2", "of": "segments when new, 3-8"},
            ("name",),
        ),
        # -- items and coin
        _s(
            "pay",
            "items",
            "coin changes hands",
            {"from": PERSON, "to": PERSON, "amount": "coins, 1-1000"},
            ("from", "to", "amount"),
            actor_may=True,
            self_param="from",
        ),
        _s(
            "give_item",
            "items",
            "an item changes hands",
            {"from": PERSON, "item": "item ref", "to": PERSON},
            ("from", "item", "to"),
            actor_may=True,
            self_param="from",
        ),
        _s(
            "create_item",
            "items",
            "a minor item now exists (a stamped pass, a rope tied off)",
            {"name": "short name", "holder": "person ref, or here", "description": "short text"},
            ("name",),
        ),
        _s(
            "destroy_item",
            "items",
            "an item is ruined or gone",
            {"item": "item ref"},
            ("item",),
        ),
        _s(
            "set_price",
            "items",
            "a seller's prices change for the party",
            {"seller": "person ref", "percent": "-50..100 (negative = discount)"},
            ("seller", "percent"),
            actor_may=True,
            self_param="seller",
        ),
        # -- body and time
        _s(
            "harm",
            "body",
            "someone is hurt",
            {"who": PERSON, "amount": "1-12 or dice like 1d6"},
            ("who", "amount"),
        ),
        _s(
            "heal",
            "body",
            "someone recovers",
            {"who": PERSON, "amount": "1-12 or dice"},
            ("who", "amount"),
        ),
        _s(
            "condition",
            "body",
            "someone gains a listed condition",
            {"who": PERSON, "condition": "condition key from the rules", "minutes": "optional"},
            ("who", "condition"),
        ),
        _s(
            "pass_time",
            "time",
            "it takes a while",
            {"minutes": "1-240"},
            ("minutes",),
        ),
        _s(
            "schedule",
            "time",
            "something will happen later",
            {"minutes": "5-1440 from now", "what": "short text"},
            ("minutes", "what"),
        ),
    )
}

MAX_PER_BRANCH = 4
ACTOR_KINDS = frozenset(k for k, s in SPECS.items() if s.actor_may)


def catalogue(*, for_actor: bool = False) -> str:
    """The list shown to a model: each kind, what it does, and its parameters."""
    lines = []
    for s in SPECS.values():
        if for_actor and not s.actor_may:
            continue
        ps = ", ".join(f"{k}: {v}" for k, v in s.params.items())
        lines.append(f"- {s.kind}: {s.summary}" + (f" ({ps})" if ps else ""))
    return "\n".join(lines)
