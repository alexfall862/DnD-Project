"""Milestone 09: stage validation without a database — truth before clues, established canon,
registered primitives, the character-creation budget and the depth policy."""

from __future__ import annotations

import copy

import pytest

from app.engine.core import RulesEngine
from app.worldgen.brief import CampaignBrief, surprise
from app.worldgen.envelope import WorldAuthorOut
from app.worldgen.stages import STAGE_BY_KEY, STAGES, ancestors, dependents
from app.worldgen.validate import Catalog, mechanic_errors, validate_stage
from tests.fixtures.saltreach import BRIEF
from tests.fixtures.saltreach import STAGES as SCRIPT

pytestmark = pytest.mark.unit

RS = RulesEngine.load("core_adventure").ruleset
BR = CampaignBrief.model_validate(BRIEF)


def catalog_before(stage_key: str) -> Catalog:
    envs = []
    for st in STAGES:
        if st.key == stage_key:
            break
        envs.append((st.key, WorldAuthorOut.model_validate(copy.deepcopy(SCRIPT[st.key]))))
    return Catalog.build(envs)


def check(stage_key: str, env: dict) -> list[str]:
    return validate_stage(
        STAGE_BY_KEY[stage_key],
        WorldAuthorOut.model_validate(env),
        catalog_before(stage_key),
        ruleset=RS,
        brief=BR,
    )


def test_the_scripted_world_passes_every_stage() -> None:
    for st in STAGES:
        assert check(st.key, copy.deepcopy(SCRIPT[st.key])) == [], st.key


def test_dependencies_are_transitive_and_ordered() -> None:
    assert dependents("starting_settlement") == [
        "local_factions",
        "npcs",
        "opportunities",
        "party",
        "opening",
    ]
    assert "premise" in ancestors("opening") and dependents("opening") == []


def test_a_stage_may_only_fill_its_sections() -> None:
    env = copy.deepcopy(SCRIPT["premise"])
    env["actors"] = [{"ref": "npc_x", "name": "X"}]
    assert any("section 'actors' is not allowed" in e for e in check("premise", env))


def test_established_canon_cannot_be_contradicted() -> None:
    env = copy.deepcopy(SCRIPT["history"])
    env["facts"].append(
        {"key": "f_bad", "predicate": "the sea-god has been silent for years", "value": 3}
    )
    env["facts"].append({"key": "f_bad2", "predicate": "not the drowned do not return"})
    errors = check("history", env)
    assert any("f_bad contradicts established canon 'f_god_silent'" in e for e in errors)
    assert any("f_bad2 contradicts established canon 'f_no_return'" in e for e in errors)


def test_the_locked_truth_cannot_be_contradicted() -> None:
    env = copy.deepcopy(SCRIPT["npcs"])
    env["facts"].append(
        {
            "key": "f_innocent",
            "predicate": "not fouled the east well with bitter salts",
            "subject_ref": "npc_harl",
        }
    )
    assert any("contradicts the locked truth 'f_harl_poisoned'" in e for e in check("npcs", env))


def test_truth_precedes_clues_and_mysteries_need_truths() -> None:
    env = copy.deepcopy(SCRIPT["secrets"])
    env["mysteries"].append({"ref": "mys_empty", "question": "Why?"})
    assert any("mys_empty has no truth facts" in e for e in check("secrets", env))
    opp = copy.deepcopy(SCRIPT["opportunities"])
    opp["clues"].append(
        {
            "ref": "clu_orphan",
            "mystery_ref": "mys_not_yet",
            "clue_type": "social",
            "supports_fact_key": "f_wenna_saw",
        }
    )
    opp["clues"][1]["entity_ref"] = None  # a document clue with no document
    model = WorldAuthorOut.model_validate(opp)
    notes: list[str] = []
    errors = validate_stage(
        STAGE_BY_KEY["opportunities"],
        model,
        catalog_before("opportunities"),
        ruleset=RS,
        brief=BR,
        notes=notes,
    )
    assert errors == []  # two good clues remain: the stage minimum holds
    assert [c.ref for c in model.clues] == ["clu_wenna", "clu_residue"]
    assert any("clu_orphan dropped" in n and "truth precedes clues" in n for n in notes)
    assert any("clu_receipt dropped" in n and "needs an existing item" in n for n in notes)


