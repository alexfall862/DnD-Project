"""A deterministic World Author script for campaign generation tests (Milestone 09): a small
salt-coast world, "Saltreach", whose starting town Marrow's Rest has a fouled well and a clerk
who did it. One envelope per stage; `responder` answers the World Author by stage key."""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from app.ai.providers import ModelRequest

BRIEF = {
    "title": "The Silent Tide",
    "campaign_mode": "sandbox",
    "genres": ["low fantasy"],
    "central_pressure": "a poisoned well and a salt market being cornered",
    "party_ai_companions": 2,
    "player_character": {"name": "Rook", "concept": "a salvager with a good eye"},
    "seed": 7,
}

STAGES: dict[str, dict[str, Any]] = {
    "premise": {
        "summary": "A salt coast where the sea-god fell silent and old certainties drowned.",
        "facts": [
            {
                "key": "f_premise_silence",
                "predicate": "the sea-god Oruun stopped answering prayers",
            },
            {"key": "f_premise_salt", "predicate": "salt is the only wealth left on the coast"},
        ],
    },
    "metaphysics": {
        "facts": [
            {"key": "f_tide_magic", "predicate": "tide-magic works only within sight of the sea"},
            {"key": "f_no_return", "predicate": "the drowned do not return"},
            {
                "key": "f_god_silent",
                "predicate": "the sea-god has been silent for years",
                "value": 7,
            },
        ],
    },
    "geography": {
        "locations": [
            {
                "ref": "loc_saltreach",
                "name": "Saltreach",
                "type": "region",
                "descriptor": "a grey salt coast",
            },
            {
                "ref": "loc_ironmarch",
                "name": "the Ironmarch",
                "type": "region",
                "descriptor": "mining hills",
            },
            {
                "ref": "loc_greyfens",
                "name": "the Greyfens",
                "type": "region",
                "descriptor": "tidal marsh",
            },
        ],
        "routes": [
            {"from_ref": "loc_saltreach", "to_ref": "loc_ironmarch", "travel_minutes": 2880}
        ],
    },
    "cultures": {
        "cultures": [
            {
                "ref": "cul_tidefolk",
                "name": "Tidefolk",
                "homeland_ref": "loc_saltreach",
                "values": ["thrift", "oaths"],
            },
            {
                "ref": "cul_marchers",
                "name": "Marchers",
                "homeland_ref": "loc_ironmarch",
                "values": ["iron", "kin"],
            },
        ]
    },
    "politics": {
        "factions": [
            {
                "ref": "fac_salt_council",
                "name": "the Salt Council",
                "kind": "polity",
                "territory_refs": ["loc_saltreach"],
                "public_goal": "keep the salt flowing",
            }
        ]
    },
    "factions": {
        "factions": [
            {
                "ref": "fac_brine_guild",
                "name": "the Brine Guild",
                "public": True,
                "public_goal": "fair salt for all",
                "hidden_goal": "corner the salt market",
                "rivals": ["fac_salt_council"],
                "plan_steps": [
                    {"title": "buy up the flats", "at_day": 2},
                    {"title": "raise the price", "at_day": 4},
                ],
            },
            {
                "ref": "fac_lantern_order",
                "name": "the Lantern Order",
                "public": False,
                "hidden_goal": "find the drowned bell",
                "plan_steps": [{"title": "dredge the chapel", "kind": "decision", "at_day": 5}],
            },
        ]
    },
    "history": {
        "facts": [
            {
                "key": "f_hist_flood",
                "predicate": "a great flood drowned the old harbor",
                "era": "century",
            },
            {
                "key": "f_hist_guild",
                "predicate": "was founded by ruined harbor masters",
                "subject_ref": "fac_brine_guild",
                "era": "decade",
            },
            {
                "key": "f_hist_silence",
                "predicate": "the temples emptied when the god fell silent",
                "era": "year",
            },
        ]
    },
    "current_state": {
        "facts": [
            {"key": "f_now_shortage", "predicate": "fresh water is scarce along the coast"},
            {"key": "f_now_refugees", "predicate": "fen families are moving into the towns"},
        ]
    },
    "conflicts": {
        "conflicts": [
            {
                "ref": "con_salt_war",
                "title": "the salt price war",
                "participant_refs": ["fac_brine_guild", "fac_salt_council"],
                "stakes": "who sets the price of salt",
            }
        ]
    },
    "secrets": {
        "actors": [
            {
                "ref": "npc_harl",
                "name": "Harl Brask",
                "importance": "full",
                "descriptor": "an ink-stained clerk",
            },
            {
                "ref": "npc_wenna",
                "name": "Wenna Ludd",
                "importance": "important",
                "descriptor": "the innkeeper",
            },
        ],
        "facts": [
            {
                "key": "f_harl_poisoned",
                "predicate": "fouled the east well with bitter salts",
                "subject_ref": "npc_harl",
                "sensitivity": "secret",
                "known_by_refs": ["npc_harl"],
            },
            {
                "key": "f_wenna_saw",
                "predicate": "was seen at the east well at dawn by",
                "subject_ref": "npc_harl",
                "object_ref": "npc_wenna",
                "sensitivity": "private",
                "known_by_refs": ["npc_wenna"],
            },
            {
                "key": "f_fen_traders",
                "predicate": "fen traders camped by the well the night it soured",
            },
        ],
        "mysteries": [
            {
                "ref": "mys_well",
                "question": "Who fouled the east well?",
                "truth_fact_keys": ["f_harl_poisoned"],
                "participant_refs": ["npc_harl"],
                "timeline": [
                    "Harl buys bitter salts",
                    "Harl pours them at dawn",
                    "the town sickens",
                ],
                "red_herring_fact_keys": ["f_fen_traders"],
            }
        ],
    },
    "pressures": {
        "pressures": [
            {
                "ref": "prs_sickness",
                "title": "sickness from the east well",
                "clock": [{"title": "more fall ill", "at_day": 2}],
            },
            {
                "ref": "prs_prices",
                "title": "salt prices climbing",
                "source_refs": ["fac_brine_guild"],
            },
        ],
        "facts": [
            {"key": "f_price_spike", "predicate": "salt prices double in the coastal towns"},
        ],
        "schedules": [
            {
                "key": "day2_price_spike",
                "at_day": 2,
                "type": "fact.establish",
                "fact_key": "f_price_spike",
            },
        ],
    },
    "starting_region": {
        "locations": [
            {
                "ref": "loc_coast_road",
                "name": "the Coast Road",
                "type": "road",
                "parent_ref": "loc_saltreach",
                "detail": "latent",
            },
            {
                "ref": "loc_salt_flats",
                "name": "the Salt Flats",
                "type": "wilds",
                "parent_ref": "loc_saltreach",
                "detail": "latent",
            },
            {
                "ref": "loc_drowned_chapel",
                "name": "the Drowned Chapel",
                "type": "site",
                "parent_ref": "loc_saltreach",
                "descriptor": "a half-sunk chapel",
            },
        ],
        "routes": [
            {"from_ref": "loc_coast_road", "to_ref": "loc_salt_flats", "travel_minutes": 40},
            {"from_ref": "loc_coast_road", "to_ref": "loc_drowned_chapel", "travel_minutes": 90},
        ],
    },
    "starting_settlement": {
        "locations": [
            {
                "ref": "loc_marrows_rest",
                "name": "Marrow's Rest",
                "type": "settlement",
                "parent_ref": "loc_saltreach",
                "detail": "materialized",
                "settlement": True,
                "descriptor": "a salt town of grey roofs",
                "zones": [
                    {"key": "square", "name": "the square", "exit": True},
                    {"key": "market", "name": "the salt market"},
                ],
                "adjacency": [["square", "market"]],
                "simulation_state": {"prosperity": 41, "security": 55, "food_supply": 60},
            },
            {
                "ref": "loc_gull_inn",
                "name": "the Gull and Anchor",
                "type": "building",
                "parent_ref": "loc_marrows_rest",
                "detail": "materialized",
                "descriptor": "an inn with a gull carved over the door",
                "features": ["a smoking hearth", "nets on the walls"],
                "zones": [
                    {"key": "door", "name": "the door", "exit": True},
                    {"key": "common_room", "name": "the common room"},
                    {"key": "bar", "name": "the bar", "cover": "light"},
                ],
                "adjacency": [["door", "common_room"], ["common_room", "bar"]],
                "entry_zone": "door",
            },
            {
                "ref": "loc_east_well",
                "name": "the East Well",
                "type": "site",
                "parent_ref": "loc_marrows_rest",
                "detail": "materialized",
                "descriptor": "a stone well behind a rope",
                "zones": [
                    {"key": "yard", "name": "the yard", "exit": True},
                    {"key": "well", "name": "the wellhead"},
                ],
                "adjacency": [["yard", "well"]],
            },
            {
                "ref": "loc_council_hall",
                "name": "the Council Hall",
                "type": "building",
                "parent_ref": "loc_marrows_rest",
                "detail": "materialized",
                "descriptor": "a hall of tarred timber",
                "zones": [
                    {"key": "hall", "name": "the hall", "exit": True},
                    {"key": "desk", "name": "the clerk's desk"},
                ],
                "adjacency": [["hall", "desk"]],
            },
        ],
        "routes": [
            {"from_ref": "loc_marrows_rest", "to_ref": "loc_gull_inn", "travel_minutes": 2},
            {"from_ref": "loc_marrows_rest", "to_ref": "loc_east_well", "travel_minutes": 5},
            {"from_ref": "loc_marrows_rest", "to_ref": "loc_council_hall", "travel_minutes": 3},
            {"from_ref": "loc_marrows_rest", "to_ref": "loc_coast_road", "travel_minutes": 10},
        ],
    },
    "local_factions": {
        "factions": [
            {
                "ref": "fac_well_wardens",
                "name": "the Well Wardens",
                "scope": "local",
                "public_goal": "keep the town's water clean",
                "plan_steps": [{"title": "rope off the east well", "at_day": 1}],
            }
        ]
    },
    "npcs": {
        "actors": [
            {
                "ref": "npc_harl",
                "occupation": "clerk of the Salt Council",
                "location_ref": "loc_council_hall",
                "attributes": {
                    "might": 4,
                    "agility": 5,
                    "intellect": 7,
                    "presence": 5,
                    "resolve": 4,
                },
                "skills": {"deception": 3, "persuasion": 2},
                "summary": "Careful, indebted to the Brine Guild, frightened of being found out.",
                "dimensions": {"honesty": 0.2, "risk_tolerance": 0.4},
                "goals": [
                    {"description": "keep anyone from looking into the well", "priority": 90}
                ],
                "faction_refs": ["fac_brine_guild"],
                "knows_refs": ["npc_wenna", "loc_east_well"],
                "relationships": [{"target_ref": "npc_wenna", "trust": 10, "familiarity": 60}],
            },
            {
                "ref": "npc_wenna",
                "occupation": "innkeeper",
                "location_ref": "loc_gull_inn",
                "attributes": {
                    "might": 4,
                    "agility": 4,
                    "intellect": 6,
                    "presence": 6,
                    "resolve": 6,
                },
                "skills": {"awareness": 2, "persuasion": 2},
                "summary": "Shrewd and kind, afraid of the Council.",
                "dimensions": {"honesty": 0.7, "risk_tolerance": 0.3},
                "goals": [
                    {
                        "description": "keep the inn's guests from drinking the bad water",
                        "priority": 80,
                    }
                ],
                "knows_refs": ["npc_harl", "npc_osk"],
                "relationships": [
                    {"target_ref": "npc_harl", "trust": -20, "fear": 30, "familiarity": 60}
                ],
            },
            {
                "ref": "npc_osk",
                "name": "Osk Tamber",
                "importance": "important",
                "occupation": "well warden",
                "descriptor": "a broad man with a lantern",
                "location_ref": "loc_east_well",
                "attributes": {
                    "might": 7,
                    "agility": 4,
                    "intellect": 4,
                    "presence": 5,
                    "resolve": 6,
                },
                "skills": {"melee": 2, "awareness": 2},
                "goals": [{"description": "find out why the well turned", "priority": 85}],
                "leads_faction_ref": "fac_well_wardens",
                "knows_refs": ["npc_wenna"],
                "relationships": [{"target_ref": "npc_wenna", "trust": 50, "familiarity": 70}],
            },
        ],
        "facts": [
            {
                "key": "f_harl_bought_salts",
                "predicate": "bought a sack of bitter salts from the apothecary",
                "subject_ref": "npc_harl",
                "sensitivity": "private",
                "known_by_refs": ["npc_harl"],
            },
            {
                "key": "f_bitter_residue",
                "predicate": "has a crust of bitter salt residue on its stones",
                "subject_ref": "loc_east_well",
            },
        ],
    },
    "opportunities": {
        "opportunities": [
            {
                "ref": "opp_sick_well",
                "title": "the sickness from the east well",
                "pressure_ref": "prs_sickness",
                "routes": [
                    {"kind": "conversation", "via_ref": "npc_wenna"},
                    {"kind": "location", "via_ref": "loc_east_well"},
                ],
            },
            {
                "ref": "opp_salt_prices",
                "title": "the salt price war",
                "pressure_ref": "prs_prices",
                "routes": [
                    {"kind": "notice", "via_ref": "loc_marrows_rest"},
                    {"kind": "conversation", "via_ref": "npc_harl"},
                ],
            },
        ],
        "items": [
            {
                "ref": "itm_receipt",
                "name": "an apothecary's receipt",
                "template_key": "item.document",
                "location_ref": "loc_council_hall",
                "zone": "desk",
                "concealed": True,
                "concealment_difficulty": "easy",
                "document": {
                    "text": (
                        "Received of H. Brask: one sack of bitter salts, paid in full. "
                        "— Ostry, apothecary"
                    ),
                    "conveys_fact_keys": ["f_harl_bought_salts"],
                },
            },
            {
                "ref": "itm_residue",
                "name": "a crust of bitter residue",
                "template_key": "item.travel_supplies",
                "location_ref": "loc_east_well",
                "zone": "well",
                "concealed": True,
                "concealment_difficulty": "routine",
            },
        ],
        "clues": [
            {
                "ref": "clu_wenna",
                "mystery_ref": "mys_well",
                "clue_type": "social",
                "supports_fact_key": "f_wenna_saw",
            },
            {
                "ref": "clu_receipt",
                "mystery_ref": "mys_well",
                "clue_type": "document",
                "supports_fact_key": "f_harl_bought_salts",
                "entity_ref": "itm_receipt",
                "destructible": True,
            },
            {
                "ref": "clu_residue",
                "mystery_ref": "mys_well",
                "clue_type": "physical",
                "supports_fact_key": "f_bitter_residue",
                "entity_ref": "itm_residue",
            },
        ],
    },
    "party": {
        "actors": [
            {
                "ref": "pc_rook",
                "name": "Rook",
                "role": "pc_human",
                "importance": "full",
                "descriptor": "a salvager with sea-cracked hands",
                "location_ref": "loc_gull_inn",
                "attributes": {
                    "might": 5,
                    "agility": 6,
                    "intellect": 5,
                    "presence": 5,
                    "resolve": 4,
                },
                "skills": {
                    "investigation": 2,
                    "awareness": 2,
                    "melee": 2,
                    "persuasion": 1,
                    "survival": 1,
                },
                "traits": ["keen_observer"],
                "equipment": [{"name": "salvager's knife", "template_key": "item.knife"}],
            },
            {
                "ref": "pc_tess",
                "name": "Tess Morrow",
                "role": "pc_ai",
                "importance": "full",
                "descriptor": "a wiry archer",
                "location_ref": "loc_gull_inn",
                "attributes": {
                    "might": 4,
                    "agility": 7,
                    "intellect": 5,
                    "presence": 5,
                    "resolve": 4,
                },
                "skills": {"ranged": 3, "stealth": 2, "survival": 2, "awareness": 2},
                "traits": ["quick_reflexes"],
                "equipment": [{"name": "short bow", "template_key": "item.bow"}],
                "summary": "Restless and loyal, hunting the men who burned her village.",
                "dimensions": {"risk_tolerance": 0.7, "loyalty": 0.7, "honesty": 0.6},
                "goals": [{"description": "find the men who burned Westhollow", "priority": 85}],
                "core_memories": ["Westhollow burning while I watched from the dunes."],
                "relationships": [
                    {"target_ref": "pc_rook", "trust": 55, "familiarity": 50},
                    {"target_ref": "pc_bran", "trust": 40, "familiarity": 40},
                ],
            },
            {
                "ref": "pc_bran",
                "name": "Bran Hollis",
                "role": "pc_ai",
                "importance": "full",
                "descriptor": "a big former sailor",
                "location_ref": "loc_gull_inn",
                "attributes": {
                    "might": 7,
                    "agility": 4,
                    "intellect": 4,
                    "presence": 6,
                    "resolve": 4,
                },
                "skills": {"melee": 3, "intimidation": 2, "persuasion": 2, "medicine": 1},
                "traits": ["iron_will"],
                "equipment": [{"name": "boarding axe", "template_key": "item.club"}],
                "summary": "Gentle until he isn't; wants an honest wage and a quiet life.",
                "dimensions": {"aggression": 0.5, "empathy": 0.7, "honesty": 0.8},
                "goals": [
                    {"description": "earn enough to buy back his father's boat", "priority": 70}
                ],
                "relationships": [
                    {"target_ref": "pc_rook", "trust": 60, "familiarity": 60},
                    {"target_ref": "pc_tess", "trust": 45, "familiarity": 40},
                ],
            },
        ]
    },
    "opening": {
        "opening": {
            "location_ref": "loc_gull_inn",
            "hour": 18,
            "weather": "a salt wind off the flats",
            "situation": "Wenna is turning guests away from the water barrel.",
            "present_refs": ["pc_rook", "pc_tess", "pc_bran", "npc_wenna"],
            "positions": {
                "pc_rook": "common_room",
                "pc_tess": "common_room",
                "pc_bran": "door",
                "npc_wenna": "bar",
            },
        }
    },
}

