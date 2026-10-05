"""Outline-then-fill (itemized stages): the outline check and the whole-stage blame."""

from __future__ import annotations

from app.worldgen.brief import CampaignBrief
from app.worldgen.envelope import GenActor, GenMystery, WorldAuthorOut
from app.worldgen.itemized import blame, fill_task, outline_errors, outline_task
from app.worldgen.stages import STAGE_BY_KEY
from app.worldgen.validate import Catalog

BRIEF = CampaignBrief(title="t", party_ai_companions=2)


def test_heavy_stages_are_itemized_and_light_ones_are_not() -> None:
    itemized = {k for k, s in STAGE_BY_KEY.items() if s.itemized}
    assert itemized == {"secrets", "starting_settlement", "npcs", "opportunities", "party"}
    for k in itemized:
        s = STAGE_BY_KEY[k]
        assert s.itemized.fill_sections <= s.sections
        assert s.itemized.primary in s.sections
        assert s.itemized.count[0] <= s.minimum.get(s.itemized.primary, 1)


def test_outline_drops_repeats_trims_and_refuses_foreign_refs() -> None:
    stage = STAGE_BY_KEY["secrets"]
    cat = Catalog()
    cat.kinds["loc_well"] = "location"
    notes: list[str] = []
    items = [GenMystery(ref="mys_a", question="q"), GenMystery(ref="mys_a", question="q2")]
    kept, errors = outline_errors(stage, items, cat, BRIEF, notes)
    assert [x.ref for x in kept] == ["mys_a"] and not errors and notes
    kept, errors = outline_errors(
        stage, [GenMystery(ref=f"mys_{i}", question="q") for i in range(4)], cat, BRIEF, []
    )
    assert len(kept) == 2 and not errors  # trimmed to the range, not rejected
    _, errors = outline_errors(stage, [GenMystery(ref="loc_well", question="q")], cat, BRIEF, [])
    assert any("already exists as a location" in e for e in errors)


def test_npc_outline_may_name_earlier_people() -> None:
    stage = STAGE_BY_KEY["npcs"]
    cat = Catalog()
    cat.kinds["npc_old"] = "actor"
    items = [GenActor(ref=r, name=r) for r in ("npc_old", "npc_b", "npc_c")]
    kept, errors = outline_errors(stage, items, cat, BRIEF, [])
    assert len(kept) == 3 and not errors


def test_party_outline_checks_the_composition_up_front() -> None:
    stage = STAGE_BY_KEY["party"]
    ok = [
        GenActor(ref="pc_a", name="A", role="pc_human"),
        GenActor(ref="pc_b", name="B", role="pc_ai"),
        GenActor(ref="pc_c", name="C", role="pc_ai"),
    ]
    assert outline_errors(stage, ok, Catalog(), BRIEF, [])[1] == []
    _, errors = outline_errors(stage, ok[:2], Catalog(), BRIEF, [])
    assert any("2 companion(s)" in e for e in errors)


def test_task_markers_name_the_call() -> None:
    stage = STAGE_BY_KEY["npcs"]
    items = [GenActor(ref="npc_a", name="A"), GenActor(ref="npc_b", name="B", occupation="smith")]
    assert outline_task(stage)[0].startswith("STAGE npcs — OUTLINE")
    task = "\n".join(fill_task(stage, items[0], items, "guide"))
    assert task.startswith("STAGE npcs — ITEM npc_a")
    assert "npc_b — B (smith)" in task  # siblings are named so the item can refer to them


def test_blame_sends_back_named_items_and_spreads_shortfalls() -> None:
    order = ["opp_a", "opp_b"]
    filled = {"opp_a": WorldAuthorOut(clues=[]).model_dump(), "opp_b": {"clues": [{"ref": "c"}]}}
    out = blame(["opportunity opp_b has one route"], order, filled, "opportunities")
    assert list(out) == ["opp_b"]
    out = blame(["stage opportunities needs at least 2 clues"], order, filled, "opportunities")
    assert list(out) == ["opp_a"] and "add clues for this item" in out["opp_a"][0]
    # a shortfall of the items themselves can only be fixed by a new outline
    assert blame(["stage npcs needs at least 3 actors"], ["npc_a"], {}, "actors") == {}


def test_the_canon_shown_to_a_call_is_filtered_but_every_ref_stays() -> None:
    from app.worldgen.envelope import GenFact

    cat = Catalog()
    cat.add("premise", WorldAuthorOut(facts=[GenFact(key="f_premise", predicate="p")]))
    cat.add("history", WorldAuthorOut(facts=[GenFact(key="f_old_war", predicate="a war")]))
    cat.add(
        "npcs",
        WorldAuthorOut(
            actors=[GenActor(ref="npc_a", name="A")],
            facts=[GenFact(key="f_a", predicate="owes", subject_ref="npc_a")],
        ),
    )
    text = "\n".join(cat.relevant_lines({"opening"}))
    assert "npc_a (A)" in text  # refs always resolve
    assert "f_premise" in text and "f_old_war" not in text and "f_a" not in text
    assert "2 further facts" in text
    focused = "\n".join(cat.relevant_lines({"opening"}, {"npc_a"}))
    assert "f_a" in focused and "f_old_war" not in focused  # facts about the focus are shown
