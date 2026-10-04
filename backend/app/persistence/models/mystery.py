"""Mysteries and clues (database-schema.md §13; world-memory §13; migration 0012).

A `Mystery` is objective: its answer is the set of `MysteryTruthFact` rows, locked at activation
(Invariant 10). A `Clue` is a route by which one supported Fact may be learned. A
`ClueDiscovery` records that one actor learned it, how (`route`), and at what `fidelity`;
testimony discoveries point at the Claim that conveyed it. Nothing here is perspective state:
what an actor *believes* about the fact lives in `beliefs`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.models.base import Base, created_at_col, jsonb_col, uuid_pk


class Mystery(Base):
    __tablename__ = "mysteries"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str | None] = mapped_column(Text)  # stable symbolic key for fixtures/tests
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="latent"
    )  # latent|active|solved|failed|abandoned
    solution_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    stakeholders: Mapped[dict[str, Any]] = jsonb_col("[]")
    consequences: Mapped[dict[str, Any]] = jsonb_col()
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    activated_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    resolved_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        Index(
            "uq_mysteries_campaign_key",
            "campaign_id",
            "key",
            unique=True,
            postgresql_where=text("key IS NOT NULL"),
        ),
    )


class MysteryTruthFact(Base):
    """Join: the objective answer. Locked mysteries refuse replacement of these rows."""

    __tablename__ = "mystery_truth_facts"

    mystery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mysteries.id", ondelete="CASCADE"), primary_key=True
    )
    fact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facts.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, server_default="answer")


class Clue(Base):
    __tablename__ = "clues"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    mystery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mysteries.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str | None] = mapped_column(Text)
    clue_type: Mapped[str] = mapped_column(String(16), nullable=False)  # physical|document|social
    supported_fact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facts.id"))
    physical_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    reliability: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("1.0")
    )
    discovery_conditions: Mapped[dict[str, Any]] = jsonb_col()
    destructible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    forgeable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="intact"
    )  # intact|destroyed
    created_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    destroyed_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        Index("ix_clues_mystery", "mystery_id"),
        Index("ix_clues_supported_fact", "supported_fact_id"),
        Index("ix_clues_physical_entity", "physical_entity_id"),
        Index(
            "uq_clues_campaign_key",
            "campaign_id",
            "key",
            unique=True,
            postgresql_where=text("key IS NOT NULL"),
        ),
    )


class ClueDiscovery(Base):
    __tablename__ = "clue_discoveries"

    id: Mapped[uuid.UUID] = uuid_pk()
    clue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clues.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actors.id", ondelete="CASCADE"), nullable=False
    )
    discovery_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    route: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # physical|document|testimony|inference|mechanic
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id"))
    fidelity: Mapped[str] = mapped_column(String(16), nullable=False, server_default="full")
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("clue_id", "actor_id", "route", "fidelity", name="uq_clue_discovery"),
        Index("ix_clue_discoveries_actor", "actor_id"),
    )