def test_red_herrings_may_not_contradict_the_truth() -> None:
    env = copy.deepcopy(SCRIPT["secrets"])
    env["facts"].append(
        {
            "key": "f_lie",
            "predicate": "not fouled the east well with bitter salts",
            "subject_ref": "npc_harl",
        }
    )
    env["mysteries"][0]["red_herring_fact_keys"].append("f_lie")
    assert any("red herring 'f_lie' contradicts the truth" in e for e in check("secrets", env))


def test_structural_references_must_resolve_and_soft_ones_are_dropped() -> None:
    env = copy.deepcopy(SCRIPT["npcs"])
    env["actors"][0]["location_ref"] = "loc_nowhere"  # structural: where someone lives
    env["actors"][1]["relationships"].append({"target_ref": "npc_ghost", "trust": 5})  # a link
    model = WorldAuthorOut.model_validate(env)
    notes: list[str] = []
    errors = validate_stage(
        STAGE_BY_KEY["npcs"], model, catalog_before("npcs"), ruleset=RS, brief=BR, notes=notes
    )
    assert any("unknown ref 'loc_nowhere'" in e for e in errors)
    assert not any("npc_ghost" in e for e in errors)
    assert all(r.target_ref != "npc_ghost" for r in model.actors[1].relationships)
    assert any("dropped relationships with unknown people" in n for n in notes)


def test_distant_content_stays_shallow() -> None:
    env = copy.deepcopy(SCRIPT["geography"])
    env["locations"][1]["detail"] = "materialized"
    env["locations"][1]["zones"] = [{"key": "a"}]
    model = WorldAuthorOut.model_validate(env)
    notes: list[str] = []
    errors = validate_stage(
        STAGE_BY_KEY["geography"],
        model,
        catalog_before("geography"),
        ruleset=RS,
        brief=BR,
        notes=notes,
    )
    assert errors == []
    assert model.locations[1].detail == "outline" and model.locations[1].zones == []
    assert any("clamped to outline" in n for n in notes)
    settlement = copy.deepcopy(SCRIPT["starting_settlement"])
    settlement["locations"][1]["zones"] = []
    errs = check("starting_settlement", settlement)
    assert any("a materialized location needs zones" in e for e in errs)


def test_player_characters_are_fitted_to_the_creation_budget() -> None:
    env = copy.deepcopy(SCRIPT["party"])
    env["actors"][0]["attributes"]["might"] = 9
    env["actors"][1]["skills"]["stealth"] = 4
    env["actors"][2]["traits"] = ["iron_will", "veteran", "quick_reflexes"]
    model = WorldAuthorOut.model_validate(env)
    notes: list[str] = []
    errors = validate_stage(
        STAGE_BY_KEY["party"], model, catalog_before("party"), ruleset=RS, brief=BR, notes=notes
    )
    assert errors == []
    rook, tess, bran = model.actors
    assert max(rook.attributes.values()) <= 8 and sum(rook.attributes.values()) <= 25
    assert tess.skills["stealth"] == 3 and sum(tess.skills.values()) <= 10
    assert bran.traits == ["iron_will", "veteran"]
    assert any("might 9 -> 8" in n for n in notes)
    lone = copy.deepcopy(SCRIPT["party"])
    lone["actors"][2]["relationships"] = []
    assert any("reason to travel with the party" in e for e in check("party", lone))


def test_party_members_never_start_with_secrets() -> None:
    env = copy.deepcopy(SCRIPT["party"])
    env["actors"][1]["knows_fact_keys"] = ["f_harl_poisoned"]
    assert any("may not start knowing secret" in e for e in check("party", env))


