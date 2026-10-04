"""The staged pipeline (campaign-generation §5, orchestration §28): each stage is one bounded
World Author call with a task, the envelope sections it may fill, minimum content, and the
stages it depends on. Rerolling a stage invalidates exactly its transitive dependents.

Depth policy (§1, §8, §27): world-scale stages may only produce outline/latent locations;
materialized locations (with zones) belong to the starting region and settlement; people
appear first as mystery participants (secrets) and are fleshed out by the NPC and party
stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Itemized:
    """Outline, then fill: one small call lists the stage's items (ref + a line each), then one
    call per item writes it in full. A bad item retries alone; good items are kept; a rerun
    resumes at the first unfinished item (A9 generation runs: the heavy stages overran their
    output budget and one bad entry cost the whole stage)."""

    primary: str  # envelope section that lists the items
    outline_fields: str  # what the outline call writes per item
    count: tuple[int, int]  # how many items the outline may list
    fill_sections: frozenset[str]  # what one item's fill may contain
    reuse_existing: bool = False  # the outline may name earlier refs (refine/deepen them)


@dataclass(frozen=True)
class Stage:
    key: str
    title: str
    task: str
    sections: frozenset[str]
    depends_on: tuple[str, ...] = ()
    minimum: dict[str, int] = field(default_factory=dict)
    max_detail: str = "outline"  # deepest location detail this stage may produce
    forced_canon: str | None = None  # facts from this stage are always this canon
    itemized: Itemized | None = None


def _s(*names: str) -> frozenset[str]:
    return frozenset(names)


STAGES: tuple[Stage, ...] = (
    Stage(
        "premise",
        "Setting premise",
        "Give the world a concise identity and its central tensions as structured thematic "
        "facts that create play opportunities, not decorative lore. Put the one-paragraph "
        "identity in `summary`.",
        _s("facts"),
        (),
        {"facts": 2},
    ),
    Stage(
        "metaphysics",
        "Physical and metaphysical rules",
        "Answer only the foundational questions this setting needs (does magic exist and how "
        "reliable is it; resurrection; gods and afterlife; technology ceiling). These become "
        "established canon.",
        _s("facts"),
        ("premise",),
        {"facts": 2},
        forced_canon="established",
    ),
    Stage(
        "geography",
        "Macro geography",
        "Regions, climate, major routes and boundaries, and a few settlement anchors. Distant "
        "places stay outlines: names, type, one-line descriptor. No villages, no zones.",
        _s("locations", "routes", "facts"),
        ("premise", "metaphysics"),
        {"locations": 3},
        max_detail="outline",
    ),
    Stage(
        "cultures",
        "Cultures",
        "Two to four cultures with homelands, values, languages and customs, each with "
        "internal variation or a contested identity.",
        _s("cultures", "facts"),
        ("geography",),
        {"cultures": 2},
    ),
    Stage(
        "politics",
        "Political structures",
        "States, city-states, councils, churches or alliances at the resolution the brief's "
        "simulation scope asks for (kind: polity).",
        _s("factions", "facts"),
        ("geography", "cultures"),
        {"factions": 1},
    ),
    Stage(
        "factions",
        "Major factions",
        "Two or three actionable factions (kind: faction) with public and hidden goals, "
        "resources, allies, rivals, and at least one plan of concrete steps each. You may turn "
        "an earlier power into one by repeating its ref with the plan and hidden goal.",
        _s("factions", "facts"),
        ("politics",),
        {"factions": 2},
    ),
    Stage(
        "history",
        "Historical backbone",
        "Only history that explains the present: one or two facts per era (ancient, century, "
        "decade, year), each tied to borders, rivalries, ruins or present conflicts.",
        _s("facts"),
        ("factions", "cultures"),
        {"facts": 3},
    ),
    Stage(
        "current_state",
        "Current world state",
        "A present-tense snapshot: wars, crises, migrations, movements, disruptions.",
        _s("facts"),
        ("history",),
        {"facts": 2},
    ),
    Stage(
        "conflicts",
        "Major conflicts",
        "Conflicts with participants, stakes, cause, status and how they could escalate or "
        "ease. Prefer local stakes if the brief's scope is local.",
        _s("conflicts", "facts"),
        ("current_state", "factions"),
        {"conflicts": 1},
    ),
    Stage(
        "secrets",
        "Secrets and mysteries",
        "Hidden truths as facts with sensitivity secret and the actors who know them. At least "
        "one mystery, truth first: the truth facts, the people involved (as actors with name, "
        "importance and descriptor only), motive and timeline. No clues yet.",
        _s("facts", "mysteries", "actors"),
        ("conflicts",),
        {"mysteries": 1},
    ),
    Stage(
        "pressures",
        "Campaign pressures",
        "Active pressures rather than quests, each with a clock of dated steps when it moves "
        "on its own. Match the campaign mode (authored, sandbox, emergent).",
        _s("pressures", "schedules", "facts"),
        ("conflicts", "secrets"),
        {"pressures": 2},
    ),
    Stage(
        "starting_region",
        "Starting region",
        "The starting region in more depth than the world: settlements, roads, wilderness, a "
        "few unexplored sites, travel times, dangers and rumors. Locations may be latent.",
        _s("locations", "routes", "facts"),
        ("geography", "pressures"),
        {"locations": 3},
        max_detail="latent",
    ),
    Stage(
        "starting_settlement",
        "Starting settlement",
        "One immediately playable settlement (settlement: true) and its important places as "
        "materialized locations with zones (key, name, cover, exit, features). To deepen a "
        "place the region stage already named, repeat its ref with the zones. Routes between "
        "them in minutes, simulation state (prosperity, security, food_supply, "
        "political_stability, outsider_hostility), notable objects.",
        _s("locations", "routes", "facts", "items"),
        ("starting_region",),
        {"locations": 3},
        max_detail="materialized",
    ),
    Stage(
        "local_factions",
        "Local factions",
        "Local powers in and around the settlement (scope: local) with plans whose steps carry "
        "at_day when they move by themselves; schedule what happens if nobody interferes.",
        _s("factions", "schedules", "facts"),
        ("starting_settlement", "factions"),
        {"factions": 1},
    ),
    Stage(
        "npcs",
        "Important NPCs and social graph",
        "Four to six important people of the settlement (including the mystery participants, "
        "repeating their refs to complete them): home location, attributes and skills, a "
        "personality summary, goals, which facts they know, whom they know by name, and "
        "relationships with each other. Keep every person compact — summary under 25 words, "
        "the 3 most telling dimensions (0..1), at most 3 skills, at most 2 goals, at most 2 "
        "relationships, no equipment — so the whole answer stays well under 3000 tokens.",
        _s("actors", "facts"),
        ("starting_settlement", "local_factions", "secrets"),
        {"actors": 3},
    ),
    Stage(
        "opportunities",
        "Starting opportunities and clues",
        "Several situations, each discoverable by at least two routes (rumor, notice, "
        "conversation, location, document). Clue routes for every mystery: physical, document "
        "and social clues supporting its truth facts, redundant so losing one never makes it "
        "unsolvable. Clue objects as items placed in materialized zones.",
        _s("opportunities", "clues", "items", "facts", "schedules"),
        ("npcs", "secrets", "pressures"),
        {"opportunities": 2, "clues": 2},
    ),
    Stage(
        "party",
        "Party integration",
        "The player character and the AI companions: legal sheets (attributes start at 3 with "
        "10 extra points, max 8; 8 skill points plus 2 ranks from background, max rank 3), "
        "distinct personalities, goals, fears, core memories, a plausible shared reason to "
        "travel together, relationships with each other, and starting equipment.",
        _s("actors"),
        ("npcs", "starting_settlement"),
        {"actors": 1},
    ),
    Stage(
        "opening",
        "Opening scene",
        "Where the campaign begins: a materialized location, the hour, the weather, who is "
        "present (the party plus anyone plausible), where they stand, and an immediate "
        "situation that offers possibilities without forcing a quest.",
        _s("opening"),
        ("party", "opportunities"),
        {},
    ),
)

IMPORT = Stage(
    "import",
    "Imported world",
    "Extract into the envelope everything the supplied text states about this world: places, "
    "peoples, factions, people (and any player character sheets, role pc_human / pc_ai), "
    "history, secrets, mysteries with their truths, items and documents. Invent nothing that "
    "the text does not state or directly imply; leave gaps for later stages. Reuse refs from "
    "earlier parts of the import exactly.",
    frozenset(
        {
            "facts",
            "locations",
            "routes",
            "cultures",
            "factions",
            "actors",
            "conflicts",
            "pressures",
            "mysteries",
            "items",
            "mechanics",
        }
    ),
    (),
    {},
    max_detail="materialized",
    forced_canon="established",  # what the user wrote is canon the generator may not contradict
)

ITEMIZED: dict[str, Itemized] = {
    "secrets": Itemized(
        "mysteries",
        "ref, question (one line)",
        (1, 2),
        frozenset({"mysteries", "facts", "actors"}),
    ),
    "starting_settlement": Itemized(
        "locations",
        "ref, name, type, settlement (true for the town itself), parent_ref, descriptor",
        (3, 6),
        frozenset({"locations", "routes", "facts", "items"}),
        reuse_existing=True,
    ),
    "npcs": Itemized(
        "actors",
        "ref, name, occupation, location_ref, importance (repeat earlier refs for people "
        "already named)",
        (3, 6),
        frozenset({"actors", "facts"}),
        reuse_existing=True,
    ),
    "opportunities": Itemized(
        "opportunities",
        "ref, title (one line)",
        (2, 4),
        frozenset({"opportunities", "clues", "items", "facts", "schedules"}),
    ),
    "party": Itemized(
        "actors",
        "ref, name, role (pc_human for the player, pc_ai for companions), occupation",
        (1, 5),  # a solo player is a party of one; the composition check does the rest
        frozenset({"actors"}),
        reuse_existing=True,
    ),
}
STAGES = tuple(replace(s, itemized=ITEMIZED[s.key]) if s.key in ITEMIZED else s for s in STAGES)

STAGE_BY_KEY = {s.key: s for s in (*STAGES, IMPORT)}
ORDER = {s.key: i for i, s in enumerate(STAGES)}


def dependents(key: str) -> list[str]:
    """Every stage that transitively depends on `key`, in pipeline order. The import stage
    underlies everything."""
    if key == "import":
        return [s.key for s in STAGES]
    out: set[str] = set()
    frontier = [key]
    while frontier:
        k = frontier.pop()
        for s in STAGES:
            if k in s.depends_on and s.key not in out:
                out.add(s.key)
                frontier.append(s.key)
    return sorted(out, key=ORDER.__getitem__)


def ancestors(key: str) -> list[str]:
    out: set[str] = set()
    frontier = [key]
    while frontier:
        k = frontier.pop()
        for d in STAGE_BY_KEY[k].depends_on:
            if d not in out:
                out.add(d)
                frontier.append(d)
    return sorted(out, key=ORDER.__getitem__)
