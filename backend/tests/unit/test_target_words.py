"""A9 Frostbridge slice (Milestone 10 run): the player's own words outrank a loose model pick."""

from __future__ import annotations

from app.services.candidates import Candidate
from app.services.orchestrator import closer_to_words

CANDS = [
    Candidate("warehouse_district", "location", "l1", "Warehouse District"),
    Candidate("shuttered", "location", "l2", "a shuttered warehouse with a faded merchant sign"),
    Candidate("guard_house", "location", "l3", "the guard house"),
    Candidate("notice", "item", "i1", "a notice nailed to the gatepost"),
    Candidate("mira", "actor", "a1", "Mira"),
]


def test_a_more_specific_place_in_the_players_words_wins() -> None:
    text = "Elara and I go to the shuttered warehouse with the merchant sign."
    assert closer_to_words(CANDS, CANDS[0], text) is CANDS[1]


def test_the_models_pick_stands_when_the_words_do_not_clearly_prefer_another() -> None:
    assert closer_to_words(CANDS, CANDS[2], "We go over to the guard house.") is None
    assert closer_to_words(CANDS, CANDS[0], "Back to the warehouse district.") is None
    assert closer_to_words(CANDS, CANDS[4], "I ask Mira about the warehouse") is None  # actors


def test_an_unmatched_ref_resolves_to_what_the_player_named() -> None:
    assert closer_to_words(CANDS, None, "I read the notice on the gatepost.") is CANDS[3]
    assert closer_to_words(CANDS, None, "I look around.") is None
    ledger = [*CANDS, Candidate("ledger", "item", "i2", "Oric's private ledger")]
    assert closer_to_words(ledger, None, "I read the ledger.") is ledger[-1]
    # one shared word that two candidates share is no evidence
    two = [*ledger, Candidate("ledger2", "item", "i3", "a dusty ledger")]
    assert closer_to_words(two, None, "I read the ledger.") is None


def test_words_only_pick_what_the_action_can_take() -> None:
    """A9 slice (third run): "attack the closest thief" had no actor match and one shared
    word picked a place; Alex walked out of the fight. An attack never word-matches a place,
    and a read only matches items."""
    from app.ai.roles import IntentInterpreterOut
    from app.services.orchestrator import SessionOrchestrator

    cands = [
        Candidate("thieves_alley", "location", "l9", "Thieves' Alley"),
        Candidate("notice", "item", "i1", "a notice nailed to the gatepost"),
        Candidate("gate", "location", "l1", "the Town Gate by the gatepost"),
    ]
    orch = SessionOrchestrator.__new__(SessionOrchestrator)

    def resolve(action: str, ref: str, text: str):
        out = IntentInterpreterOut.model_validate(
            {
                "channel": "do",
                "confidence": 0.9,
                "intents": [{"order": 1, "action_type": action, "target_ref": ref}],
            }
        )
        return orch._resolve_targets(out, cands, text, None)[0]["candidate"]

    assert resolve("attack", "closest_thief", "I attack the closest thief") is None
    assert resolve("read", "the_notice", "I read the notice on the gatepost") is cands[1]
    assert resolve("travel", "alley", "We head down Thieves' Alley") is cands[0]


async def test_the_players_words_say_who_comes_along() -> None:
    """A9 slice (fourth run): "We head to the Red Lantern, all three of us" moved only Alex."""
    from app.services.orchestrator import SessionOrchestrator

    orch = SessionOrchestrator.__new__(SessionOrchestrator)
    me = "00000000-0000-0000-0000-000000000001"
    elara = "00000000-0000-0000-0000-000000000002"
    tomas = "00000000-0000-0000-0000-000000000003"
    cands = [
        Candidate("alex", "actor", me, "you"),
        Candidate("elara", "actor", elara, "Elara"),
        Candidate("tomas", "actor", tomas, "Tomas"),
        Candidate("tavern", "location", "l1", "the Red Lantern Tavern"),
    ]
    import uuid

    async def who(text: str) -> set[str]:
        return {str(x) for x in await orch._companions_in_words(uuid.UUID(me), cands, text)}

    assert await who("We head to the Red Lantern, all three of us.") == {elara, tomas}
    assert await who("Elara and I go to the shuttered warehouse.") == {elara}
    assert await who("We go over to the guard house.") == {elara, tomas}
    assert await who("I go to the guard house.") == set()
    assert await who("Tomas, would you look at the guard house records?") == set()


def test_the_models_ref_words_find_the_person_before_the_sentence_finds_a_place() -> None:
    """A9 session replay: "tail this merchant" with the ref "irritated_merchant" matched no ref;
    the sentence then matched "a shuttered warehouse with a faded merchant sign" by one word
    and the party walked away from the merchant."""
    from app.services.orchestrator import by_ref_words

    cands = [
        Candidate("an_irritated_merchant", "actor", "a1", "an irritated merchant"),
        Candidate(
            "shuttered", "location", "l2", "a shuttered warehouse with a faded merchant sign"
        ),
    ]
    assert by_ref_words(cands, "irritated_merchant") is cands[0]
    # a place is never picked by one shared word alone
    assert (
        closer_to_words(cands, None, "We tail this merchant.", kinds=("location", "zone")) is None
    )