def test_generated_mechanics_use_registered_primitives() -> None:
    ok = {
        "key": "x",
        "tier": "low",
        "passive": {"type": "modify_check", "params": {}},
        "activated": {"type": "apply_condition", "params": {"condition": "condition.hidden"}},
    }
    assert mechanic_errors(ok, RS) == []
    assert mechanic_errors({**ok, "passive": {"type": "teleport"}}, RS)
    assert mechanic_errors({**ok, "passive": {"type": "exec_python"}}, RS)
    assert mechanic_errors({**ok, "tier": "legendary"}, RS)
    assert mechanic_errors(
        {**ok, "activated": {"type": "apply_condition", "params": {"condition": "condition.x"}}},
        RS,
    )


def test_surprise_briefs_are_reproducible() -> None:
    assert surprise(42) == surprise(42)
    assert surprise(42, title="Mine").title == "Mine"
    assert "Party:" in surprise(1).as_context()


def test_item_effects_must_be_item_primitives_with_the_params_they_read() -> None:
    """The first A9 run proposed `create_entity` with invented params and `{name}` templates:
    registered, structurally a dict, and meaningless in play."""
    a9_relic = {
        "key": "item.generated_relic",
        "tier": "low",
        "description": "Ghostly fingerprints of {digger_name}.",
        "passive": {
            "type": "reveal_information",
            "params": {"fact_key": "x", "target_actor": "holder"},
        },
        "activated": {
            "type": "create_entity",
            "params": {"entity_type": "memory", "content": "Their name is {digger_name}."},
        },
    }
    errs = mechanic_errors(a9_relic, RS)
    assert any("'reveal_information' is not an item effect" in e for e in errs)
    assert any("'create_entity' is not an item effect" in e for e in errs)
    assert any("description contains a template placeholder" in e for e in errs)
    bad_params = {
        "key": "y",
        "tier": "low",
        "passive": {"type": "modify_check", "params": {"target": "check.*", "value": 1}},
        "activated": {"type": "deal_damage", "params": {"amount": "4d12"}},
    }
    errs = mechanic_errors(bad_params, RS)
    assert any("modify_check does not read 'target'" in e for e in errs)
    assert any("not low-tier dice" in e for e in errs)
    assert (
        mechanic_errors(
            {
                "key": "z",
                "tier": "low",
                "passive": {
                    "type": "modify_check",
                    "params": {"check": "check.*", "op": "add", "amount": 1, "when": "in darkness"},
                },
                "activated": {
                    "type": "restore_resource",
                    "params": {"resource": "resource.stamina", "amount": "1d4", "uses_per_day": 1},
                },
            },
            RS,
        )
        == []
    )


def test_unknown_fact_subjects_become_wording_not_errors() -> None:
    """First A9 run: GLM wrote free text into fact refs before any entity existed."""
    env = WorldAuthorOut.model_validate(
        {
            "facts": [
                {
                    "key": "f1",
                    "predicate": "is",
                    "subject_ref": "the_silver_seam",
                    "object_ref": "failing",
                },
                {"key": "f2", "predicate": "rule the hills", "subject_ref": "the old kings"},
            ]
        }
    )
    errors = validate_stage(STAGE_BY_KEY["premise"], env, Catalog(), ruleset=RS, brief=BR)
    assert errors == []
    assert env.facts[0].predicate == "the silver seam is" and env.facts[0].value == "failing"
    assert env.facts[1].predicate == "the old kings rule the hills"
    assert env.facts[0].subject_ref is None and env.facts[1].subject_ref is None
    # knowers who do not exist are dropped (narrowing knowledge), and noted
    env2 = WorldAuthorOut.model_validate(
        {
            "facts": [
                {"key": "f3", "predicate": "x", "known_by_refs": ["npc_ghost"]},
                {"key": "f4", "predicate": "y"},
            ]
        }
    )
    notes: list[str] = []
    errs = validate_stage(
        STAGE_BY_KEY["premise"], env2, Catalog(), ruleset=RS, brief=BR, notes=notes
    )
    assert errs == [] and env2.facts[0].known_by_refs == []
    assert any("dropped knowers" in n for n in notes)


