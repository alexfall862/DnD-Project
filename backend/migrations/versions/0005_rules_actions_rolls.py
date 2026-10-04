"""rules metadata, rolls, intents/actions/steps/traces, pending clarifications (database-schema.md §9, §10, §14)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('rulesets',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('version', sa.Text(), nullable=False),
    sa.Column('engine_schema_version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('manifest', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('installed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key', 'version', name='uq_rulesets_key_version')
    )
    op.create_table('rule_modules',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('ruleset_id', sa.UUID(), nullable=False),
    sa.Column('module_key', sa.Text(), nullable=False),
    sa.Column('module_type', sa.String(length=32), nullable=False),
    sa.Column('version', sa.Text(), nullable=False),
    sa.Column('precedence', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('definition', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['ruleset_id'], ['rulesets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rule_modules_ruleset', 'rule_modules', ['ruleset_id'], unique=False)
    op.create_table('mechanical_definitions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('ruleset_id', sa.UUID(), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=True),
    sa.Column('definition_key', sa.Text(), nullable=False),
    sa.Column('definition_type', sa.String(length=32), nullable=False),
    sa.Column('source_kind', sa.String(length=32), server_default='ruleset', nullable=False),
    sa.Column('source_ref', sa.Text(), nullable=True),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('status', sa.String(length=32), server_default='active', nullable=False),
    sa.Column('definition', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('power', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_event_id', sa.UUID(), nullable=True),
    sa.Column('established_event_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['established_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['ruleset_id'], ['rulesets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mechanical_definitions_campaign_key', 'mechanical_definitions', ['campaign_id', 'definition_key'], unique=False)
    op.create_table('ruling_precedents',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('mechanical_definition_id', sa.UUID(), nullable=True),
    sa.Column('scope', sa.String(length=32), server_default='single_use', nullable=False),
    sa.Column('usage_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('created_event_id', sa.UUID(), nullable=True),
    sa.Column('last_used_event_id', sa.UUID(), nullable=True),
    sa.Column('embedding_meta', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['last_used_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['mechanical_definition_id'], ['mechanical_definitions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ruling_precedents_campaign', 'ruling_precedents', ['campaign_id'], unique=False)
    op.create_table('rolls',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=False),
    sa.Column('timeline_id', sa.UUID(), nullable=False),
    sa.Column('event_id', sa.UUID(), nullable=True),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('expression', sa.Text(), nullable=False),
    sa.Column('seed', sa.BigInteger(), nullable=False),
    sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('kept', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('modifier', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('final_result', sa.Integer(), nullable=False),
    sa.Column('purpose', sa.Text(), server_default='', nullable=False),
    sa.Column('visibility', sa.String(length=16), server_default='public', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['actors.id'], ),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['timeline_id'], ['timelines.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rolls_event', 'rolls', ['event_id'], unique=False)
    op.create_index('ix_rolls_timeline', 'rolls', ['timeline_id'], unique=False)
    op.create_table('intents',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=False),
    sa.Column('timeline_id', sa.UUID(), nullable=False),
    sa.Column('scene_id', sa.UUID(), nullable=True),
    sa.Column('actor_id', sa.UUID(), nullable=False),
    sa.Column('source_message_id', sa.UUID(), nullable=True),
    sa.Column('intent_type', sa.String(length=32), nullable=False),
    sa.Column('natural_text', sa.Text(), nullable=True),
    sa.Column('structured', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('status', sa.String(length=32), server_default='proposed', nullable=False),
    sa.Column('based_on_world_version', sa.BigInteger(), nullable=True),
    sa.Column('based_on_scene_version', sa.BigInteger(), nullable=True),
    sa.Column('turn_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['actors.id'], ),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ),
    sa.ForeignKeyConstraint(['source_message_id'], ['transcript_messages.id'], ),
    sa.ForeignKeyConstraint(['timeline_id'], ['timelines.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_intents_scene', 'intents', ['scene_id'], unique=False)
    op.create_index('ix_intents_turn', 'intents', ['turn_id'], unique=False)
    op.create_table('actions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=False),
    sa.Column('intent_id', sa.UUID(), nullable=True),
    sa.Column('actor_id', sa.UUID(), nullable=False),
    sa.Column('scene_id', sa.UUID(), nullable=True),
    sa.Column('action_key', sa.Text(), nullable=False),
    sa.Column('target_ref', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('requirements', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('costs', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('effects', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('based_on_scene_version', sa.BigInteger(), nullable=True),
    sa.Column('start_event_id', sa.UUID(), nullable=True),
    sa.Column('resolution_event_id', sa.UUID(), nullable=True),
    sa.Column('turn_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['actors.id'], ),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['intent_id'], ['intents.id'], ),
    sa.ForeignKeyConstraint(['resolution_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ),
    sa.ForeignKeyConstraint(['start_event_id'], ['events.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_actions_actor', 'actions', ['actor_id'], unique=False)
    op.create_index('ix_actions_scene', 'actions', ['scene_id'], unique=False)
    op.create_table('action_steps',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('action_id', sa.UUID(), nullable=False),
    sa.Column('order_index', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('resolved_event_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['action_id'], ['actions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['resolved_event_id'], ['events.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_action_steps_action', 'action_steps', ['action_id'], unique=False)
    op.create_table('reaction_windows',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('action_id', sa.UUID(), nullable=False),
    sa.Column('trigger_step_id', sa.UUID(), nullable=True),
    sa.Column('trigger', sa.String(length=32), nullable=False),
    sa.Column('rules', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('status', sa.String(length=32), server_default='closed', nullable=False),
    sa.Column('chosen', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('opened_event_id', sa.UUID(), nullable=True),
    sa.Column('closed_event_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['action_id'], ['actions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['closed_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['opened_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['trigger_step_id'], ['action_steps.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('reaction_eligible_actors',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('window_id', sa.UUID(), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=False),
    sa.Column('action_key', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['actor_id'], ['actors.id'], ),
    sa.ForeignKeyConstraint(['window_id'], ['reaction_windows.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###
    op.create_table('resolution_traces',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('action_id', sa.UUID(), nullable=False),
    sa.Column('rules_consulted', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('requirements', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('modifiers', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('roll_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('effects_applied', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('effects_rejected', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('summary', sa.Text(), server_default='', nullable=False),
    sa.Column('trace', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.ForeignKeyConstraint(['action_id'], ['actions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('action_id')
    )
    op.create_table('pending_clarifications',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=False),
    sa.Column('scene_id', sa.UUID(), nullable=True),
    sa.Column('actor_id', sa.UUID(), nullable=False),
    sa.Column('clarification_id', sa.UUID(), nullable=False),
    sa.Column('original_input', sa.Text(), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('candidate_entity_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('reason', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='open', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['actor_id'], ['actors.id'], ),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('clarification_id')
    )
    op.create_index('uq_pending_clarifications_open', 'pending_clarifications', ['actor_id'], unique=True, postgresql_where=sa.text("status = 'open'"))


def downgrade() -> None:
    op.drop_table("pending_clarifications")
    op.drop_table("resolution_traces")
    op.drop_table("reaction_eligible_actors")
    op.drop_table("reaction_windows")
    op.drop_table("action_steps")
    op.drop_table("actions")
    op.drop_table("intents")
    op.drop_table("rolls")
    op.drop_table("ruling_precedents")
    op.drop_table("mechanical_definitions")
    op.drop_table("rule_modules")
    op.drop_table("rulesets")
