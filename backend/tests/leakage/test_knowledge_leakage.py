"""knowledge-leakage.md §2–§8, §12, §14, §16, §19 and the Milestone 03 whisper gate."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.beliefs import Proposition
from app.persistence.models import Belief, Claim, Event, Observation
from app.services.perspective import PerspectiveService, UnauthorizedPerspective
from app.services.speech import ConveysItem, LeakageError, SpeechService
from tests.fixtures.frostbridge import World

pytestmark = [pytest.mark.integration, pytest.mark.leakage]

WHISPER = "I think Mira had something to do with Oric's disappearance."


def mira_involved(w: World) -> dict:
    return {
        "subject_entity_id": str(w.entities["Mira"]),
        "predicate": "involved in the disappearance of",
        "object_entity_id": str(w.entities["Oric"]),
    }


async def whisper(session: AsyncSession, w: World):
    return await SpeechService(session).utter(
        w.h,
        w.scene,
        w.actors["Alex"],
        WHISPER,
        channel="whisper",
        target_actor_ids=[w.actors["Elara"]],
        conveys=[ConveysItem("proposition", proposition=mira_involved(w), stance="uncertain")],
        conveyance_source="fixture",
    )


# --- §2 private whisper + the Milestone 03 gate ------------------------------------------------


async def test_whisper_gate(session: AsyncSession, frostbridge: World) -> None:
    w = frostbridge
    result = await whisper(session, w)
    assert result.recipients == [w.actors["Elara"]]
    alex, elara, tomas, mira = (w.actors[n] for n in ("Alex", "Elara", "Tomas", "Mira"))

    obs = {
        o.actor_id: o
        for o in (
            await session.execute(
                select(Observation).where(Observation.source_event_id == result.event.id)
            )
        )
        .scalars()
        .all()
    }
    assert obs[alex].observation_type == "spoke" and obs[elara].observation_type == "heard_claim"
    assert tomas not in obs and mira not in obs

    psv = PerspectiveService(session)
    # exact belief rows (communication-and-knowledge §8, belief-update-rules §4)
    eb = {(b.proposition["predicate"], b.belief_type): b for b in await psv.beliefs(elara)}
    assert eb[("asserted", "known")].confidence == 1.0
    involved = eb[("involved in the disappearance of", "suspected")]
    assert involved.confidence == pytest.approx(
        0.585
    )  # 0.35 + trust 60*0.0035 + familiarity 50*0.0005, cap 0.60
    assert involved.source_known_as == "Alex" and involved.source_type == "told"
    ab = {b.proposition["predicate"]: b for b in await psv.beliefs(alex)}
    assert (
        ab["involved in the disappearance of"].belief_type == "stated"
        and ab["involved in the disappearance of"].confidence == 0.55
    )
    # Tomas: nothing, by every path
    assert all(
        b.proposition["predicate"] != "involved in the disappearance of"
        for b in await psv.beliefs(tomas)
    )
    assert await psv.heard_claims(tomas) == []
    ctx = await psv.context_candidates(tomas)
    assert "involved" not in str(ctx) and "Mira had something" not in str(ctx)
    assert all(
        b.proposition["predicate"] != "involved in the disappearance of"
        for b in await psv.beliefs(mira)
    )
    # objective truth unchanged: no Fact was created by speech
    from app.persistence.repositories.objective import ObjectiveWorldRepository

    facts = await ObjectiveWorldRepository(session).facts(w.h.campaign_id)
    assert not any(f.predicate.startswith("involved") for f in facts)
    claims = (
        (await session.execute(select(Claim).where(Claim.statement_event_id == result.event.id)))
        .scalars()
        .all()
    )
    assert (
        len(claims) == 1
        and claims[0].speaker_stance == "uncertain"
        and claims[0].deliberate_false is False
    )
    # the ledger payload carries no text
    ev = await session.get(Event, result.event.id)
    assert "Mira had" not in str(ev.payload)


async def test_party_membership_does_not_synchronize_even_after_moving_together(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    await whisper(session, w)
    # Tomas leaves for the Guard House and comes back: still nothing
    await w.world.move_actor(w.h, w.actors["Tomas"], w.guard_house, require_edge=True)
    await w.world.move_actor(w.h, w.actors["Tomas"], w.tavern, require_edge=True)
    psv = PerspectiveService(session)
    assert all(
        b.proposition["predicate"] != "involved in the disappearance of"
        for b in await psv.beliefs(w.actors["Tomas"])
    )


# --- §3/§8 say, hearing, language ---------------------------------------------------------------


async def test_say_reaches_hearing_actors_and_partial_fidelity_keeps_the_rest_hidden(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    svc = SpeechService(session)
    r = await svc.utter(
        w.h,
        w.scene,
        w.actors["Mira"],
        "He was here that night. They argued.",
        channel="say",
        conveys=[
            ConveysItem(
                "fact_ref",
                ref_id=str(w.facts["renn_met_oric"]),
                stance="asserts_true",
                fidelity="partial",
            )
        ],
        conveyance_source="fixture",
    )
    assert set(r.recipients) == {w.actors[n] for n in ("Alex", "Elara", "Tomas", "Renn")}
    psv = PerspectiveService(session)
    tb = [
        b
        for b in await psv.beliefs(w.actors["Tomas"])
        if b.proposition["predicate"].startswith("met privately")
    ]
    assert (
        tb and tb[0].belief_type == "suspected" and tb[0].confidence == pytest.approx(0.35)
    )  # stranger
    # partial fidelity: belief is not linked to the fact row
    row = (
        (
            await session.execute(
                select(Belief).where(
                    Belief.actor_id == w.actors["Tomas"],
                    Belief.proposition_key.like("%met privately%"),
                )
            )
        )
        .scalars()
        .first()
    )
    assert row is not None and row.fact_id is None and row.claim_id is not None


async def test_unknown_language_yields_no_claim(session: AsyncSession, frostbridge: World) -> None:
    w = frostbridge
    # Elara reads the old tongue; Alex does not
    from app.persistence.models import Actor

    elara = await session.get(Actor, w.actors["Elara"])
    elara.mechanical_profile = {**elara.mechanical_profile, "languages": ["common", "old_imperial"]}
    await session.flush()
    r = await SpeechService(session).utter(
        w.h,
        w.scene,
        w.actors["Renn"],
        "(in Old Imperial) I met him.",
        channel="say",
        language="old_imperial",
        conveys=[
            ConveysItem("fact_ref", ref_id=str(w.facts["renn_met_oric"]), stance="asserts_true")
        ],
        conveyance_source="fixture",
    )
    assert (
        w.actors["Alex"] in r.unknown_language_for
        and w.actors["Elara"] not in r.unknown_language_for
    )
    psv = PerspectiveService(session)
    alex_obs = await psv.recent_observations(w.actors["Alex"])
    assert (
        alex_obs[-1]["type"] == "speech_in_unknown_language"
        and "do not understand" in alex_obs[-1]["rendered"]
    )
    assert not any(
        b.proposition["predicate"].startswith("met privately")
        for b in await psv.beliefs(w.actors["Alex"])
    )
    assert any(
        b.proposition["predicate"].startswith("met privately")
        for b in await psv.beliefs(w.actors["Elara"])
    )


# --- §14 overheard whisper is a capability, not a hard-coded recipient list -------------------


async def test_whisper_can_be_overheard_only_with_a_capability_and_proximity(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    from app.persistence.models import Actor

    tomas = await session.get(Actor, w.actors["Tomas"])
    tomas.mechanical_profile = {**tomas.mechanical_profile, "capabilities": ["hear:whispers"]}
    mira = await session.get(Actor, w.actors["Mira"])
    mira.mechanical_profile = {
        **mira.mechanical_profile,
        "capabilities": ["hear:whispers"],
    }  # but at the bar: too far
    await session.flush()
    r = await whisper(session, w)
    assert set(r.recipients) == {w.actors["Elara"], w.actors["Tomas"]}
    assert w.actors["Mira"] not in r.recipients


# --- §19 conveys authorization ----------------------------------------------------------------


async def test_ai_output_referencing_a_fact_outside_its_perspective_is_rejected(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    svc = SpeechService(session)
    before = (await session.execute(select(Claim))).scalars().all()
    with pytest.raises(LeakageError):
        await svc.utter(
            w.h,
            w.scene,
            w.actors["Elara"],
            "Renn killed Oric, I'm sure of it.",
            channel="say",
            conveys=[
                ConveysItem(
                    "fact_ref", ref_id=str(w.facts["renn_killed_oric"]), stance="asserts_true"
                )
            ],
            conveyance_source="structured",
        )
    session.expire_all()
    assert len((await session.execute(select(Claim))).scalars().all()) == len(before)
    assert (
        not (
            await session.execute(
                select(Observation).where(
                    Observation.actor_id == w.actors["Tomas"],
                    Observation.observation_type == "heard_claim",
                )
            )
        )
        .scalars()
        .all()
    )
    rejected = (
        (
            await session.execute(
                select(Event).where(Event.event_type == "proposal.rejected_leakage")
            )
        )
        .scalars()
        .all()
    )
    assert rejected and rejected[-1].payload["ref_id"] == str(w.facts["renn_killed_oric"])
    # a belief_ref to someone else's belief is just as illegal
    tomas_belief = (
        (await session.execute(select(Belief).where(Belief.actor_id == w.actors["Tomas"])))
        .scalars()
        .first()
    )
    with pytest.raises(LeakageError):
        await svc.utter(
            w.h,
            w.scene,
            w.actors["Elara"],
            "...",
            channel="say",
            conveys=[ConveysItem("belief_ref", ref_id=str(tomas_belief.id))],
            conveyance_source="structured",
        )
    # Renn may reference what he knows — and lie about it
    r = await svc.utter(
        w.h,
        w.scene,
        w.actors["Renn"],
        "Weeks ago.",
        channel="say",
        conveys=[
            ConveysItem(
                "fact_ref",
                ref_id=str(w.facts["renn_met_oric"]),
                stance="asserts_false",
                deliberate_false=True,
            )
        ],
        conveyance_source="structured",
    )
    claim = r.claims[0]
    assert claim.deliberate_false is True
    psv = PerspectiveService(session)
    heard = [c for c in await psv.heard_claims(w.actors["Tomas"]) if c.claim_id == claim.id]
    assert heard and not hasattr(heard[0], "deliberate_false")
    tb = [
        b
        for b in await psv.beliefs(w.actors["Tomas"])
        if b.proposition["predicate"].startswith("not met privately")
    ]
    assert tb and tb[0].belief_type == "suspected"  # Renn is a stranger to Tomas: 0.35
    # Renn himself keeps his knowledge (the lie created no belief for him)
    rb = [
        b
        for b in await psv.beliefs(w.actors["Renn"])
        if "met privately" in b.proposition["predicate"]
    ]
    assert len(rb) == 1 and rb[0].belief_type == "known"


# --- §4 mystery truth, §12 belief vs fact ---------------------------------------------------


async def test_mystery_truth_is_in_no_perspective_but_the_killers(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    psv = PerspectiveService(session)
    for n in ("Alex", "Elara", "Tomas", "Mira"):
        ctx = await psv.context_candidates(w.actors[n])
        assert "killed" not in str(ctx), n
        assert await psv.entity_view(
            w.actors[n], w.entities["Renn"]
        ) is None or "killed" not in str(await psv.entity_view(w.actors[n], w.entities["Renn"]))
    renn = await psv.beliefs(w.actors["Renn"])
    assert any(b.proposition["predicate"] == "killed" and b.belief_type == "known" for b in renn)
    # Alex can hold a false belief that contradicts truth; the fact is untouched
    await w.knowledge.seed_belief(
        w.h,
        w.actors["Alex"],
        Proposition("killed", subject=str(w.entities["Mira"]), object=str(w.entities["Oric"])),
        "suspected",
        0.55,
    )
    ab = [b for b in await psv.beliefs(w.actors["Alex"]) if b.proposition["predicate"] == "killed"]
    assert ab[0].proposition["subject_entity_id"] == str(w.entities["Mira"])
    from app.persistence.repositories.objective import ObjectiveWorldRepository

    fact = await ObjectiveWorldRepository(session).fact_by_key(w.h.campaign_id, "renn_killed_oric")
    assert fact.subject_entity_id == w.entities["Renn"] and fact.truth_status == "true"


# --- §6 secret identity, §5 hidden item property, §7 hidden actor, §16 UUID probing ----------


async def test_secret_identity_is_perspective_specific(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    psv = PerspectiveService(session)
    assert await psv.repo.resolve_name(w.actors["Alex"], "Lady Veyra") == []
    assert await psv.repo.resolve_name(w.actors["Alex"], "the Masked Woman") == [w.veyra_entity]
    assert await psv.repo.resolve_name(w.actors["Elara"], "Lady Veyra") == [w.veyra_entity]
    assert (await psv.known_entities(w.actors["Alex"]))[w.veyra_entity] == "the Masked Woman"
    assert await psv.entity_view(w.actors["Tomas"], w.veyra_entity) is None


async def test_hidden_item_property_is_absent_from_inventory_but_present_objectively(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    psv = PerspectiveService(session)
    items = await psv.inventory(w.actors["Alex"])
    dagger = next(i for i in items if i.item_id == w.dagger)
    assert "bonus_damage_vs_tags" not in str(dagger) and "lore" not in str(dagger)
    assert dagger.public_properties == {"description": "well-made, chipped near the tip"}
    assert "spirit" not in str(await psv.context_candidates(w.actors["Alex"]))
    from app.persistence.repositories.objective import ObjectiveWorldRepository

    row = await ObjectiveWorldRepository(session).item(w.dagger)
    assert row.hidden_properties["bonus_damage_vs_tags"] == {"spirit": 2}


async def test_hidden_actor_is_absent_from_the_scene_view(
    session: AsyncSession, frostbridge: World
) -> None:
    w = frostbridge
    from app.engine.core import RulesEngine
    from app.persistence.models import ConditionInstanceRow

    session.add(
        ConditionInstanceRow(
            target_entity_id=w.entities["Renn"],
            condition_key="condition.hidden",
            instance_key="hid1",
            intensity=1,
            status="active",
        )
    )
    await session.flush()
    psv = PerspectiveService(session)
    view = await psv.scene_view(w.actors["Alex"])
    names = [p.known_as for p in view.participants]
    assert "a man you have not met" not in names and w.entities["Renn"] not in [
        p.entity_id for p in view.participants
    ]
    assert {p.known_as for p in view.participants} == {"you", "Elara", "Tomas", "Mira"}
    renn_view = await psv.scene_view(w.actors["Renn"])
    assert any(p.is_self for p in renn_view.participants)  # he still sees himself
    _ = RulesEngine


async def test_normal_api_refuses_non_focus_actors_and_leaks_nothing_by_id(
    session: AsyncSession, frostbridge: World, client
) -> None:
    w = frostbridge
    await session.commit()
    cid = w.h.campaign_id
    # Tomas is AI-controlled: his perspective is not the human's to read
    r = await client.get(
        f"/api/v1/campaigns/{cid}/scene", params={"actor_id": str(w.actors["Tomas"])}
    )
    assert (
        r.status_code == 403
        and r.json()["error"]["code"] == "UNAUTHORIZED_PERSPECTIVE"
        and r.headers["X-Request-ID"]
    )
    r = await client.get(f"/api/v1/characters/{w.actors['Renn']}/inventory")
    assert r.status_code == 403
    # Alex's own view
    r = await client.get(
        f"/api/v1/campaigns/{cid}/scene", params={"actor_id": str(w.actors["Alex"])}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["location_known_as"] == "Red Lantern Tavern" and body["your_zone"] == "tables"
    known = {p["known_as"] for p in body["participants"]}
    assert known == {"you", "Elara", "Tomas", "Mira", "a man you have not met"}
    assert "Renn" not in str(body) and "Veyra" not in str(body)
    r = await client.get(f"/api/v1/characters/{w.actors['Alex']}/inventory")
    assert r.status_code == 200 and "spirit" not in r.text and "lore" not in r.text
    r = await client.get(f"/api/v1/characters/{w.actors['Alex']}/beliefs")
    assert r.status_code == 200 and "killed" not in r.text
    # debug is omniscient, and gated
    r = await client.get(f"/api/v1/debug/campaigns/{cid}/facts")
    assert r.status_code == 200 and any(f["key"] == "renn_killed_oric" for f in r.json())
    r = await client.get(
        f"/api/v1/debug/campaigns/{cid}/perspectives/compare",
        params={"actor_ids": f"{w.actors['Alex']},{w.actors['Renn']}"},
    )
    assert r.status_code == 200
    cmp = r.json()
    assert any(
        b["proposition"]["predicate"] == "killed"
        for b in cmp["actors"][str(w.actors["Renn"])]["beliefs"]
    )
    assert not any(
        b["proposition"]["predicate"] == "killed"
        for b in cmp["actors"][str(w.actors["Alex"])]["beliefs"]
    )


async def test_debug_endpoints_require_debug_mode(
    session: AsyncSession, frostbridge: World, test_settings
) -> None:
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    await session.commit()
    app = create_app(test_settings.model_copy(update={"debug_mode": False}))
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"/api/v1/debug/campaigns/{frostbridge.h.campaign_id}/facts")
    assert r.status_code == 403 and r.json()["error"]["code"] == "DEBUG_MODE_REQUIRED"


async def test_require_focus_actor_is_a_service_rule_not_only_an_api_rule(
    session: AsyncSession, frostbridge: World
) -> None:
    psv = PerspectiveService(session)
    with pytest.raises(UnauthorizedPerspective):
        await psv.require_focus_actor(frostbridge.actors["Elara"])
    await psv.require_focus_actor(frostbridge.actors["Alex"])
