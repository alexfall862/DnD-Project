"""NarrationService — the human-facing narrator and the post-narration canon pass
(orchestration §21–§22, §29; ai-contracts §9–§10; observation-authoring §5;
human-visibility §6; canon-extraction-allowlist).

The narrator receives a NarrativeBundle built from the focus actor's own rendered
observations for this turn, the dialogue that actor heard verbatim, the mechanics visible to
them, a perspective-safe scene line and the campaign's style profile. It streams prose.
Narration is presentation: it is never written back as anyone's Observation and it cannot
change state. The only thing that may persist from it is decoration, through the allowlist
validator in `app/engine/canon.py`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import ContextCompiler
from app.ai.roles import CanonExtractorOut
from app.ai.runner import ModelRunner, RunResult
from app.domain import events as ev
from app.engine.canon import CanonCandidate, validate
from app.persistence.models import (
    Entity,
    Event,
    Location,
    Observation,
    Scene,
    TranscriptMessage,
)
from app.services.events import EventTransaction
from app.services.perspective import PerspectiveService
from app.services.turns import Turn
from app.services.world import CampaignHandle

DEFAULT_STYLE = {
    "perspective": "second person, present tense",
    "verbosity": "60-120 words",
    "dialogue_style": "quote NPC lines verbatim, attributed",
    "description_density": "moderate",
    "humor": "dry, sparing",
    "combat_style": "quick and physical",
    "mechanics_visibility": "no numbers; outcomes only",
}
SHORT_STYLE = {**DEFAULT_STYLE, "verbosity": "resolve in two sentences"}
# campaign.settings.narration_style may be a preset name (the player client's choice) or a
# dict of style overrides
STYLE_PRESETS: dict[str, dict[str, str]] = {
    "terse": {"verbosity": "two or three sentences", "description_density": "spare"},
    "standard": {},
    "rich": {"verbosity": "120-200 words", "description_density": "rich"},
}


@dataclass
class NarrativeBundle:
    focus_actor_id: uuid.UUID
    observations: list[str]  # rendered, this turn, the focus actor's own
    dialogue: list[str]  # verbatim lines the focus actor heard (or said)
    mechanics: list[str]  # visible rolls / state changes as plain lines
    scene_line: str
    style: dict[str, str]
    own_input: str = ""
    compressed: list[str] = field(default_factory=list)  # governor summaries
    # what became of the focus actor's own attempts this turn, authoritative (A9 slice:
    # an invalid pick-up was narrated as success because only the intent was given)
    outcomes: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.observations or self.dialogue or self.mechanics)

    def situation(self) -> str:
        parts = [f"The player ({'you'}) did: {self.own_input}"] if self.own_input else []
        if self.outcomes:
            parts.append(
                "Outcome of what you attempted (authoritative; narrate exactly this):\n- "
                + "\n- ".join(self.outcomes)
            )
        if self.observations:
            parts.append("What you observed this turn:\n- " + "\n- ".join(self.observations))
        if self.dialogue:
            parts.append("Dialogue you heard, verbatim:\n- " + "\n- ".join(self.dialogue))
        if self.compressed:
            parts.append("Also, briefly: " + " ".join(self.compressed))
        return "\n\n".join(parts) or "Nothing of note happened."

    def mechanics_text(self) -> str:
        return "\n".join(self.mechanics) if self.mechanics else "No rolls or state changes."

    def style_text(self) -> str:
        return "\n".join(f"{k.replace('_', ' ')}: {v}" for k, v in self.style.items())


class NarrationService:
    def __init__(
        self, session: AsyncSession, *, compiler: ContextCompiler, runner: ModelRunner
    ) -> None:
        self.session = session
        self.compiler = compiler
        self.runner = runner
        self.perspective = PerspectiveService(session)

    # -- bundle ------------------------------------------------------------------------------------

    async def bundle(
        self,
        focus_actor_id: uuid.UUID,
        events: list[Event],
        *,
        own_input: str,
        visible_rolls: list[dict[str, Any]],
        state_changes: list[dict[str, Any]],
        style: dict[str, Any] | None,
        short: bool = False,
        compressed: list[str] | None = None,
        outcomes: list[str] | None = None,
    ) -> NarrativeBundle:
        """Only the focus actor's own Observations for this turn's events, the transcript lines
        of speech events whose recipients include them, and mechanics they can see."""
        event_ids = [e.id for e in events]
        names = await self.perspective.known_entities(focus_actor_id)
        rendered: list[str] = []
        dialogue: list[str] = []
        if event_ids:
            obs = (
                (
                    await self.session.execute(
                        select(Observation)
                        .where(
                            Observation.actor_id == focus_actor_id,
                            Observation.source_event_id.in_(event_ids),
                        )
                        .order_by(Observation.created_at)
                    )
                )
                .scalars()
                .all()
            )
            seen: set[str] = set()
            for o in obs:
                if o.observation_type in ("heard_claim", "spoke"):
                    continue  # dialogue is given verbatim below
                line = PerspectiveService.render(o.observation_type, o.raw, names)
                if line not in seen:
                    seen.add(line)
                    rendered.append(line)
            speech_events = [e for e in events if e.event_type == "speech.uttered"]
            if speech_events:
                msgs = {
                    m.event_id: m
                    for m in (
                        await self.session.execute(
                            select(TranscriptMessage).where(
                                TranscriptMessage.event_id.in_([e.id for e in speech_events])
                            )
                        )
                    )
                    .scalars()
                    .all()
                }
                for e in speech_events:
                    p = e.payload
                    recipients = {str(x) for x in p.get("recipient_actor_ids", [])}
                    speaker = p.get("speaker_actor_id")
                    mine = speaker == str(focus_actor_id)
                    if not mine and str(focus_actor_id) not in recipients:
                        continue
                    m = msgs.get(e.id)
                    if m is None:
                        continue
                    who = (
                        "You" if mine else await self._speaker_name(focus_actor_id, speaker, names)
                    )
                    verb = "whisper" if p.get("channel") == "whisper" else "say"
                    dialogue.append(f'{who} {verb}{"" if mine else "s"}: "{m.raw_text}"')
        mech = [
            f"{r.get('purpose', 'roll')}: {r.get('expression')} = {r.get('total')}"
            for r in visible_rolls
        ] + [f"{c['resource']}: {c['before']} -> {c['after']}" for c in state_changes]
        view = await self.perspective.scene_view(focus_actor_id)
        scene_line = (
            f"{view.location_known_as or 'an unfamiliar place'} ({view.scene_type}); you are at "
            f"{view.space_zone or 'here'}; present: "
            + (", ".join(x.known_as for x in view.participants if not x.is_self) or "no one")
            if view
            else "nowhere in particular"
        )
        base = SHORT_STYLE if short else DEFAULT_STYLE
        if isinstance(style, str):
            style = STYLE_PRESETS.get(style, {})
        return NarrativeBundle(
            focus_actor_id,
            rendered,
            dialogue,
            mech,
            scene_line,
            {**base, **{k: str(v) for k, v in (style or {}).items()}},
            own_input,
            list(compressed or []),
            list(outcomes or []),
        )

    async def _speaker_name(
        self, focus: uuid.UUID, speaker_id: str | None, names: dict[uuid.UUID, str]
    ) -> str:
        if not speaker_id:
            return "Someone"
        actor = await self.perspective.repo.actor(uuid.UUID(speaker_id))
        if actor is None:
            return "Someone"
        if actor.entity_id in names:
            return names[actor.entity_id]
        ent = await self.session.get(Entity, actor.entity_id)
        return ((ent.metadata_ or {}).get("descriptor") if ent else None) or "a stranger"

    # -- narrator ----------------------------------------------------------------------------------

    async def narrate(
        self,
        h: CampaignHandle,
        bundle: NarrativeBundle,
        turn: Turn,
        emit,
    ) -> tuple[str | None, RunResult | None]:
        """Stream the narrator; returns (narration, run). Never raises on model failure: the
        caller falls back to the plain structured result (PROMPT.md error philosophy)."""
        ctx = await self.compiler.compile(
            h,
            "narrator",
            actor_id=bundle.focus_actor_id,
            purpose="narrate the turn",
            situation=bundle.situation(),
            extra_sections={
                "style": bundle.style_text(),
                "resolved_mechanics": bundle.mechanics_text(),
                "scene": "Scene: " + bundle.scene_line,
            },
        )
        chunks: list[str] = []
        final: RunResult | None = None
        async for item in self.runner.stream(h, ctx, turn_id=turn.turn_id):
            if isinstance(item, RunResult):
                final = item
            else:
                if not chunks:
                    turn.mark_first_narration()
                chunks.append(item)
                emit("narration_delta", {"text": item})
        turn.record_call(
            "narrator",
            calls=1,
            prompt_tokens=final.prompt_tokens if final else None,
            completion_tokens=final.completion_tokens if final else None,
            context_tokens=ctx.estimated_tokens,
        )
        text = "".join(chunks).strip()
        if final is None or not final.ok or not text:
            turn.notes.append("narrator failed; plain structured result shown")
            return None, final
        return text, final

    # -- canon extraction ------------------------------------------------------------------------

    async def extract_canon(
        self,
        h: CampaignHandle,
        scene: Scene,
        focus_actor_id: uuid.UUID,
        narration: str,
        turn: Turn,
    ) -> dict[str, Any]:
        """One bounded Canon Extractor call on the narration; candidates validated structurally
        against the allowlist and stored as latent decoration. Background budget."""
        if not turn.can_make_sync_call():
            return {"skipped": "call cap"}
        present = {str(e.id) for _a, e in await self.perspective.repo.scene_participants(scene.id)}
        location = (
            await self.session.get(Location, scene.location_id) if scene.location_id else None
        )
        ctx = await self.compiler.compile(
            h,
            "canon_extractor",
            actor_id=focus_actor_id,
            purpose="extract decoration",
            situation=(
                "Narration:\n"
                + narration
                + "\n\nEntities present (ids you may reference): "
                + ", ".join(sorted(present))
            ),
        )
        res = await self.runner.run(h, ctx, turn_id=turn.turn_id)
        turn.record_call(
            "canon_extractor",
            sync=False,
            calls=res.calls,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
            context_tokens=ctx.estimated_tokens,
        )
        if not res.ok or not isinstance(res.output, CanonExtractorOut):
            return {"accepted": 0, "rejected": 0, "status": res.status}
        existing = {
            str(f.get("description", "")).lower()
            for f in ((location.properties if location else {}) or {}).get("features", [])
        }
        v = validate(
            [CanonCandidate.from_dict(c) for c in res.output.candidates if isinstance(c, dict)],
            present_entity_ids=present,
            current_location_id=str(location.id) if location else None,
            existing_feature_texts=existing,
        )
        for c, reason in v.rejected:
            turn.notes.append(f"canon candidate rejected ({reason}): {c.description[:60]}")
        if v.accepted:
            async with EventTransaction(
                self.session, h.campaign_id, h.timeline_id, created_by_type="engine"
            ) as tx:
                for c, action in v.accepted:
                    entity_id = None
                    if action == "entity_descriptor":
                        entity_id = uuid.UUID(str(c.target_ref))
                        ent = await self.session.get(Entity, entity_id)
                        if ent is not None:
                            extra = list((ent.metadata_ or {}).get("latent_descriptors", []))
                            extra.append(c.description)
                            ent.metadata_ = {**(ent.metadata_ or {}), "latent_descriptors": extra}
                    elif location is not None:
                        feats = list((location.properties or {}).get("features", []))
                        feats.append(
                            {
                                "description": c.description,
                                "classification": c.classification,
                                "canon_status": "latent",
                            }
                        )
                        location.properties = {**(location.properties or {}), "features": feats}
                    await tx.emit(
                        ev.CanonDetailAdded(
                            classification=c.classification,
                            description=c.description,
                            location_id=location.id if location else None,
                            entity_id=entity_id,
                            model_run_id=res.model_run_id,
                        ),
                        scene=scene,
                        location_id=scene.location_id,
                    )
        return {"accepted": len(v.accepted), "rejected": len(v.rejected), "status": res.status}

    async def establish_referenced(self, h: CampaignHandle, scene: Scene, text: str) -> list[str]:
        """A later player action that names a latent feature promotes it to established
        (allowlist §2). Lexical: a feature's key words appear in the player's text."""
        if scene.location_id is None:
            return []
        location = await self.session.get(Location, scene.location_id)
        if location is None:
            return []
        feats = list((location.properties or {}).get("features", []))
        low = set(text.lower().replace(",", " ").replace(".", " ").split())
        promoted: list[str] = []
        changed = False
        for f in feats:
            if f.get("canon_status") != "latent":
                continue
            words = {w for w in f["description"].lower().split() if len(w) > 3}
            if words & low:
                f["canon_status"] = "established"
                promoted.append(f["description"])
                changed = True
        if changed:
            async with EventTransaction(
                self.session, h.campaign_id, h.timeline_id, created_by_type="engine"
            ) as tx:
                location.properties = {**(location.properties or {}), "features": feats}
                for d in promoted:
                    await tx.emit(
                        ev.CanonDetailEstablished(description=d, location_id=location.id),
                        scene=scene,
                        location_id=scene.location_id,
                    )
        return promoted