def test_repeated_earlier_content_is_dropped_and_the_earlier_version_stands() -> None:
    """Third A9 run: the politics stage re-emitted every earlier fact under its old key."""
    env = copy.deepcopy(SCRIPT["factions"])
    env["facts"] = copy.deepcopy(SCRIPT["premise"]["facts"]) + [
        {"key": "f_new", "predicate": "the guild hires sellswords"}
    ]
    env["factions"].append(copy.deepcopy(SCRIPT["politics"]["factions"][0]))  # a repeat
    model = WorldAuthorOut.model_validate(env)
    notes: list[str] = []
    errors = validate_stage(
        STAGE_BY_KEY["factions"],
        model,
        catalog_before("factions"),
        ruleset=RS,
        brief=BR,
        notes=notes,
    )
    assert errors == []
    assert [f.key for f in model.facts] == ["f_new"]
    assert [f.ref for f in model.factions] == ["fac_brine_guild", "fac_lantern_order"]
    assert any("repeated earlier keys" in n for n in notes)
    assert any("fac_salt_council" in n for n in notes)


def test_the_factions_stage_may_refine_an_earlier_power() -> None:
    """Seventh A9 run: every power came from the politics stage; plans came later."""
    env = {
        "factions": [
            {
                "ref": "fac_salt_council",
                "name": "the Salt Council",
                "hidden_goal": "tax the guild into ruin",
                "plan_steps": [{"title": "raise the levy", "at_day": 3}],
            },
            copy.deepcopy(SCRIPT["factions"]["factions"][0]),
        ]
    }
    model = WorldAuthorOut.model_validate(env)
    cat = catalog_before("factions")
    assert check("factions", env) == []
    cat.add("factions", model)
    council = cat.factions["fac_salt_council"]
    assert council.kind == "faction" and council.plan_steps and council.territory_refs
    from app.worldgen.build import combine

    world = combine([WorldAuthorOut.model_validate(SCRIPT["politics"]), model])
    council2 = next(f for f in world.factions if f.ref == "fac_salt_council")
    assert len([f for f in world.factions if f.ref == "fac_salt_council"]) == 1
    assert council2.hidden_goal == "tax the guild into ruin" and council2.territory_refs == [
        "loc_saltreach"
    ]


def test_a_later_stage_may_deepen_an_earlier_place_and_misplaced_items_move() -> None:
    """Ninth A9 run: the region stage named the town, the settlement stage materialized it."""
    env = copy.deepcopy(SCRIPT["starting_settlement"])
    env["locations"].append(
        {
            "ref": "loc_salt_flats",  # latent from the region stage
            "name": "the Salt Flats",
            "detail": "materialized",
            "zones": [{"key": "pans", "exit": True}],
            "features": ["white crusted pans"],
        }
    )
    env["items"] = [
        {"ref": "itm_x", "name": "a rake", "location_ref": "loc_gull_inn", "zone": "cellar"}
    ]
    model = WorldAuthorOut.model_validate(env)
    notes: list[str] = []
    cat = catalog_before("starting_settlement")
    errors = validate_stage(
        STAGE_BY_KEY["starting_settlement"], model, cat, ruleset=RS, brief=BR, notes=notes
    )
    assert errors == []
    assert any("deepened from latent" in n for n in notes)
    assert model.items[0].zone == "door"  # the inn's entry zone
    cat.add("starting_settlement", model)
    flats = cat.locations["loc_salt_flats"]
    assert flats.detail == "materialized" and flats.parent_ref == "loc_saltreach"
    from app.worldgen.build import combine

    world = combine([WorldAuthorOut.model_validate(SCRIPT["starting_region"]), model])
    assert len([x for x in world.locations if x.ref == "loc_salt_flats"]) == 1


