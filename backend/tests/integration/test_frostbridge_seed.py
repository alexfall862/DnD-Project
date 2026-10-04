"""Milestone 07: the full Frostbridge seed builds, verifies (frostbridge §40) and matches the
initial leakage matrix (§42) before any play happens."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import Belief, Campaign, Fact, Item, Scene
from app.seeds.frostbridge import SeedError, seed_frostbridge, validate_artifact
from app.services.mystery import MysteryLockedError, MysteryService
from app.services.perspective import PerspectiveService
from app.services.schedule import ScheduleService

pytestmark = [pytest.mark.integration, pytest.mark.leakage]

MATRIX = {
    # fact key: actors allowed to hold a belief linked to it at seed time (§42)
    "oric_dead": {"Renn"},
    "renn_met_oric": {"Mira", "Renn"},
    "renn_killed_oric": {"Renn"},
    "renn_smuggling": {"Renn"},
    "ledger_shows_discrepancies": set(),
    "renn_altered_log": {"Renn"},
    "guard_log_gap": set(),
    "dagger_harms_spirits": set(),
}


async def test_seed_builds_verifies_and_matches_the_leakage_matrix(
    session: AsyncSession,
) -> None:
    w = await seed_frostbridge(session, name="seed-test", engine_version="test")
    await session.commit()
    s = w.summary()
    assert set(s["actors"]) >= {"Alex", "Elara", "Tomas", "Mira", "Renn", "Oric"}
    assert len(w.locations) == 10 and w.mystery and w.party and w.plan
    # objective truth vs. perspective: belief rows linked to secret facts stay with the knowers
    for key, allowed in MATRIX.items():
        holders = {
            b.actor_id
            for b in (
                await session.execute(select(Belief).where(Belief.fact_id == w.facts[key]))
            ).scalars()
        }
        assert holders == {w.actors[n] for n in allowed}, key
    psv = PerspectiveService(session)
    for n in ("Alex", "Elara", "Tomas", "Mira"):
        ctx = str(await psv.context_candidates(w.actors[n]))
        assert "killed" not in ctx and "spirit" not in ctx and "removed a page" not in ctx, n
    # the mystery is locked and redundant; the dagger's property is objective but hidden
    myst = MysteryService(session)
    with pytest.raises(MysteryLockedError):
        await myst.replace_truth(w.h, w.mystery, [w.facts["oric_owed_mira"]])
    rr = await myst.routes_remaining(w.mystery)
    assert rr.solvable and rr.intact_by_fact[w.facts["guard_log_gap"]] == 2
    dagger = await session.get(Item, w.items["dagger"])
    assert dagger.concealed and dagger.hidden_properties["bonus_damage_vs_tags"] == {"spirit": 2}
    assert await psv.inventory(w.actors["Alex"])  # gear, no dagger yet
    assert all(i.item_id != w.items["dagger"] for i in await psv.inventory(w.actors["Alex"]))
    # clocks: four pending scheduled events (Day +2 ×2, Day +3 ×2, Day +5, Day +8)
    pending = await ScheduleService(session).pending(w.h)
    assert {p.payload["key"] for p in pending} == {
        "day2_caravan",
        "day2_market",
        "day3_log_draft",
        "day3_plan",
        "day5_renn_to_dock",
        "day5_shipment",
        "day8_quarry",
    }
    # opening scene at the gate; Mira and Renn wait offscreen in the tavern
    scenes = (
        (
            await session.execute(
                select(Scene).where(Scene.campaign_id == w.h.campaign_id, Scene.status == "active")
            )
        )
        .scalars()
        .all()
    )
    assert {s.location_id for s in scenes} == {w.locations["town_gate"], w.locations["red_lantern"]}
    gate = next(s for s in scenes if s.location_id == w.locations["town_gate"])
    assert gate.id == w.scene and gate.state["weather"] == "cold rain"
    # the party does not yet know Oric, Mira or Renn by name
    names = set((await psv.known_entities(w.actors["Alex"])).values())
    assert "Oric Dane" not in names and "Captain Renn" not in names and "Mira" not in names
    assert "Red Lantern Tavern" in names and "Guard House" in names
    caravan = await session.get(Fact, w.facts["caravan_arrival"])
    assert caravan.canon_status == "latent"


async def test_seed_failure_leaves_no_campaign_behind(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.seeds.frostbridge as mod

    async def broken(session_, w):
        raise SeedError("forced")

    monkeypatch.setattr(mod, "verify", broken)
    before = len((await session.execute(select(Campaign))).scalars().all())
    with pytest.raises(SeedError):
        await seed_frostbridge(session, name="seed-broken", engine_version="test")
    after = len((await session.execute(select(Campaign))).scalars().all())
    assert after == before


def test_fixed_artifact_respects_the_constraints() -> None:
    validate_artifact(
        {
            "key": "x",
            "tier": "low",
            "passive": {"type": "modify_check", "params": {}},
            "activated": {"type": "apply_condition", "params": {"condition": "condition.hidden"}},
        }
    )
    with pytest.raises(SeedError):
        validate_artifact({"key": "x", "tier": "low", "passive": {"type": "teleport"}})
    with pytest.raises(SeedError):
        validate_artifact(
            {"key": "x", "tier": "low", "passive": {"type": "modify_attribute", "params": {}}}
        )
    with pytest.raises(SeedError):
        validate_artifact({"key": "x", "tier": "epic", "passive": {"type": "modify_check"}})


async def test_the_artifact_slot_uses_the_world_author_and_falls_back_safely(
    session: AsyncSession,
) -> None:
    from app.ai.providers import FakeModelProvider
    from app.persistence.models import MechanicalDefinition

    good = {
        "mechanics": [
            {
                "key": "anything",
                "name": "Rimewatch Compass",
                "tier": "low",
                "description": "A compass whose needle frosts over when danger is near.",
                "passive": {
                    "type": "modify_check",
                    "params": {"check": "check.*", "op": "add", "amount": 1, "when": "danger"},
                },
            }
        ]
    }
    fake = (
        FakeModelProvider()
        .register("world_author", {"mechanics": []})
        .register("world_author", good)
    )
    w = await seed_frostbridge(
        session, name="seed-artifact", engine_version="test", artifact_provider=fake
    )
    await session.commit()
    assert w.artifact_source == "world_author" and len(fake.calls) == 2  # one corrective retry
    row = (
        await session.execute(
            select(MechanicalDefinition).where(MechanicalDefinition.campaign_id == w.h.campaign_id)
        )
    ).scalar_one()
    assert row.source_kind == "world_author" and row.definition["name"] == "Rimewatch Compass"
    assert row.definition_key == "item.frostglass_shard"  # the slot keeps its key
    item = await session.get(Item, w.items["artifact"])
    assert item.public_properties["description"].startswith("A compass")
    # a model that keeps proposing a forbidden effect gets the fixed artifact instead
    bad = {
        "mechanics": [{"key": "x", "name": "Gate", "tier": "low", "passive": {"type": "teleport"}}]
    }
    fake2 = FakeModelProvider().register("world_author", bad)
    w2 = await seed_frostbridge(
        session, name="seed-artifact-bad", engine_version="test", artifact_provider=fake2
    )
    assert w2.artifact_source == "fixture" and w2.artifact_errors
    assert (
        (await session.get(Item, w2.items["artifact"]))
        .public_properties["description"]
        .startswith("A thumb-sized shard")
    )
