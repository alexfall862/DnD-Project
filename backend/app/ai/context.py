"""ContextCompiler (orchestration §30–§32; Invariant 3, 13).

Every inference context is compiled fresh for one role and (for actor roles) one actor:

    role → authorization scope → mandatory sections → structured records → semantic memory
    retrieval → score/dedupe → fit the role budget → render stable-prefix-first → store snapshot

Authorization precedes retrieval: every item records its owner, and an item whose owner is not
the requesting actor (and is not public) is `denied`. In development a denied item aborts the
call (`ContextAuthorizationError`) after the snapshot is stored for audit.

This module reads only through `PerspectiveService`/`PerspectiveRepository` and
`MemoryService.retrieve` (actor-scoped). It never imports the objective repository or the
`Fact` model; `tests/invariants/test_repository_boundary.py` enforces that.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.roles import RoleSpec
from app.ai.roles import role as role_spec
from app.engine.core import RulesEngine
from app.persistence.models import ContextItem, ContextSnapshot
from app.services.memory import MemoryService
from app.services.perspective import PerspectiveService
from app.services.world import CampaignHandle

# total budget per call (context + output). A9 serves a 32k window; these keep prompts lean
# for latency while leaving room for the larger output caps (play session 2026-10-05)
PROFILE_BUDGET_TOKENS = {
    "fast_structured": 6000,
    "balanced_reasoning": 10000,
    "creative_narrative": 10000,
    "deep_world_author": 14000,
}
SECTION_ORDER = (
    "identity",
    "behavior",
    "known_entities",
    "mechanics_player_layer",
    "core_memories",
    "goals_own",
    "emotions_own",
    "relationships_own",
    "beliefs",
    "inventory_public",
    "memories",
    "recent_turns",
    "scene",
    "heard_claims",
    "observations",
    "available_actions",
    "style",
    "rules_public",
    "candidates",
    "resolved_mechanics",
    "situation",
)
STABLE_SECTIONS = {
    "identity",
    "behavior",
    "known_entities",
    "mechanics_player_layer",
    "core_memories",
    "goals_own",
    "relationships_own",
    "style",
    "rules_public",
}
TRIM_ORDER = (
    "observations",
    "heard_claims",
    "memories",
    "beliefs",
)  # trimmed first when over budget


class ContextAuthorizationError(RuntimeError):
    def __init__(self, snapshot_id: uuid.UUID, denied: list[ContextItemDraft]) -> None:
        super().__init__(
            f"{len(denied)} unauthorized context item(s) in snapshot {snapshot_id}: "
            + ", ".join(f"{d.source_type}:{d.source_id}" for d in denied[:5])
        )
        self.snapshot_id = snapshot_id
        self.denied = denied


@dataclass
class ContextItemDraft:
    section: str
    source_type: str
    source_id: str | None
    owner_actor_id: uuid.UUID | None
    text: str
    reason: str = ""
    score: float | None = None
    public: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def authorization(self, actor_id: uuid.UUID | None) -> str:
        if self.public:
            return "public"
        return (
            "allowed"
            if self.owner_actor_id is not None and self.owner_actor_id == actor_id
            else "denied"
        )


@dataclass
class CompiledContext:
    snapshot_id: uuid.UUID
    role: RoleSpec
    actor_id: uuid.UUID | None
    rendered: str
    stable_prefix_chars: int
    estimated_tokens: int
    items: list[ContextItemDraft]
    ref_map: dict[str, uuid.UUID]  # "b_xxxx"/"f_xxxx" → real ids, for conveys authorization
    sections: dict[str, str]

    @property
    def belief_refs(self) -> set[str]:
        return {k for k in self.ref_map if k.startswith("b_")}

    @property
    def fact_refs(self) -> set[str]:
        return {k for k in self.ref_map if k.startswith("f_")}


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def short_ref(prefix: str, id_: uuid.UUID) -> str:
    return f"{prefix}_{id_.hex[:8]}"


class ContextCompiler:
    def __init__(
        self,
        session: AsyncSession,
        *,
        memory: MemoryService | None = None,
        engine: RulesEngine | None = None,
        strict: bool = True,
    ) -> None:
        self.session = session
        self.perspective = PerspectiveService(session)
        self.memory = memory
        self.engine = engine
        self.strict = strict  # development: denied items abort

    async def compile(
        self,
        h: CampaignHandle,
        role_name: str,
        *,
        actor_id: uuid.UUID | None,
        purpose: str,
        situation: str,
        query: str | None = None,
        focus_entity_ids: list[uuid.UUID] | None = None,
        extra_sections: dict[str, str] | None = None,
        extra_items: list[ContextItemDraft] | None = None,
        now_tick: int | None = None,
    ) -> CompiledContext:
        spec = role_spec(role_name)
        items: list[ContextItemDraft] = []
        ref_map: dict[str, uuid.UUID] = {}
        if spec.actor_scoped:
            if actor_id is None:
                raise ValueError(f"role {role_name} is actor-scoped; actor_id required")
            items += await self._actor_items(
                spec, actor_id, query or situation, focus_entity_ids or [], ref_map, now_tick
            )
        for section, text in (extra_sections or {}).items():
            items.append(
                ContextItemDraft(
                    section,
                    "supplied",
                    None,
                    actor_id,
                    text,
                    reason="supplied by orchestrator",
                    # an objective role's sections are engine-built (no actor's perspective
                    # to protect); an actor-scoped role only gets the listed public ones
                    public=not spec.actor_scoped
                    or section
                    in (
                        "style",
                        "rules_public",
                        "available_actions",
                        "resolved_mechanics",
                        "candidates",
                        "situation",
                    ),
                )
            )
        items += list(extra_items or [])
        items.append(
            ContextItemDraft(
                "situation",
                "situation",
                None,
                actor_id,
                situation,
                reason="this request",
                public=True,
            )
        )
        # authorization audit before anything else
        allowed = [
            i
            for i in items
            if spec.allowed_context
            and i.section in spec.allowed_context
            or i.section == "situation"
        ]
        dropped = [i for i in items if i not in allowed]
        for d in dropped:
            d.metadata["dropped"] = "section not allowed for role"
        denied = [i for i in allowed if i.authorization(actor_id) == "denied"]
        # budget fit
        budget = PROFILE_BUDGET_TOKENS.get(spec.profile, 8000) - spec.max_tokens
        kept = self._fit(allowed, budget)
        rendered, stable_chars, sections = self._render(kept)
        snapshot = ContextSnapshot(
            campaign_id=h.campaign_id,
            timeline_id=h.timeline_id,
            role=spec.name,
            actor_id=actor_id,
            purpose=purpose,
            authorization_scope={
                "actor_scoped": spec.actor_scoped,
                "allowed_sections": sorted(spec.allowed_context),
                "ref_map": {k: str(v) for k, v in ref_map.items()},
                "denied": len(denied),
                "dropped": len(dropped),
            },
            rendered_context=rendered,
            estimated_tokens=estimate_tokens(rendered),
            stable_prefix_chars=stable_chars,
        )
        self.session.add(snapshot)
        await self.session.flush()
        for i in items:
            self.session.add(
                ContextItem(
                    snapshot_id=snapshot.id,
                    source_type=i.source_type,
                    source_id=i.source_id,
                    owner_actor_id=i.owner_actor_id,
                    reason=i.reason,
                    retrieval_score=i.score,
                    authorization=i.authorization(actor_id) if i in allowed else "dropped",
                    section=i.section,
                    metadata_={**i.metadata, "kept": i in kept},
                )
            )
        await self.session.flush()
        if denied and self.strict:
            raise ContextAuthorizationError(snapshot.id, denied)
        return CompiledContext(
            snapshot.id,
            spec,
            actor_id,
            rendered,
            stable_chars,
            estimate_tokens(rendered),
            kept,
            ref_map,
            sections,
        )

    # -- actor-scoped sources ----------------------------------------------------------------------

    async def _actor_items(
        self,
        spec: RoleSpec,
        actor_id: uuid.UUID,
        query: str,
        focus: list[uuid.UUID],
        ref_map: dict[str, uuid.UUID],
        now_tick: int | None,
    ) -> list[ContextItemDraft]:
        p = self.perspective
        repo = p.repo
        actor = await repo.actor(actor_id)
        if actor is None:
            raise ValueError("unknown actor")
        own = actor_id
        items: list[ContextItemDraft] = []
        names = await p.known_entities(actor_id)
        self_name = names.get(actor.entity_id) or await repo.self_name(actor_id) or "you"
        names.setdefault(
            actor.entity_id, self_name
        )  # own beliefs read "Renn killed", not "someone"
        profile = actor.mechanical_profile or {}
        behavior = actor.behavior_profile or {}

        # identity + behaviour (stable)
        ident = [f"You are {behavior.get('name') or self_name}."]
        if behavior.get("summary"):
            ident.append(behavior["summary"])
        items.append(
            ContextItemDraft(
                "identity", "actor", str(actor_id), own, " ".join(ident), reason="own identity"
            )
        )
        known = sorted(v for k, v in names.items() if k != actor.entity_id)
        if known:
            items.append(
                ContextItemDraft(
                    "known_entities",
                    "identity_knowledge",
                    str(actor_id),
                    own,
                    "People and places you know by name: " + ", ".join(known),
                    reason="own identity knowledge",
                )
            )
        dims = behavior.get("dimensions") or {}
        if dims or behavior.get("traits"):
            lines = []
            if behavior.get("traits"):
                lines.append("Traits: " + ", ".join(behavior["traits"]))
            if dims:
                lines.append("Dimensions (0-1): " + ", ".join(f"{k} {v}" for k, v in dims.items()))
            items.append(
                ContextItemDraft(
                    "behavior",
                    "behavior_profile",
                    str(actor_id),
                    own,
                    "\n".join(lines),
                    reason="own behaviour profile",
                )
            )
        # player-agent mechanics (own sheet; never another actor's)
        if self.engine is not None and profile:
            try:
                st = self.engine.actor(
                    str(actor_id),
                    {
                        k: v
                        for k, v in profile.items()
                        if k in ("attributes", "skills", "traits", "capabilities", "tags")
                    },
                )
                res = await repo.own_resources(actor.entity_id)
                sheet = [
                    "Attributes: "
                    + ", ".join(f"{k.split('.')[1]} {v}" for k, v in st.attributes.items()),
                    "Skills: "
                    + (", ".join(f"{k.split('.')[1]} {v}" for k, v in st.skills.items()) or "none"),
                    "Resources: "
                    + (
                        ", ".join(
                            f"{r.resource_key.split('.')[1]} {r.current}/{r.max_value}" for r in res
                        )
                        or "n/a"
                    ),
                ]
                items.append(
                    ContextItemDraft(
                        "mechanics_player_layer",
                        "sheet",
                        str(actor_id),
                        own,
                        "\n".join(sheet),
                        reason="own sheet (player-agent layer)",
                    )
                )
            except Exception as exc:  # noqa: BLE001 - a broken profile must not block a turn
                items.append(
                    ContextItemDraft(
                        "mechanics_player_layer",
                        "sheet",
                        str(actor_id),
                        own,
                        f"(sheet unavailable: {exc})",
                        reason="own sheet",
                    )
                )
        # goals (goals table; behaviour-profile strings as a fallback) / emotions / relationships
        goal_rows = await repo.goals(actor_id)
        goals = [g.description for g in goal_rows] or list(behavior.get("goals") or [])
        for i, g in enumerate(goal_rows):
            ref_map[f"g{i + 1}"] = g.id
        if goals:
            items.append(
                ContextItemDraft(
                    "goals_own",
                    "goals",
                    ",".join(str(g.id) for g in goal_rows) or str(actor_id),
                    own,
                    "Goals: " + "; ".join(f"g{i + 1} {g}" for i, g in enumerate(goals)),
                    reason="own goals",
                )
            )
        emotions = await repo.emotions(actor_id)
        if emotions:
            items.append(
                ContextItemDraft(
                    "emotions_own",
                    "emotions",
                    str(actor_id),
                    own,
                    "Current feelings: "
                    + ", ".join(f"{e.emotion_key} {float(e.intensity):.2f}" for e in emotions),
                    reason="own emotion state",
                )
            )
        rels = await repo.relationships_from(actor_id)
        if rels:
            lines = []
            for r in rels:
                nm = names.get(r.target_entity_id) or "someone"
                lines.append(
                    f"{nm}: trust {r.trust} respect {r.respect} affection {r.affection} "
                    f"fear {r.fear} familiarity {r.familiarity}"
                )
            items.append(
                ContextItemDraft(
                    "relationships_own",
                    "relationships",
                    str(actor_id),
                    own,
                    "Relationships (yours -> them): " + "; ".join(lines),
                    reason="own relationships",
                )
            )
        # core memories (stable) + retrieved memories (per turn)
        if self.memory is not None:
            core = await self.memory.retrieve(actor_id, "", k=6, now_tick=now_tick, rerank=False)
            core = [m for m in core if m.is_core]
            if core:
                items.append(
                    ContextItemDraft(
                        "core_memories",
                        "memory",
                        ",".join(str(m.memory_id) for m in core),
                        own,
                        "Core memories: " + " | ".join(m.summary for m in core),
                        reason="core memories",
                    )
                )
            if query.strip():
                rec = await self.memory.retrieve(
                    actor_id, query, k=5, focus_entity_ids=focus, now_tick=now_tick
                )
                for m in rec:
                    if not m.is_core:
                        items.append(
                            ContextItemDraft(
                                "memories",
                                "memory",
                                str(m.memory_id),
                                own,
                                m.summary,
                                reason="; ".join(m.reasons),
                                score=m.score,
                            )
                        )
        # beliefs with ids the model may reference
        beliefs = await p.beliefs(actor_id)
        for b in beliefs:
            if b.belief_type == "known" and b.proposition.get("predicate") == "asserted":
                continue  # meta-beliefs are noise for decisions
            ref = short_ref("b", b.belief_id)
            ref_map[ref] = b.belief_id
            prop = b.proposition
            subj = _name_or_unknown(names, prop.get("subject_entity_id"))
            obj = _name_or_unknown(names, prop.get("object_entity_id"))
            text = f"{ref}: {subj} {prop.get('predicate')} {obj} {prop.get('value') or ''}".replace(
                "  ", " "
            ).strip()
            text += f" — {b.belief_type} {b.confidence:.2f}" + (
                f" (from {b.source_known_as})" if b.source_known_as else ""
            )
            if b.fact_id is not None and b.belief_type == "known":
                fref = short_ref("f", b.fact_id)
                ref_map[fref] = b.fact_id
                text += f" [fact {fref}]"
            items.append(
                ContextItemDraft(
                    "beliefs",
                    "belief",
                    str(b.belief_id),
                    own,
                    text,
                    reason="own belief",
                    score=b.confidence,
                    metadata={"status": b.status},
                )
            )
        # inventory (public properties only)
        inv = await p.inventory(actor_id)
        if inv:
            items.append(
                ContextItemDraft(
                    "inventory_public",
                    "inventory",
                    str(actor_id),
                    own,
                    "Carrying: " + "; ".join(_item_line(i) for i in inv),
                    reason="own inventory, public properties",
                )
            )
        # scene (per turn)
        scene = await p.scene_view(actor_id)
        if scene is not None:
            parts = ", ".join(_participant_line(x) for x in scene.participants if not x.is_self)
            items.append(
                ContextItemDraft(
                    "scene",
                    "scene",
                    str(scene.scene_id),
                    own,
                    f"Scene: {scene.location_known_as or 'an unfamiliar place'} "
                    f"({scene.scene_type}). "
                    f"You are at {scene.space_zone or 'here'}. "
                    f"Present: {parts or 'no one else you can see'}.",
                    reason="perspective-safe scene view",
                )
            )
        # recent observations / heard dialogue (per turn)
        obs = await p.recent_observations(actor_id, limit=12)
        for idx, o in enumerate(obs):
            section = "observations" if o["type"] != "heard_claim" else "heard_claims"
            items.append(
                ContextItemDraft(
                    section,
                    "observation",
                    None,
                    own,
                    f"[t{o['tick']}] {o['rendered']}",
                    reason="own recent observation",
                    score=round((idx + 1) / len(obs), 4),  # recency rank 0..1
                    metadata={"tick": o["tick"]},
                )
            )
        return items

    # -- fitting / rendering --------------------------------------------------------------------

    @staticmethod
    def _fit(items: list[ContextItemDraft], budget_tokens: int) -> list[ContextItemDraft]:
        kept = list(items)
        total = sum(estimate_tokens(i.text) for i in kept)
        for section in TRIM_ORDER:
            while total > budget_tokens:
                victims = [i for i in kept if i.section == section]
                if not victims:
                    break
                v = min(victims, key=lambda i: i.score if i.score is not None else 0.0)
                kept.remove(v)
                total -= estimate_tokens(v.text)
        return kept

    @staticmethod
    def _render(items: list[ContextItemDraft]) -> tuple[str, int, dict[str, str]]:
        by: dict[str, list[ContextItemDraft]] = {}
        for i in items:
            by.setdefault(i.section, []).append(i)
        sections: dict[str, str] = {}
        chunks: list[str] = []
        stable_chars = 0
        for section in SECTION_ORDER:
            if section not in by:
                continue
            body = "\n".join(i.text for i in by[section])
            sections[section] = body
            chunk = f"## {section.replace('_', ' ')}\n{body}"
            chunks.append(chunk)
            if section in STABLE_SECTIONS:
                stable_chars += len(chunk) + 2
        for section in by:  # any custom sections last
            if section not in SECTION_ORDER:
                body = "\n".join(i.text for i in by[section])
                sections[section] = body
                chunks.append(f"## {section}\n{body}")
        return "\n\n".join(chunks), stable_chars, sections


def _item_line(i: Any) -> str:
    desc = i.public_properties.get("description")
    equipped = " (equipped)" if i.equipped else ""
    return f"{i.name or i.template_key}{equipped}{': ' + desc if desc else ''}"


def _participant_line(x: Any) -> str:
    conds = ", ".join(c.split(".")[1] for c in x.visible_conditions)
    return f"{x.known_as}{' (' + conds + ')' if conds else ''}{' @' + x.zone if x.zone else ''}"


def _name_or_unknown(names: dict[uuid.UUID, str], raw: Any) -> str:
    """Render an entity reference by the actor's own name for it; an unknown id becomes
    'someone' rather than leaking a UUID into the prompt."""
    if not raw:
        return ""
    u = _uuid(raw)
    if u is None:
        return str(raw)  # free-text subject from a proposition
    return names.get(u) or "someone"


def _uuid(v: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(v)) if v else None
    except ValueError:
        return None
