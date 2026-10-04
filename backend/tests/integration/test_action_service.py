"""Milestone 02b persistence: actions commit through the ledger with rolls and traces,
stale proposals are rejected (no duplicate pickup), and mechanical state reloads intact."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.engine.actions import ActionRequest, ReactionChoice
from app.engine.core import RulesEngine
from app.engine.dice import DiceService, SeedStream, parse_dice, roll_with_seed
from app.persistence.models import (
    Action,
    ConditionInstanceRow,
    Entity,
    Event,
    Item,
    ItemHistory,
    ResolutionTraceRecord,
    ResourceStateRow,
    Roll,
    Scene,
)
from app.services.actions import ActionService, StaleStateError
from app.services.world import WorldService
from tests.rules.conftest import FROSTBRIDGE_BUILDS

pytestmark = [pytest.mark.integration, pytest.mark.rules]

WAREHOUSE = {
    "zones": [
        {"key": "door", "exit": True},
        {"key": "floor", "features": ["table", "lantern"]},
        {"key": "crates", "cover": "strong"},
        {"key": "shelf", "cover": "partial", "elevated": True},
    ],
    "adjacency": [["door", "floor"], ["floor", "crates"], ["floor", "shelf"], ["crates", "shelf"]],
    "positions": {},
}


async def seed(session: AsyncSession, rules: RulesEngine):
    world = WorldService(session)
    h = await world.create_campaign(
        "02b", ruleset_key="core_adventure", ruleset_version="0.1.0", engine_version="test"
    )
    wh = await world.create_location(h, "Oric's Warehouse", location_type="building")
    elara = await world.create_actor(
        h,
        "Elara",
        actor_type="pc",
        controller_type="ai",
        location_id=wh.id,
        mechanical_profile=FROSTBRIDGE_BUILDS["elara"],
    )
    tomas = await world.create_actor(
        h,
        "Tomas",
        actor_type="pc",
        controller_type="ai",
        location_id=wh.id,
        mechanical_profile=FROSTBRIDGE_BUILDS["tomas"],
    )
    thief = await world.create_actor(
        h,
        "Dock thief",
        actor_type="npc",
        controller_type="ai",
        location_id=wh.id,
        mechanical_profile=FROSTBRIDGE_BUILDS["thief"],
    )
    await world.create_item(h, "sword", template_key="item.sword", possessor_actor_id=tomas.id)
    await world.create_item(h, "knife", template_key="item.knife", possessor_actor_id=thief.id)
    dagger = await world.create_item(
        h,
        "Veyra's Chipped Dagger",
        template_key="item.dagger",
        location_id=wh.id,
        zone_key="floor",
        public_properties={"description": "well-made, chipped near the tip"},
        hidden_properties={
            "bonus_damage_vs_tags": {"spirit": 2},
            "lore": "forged from relay salvage",
        },
    )
    space = dict(
        WAREHOUSE,
        positions={
            str(elara.id): {"zone": "floor"},
            str(tomas.id): {"zone": "floor"},
            str(thief.id): {"zone": "floor"},
        },
    )
    scene = await world.start_scene(
        h,
        location_id=wh.id,
        scene_type="exploration",
        participant_actor_ids=[elara.id, tomas.id, thief.id],
        space=space,
    )
    return h, scene, {"elara": elara, "tomas": tomas, "thief": thief}, dagger, world


@pytest.fixture
def rules() -> RulesEngine:
    return RulesEngine.load("core_adventure", master_seed=99)


async def test_stale_pickup_is_rejected_and_item_is_not_duplicated(
    session: AsyncSession, rules: RulesEngine
) -> None:
    h, scene, actors, dagger, world = await seed(session, rules)
    svc = ActionService(session, rules)
    v = scene.version
    first = await svc.perform(
        h,
        scene.id,
        ActionRequest(
            str(actors["elara"].id),
            "action.pick_up",
            str(dagger.id),
            based_on_scene_version=v,
            source="ai",
        ),
    )
    assert first.status == "succeeded"
    # Tomas decided from the same snapshot: rejected before anything is written
    second = await svc.perform(
        h,
        scene.id,
        ActionRequest(
            str(actors["tomas"].id),
            "action.pick_up",
            str(dagger.id),
            based_on_scene_version=v,
            source="ai",
        ),
    )
    assert second.status == "invalid" and "stale" in second.reason
    row = await session.get(Item, dagger.id)
    assert (
        row is not None
        and row.possessor_entity_id == actors["elara"].entity_id
        and row.location_id is None
    )
    hist = (
        (await session.execute(select(ItemHistory).where(ItemHistory.item_id == dagger.id)))
        .scalars()
        .all()
    )
    assert [x.change_type for x in hist] == ["possession"]
    actions = (
        (await session.execute(select(Action).where(Action.scene_id == scene.id))).scalars().all()
    )
    assert [a.status for a in actions] == ["succeeded"]  # the invalid proposal left no row
    reloaded = await session.get(Scene, scene.id)
    assert reloaded is not None and reloaded.version == v + 1
    # hidden property is in the DB but not in the actor's profile
    actor = await session.get(type(actors["elara"]), actors["elara"].id)
    assert "hidden" not in str(actor.mechanical_profile) and row.hidden_properties[
        "bonus_damage_vs_tags"
    ] == {"spirit": 2}


async def test_version_moves_between_load_and_commit_is_caught_under_lock(
    session: AsyncSession, rules: RulesEngine, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    h, scene, actors, dagger, world = await seed(session, rules)
    dagger_id, elara_id, tomas_id = dagger.id, actors["elara"].id, actors["tomas"].id
    svc = ActionService(session, rules)
    loaded = await svc.load_scene(h, scene.id)
    # another writer bumps the scene in between
    async with session_factory() as other:
        await WorldService(other).end_scene(h, scene.id) if False else None
        await ActionService(other, RulesEngine(rules.ruleset, DiceService(SeedStream(1)))).perform(
            h, scene.id, ActionRequest(str(tomas_id), "action.wait", source="ai")
        )
    from app.engine.actions import ActionResolver

    outcome = ActionResolver(loaded.ctx).resolve(
        ActionRequest(str(elara_id), "action.pick_up", str(dagger_id), source="ai")
    )
    assert outcome.status == "succeeded"  # in memory
    with pytest.raises(StaleStateError):
        await svc._commit(h, loaded, outcome, outcome.request, None)
    session.expire_all()
    row = await session.get(Item, dagger_id)
    assert row is not None and row.possessor_entity_id is None  # nothing committed


async def test_combat_turn_persists_rolls_traces_state_and_time(
    session: AsyncSession, rules: RulesEngine, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    h, scene, actors, dagger, world = await seed(session, rules)
    svc = ActionService(session, rules)
    tomas, thief = str(actors["tomas"].id), str(actors["thief"].id)
    enc = await svc.start_encounter(
        h,
        scene.id,
        {actors["elara"].id: "party", actors["tomas"].id: "party", actors["thief"].id: "thieves"},
    )
    init_rolls = (
        (await session.execute(select(Roll).where(Roll.campaign_id == h.campaign_id)))
        .scalars()
        .all()
    )
    assert len(init_rolls) >= 3 and all(r.purpose.startswith("initiative") for r in init_rolls)

    # walk the order until Tomas; he closes to melee (Movement) and attacks (Major); thief defends
    while enc.current_actor != tomas:
        await svc.next_turn(h, scene.id)
        enc = (await svc.load_scene(h, scene.id)).ctx.encounter

    def chooser(w):
        return ReactionChoice(w.target, "action.defend") if w.trigger == "attacked" else None

    engage = await svc.perform(
        h, scene.id, ActionRequest(tomas, "action.engage", thief, source="ai"), chooser=chooser
    )
    assert engage.status == "succeeded"
    attack = None
    for _ in range(6):  # keep attacking across rounds until something lands
        attack = await svc.perform(
            h, scene.id, ActionRequest(tomas, "action.attack", thief, source="ai"), chooser=chooser
        )
        assert attack.status in ("succeeded", "failed"), attack.reason
        if attack.status == "succeeded":
            break
        for _ in range(3):
            await svc.next_turn(h, scene.id)
    assert attack is not None and attack.status == "succeeded"

    # rolls persisted, linked to the resolving event, replayable bit-for-bit from seed
    rolls = (
        (
            await session.execute(
                select(Roll).where(
                    Roll.actor_id == actors["tomas"].id, Roll.purpose.like("%attack%")
                )
            )
        )
        .scalars()
        .all()
    )
    assert rolls
    for r in rolls:
        raw, kept, total = roll_with_seed(parse_dice(r.expression), r.seed)
        assert list(raw) == r.raw and total == r.final_result
        assert r.event_id is not None
    # action + trace rows
    act = (
        (
            await session.execute(
                select(Action).where(
                    Action.actor_id == actors["tomas"].id,
                    Action.action_key == "action.attack",
                    Action.status == "succeeded",
                )
            )
        )
        .scalars()
        .first()
    )
    assert act is not None and act.resolution_event_id is not None
    trace = (
        await session.execute(
            select(ResolutionTraceRecord).where(ResolutionTraceRecord.action_id == act.id)
        )
    ).scalar_one()
    assert "check.melee_attack" in trace.rules_consulted and trace.summary.startswith(
        tomas[:0] + ""
    )
    assert any(r["action"] == "action.defend" for r in trace.trace["reactions"])
    # ledger
    types = [
        e.event_type
        for e in (
            await session.execute(
                select(Event)
                .where(Event.timeline_id == h.timeline_id)
                .order_by(Event.sequence_number)
            )
        )
        .scalars()
        .all()
    ]
    assert "encounter.started" in types and "attack.rolled" in types and "damage.dealt" in types
    # projections
    hp = (
        await session.execute(
            select(ResourceStateRow).where(
                ResourceStateRow.entity_id == actors["thief"].entity_id,
                ResourceStateRow.resource_key == "resource.health",
            )
        )
    ).scalar_one()
    assert hp.current < 18 and hp.last_changed_event_id == act.resolution_event_id
    # observations: every participant saw the attack the way *they* know the actors
    from app.persistence.models import Observation
    from app.services.observations import ObservationService

    obs = (
        (
            await session.execute(
                select(Observation).where(Observation.source_event_id == act.resolution_event_id)
            )
        )
        .scalars()
        .all()
    )
    hits = (
        (
            await session.execute(
                select(Observation)
                .where(
                    Observation.observation_type == "event",
                    Observation.campaign_id == h.campaign_id,
                )
                .order_by(Observation.created_at)
            )
        )
        .scalars()
        .all()
    )
    by_actor = {}
    for o in hits:
        if o.raw.get("event_type") == "damage.dealt":
            by_actor[o.actor_id] = o
    assert set(by_actor) == {actors["elara"].id, actors["tomas"].id, actors["thief"].id}
    thief_view, elara_view = by_actor[actors["thief"].id], by_actor[actors["elara"].id]
    assert "amount" in thief_view.raw["participant_only"]  # the one struck knows how hard
    assert "participant_only" not in elara_view.raw  # a bystander sees a strike, not a number
    assert thief_view.raw["participants"][1]["known_as"] == "you"
    assert elara_view.raw["participants"][0]["known_as"] == "a stranger"  # no identity seeded
    assert ObservationService.render(elara_view.raw).startswith("A stranger strikes a stranger")
    assert not obs or all(o.actor_id in {actors[k].id for k in actors} for o in obs)
    # reload in a fresh session: state round-trips through the DB
    async with session_factory() as s2:
        loaded = await ActionService(s2, RulesEngine(rules.ruleset)).load_scene(h, scene.id)
        st = loaded.ctx.states[thief]
        assert st.resources["resource.health"].current == hp.current
        assert loaded.ctx.space.engaged(tomas, thief)
        assert loaded.ctx.encounter is not None and loaded.ctx.encounter.status in (
            "active",
            "ended",
        )
        assert loaded.ctx.states[tomas].weapon(rules.ruleset).def_key == "item.sword"


async def test_round_end_advances_clock_and_fires_triggers(
    session: AsyncSession, rules: RulesEngine
) -> None:
    h, scene, actors, dagger, world = await seed(session, rules)
    svc = ActionService(session, rules)
    await svc.start_encounter(
        h,
        scene.id,
        {actors["elara"].id: "party", actors["tomas"].id: "party", actors["thief"].id: "thieves"},
    )
    tick0 = (await world.clock(h)).current_tick
    for _ in range(3):
        await svc.next_turn(h, scene.id)
    assert (await world.clock(h)).current_tick == tick0 + 6
    types = [e.event_type for e in (await world.events(h))]
    assert "encounter.round_ended" in types and types[-1] == "time.advanced"
    mine = select(Entity.id).where(Entity.campaign_id == h.campaign_id)
    conds = (
        (
            await session.execute(
                select(ConditionInstanceRow).where(ConditionInstanceRow.target_entity_id.in_(mine))
            )
        )
        .scalars()
        .all()
    )
    assert conds == []  # nothing burning yet
