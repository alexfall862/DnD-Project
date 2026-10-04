"""scenes, events, transcript, scheduled events + deferred FKs + local_tick guard
(database-schema.md §6–§8, §22; time-accounting.md §3)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
EMPTY = sa.text("'{}'::jsonb")
NOW = sa.text("now()")
GEN_UUID = sa.text("gen_random_uuid()")

# (constraint name, table, column) — FKs to events.id that earlier migrations deferred.
DEFERRED_EVENT_FKS: list[tuple[str, str, str]] = [
    ("fk_timelines_branch_event", "timelines", "branch_event_id"),
    ("fk_entities_created_event", "entities", "created_event_id"),
    ("fk_entities_established_event", "entities", "established_event_id"),
    ("fk_location_edges_created_event", "location_edges", "created_event_id"),
    ("fk_actors_updated_event", "actors", "updated_event_id"),
    ("fk_actor_controllers_from_event", "actor_controllers", "valid_from_event_id"),
    ("fk_actor_controllers_until_event", "actor_controllers", "valid_until_event_id"),
    ("fk_factions_created_event", "factions", "created_event_id"),
    ("fk_faction_memberships_joined_event", "faction_memberships", "joined_event_id"),
    ("fk_faction_memberships_left_event", "faction_memberships", "left_event_id"),
    ("fk_parties_created_event", "parties", "created_event_id"),
    ("fk_party_memberships_joined_event", "party_memberships", "joined_event_id"),
    ("fk_party_memberships_left_event", "party_memberships", "left_event_id"),
    ("fk_scenes_start_event", "scenes", "start_event_id"),
    ("fk_scenes_end_event", "scenes", "end_event_id"),
    ("fk_scene_participants_joined_event", "scene_participants", "joined_event_id"),
    ("fk_scene_participants_left_event", "scene_participants", "left_event_id"),
]

LOCAL_TICK_GUARD = """
CREATE OR REPLACE FUNCTION scenes_local_tick_guard() RETURNS trigger AS $$
DECLARE
    clock_tick BIGINT;