def test_a_repeated_outline_place_is_promoted_in_a_deeper_stage() -> None:
    """Eleventh A9 run: the region stage re-listed geography's regions at outline depth."""
    env = copy.deepcopy(SCRIPT["starting_region"])
    env["locations"].append({"ref": "loc_greyfens", "name": "the Greyfens", "detail": "outline"})
    model = WorldAuthorOut.model_validate(env)
    notes: list[str] = []
    errors = validate_stage(
        STAGE_BY_KEY["starting_region"],
        model,
        catalog_before("starting_region"),
        ruleset=RS,
        brief=BR,
        notes=notes,
    )
    assert errors == []
    fens = next(x for x in model.locations if x.ref == "loc_greyfens")
    assert fens.detail == "latent" and any("deepened from outline" in n for n in notes)


def test_dotted_zone_refs_are_split_and_unknown_document_facts_dropped() -> None:
    """Fourteenth A9 run: "loc.zone" refs and documents conveying facts never defined."""
    env = copy.deepcopy(SCRIPT["starting_settlement"])
    env["locations"][1]["adjacency"].append(["loc_gull_inn.bar", "loc_east_well.yard"])
    env["items"] = [
        {
            "ref": "itm_note",
            "name": "a note",
            "template_key": "item.document",
            "location_ref": "loc_gull_inn.bar",
            "document": {"text": "x", "conveys_fact_keys": ["f_never_defined"]},
        }
    ]
    model = WorldAuthorOut.model_validate(env)
    notes: list[str] = []
    errors = validate_stage(
        STAGE_BY_KEY["starting_settlement"],
        model,
        catalog_before("starting_settlement"),
        ruleset=RS,
        brief=BR,
        notes=notes,
    )
    assert errors == []
    it = model.items[0]
    assert (it.location_ref, it.zone) == ("loc_gull_inn", "bar")
    assert it.document.conveys_fact_keys == []
    assert ["loc_gull_inn.bar", "loc_east_well.yard"] not in model.locations[1].adjacency


def test_npc_and_object_ruleset_keys_are_normalized() -> None:
    """Fifteenth A9 run: templates written without their `item.` prefix."""
    env = copy.deepcopy(SCRIPT["npcs"])
    env["actors"][2]["equipment"] = [
        {"name": "ledger", "template_key": "document"},
        {"name": "whatsit", "template_key": "sky_harpoon"},
    ]
    env["actors"][2]["traits"] = ["veteran", "dragon_blood"]
    env["actors"][2]["skills"]["basket_weaving"] = 2
    model = WorldAuthorOut.model_validate(env)
    notes: list[str] = []
    errors = validate_stage(
        STAGE_BY_KEY["npcs"], model, catalog_before("npcs"), ruleset=RS, brief=BR, notes=notes
    )
    assert errors == []
    osk = model.actors[2]
    assert [e.template_key for e in osk.equipment] == ["item.document", "item.travel_supplies"]
    assert osk.traits == ["veteran"] and "basket_weaving" not in osk.skills


def test_latent_people_may_be_revised_before_play_but_imported_ones_may_not() -> None:
    """Sixteenth A9 run: the NPC stage rewrote a latent mystery participant's details."""
    env = copy.deepcopy(SCRIPT["npcs"])
    env["actors"][1]["descriptor"] = "a tired innkeeper with burn scars"  # was "the innkeeper"
    notes: list[str] = []
    model = WorldAuthorOut.model_validate(env)
    assert (
        validate_stage(
            STAGE_BY_KEY["npcs"], model, catalog_before("npcs"), ruleset=RS, brief=BR, notes=notes
        )
        == []
    )
    assert any("latent actor revised" in n and "burn scars" in n for n in notes)
    cat = catalog_before("npcs")
    cat.established_actors.add("npc_wenna")  # as if the user's import had defined her
    errors = validate_stage(
        STAGE_BY_KEY["npcs"], WorldAuthorOut.model_validate(env), cat, ruleset=RS, brief=BR
    )
    assert any("contradicts established canon" in e and "npc_wenna" in e for e in errors)


