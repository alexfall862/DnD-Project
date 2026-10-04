"""ObservationService — template-generated Observations (observation-authoring.md §2–§3).

For each ledger Event with a template, every eligible observer in the scene receives an
Observation whose `raw` names participants the way *that* observer knows them and exposes only
the fields the template marks observer-visible. No model is involved; rendering to prose
(`render()`) is a pure function of `raw` and is never stored.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import Entity, Event, Observation, Scene
from app.services.events import EventTransaction


@dataclass(frozen=True)
class Template:
    participants: tuple[tuple[str, str], ...]  # (payload field holding an actor id, role)
    visible: tuple[str, ...] = ()  # payload fields every observer sees
    participant_only: tuple[str, ...] = ()  # fields only the participants see
    channel: str = "vision"
    verb: str = ""  # rendering stem


TEMPLATES: dict[str, Template] = {
    "attack.rolled": Template(
        (("actor", "attacker"), ("target", "target")),
        ("weapon", "success", "degree"),
        ("total", "versus"),
        verb="attacks",
    ),
    "damage.dealt": Template(
        (("actor", "attacker"), ("target", "target")),
        ("damage_type",),
        ("amount", "remaining"),
        verb="strikes",
    ),
    "actor.incapacitated": Template((("actor", "subject"), ("by", "cause")), verb="goes down"),
    "actor.repositioned": Template((("actor", "subject"),), ("from_zone", "to_zone"), verb="moves"),
    "actor.engaged": Template((("actor", "subject"), ("target", "target")), verb="closes with"),
    "actor.disengaged": Template((("actor", "subject"),), ("unsafe",), verb="breaks away"),
    "actor.took_cover": Template((("actor", "subject"),), ("level",), verb="takes cover"),
    "actor.rested": Template((("actor", "subject"),), ("kind",), verb="rests"),
    "actor.fled": Template((("actor", "subject"),), ("via",), verb="flees"),
    "actor.surrendered": Template((("actor", "subject"),), verb="surrenders"),
    "check.rolled": Template(
        (("actor", "subject"),),
        ("action",),
        ("total", "versus", "success", "degree"),
        verb="attempts",
    ),
    "item.picked_up": Template((("actor", "subject"),), ("item", "zone"), verb="picks up"),
    "item.dropped": Template((("actor", "subject"),), ("item", "zone"), verb="drops"),
    "item.revealed": Template((("actor", "subject"),), ("item", "zone", "name"), verb="finds"),
    "actor.moved": Template((("actor_id", "subject"),), ("to_location_id",), verb="leaves for"),
    "encounter.started": Template((), ("order",), verb="combat begins"),
}


@dataclass
class Observer:
    actor_id: uuid.UUID
    entity_id: uuid.UUID
    senses: set[str] = field(default_factory=lambda: {"sense:vision", "sense:hearing"})
    incapacitated: bool = False
    detected: set[str] = field(default_factory=set)  # hidden actor keys this observer has detected


@dataclass
class ObservationInputs:
    """Everything the templates need about the scene, supplied by the caller (ActionService)."""

    observers: dict[str, Observer]  # actor key (uuid str) -> observer
    hidden_actors: set[str]  # actor keys currently hidden
    identity: dict[
        uuid.UUID, dict[uuid.UUID, str]
    ]  # observer actor id -> {entity id -> known name}
    actor_entity: dict[str, uuid.UUID]  # actor key -> entity id
    descriptors: dict[uuid.UUID, str]  # entity id -> descriptor for strangers


class ObservationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def known_as(
        observer: Observer, entity_id: uuid.UUID | None, inputs: ObservationInputs, *, is_self: bool
    ) -> str:
        if is_self:
            return "you"
        if entity_id is None:
            return "someone"
        name = inputs.identity.get(observer.actor_id, {}).get(entity_id)
        return name or inputs.descriptors.get(entity_id) or "a stranger"

    async def observe(
        self,
        tx: EventTransaction,
        event: Event,
        payload: dict[str, Any],
        scene: Scene,
        inputs: ObservationInputs,
    ) -> list[Observation]:
        """Create per-observer Observations for one event. Returns the rows (added to session)."""
        template = TEMPLATES.get(event.event_type)
        if template is None:
            return []
        participants: list[tuple[str | None, str]] = [
            (payload.get(f), role) for f, role in template.participants
        ]
        participant_keys = {p for p, _ in participants if p}
        out: list[Observation] = []
        for key, obs in inputs.observers.items():
            is_participant = key in participant_keys
            if obs.incapacitated and not is_participant:
                continue
            if f"sense:{template.channel}" not in obs.senses and not is_participant:
                continue
            # a hidden actor's doings are unseen by observers who have not detected it
            hidden_involved = [
                p
                for p in participant_keys
                if p in inputs.hidden_actors and p != key and p not in obs.detected
            ]
            if hidden_involved and not is_participant:
                continue
            raw: dict[str, Any] = {
                "event_type": event.event_type,
                "participants": [
                    {
                        "entity_id": str(inputs.actor_entity[p])
                        if p in inputs.actor_entity
                        else None,
                        "known_as": self.known_as(
                            obs,
                            inputs.actor_entity.get(p) if p else None,
                            inputs,
                            is_self=(p == key),
                        ),
                        "role": role,
                    }
                    for p, role in participants
                    if p
                ],
                "outcome_visible": {f: payload[f] for f in template.visible if f in payload},
                "details": [],
            }
            if is_participant:
                raw["participant_only"] = {
                    f: payload[f] for f in template.participant_only if f in payload
                }
            row = Observation(
                campaign_id=tx.campaign_id,
                actor_id=obs.actor_id,
                source_event_id=event.id,
                channel=template.channel,
                observation_type="event",
                raw=raw,
                confidence=1.0,
                game_tick=event.game_tick,
                scene_id=scene.id,
            )
            self.session.add(row)
            out.append(row)
        return out

    @staticmethod
    def render(raw: dict[str, Any]) -> str:
        """Deterministic prose line for a model context. Pure function of `raw`."""
        t = TEMPLATES.get(raw.get("event_type", ""))
        names = {p["role"]: p["known_as"] for p in raw.get("participants", [])}
        subj = names.get("subject") or names.get("attacker") or "someone"
        obj = names.get("target") or names.get("cause")
        verb = t.verb if t else raw.get("event_type", "")
        if subj == "you":
            verb = _second_person(verb)
        vis = raw.get("outcome_visible", {})
        line = f"{subj.capitalize()} {verb}" + (f" {obj}" if obj else "")
        if raw.get("event_type") == "attack.rolled":
            line += " and " + ("hits" if vis.get("success") else "misses")
        elif raw.get("event_type") == "actor.repositioned":
            line += f" from {vis.get('from_zone')} to {vis.get('to_zone')}"
        elif raw.get("event_type") == "actor.took_cover":
            line += f" ({vis.get('level')})"
        elif raw.get("event_type") == "item.picked_up":
            line = f"{subj.capitalize()} pick{'' if subj == 'you' else 's'} something up"
        elif raw.get("event_type") == "item.revealed":
            line = f"{subj.capitalize()} finds {vis.get('name') or 'something'}"
        po = raw.get("participant_only")
        if po and "amount" in po:
            line += f" for {po['amount']}"
        return line + "."

    @staticmethod
    async def descriptors_for(
        session: AsyncSession, entity_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        out: dict[uuid.UUID, str] = {}
        for eid in entity_ids:
            e = await session.get(Entity, eid)
            if e is not None:
                out[eid] = (e.metadata_ or {}).get("descriptor") or "a stranger"
        return out


def _second_person(verb: str) -> str:
    """'attempts' -> 'attempt', 'closes with' -> 'close with'; irregulars are handled."""
    head, _, rest = verb.partition(" ")
    if head.endswith("es") and head[:-2] in ("clos", "go", "do"):
        head = head[:-2] + ("e" if head[:-2] == "clos" else "")
    elif head.endswith("s") and not head.endswith("ss"):
        head = head[:-1]
    return f"{head} {rest}".strip()
