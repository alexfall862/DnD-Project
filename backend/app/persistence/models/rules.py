"""Rules metadata, rolls, intents/actions/traces, pending clarifications
(database-schema.md §9 rolls/pending_clarifications, §10, §14; migration 0005)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, created_at_col, jsonb_col, uuid_pk


class RulesetRecord(Base):
    __tablename__ = "rulesets"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    engine_schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    manifest: Mapped[dict[str, Any]] = jsonb_col()
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    installed_at: Mapped[datetime] = created_at_col()

    __table_args__ = (UniqueConstraint("key", "version", name="uq_rulesets_key_version"),)


class RuleModule(Base):
    __tablename__ = "rule_modules"

    id: Mapped[uuid.UUID] = uuid_pk()
    ruleset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rulesets.id", ondelete="CASCADE"), nullable=False
    )
    module_key: Mapped[str] = mapped_column(Text, nullable=False)
    module_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    precedence: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    definition: Mapped[dict[str, Any]] = jsonb_col()
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (Index("ix_rule_modules_ruleset", "ruleset_id"),)


class MechanicalDefinition(Base):
    """Generated / campaign-specific mechanics with snapshot semantics (rules-engine §35)."""

    __tablename__ = "mechanical_definitions"

    id: Mapped[uuid.UUID] = uuid_pk()
    ruleset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rulesets.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    definition_key: Mapped[str] = mapped_column(Text, nullable=False)
    definition_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="ruleset")
    source_ref: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    definition: Mapped[dict[str, Any]] = jsonb_col()
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    power: Mapped[dict[str, Any]] = jsonb_col()
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    established_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))

    __table_args__ = (
        Index("ix_mechanical_definitions_campaign_key", "campaign_id", "definition_key"),
    )


class RulingPrecedent(Base):
    __tablename__ = "ruling_precedents"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    mechanical_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("mechanical_definitions.id")
    )
    scope: Mapped[str] = mapped_column(String(32), nullable=False, server_default="single_use")
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    last_used_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    embedding_meta: Mapped[dict[str, Any]] = jsonb_col()

    __table_args__ = (Index("ix_ruling_precedents_campaign", "campaign_id"),)


class Roll(Base):
    """Every random number the engine produced (rules-engine §8). Replayable from `seed`."""

    __tablename__ = "rolls"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    timeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actors.id"))
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    kept: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    modifier: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    final_result: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, server_default="public")
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        Index("ix_rolls_event", "event_id"),
        Index("ix_rolls_timeline", "timeline_id"),
    )


class Intent(Base):
    __tablename__ = "intents"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    timeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("timelines.id", ondelete="CASCADE"), nullable=False
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenes.id"))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), nullable=False)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transcript_messages.id")
    )
    intent_type: Mapped[str] = mapped_column(String(32), nullable=False)
    natural_text: Mapped[str | None] = mapped_column(Text)
    structured: Mapped[dict[str, Any]] = jsonb_col()
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="proposed")
    based_on_world_version: Mapped[int | None] = mapped_column(BigInteger)
    based_on_scene_version: Mapped[int | None] = mapped_column(BigInteger)
    turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_intents_scene", "scene_id"), Index("ix_intents_turn", "turn_id"))


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    intent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("intents.id"))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), nullable=False)
    scene_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenes.id"))
    action_key: Mapped[str] = mapped_column(Text, nullable=False)
    target_ref: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    params: Mapped[dict[str, Any]] = jsonb_col()
    requirements: Mapped[dict[str, Any]] = jsonb_col()
    costs: Mapped[dict[str, Any]] = jsonb_col()
    effects: Mapped[dict[str, Any]] = jsonb_col()
    reason: Mapped[str | None] = mapped_column(Text)
    based_on_scene_version: Mapped[int | None] = mapped_column(BigInteger)
    start_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    resolution_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_actions_scene", "scene_id"), Index("ix_actions_actor", "actor_id"))


class ActionStep(Base):
    __tablename__ = "action_steps"

    id: Mapped[uuid.UUID] = uuid_pk()
    action_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actions.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = jsonb_col()
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    resolved_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))

    __table_args__ = (Index("ix_action_steps_action", "action_id"),)


class ReactionWindowRecord(Base):
    __tablename__ = "reaction_windows"

    id: Mapped[uuid.UUID] = uuid_pk()
    action_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actions.id", ondelete="CASCADE"), nullable=False
    )
    trigger_step_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("action_steps.id"))
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    rules: Mapped[dict[str, Any]] = jsonb_col()
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="closed")
    chosen: Mapped[dict[str, Any]] = jsonb_col()
    opened_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    closed_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))


class ReactionEligibleActor(Base):
    __tablename__ = "reaction_eligible_actors"

    id: Mapped[uuid.UUID] = uuid_pk()
    window_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reaction_windows.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), nullable=False)
    action_key: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)


class ResolutionTraceRecord(Base):
    __tablename__ = "resolution_traces"

    id: Mapped[uuid.UUID] = uuid_pk()
    action_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    rules_consulted: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    requirements: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    modifiers: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    roll_ids: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    effects_applied: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    effects_rejected: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    trace: Mapped[dict[str, Any]] = jsonb_col()


class PendingClarification(Base):
    __tablename__ = "pending_clarifications"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenes.id"))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), nullable=False)
    clarification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    original_input: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_entity_ids: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    reason: Mapped[str] = mapped_column(String(32), nullable=False)  # AMBIGUOUS | ASSERTION_REFUSED
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    created_at: Mapped[datetime] = created_at_col()
    resolved_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        Index(
            "uq_pending_clarifications_open",
            "actor_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )


_ = Numeric  # keep import for future precision columns