BEGIN
    SELECT current_tick INTO clock_tick FROM world_clocks WHERE timeline_id = NEW.timeline_id;
    IF clock_tick IS NOT NULL AND NEW.local_tick > clock_tick THEN
        RAISE EXCEPTION 'scenes.local_tick (%) may not exceed world clock (%) for timeline %',
            NEW.local_tick, clock_tick, NEW.timeline_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "scenes",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("timeline_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=True),
        sa.Column("scene_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("start_event_id", sa.UUID(), nullable=True),
        sa.Column("end_event_id", sa.UUID(), nullable=True),
        sa.Column("start_tick", sa.BigInteger(), nullable=True),
        sa.Column("end_tick", sa.BigInteger(), nullable=True),
        sa.Column("version", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("local_tick", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("merged_from", postgresql.ARRAY(sa.UUID()), nullable=True),
        sa.Column("state", JSONB, server_default=EMPTY, nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scenes_location", "scenes", ["location_id"])
    op.create_index("ix_scenes_timeline_status", "scenes", ["timeline_id", "status"])

    op.create_table(
        "events",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("timeline_id", sa.UUID(), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("game_tick", sa.BigInteger(), nullable=False),
        sa.Column("scene_id", sa.UUID(), nullable=True),
        sa.Column("location_id", sa.UUID(), nullable=True),
        sa.Column("cause_event_id", sa.UUID(), nullable=True),
        sa.Column("created_by_type", sa.String(32), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("payload", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("world_version_after", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cause_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("timeline_id", "sequence_number", name="uq_events_timeline_sequence"),
    )
    op.create_index("ix_events_campaign_type", "events", ["campaign_id", "event_type"])
    op.create_index("ix_events_scene", "events", ["scene_id"])
    op.create_index("ix_events_timeline_tick", "events", ["timeline_id", "game_tick"])

    op.create_table(
        "event_entities",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_entities_entity", "event_entities", ["entity_id"])
    op.create_index("ix_event_entities_event", "event_entities", ["event_id"])

    op.create_table(
        "scene_participants",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("scene_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("zone_key", sa.String(64), nullable=True),
        sa.Column("position_state", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("joined_event_id", sa.UUID(), nullable=True),
        sa.Column("left_event_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scene_participants_actor", "scene_participants", ["actor_id"])
    op.create_index(
        "uq_scene_participants_active",
        "scene_participants",
        ["scene_id", "actor_id"],
        unique=True,
        postgresql_where=sa.text("left_event_id IS NULL"),
    )

    op.create_table(
        "transcript_messages",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("timeline_id", sa.UUID(), nullable=False),
        sa.Column("scene_id", sa.UUID(), nullable=True),
        sa.Column("speaker_actor_id", sa.UUID(), nullable=True),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("game_tick", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("turn_id", sa.UUID(), nullable=True),
        sa.Column("event_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
        sa.ForeignKeyConstraint(["speaker_actor_id"], ["actors.id"]),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transcript_scene", "transcript_messages", ["scene_id"])
    op.create_index("ix_transcript_turn", "transcript_messages", ["turn_id"])

    op.create_table(
        "transcript_recipients",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["transcript_messages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transcript_recipients_message", "transcript_recipients", ["message_id"])

    op.create_table(
        "scheduled_events",
        sa.Column("id", sa.UUID(), server_default=GEN_UUID, nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("timeline_id", sa.UUID(), nullable=False),
        sa.Column("scheduled_tick", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("created_event_id", sa.UUID(), nullable=True),
        sa.Column("processed_event_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["processed_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scheduled_events_due", "scheduled_events", ["timeline_id", "status", "scheduled_tick"]
    )

    # Deferred foreign keys now that events/scenes exist.
    for name, table, column in DEFERRED_EVENT_FKS:
        op.create_foreign_key(name, table, "events", [column], ["id"])
    op.create_foreign_key(
        "fk_actors_current_scene", "actors", "scenes", ["current_scene_id"], ["id"]
    )

    # scenes.local_tick <= world clock (time-accounting.md §3, §7).
    op.execute(LOCAL_TICK_GUARD)
    op.execute(
        "CREATE TRIGGER trg_scenes_local_tick_guard BEFORE INSERT OR UPDATE OF local_tick "
        "ON scenes FOR EACH ROW EXECUTE FUNCTION scenes_local_tick_guard()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_scenes_local_tick_guard ON scenes")
    op.execute("DROP FUNCTION IF EXISTS scenes_local_tick_guard()")
    op.drop_constraint("fk_actors_current_scene", "actors", type_="foreignkey")
    for name, table, _column in DEFERRED_EVENT_FKS:
        if table not in {"scenes", "scene_participants"}:  # dropped with their tables below
            op.drop_constraint(name, table, type_="foreignkey")

    op.drop_index("ix_scheduled_events_due", table_name="scheduled_events")
    op.drop_table("scheduled_events")
    op.drop_index("ix_transcript_recipients_message", table_name="transcript_recipients")
    op.drop_table("transcript_recipients")
    op.drop_index("ix_transcript_turn", table_name="transcript_messages")
    op.drop_index("ix_transcript_scene", table_name="transcript_messages")
    op.drop_table("transcript_messages")
    op.drop_index(
        "uq_scene_participants_active",
        table_name="scene_participants",
        postgresql_where=sa.text("left_event_id IS NULL"),
    )
    op.drop_index("ix_scene_participants_actor", table_name="scene_participants")
    op.drop_table("scene_participants")
    op.drop_index("ix_event_entities_event", table_name="event_entities")
    op.drop_index("ix_event_entities_entity", table_name="event_entities")
    op.drop_table("event_entities")
    # scenes -> events and events -> scenes reference each other; drop the scene-side FKs first.
    op.drop_constraint("fk_scenes_start_event", "scenes", type_="foreignkey")
    op.drop_constraint("fk_scenes_end_event", "scenes", type_="foreignkey")
    op.drop_index("ix_events_timeline_tick", table_name="events")
    op.drop_index("ix_events_scene", table_name="events")
    op.drop_index("ix_events_campaign_type", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_scenes_timeline_status", table_name="scenes")
    op.drop_index("ix_scenes_location", table_name="scenes")
    op.drop_table("scenes")
