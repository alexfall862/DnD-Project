"""Objective truth vs. subjective perspective (database-schema.md §11, §12 relationships;
migration 0007).

`Fact` is objective. `Claim` is what someone asserted (with speaker-private deception flags).
`Observation` is what one actor perceived of one event. `Belief` is one actor's held
proposition. `EntityIdentityKnowledge` is what an actor calls an entity. Perspective reads go
through `app.persistence.repositories.perspective` only; nothing there selects
`Fact.truth_status` or `Claim.deliberate_false`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, created_at_col, jsonb_col, uuid_pk


class Fact(Base):
    __tablename__ = "facts"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str | None] = mapped_column(Text)  # stable symbolic key for fixtures/tests
    subject_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    predicate: Mapped[str] = mapped_column(Text, nullable=False)
    object_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    object_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    canon_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="latent")
    truth_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="true")
    sensitivity: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="public"
    )  # public|private|secret
    valid_from_tick: Mapped[int | None] = mapped_column(BigInteger)
    valid_until_tick: Mapped[int | None] = mapped_column(BigInteger)
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    established_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    supersedes_fact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facts.id"))
    provenance: Mapped[dict[str, Any]] = jsonb_col()
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        Index("ix_facts_campaign_subject", "campaign_id", "subject_entity_id"),
        Index(
            "uq_facts_campaign_key",
            "campaign_id",
            "key",
            unique=True,
            postgresql_where=text("key IS NOT NULL"),
        ),
    )


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    speaker_actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), nullable=False)
    statement_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    subject_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    predicate: Mapped[str] = mapped_column(Text, nullable=False)
    object_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    object_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    speaker_stance: Mapped[str] = mapped_column(String(16), nullable=False)
    fidelity: Mapped[str] = mapped_column(String(16), nullable=False, server_default="full")
    deliberate_false: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )  # speaker-private
    about_speaker_self: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    source_fact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facts.id"))
    source_belief_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("beliefs.id", use_alter=True, name="fk_claims_source_belief")
    )
    conveyance_source: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # structured|extracted|player_text|document|fixture
    confidence: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("1.0")
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        Index("ix_claims_event", "statement_event_id"),
        Index("ix_claims_speaker", "speaker_actor_id"),
    )


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), nullable=False)
    source_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)  # vision|hearing|touch|...
    observation_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # event|heard_claim|spoke|speech_in_unknown_language|...
    raw: Mapped[dict[str, Any]] = (
        jsonb_col()
    )  # template-generated structure (observation-authoring §2)
    interpreted_text: Mapped[str | None] = mapped_column(Text)  # deterministic rule templates only
    confidence: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("1.0")
    )
    game_tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id"))
    scene_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenes.id"))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        Index("ix_observations_actor_tick", "actor_id", "game_tick"),
        Index("ix_observations_event", "source_event_id"),
    )


class Belief(Base):
    __tablename__ = "beliefs"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), nullable=False)
    fact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facts.id"))
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id"))
    proposition: Mapped[dict[str, Any]] = (
        jsonb_col()
    )  # {subject_entity_id, predicate, object_entity_id, value}
    proposition_key: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # canonical string for matching
    belief_type: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # witnessed|told|read|inferred|stated|seeded|mechanic
    source_actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actors.id"))
    acquired_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    superseded_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    salience: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("0.5")
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(
            "fact_id IS NOT NULL OR claim_id IS NOT NULL OR proposition <> '{}'::jsonb",
            name="ck_beliefs_has_subject",
        ),
        Index("ix_beliefs_actor_status", "actor_id", "status"),
        Index("ix_beliefs_actor_prop", "actor_id", "proposition_key"),
    )


class EntityIdentityKnowledge(Base):
    __tablename__ = "entity_identity_knowledge"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), nullable=False)
    known_name: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("1.0")
    )
    recognized_as_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    learned_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")

    __table_args__ = (
        UniqueConstraint("actor_id", "entity_id", "known_name", name="uq_identity_knowledge"),
        Index("ix_identity_knowledge_actor", "actor_id"),
    )


class Relationship(Base):
    """Directional. Values -100..100 (familiarity 0..100). Changes carry event-linked deltas."""

    __tablename__ = "relationships"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    source_actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), nullable=False)
    target_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), nullable=False)
    trust: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    affection: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    respect: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    fear: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    resentment: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    obligation: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    familiarity: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    qualitative: Mapped[dict[str, Any]] = jsonb_col()
    last_changed_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))

    __table_args__ = (
        UniqueConstraint("source_actor_id", "target_entity_id", name="uq_relationships_pair"),
    )


class RelationshipDelta(Base):
    __tablename__ = "relationship_deltas"

    id: Mapped[uuid.UUID] = uuid_pk()
    relationship_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("relationships.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    dimension: Mapped[str] = mapped_column(String(16), nullable=False)
    delta: Mapped[int] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    __table_args__ = (Index("ix_relationship_deltas_rel", "relationship_id"),)