STAGE_RE = re.compile(r"STAGE (\w+) —(?: (OUTLINE)| ITEM (\w+))?")


def split_items(key: str, env: dict[str, Any]) -> tuple[list[dict], dict[str, dict]]:
    """An itemized stage's envelope as (outline entries, one envelope per item): every other
    entry goes to the first item it mentions or that mentions it (else the first item)."""
    from app.worldgen.stages import STAGE_BY_KEY

    cfg = STAGE_BY_KEY[key].itemized
    assert cfg is not None
    primary = env.get(cfg.primary, [])
    refs = [x["ref"] for x in primary]
    per = {r: {cfg.primary: [x]} for r, x in zip(refs, primary, strict=True)}
    texts = {r: json.dumps(x) for r, x in zip(refs, primary, strict=True)}
    for sec, entries in env.items():
        if sec == cfg.primary or not isinstance(entries, list):
            continue
        for e in entries:
            ident = e.get("ref") or e.get("key") or ""
            body = json.dumps(e)
            owner = next(
                (r for r in refs if f'"{r}"' in body or (ident and f'"{ident}"' in texts[r])),
                refs[0],
            )
            per[owner].setdefault(sec, []).append(e)
    return primary, per


def responder(overrides: dict[str, Any] | None = None, *, calls: list[str] | None = None):
    """Answer the World Author by stage key. `overrides[stage]` may be a dict (used every
    time) or a list (consumed one per call: e.g. a rejected answer then a fixed one).
    Itemized stages are asked for an outline, then item by item: the stage's envelope (or its
    override) is split per item; `overrides["<stage>:outline"]` and `overrides["<stage>:<ref>"]`
    replace just that call. `calls` records "stage", "stage:outline" or "stage:<ref>"."""
    overrides = dict(overrides or {})
    current: dict[str, dict] = {}  # the envelope an itemized stage is being split from

    def take(name: str) -> Any:
        o = overrides.get(name)
        if isinstance(o, list) and o:
            return o.pop(0) if len(o) > 1 else o[0]
        return o

    def pick(req: ModelRequest) -> dict[str, Any]:
        m = STAGE_RE.search(req.user)
        assert m, f"no stage marker in request:\n{req.user[-600:]}"
        key, outline, item = m.group(1), m.group(2), m.group(3)
        name = f"{key}:outline" if outline else f"{key}:{item}" if item else key
        if calls is not None:
            calls.append(name)
        o = take(name)
        if o is not None:
            return copy.deepcopy(o)
        if not (outline or item):
            o = take(key)
            return copy.deepcopy(o if o is not None else STAGES[key])
        if outline:  # a new pass over the stage: consume the next scripted envelope
            o = take(key)
            current[key] = copy.deepcopy(o if o is not None else STAGES[key])
        env = current.get(key) or STAGES[key]
        primary, per = split_items(key, copy.deepcopy(env))
        if outline:
            from app.worldgen.stages import STAGE_BY_KEY

            return {STAGE_BY_KEY[key].itemized.primary: primary}
        return per.get(item, {})

    return pick


def expected_calls(keys: list[str] | None = None, script: dict | None = None) -> list[str]:
    """The World Author calls a clean run makes: one per plain stage; an outline plus one per
    item for an itemized stage."""
    from app.worldgen.stages import STAGE_BY_KEY

    script = script or STAGES
    out: list[str] = []
    for key in keys or list(STAGES):
        cfg = STAGE_BY_KEY[key].itemized
        if cfg is None:
            out.append(key)
        else:
            out.append(f"{key}:outline")
            out += [f"{key}:{x['ref']}" for x in script[key][cfg.primary]]
    return out
