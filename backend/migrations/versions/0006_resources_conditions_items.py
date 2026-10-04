"""resource states, condition instances, items, item history, documents (database-schema.md §9)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('resource_states',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('resource_key', sa.Text(), nullable=False),
    sa.Column('current', sa.Integer(), nullable=False),
    sa.Column('max_value', sa.Integer(), nullable=True),
    sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('last_changed_event_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['last_changed_event_id'], ['events.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('entity_id', 'resource_key', name='uq_resource_states_entity_key')
    )
    op.create_table('condition_instances',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('target_entity_id', sa.UUID(), nullable=False),
    sa.Column('condition_key', sa.Text(), nullable=False),
    sa.Column('instance_key', sa.String(length=32), nullable=False),
    sa.Column('intensity', sa.Integer(), server_default='1', nullable=False),
    sa.Column('source_entity_id', sa.UUID(), nullable=True),
    sa.Column('source_ref', sa.Text(), nullable=True),
    sa.Column('source_event_id', sa.UUID(), nullable=True),
    sa.Column('start_tick', sa.BigInteger(), nullable=True),
    sa.Column('expiry_tick', sa.BigInteger(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default='active', nullable=False),
    sa.Column('ended_event_id', sa.UUID(), nullable=True),
    sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.ForeignKeyConstraint(['ended_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['source_entity_id'], ['entities.id'], ),
    sa.ForeignKeyConstraint(['source_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['target_entity_id'], ['entities.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('target_entity_id', 'instance_key', name='uq_condition_instances_instance')
    )
    op.create_index('ix_condition_instances_target', 'condition_instances', ['target_entity_id', 'status'], unique=False)
    op.create_table('items',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('template_key', sa.Text(), nullable=True),
    sa.Column('item_type', sa.String(length=32), server_default='gear', nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('mechanical_snapshot', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('condition_state', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('owner_entity_id', sa.UUID(), nullable=True),
    sa.Column('possessor_entity_id', sa.UUID(), nullable=True),
    sa.Column('container_item_id', sa.UUID(), nullable=True),
    sa.Column('location_id', sa.UUID(), nullable=True),
    sa.Column('zone_key', sa.String(length=64), nullable=True),
    sa.Column('hidden_properties', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('public_properties', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('provenance', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_event_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['container_item_id'], ['items.id'], ),
    sa.ForeignKeyConstraint(['created_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
    sa.ForeignKeyConstraint(['owner_entity_id'], ['entities.id'], ),
    sa.ForeignKeyConstraint(['possessor_entity_id'], ['entities.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('entity_id')
    )
    op.create_index('ix_items_location', 'items', ['location_id'], unique=False)
    op.create_index('ix_items_possessor', 'items', ['possessor_entity_id'], unique=False)
    op.create_table('item_history',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('event_id', sa.UUID(), nullable=False),
    sa.Column('change_type', sa.String(length=32), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_item_history_item', 'item_history', ['item_id'], unique=False)
    op.create_table('documents',
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('original_text', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('author_entity_id', sa.UUID(), nullable=True),
    sa.Column('creation_tick', sa.BigInteger(), nullable=True),
    sa.Column('language', sa.String(length=32), server_default='common', nullable=False),
    sa.Column('cipher', sa.String(length=32), nullable=True),
    sa.Column('conveys', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.ForeignKeyConstraint(['author_entity_id'], ['entities.id'], ),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('item_id')
    )


def downgrade() -> None:
    op.drop_table("documents")
    op.drop_table("item_history")
    op.drop_table("items")
    op.drop_table("condition_instances")
    op.drop_table("resource_states")