def test_schedules_recover_facts_from_their_patch_or_are_dropped() -> None:
    """Eighteenth A9 run: fact.establish schedules for facts written only inside the patch."""
    env = copy.deepcopy(SCRIPT["pressures"])
    env["schedules"] += [
        {
            "key": "day7_riot",
            "at_day": 7,
            "type": "fact.establish",
            "fact_key": "f_riot",
            "patch": {"predicate": "the salt workers riot in the square"},
        },
        {"key": "day9_ghost", "at_day": 9, "type": "actor.travel", "actor_ref": "npc_ghost"},
    ]
    model = WorldAuthorOut.model_validate(env)
    notes: list[str] = []
    errors = validate_stage(
        STAGE_BY_KEY["pressures"],
        model,
        catalog_before("pressures"),
        ruleset=RS,
        brief=BR,
        notes=notes,
    )
    assert errors == []
    assert any(f.key == "f_riot" and "riot" in f.predicate for f in model.facts)
    assert [s.key for s in model.schedules] == ["day2_price_spike", "day7_riot"]


def test_an_item_in_a_place_without_zones_is_told_where_it_can_go() -> None:
    """A9 itemized run (09c): an opportunity kept placing its objects at a latent place with no
    zones; the corrective retry was not told where objects can go."""
    cat = catalog_before("opportunities")
    bare = next(r for r, x in cat.locations.items() if not x.zones)
    zoned = [r for r, x in cat.locations.items() if x.zones]
    env = copy.deepcopy(SCRIPT["opportunities"])
    env["items"][0] = {**env["items"][0], "location_ref": bare, "zone": "anywhere"}
    env["items"][0].pop("holder_ref", None)
    errors = check("opportunities", env)
    msg = next(e for e in errors if "has no zones" in e)
    assert zoned[0] in msg and "holder_ref" in msg


def test_untrained_skills_never_go_negative_when_fitting_the_budget() -> None:
    """A9 itemized run (09c): a companion listed eight skills, two at rank 0; trimming the
    lowest first drove crafting to -9."""
    from app.worldgen.envelope import GenActor
    from app.worldgen.validate import fit_pc_budget

    a = GenActor(
        ref="pc_x",
        name="X",
        role="pc_ai",
        skills={
            "athletics": 2,
            "stealth": 3,
            "awareness": 3,
            "investigation": 3,
            "lore": 2,
            "crafting": 0,
            "medicine": 0,
            "persuasion": 1,
        },
    )
    fit_pc_budget(a, RS)
    assert a.skills and all(v > 0 for v in a.skills.values())
    assert "crafting" not in a.skills and "medicine" not in a.skills


def test_one_party_sheet_gets_the_member_rules_on_its_own() -> None:
    """Item scope: secrets and companion goals are checked per sheet (their retry is the
    sheet's own); the composition waits for the whole party."""
    env = copy.deepcopy(SCRIPT["party"])
    tess = next(a for a in env["actors"] if a["role"] == "pc_ai")
    secret = next(f["key"] for f in SCRIPT["secrets"]["facts"])
    tess["knows_fact_keys"] = [secret]
    cat = catalog_before("party")
    errors = validate_stage(
        STAGE_BY_KEY["party"],
        WorldAuthorOut.model_validate({"actors": [tess]}),
        cat,
        ruleset=RS,
        brief=BR,
        scope="item",
        siblings={a["ref"]: "actor" for a in env["actors"] if a["ref"] != tess["ref"]},
    )
    assert any("may not start knowing secret" in e for e in errors)
    assert not any("exactly one player character" in e or "companion(s)" in e for e in errors)
