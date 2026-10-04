"""SpeechService — the communication → knowledge pipeline
(docs/specifications/communication-and-knowledge.md §2–§4, §7; Invariant 16).

    utterance + conveys[]
      └─ authorization: every belief_ref is the speaker's, every fact_ref is in the speaker's
         perspective — anything else is a leakage incident: rejected, nothing stored
           └─ Claim rows (speaker-private deception flags stay on the Claim)
                └─ per legitimate recipient (audibility, language): Observation(heard_claim)
                     └─ belief-update rules → Belief rows with provenance

In Milestone 03 `conveys[]` is supplied structurally by the caller (fixtures, tests, the
deterministic `/play` path). The Intent Interpreter and Claim Extractor arrive in 06a/06b.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import events as ev
from app.engine import beliefs as rules
from app.engine.beliefs import Proposition
from app.engine.positioning import SceneSpace
from app.persistence.models import (
    Actor,
    Claim,
    Entity,
    Event,
    Observation,
    Scene,
    TranscriptMessage,
    TranscriptRecipient,
)
from app.persistence.repositories.objective import ObjectiveWorldRepository
from app.persistence.repositories.perspective import PerspectiveRepository
from app.services.events import EventTransaction
from app.services.knowledge import KnowledgeService
from app.services.world import CampaignHandle, WorldError

DEFAULT_SENSES = {"sense:vision", "sense:hearing"}
DEFAULT_LANGUAGES = {"common"}


class LeakageError(RuntimeError):
    """An AI/structured proposal referenced knowledge outside the speaker's perspective."""

    def __init__(self, speaker: uuid.UUID, kind: str, ref_id: str, reason: str) -> None:
        super().__init__(f"leakage: {speaker} {kind} {ref_id}: {reason}")
        self.speaker, self.kind, self.ref_id, self.reason = speaker, kind, ref_id, reason


@dataclass
class ConveysItem:
    kind: str  # belief_ref | fact_ref | proposition
    ref_id: str | None = None
    proposition: dict[str, Any] | None = None
    stance: str = "asserts_true"
    fidelity: str = "full"
    deliberate_false: bool = False  # speaker-private
    about_speaker_self: bool = False


@dataclass
class SpeechResult:
    event: Event
    claims: list[Claim]
    recipients: list[uuid.UUID]
    observations: list[Observation]
    unknown_language_for: list[uuid.UUID] = field(default_factory=list)


@dataclass
class _Participant:
    actor: Actor
    entity: Entity
    senses: set[str]
    languages: set[str]
    capabilities: set[str]
    incapacitated: bool
    controller: str


