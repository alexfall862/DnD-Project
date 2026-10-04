"""Player-authored canon (docs/specifications/player-authored-canon.md).

The Intent Interpreter emits `asserted_facts[]`; each is classified and handled by the
campaign's `player_canon_policy`:

| class          | strict     | personal (default) | collaborative          |
| self_minor     | adjudicate | accept             | accept                 |
| self_major     | refuse     | adjudicate         | adjudicate (yes-and)   |
| world_minor    | refuse     | adjudicate         | accept                 |
| world_major    | refuse     | refuse             | adjudicate (yes-and)   |
| contradiction  | refuse     | refuse             | refuse                 |

`accept` creates an established Fact with `player_assertion` provenance (plus a lightweight
item for keepsakes); `adjudicate` routes to the Rules Adjudicator and accepts only a ruling
with no check and no mechanics (anything heavier is refused with an OOC note in v0.1);
`refuse` changes nothing and reports why. A refused `contradiction` still becomes the
speaker's own `stated` belief — the character believes it even if the world disagrees.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.roles import AssertedFactOut, RulesAdjudicatorOut
from app.engine.beliefs import BeliefProposal, Proposition
from app.services.events import EventTransaction
from app.services.knowledge import KnowledgeService
from app.services.world import CampaignHandle, WorldService

Policy = Literal["strict", "personal", "collaborative"]
Decision = Literal["accept", "adjudicate", "refuse"]

TABLE: dict[str, dict[Policy, Decision]] = {
    "self_minor": {"strict": "adjudicate", "personal": "accept", "collaborative": "accept"},
    "self_major": {"strict": "refuse", "personal": "adjudicate", "collaborative": "adjudicate"},
    "world_minor": {"strict": "refuse", "personal": "adjudicate", "collaborative": "accept"},
    "world_major": {"strict": "refuse", "personal": "refuse", "collaborative": "adjudicate"},
    "contradiction": {"strict": "refuse", "personal": "refuse", "collaborative": "refuse"},
}
DEFAULT_POLICY: Policy = "personal"
MAX_AUTO_ACCEPTS_PER_SCENE = 3


@dataclass
class AssertionOutcome:
    proposition: dict[str, Any]
    class_: str
    decision: Decision
    result: Literal["accepted", "refused", "adjudicated_accepted", "adjudicated_refused"]
    note: str = ""
    fact_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None
    adjudicator_called: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def decide(class_: str, policy: Policy) -> Decision:
    try:
        return TABLE[class_][policy]
    except KeyError:
        return "refuse"


class PlayerCanonService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.world = WorldService(session)
        self.knowledge = KnowledgeService(session)

    async def handle(
        self,
        h: CampaignHandle,
        actor_id: uuid.UUID,
        assertion: AssertedFactOut,
        *,
        policy: Policy,
        scene_id: uuid.UUID | None,
        auto_accepts_so_far: int,
        adjudicate: Any = None,  # async callable(assertion) -> RulesAdjudicatorOut | None
        location_id: uuid.UUID | None = None,
    ) -> AssertionOutcome:
        prop = assertion.proposition.model_dump()
        class_ = assertion.class_
        decision = decide(class_, policy)
        if (
            class_ == "contradiction"
            or assertion.mechanical_weight == "significant"
            and decision == "accept"
        ):
            decision = "refuse" if class_ == "contradiction" else "adjudicate"
        if decision == "accept" and auto_accepts_so_far >= MAX_AUTO_ACCEPTS_PER_SCENE:
            decision = "adjudicate"  # rate limit falls back to adjudication, not refusal

        if decision == "accept":
            fact, item = await self._accept(
                h, actor_id, prop, class_, location_id, provenance="player_assertion"
            )
            return AssertionOutcome(
                prop,
                class_,
                decision,
                "accepted",
                "accepted as established canon",
                fact.id,
                item.id if item else None,
            )

        if decision == "adjudicate":
            ruling: RulesAdjudicatorOut | None = (
                await adjudicate(assertion) if adjudicate is not None else None
            )
            if (
                ruling is not None
                and not ruling.requires_check
                and not ruling.on_success
                and not ruling.on_failure
            ):
                fact, item = await self._accept(
                    h,
                    actor_id,
                    prop,
                    class_,
                    location_id,
                    provenance="player_assertion_adjudicated",
                    note=ruling.summary,
                )
                return AssertionOutcome(
                    prop,
                    class_,
                    decision,
                    "adjudicated_accepted",
                    ruling.summary or "accepted after adjudication",
                    fact.id,
                    item.id if item else None,
                    adjudicator_called=True,
                )
            note = (
                (
                    ruling.summary
                    if ruling and ruling.summary
                    else "needs a check or mechanics; not accepted as given"
                )
                if ruling
                else "no adjudicator available"
            )
            return AssertionOutcome(
                prop,
                class_,
                decision,
                "adjudicated_refused",
                note,
                adjudicator_called=ruling is not None,
            )

        # refuse: nothing changes in the world; a contradiction is still what the character thinks
        note = {
            "contradiction": (
                "that conflicts with what is established; your character may believe it, "
                "but it is not so"
            ),
            "world_major": "that would create plot structure; not accepted under this policy",
        }.get(class_, "not accepted under this policy")
        if class_ == "contradiction":
            await self._stated_belief(h, actor_id, prop)
        return AssertionOutcome(prop, class_, decision, "refused", note)

    async def _accept(
        self,
        h: CampaignHandle,
        actor_id: uuid.UUID,
        prop: dict[str, Any],
        class_: str,
        location_id: uuid.UUID | None,
        *,
        provenance: str,
        note: str = "",
    ):
        actor = await self.world._get(
            __import__("app.persistence.models", fromlist=["Actor"]).Actor, actor_id, what="actor"
        )
        subject = prop.get("subject_entity_id")
        fact = await self.knowledge.create_fact(
            h,
            key=None,
            predicate=prop["predicate"],
            subject_entity_id=_uuid(subject) or actor.entity_id
            if class_.startswith("self")
            else _uuid(subject),
            object_entity_id=_uuid(prop.get("object_entity_id")),
            value=prop.get("value"),
            canon_status="established",
            sensitivity="public",
            known_by=[actor_id],
            provenance={
                "source": provenance,
                "class": class_,
                "actor_id": str(actor_id),
                "note": note,
            },
        )
        item = None
        if class_ == "self_minor" and _looks_like_object(prop["predicate"]):
            name = _object_name(prop["predicate"], prop.get("value"))
            item = await self.world.create_item(
                h,
                name,
                template_key="item.travel_supplies",
                possessor_actor_id=actor_id,
                equipped=False,
                item_type="keepsake",
                public_properties={"description": prop["predicate"]},
                provenance={"source": provenance, "fact_id": str(fact.id)},
                importance_tier="background",
            )
        return fact, item

    async def _stated_belief(
        self, h: CampaignHandle, actor_id: uuid.UUID, prop: dict[str, Any]
    ) -> None:
        async with EventTransaction(
            self.session,
            h.campaign_id,
            h.timeline_id,
            created_by_type="human",
            created_by_id=actor_id,
        ) as tx:
            from app.domain import events as ev

            event = await tx.emit(
                ev.BeliefSeeded(
                    actor_id=actor_id,
                    proposition_key=Proposition.from_dict(prop).key,
                    belief_type="stated",
                    confidence=0.8,
                )
            )
            await self.knowledge.store_belief(
                tx,
                actor_id,
                BeliefProposal(
                    Proposition.from_dict(prop),
                    "stated",
                    0.8,
                    "stated",
                    ("player assertion refused as canon",),
                ),
                acquired_event=event,
            )


def _uuid(v: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(v)) if v else None
    except ValueError:
        return None


OBJECT_WORDS = (
    "compass",
    "map",
    "locket",
    "ring",
    "knife",
    "coin",
    "letter",
    "charm",
    "token",
    "pendant",
    "keepsake",
    "flask",
    "journal",
    "pipe",
    "amulet",
    "brooch",
    "blade",
    "sword",
    "dagger",
)


def _looks_like_object(predicate: str) -> bool:
    p = predicate.lower()
    return any(w in p for w in OBJECT_WORDS) or p.startswith(
        ("has ", "carries ", "owns ", "keeps ")
    )


def _object_name(predicate: str, value: Any) -> str:
    p = predicate.lower()
    for w in OBJECT_WORDS:
        if w in p:
            return f"{w} ({predicate})" if len(predicate) < 60 else w
    return str(value) if value else predicate[:40]