class SpeechService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.objective = ObjectiveWorldRepository(session)
        self.perspective = PerspectiveRepository(session)
        self.knowledge = KnowledgeService(session)

    # -- loading -------------------------------------------------------------------------------

    async def _participants(self, scene: Scene) -> dict[uuid.UUID, _Participant]:
        out: dict[uuid.UUID, _Participant] = {}
        actors = await self.objective.actors_in_scene(scene.id)
        conds = await self.perspective.active_conditions([a.entity_id for a in actors])
        for a in actors:
            ent = await self.session.get(Entity, a.entity_id)
            profile = a.mechanical_profile or {}
            caps = set(profile.get("capabilities", []))
            senses = {c for c in caps if c.startswith("sense:")} or set(DEFAULT_SENSES)
            languages = set(profile.get("languages", [])) or set(DEFAULT_LANGUAGES)
            out[a.id] = _Participant(
                a,
                ent,
                senses,
                languages,
                caps,
                "condition.incapacitated" in conds.get(a.entity_id, set()),
                (await self.perspective.controller_type(a.id)) or "ai",
            )
        return out

    # -- authorization (c&k §2) ----------------------------------------------------------------

    async def _authorize(
        self, h: CampaignHandle, speaker: uuid.UUID, items: list[ConveysItem]
    ) -> list[tuple[ConveysItem, Proposition, uuid.UUID | None, uuid.UUID | None, bool]]:
        """Returns (item, proposition, source_fact_id, source_belief_id, speaker_secondhand) per
        item, or raises LeakageError after recording the incident."""
        resolved = []
        for it in items:
            if it.kind == "belief_ref":
                if not it.ref_id:
                    raise WorldError("belief_ref needs ref_id")
                b = await self.perspective.holds_belief(speaker, uuid.UUID(it.ref_id))
                if b is None:
                    await self._record_leak(
                        h, speaker, it.kind, it.ref_id, "belief not held by speaker"
                    )
                    raise LeakageError(speaker, it.kind, it.ref_id, "belief not held by speaker")
                resolved.append(
                    (
                        it,
                        Proposition.from_dict(b.proposition),
                        b.fact_id,
                        b.id,
                        b.belief_type == "rumor",
                    )
                )
            elif it.kind == "fact_ref":
                if not it.ref_id:
                    raise WorldError("fact_ref needs ref_id")
                fact_id = uuid.UUID(it.ref_id)
                if not await self.perspective.holds_fact(speaker, fact_id):
                    await self._record_leak(
                        h, speaker, it.kind, it.ref_id, "fact outside speaker perspective"
                    )
                    raise LeakageError(
                        speaker, it.kind, it.ref_id, "fact outside speaker perspective"
                    )
                fact = await self.objective.fact(fact_id)
                assert fact is not None
                resolved.append((it, KnowledgeService.proposition_of(fact), fact.id, None, False))
            elif it.kind == "proposition":
                if not it.proposition or not it.proposition.get("predicate"):
                    raise WorldError("proposition needs a predicate")
                resolved.append((it, Proposition.from_dict(it.proposition), None, None, False))
            else:
                raise WorldError(f"unknown conveys kind {it.kind!r}")
        return resolved

    async def _record_leak(
        self, h: CampaignHandle, speaker: uuid.UUID, kind: str, ref_id: str, reason: str
    ) -> None:
        async with EventTransaction(
            self.session, h.campaign_id, h.timeline_id, created_by_type="engine"
        ) as tx:
            await tx.emit(
                ev.LeakageRejected(actor_id=speaker, ref_kind=kind, ref_id=ref_id, reason=reason)
            )

    # -- audibility (world-memory §8, §26; leakage §14) ----------------------------------------

    @staticmethod
    def _recipients(
        speaker: uuid.UUID,
        channel: str,
        targets: list[uuid.UUID],
        parts: dict[uuid.UUID, _Participant],
        scene: Scene,
    ) -> list[uuid.UUID]:
        out: list[uuid.UUID] = []
        space = SceneSpace.from_dict(scene.state["space"]) if scene.state.get("space") else None
        for aid, p in parts.items():
            if aid == speaker or p.incapacitated or "sense:hearing" not in p.senses:
                continue
            if channel == "say":
                out.append(aid)
            elif channel == "whisper":
                if aid in targets:
                    out.append(aid)
                elif (
                    "hear:whispers" in p.capabilities
                    and space is not None
                    and str(aid) in space.positions
                    and str(speaker) in space.positions
                ):
                    if space.band(str(speaker), str(aid)) in ("engaged", "close"):
                        out.append(aid)  # a capability, not a hard-coded recipient list
        return out

    # -- the pipeline ----------------------------------------------------------------------------

    async def utter(
        self,
        h: CampaignHandle,
        scene_id: uuid.UUID,
        speaker_id: uuid.UUID,
        text: str,
        *,
        channel: str = "say",
        conveys: list[ConveysItem] | None = None,
        target_actor_ids: list[uuid.UUID] | None = None,
        language: str = "common",
        conveyance_source: str = "player_text",
        turn_id: uuid.UUID | None = None,
    ) -> SpeechResult:
        if channel not in ("say", "whisper"):
            raise WorldError(f"unsupported channel {channel!r}")
        scene = await self.session.get(Scene, scene_id)
        if scene is None:
            raise WorldError("scene not found")
        parts = await self._participants(scene)
        if speaker_id not in parts:
            raise WorldError("speaker is not in the scene")
        speaker = parts[speaker_id]
        targets = list(target_actor_ids or [])
        if channel == "whisper" and not targets:
            raise WorldError("whisper needs target_actor_ids")
        resolved = await self._authorize(h, speaker_id, conveys or [])
        recipients = self._recipients(speaker_id, channel, targets, parts, scene)

        created_by = "human" if speaker.controller == "human" else "ai"
        async with EventTransaction(
            self.session,
            h.campaign_id,
            h.timeline_id,
            created_by_type=created_by,
            created_by_id=speaker_id,
        ) as tx:
            msg = TranscriptMessage(
                campaign_id=h.campaign_id,
                timeline_id=h.timeline_id,
                scene_id=scene.id,
                speaker_actor_id=speaker_id,
                channel=channel,
                raw_text=text,
                game_tick=tx.clock.current_tick,
                source=created_by,
                turn_id=turn_id,
            )
            self.session.add(msg)
            await self.session.flush()
            for t in targets:
                self.session.add(TranscriptRecipient(message_id=msg.id, actor_id=t))
            event = await tx.emit(
                ev.SpeechUttered(
                    speaker_actor_id=speaker_id,
                    channel=channel,
                    language=language,
                    transcript_message_id=msg.id,
                    target_actor_ids=targets,
                    recipient_actor_ids=recipients,
                    claim_count=len(resolved),
                ),
                scene=scene,
                location_id=scene.location_id,
                entities=[(speaker.entity.id, "speaker")],
            )
            msg.event_id = event.id
            tx.touch_scene(scene)

            claims: list[Claim] = []
            for it, prop, fact_id, belief_id, _secondhand in resolved:
                c = Claim(
                    campaign_id=h.campaign_id,
                    speaker_actor_id=speaker_id,
                    statement_event_id=event.id,
                    subject_entity_id=await self._entity_or_none(prop.subject),
                    predicate=prop.predicate,
                    object_entity_id=await self._entity_or_none(prop.object),
                    object_value={"value": prop.value} if prop.value is not None else None,
                    speaker_stance=it.stance,
                    fidelity=it.fidelity,
                    deliberate_false=it.deliberate_false,
                    about_speaker_self=it.about_speaker_self,
                    source_fact_id=fact_id,
                    source_belief_id=belief_id,
                    conveyance_source=conveyance_source,
                )
                self.session.add(c)
                claims.append(c)
            await self.session.flush()

            observations: list[Observation] = []
            # the speaker's own observation of having spoken (leakage §2: "Alex observation exists")
            observations.append(
                self._obs(
                    tx,
                    speaker_id,
                    event,
                    scene,
                    "spoke",
                    {
                        "event_type": "speech.uttered",
                        "channel": channel,
                        "claim_ids": [str(c.id) for c in claims],
                        "recipients": [str(r) for r in recipients],
                    },
                )
            )
            # speaker self-belief: speech is evidence of the speaker's state (c&k §3, human only)
            if speaker.controller == "human":
                for (it, prop, fact_id, _b, _s), c in zip(resolved, claims, strict=True):
                    if it.stance == "uncertain" or (
                        it.stance == "asserts_true" and it.about_speaker_self
                    ):
                        sb = rules.speaker_self_belief(prop, it.stance)
                        if sb is not None:
                            await self.knowledge.store_belief(
                                tx,
                                speaker_id,
                                sb,
                                fact_id=fact_id,
                                claim_id=c.id,
                                acquired_event=event,
                            )

            unknown: list[uuid.UUID] = []
            speaker_identity_cache: dict[uuid.UUID, str] = {}
            for rid in recipients:
                r = parts[rid]
                if f"lang:{language}" not in r.capabilities and language not in r.languages:
                    observations.append(
                        self._obs(
                            tx,
                            rid,
                            event,
                            scene,
                            "speech_in_unknown_language",
                            {
                                "event_type": "speech.uttered",
                                "speaker": await self._known_as(
                                    rid, speaker.entity, speaker_identity_cache
                                ),
                                "language": "unknown",
                                "channel": channel,
                            },
                        )
                    )
                    unknown.append(rid)
                    continue
                relationship = await self.knowledge.relationship_view(rid, speaker_id)
                existing = await self.knowledge.existing_beliefs(rid)
                for (it, prop, fact_id, _b, secondhand), c in zip(resolved, claims, strict=True):
                    speaker_name = await self._known_as(rid, speaker.entity, speaker_identity_cache)
                    obs = self._obs(
                        tx,
                        rid,
                        event,
                        scene,
                        "heard_claim",
                        {
                            "event_type": "speech.uttered",
                            "channel": channel,
                            "speaker": speaker_name,
                            "stance": it.stance,
                            "proposition": prop.to_dict(),
                        },
                        claim_id=c.id,
                    )
                    observations.append(obs)
                    # the recipient knows the speaker said it
                    await self.knowledge.store_belief(
                        tx,
                        rid,
                        rules.meta_belief_that_asserted(str(speaker_id), prop),
                        claim_id=c.id,
                        acquired_event=event,
                        source_actor_id=speaker_id,
                    )
                    if it.stance == "question":
                        continue
                    stance_prop = prop if it.stance != "asserts_false" else prop.negated()
                    proposal = rules.from_testimony(
                        stance_prop,
                        it.stance,
                        relationship,
                        existing,
                        about_speaker_self=it.about_speaker_self,
                        speaker_secondhand=secondhand,
                    )
                    await self.knowledge.store_belief(
                        tx,
                        rid,
                        proposal,
                        fact_id=fact_id
                        if it.fidelity == "full" and it.stance == "asserts_true"
                        else None,
                        claim_id=c.id,
                        acquired_event=event,
                        source_actor_id=speaker_id,
                    )
                    existing = await self.knowledge.existing_beliefs(rid)
        return SpeechResult(event, claims, recipients, observations, unknown)

    def _obs(
        self,
        tx: EventTransaction,
        actor_id: uuid.UUID,
        event: Event,
        scene: Scene,
        kind: str,
        raw: dict[str, Any],
        *,
        claim_id: uuid.UUID | None = None,
    ) -> Observation:
        row = Observation(
            campaign_id=tx.campaign_id,
            actor_id=actor_id,
            source_event_id=event.id,
            channel="hearing",
            observation_type=kind,
            raw=raw,
            confidence=1.0,
            game_tick=event.game_tick,
            claim_id=claim_id,
            scene_id=scene.id,
        )
        self.session.add(row)
        return row

    async def _entity_or_none(self, v: str | None) -> uuid.UUID | None:
        """Models write ids they were never given (a whisper target's actor id, a made-up
        uuid). Only an existing entity id is stored as a reference; anything else is free
        text that stays in the proposition dict only."""
        eid = _uuid_or_none(v)
        if eid is None:
            return None
        return eid if await self.session.get(Entity, eid) is not None else None

    async def _known_as(
        self, observer: uuid.UUID, speaker_entity: Entity, cache: dict[uuid.UUID, str]
    ) -> str:
        if observer in cache:
            return cache[observer]
        ident = await self.perspective.identity_knowledge(observer)
        row = ident.get(speaker_entity.id)
        name = (
            row.known_name
            if row
            else ((speaker_entity.metadata_ or {}).get("descriptor") or "a stranger")
        )
        cache[observer] = name
        return name


def _uuid_or_none(v: str | None) -> uuid.UUID | None:
    if not v:
        return None
    try:
        return uuid.UUID(v)
    except ValueError:
        return None
