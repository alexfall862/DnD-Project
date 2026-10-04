"""facts, claims, observations, beliefs, identity knowledge, relationships (database-schema.md §11–§12)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-03 19:51:28.709275
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('entity_identity_knowledge',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('known_name', sa.Text(), nullable=False),
    sa.Column('confidence', sa.Numeric(precision=4, scale=3), server_default=sa.text('1.0'), nullable=False),
    sa.Column('recognized_as_entity_id', sa.UUID(), nullable=True),
    sa.Column('learned_event_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default='active', nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['actors.id'], ),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ),
    sa.ForeignKeyConstraint(['learned_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['recognized_as_entity_id'], ['entities.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('actor_id', 'entity_id', 'known_name', name='uq_identity_knowledge')
    )
    op.create_index('ix_identity_knowledge_actor', 'entity_identity_knowledge', ['actor_id'], unique=False)
    op.create_table('facts',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=False),
    sa.Column('key', sa.Text(), nullable=True),
    sa.Column('subject_entity_id', sa.UUID(), nullable=True),
    sa.Column('predicate', sa.Text(), nullable=False),
    sa.Column('object_entity_id', sa.UUID(), nullable=True),
    sa.Column('object_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('canon_status', sa.String(length=16), server_default='latent', nullable=False),
    sa.Column('truth_status', sa.String(length=16), server_default='true', nullable=False),
    sa.Column('sensitivity', sa.String(length=16), server_default='public', nullable=False),
    sa.Column('valid_from_tick', sa.BigInteger(), nullable=True),
    sa.Column('valid_until_tick', sa.BigInteger(), nullable=True),
    sa.Column('created_event_id', sa.UUID(), nullable=True),
    sa.Column('established_event_id', sa.UUID(), nullable=True),
    sa.Column('supersedes_fact_id', sa.UUID(), nullable=True),
    sa.Column('provenance', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['established_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['object_entity_id'], ['entities.id'], ),
    sa.ForeignKeyConstraint(['subject_entity_id'], ['entities.id'], ),
    sa.ForeignKeyConstraint(['supersedes_fact_id'], ['facts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_facts_campaign_subject', 'facts', ['campaign_id', 'subject_entity_id'], unique=False)
    op.create_index('uq_facts_campaign_key', 'facts', ['campaign_id', 'key'], unique=True, postgresql_where=sa.text('key IS NOT NULL'))
    op.create_table('relationships',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=False),
    sa.Column('source_actor_id', sa.UUID(), nullable=False),
    sa.Column('target_entity_id', sa.UUID(), nullable=False),
    sa.Column('trust', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('affection', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('respect', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('fear', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('resentment', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('obligation', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('familiarity', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('qualitative', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('last_changed_event_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['last_changed_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['source_actor_id'], ['actors.id'], ),
    sa.ForeignKeyConstraint(['target_entity_id'], ['entities.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_actor_id', 'target_entity_id', name='uq_relationships_pair')
    )
    op.create_table('claims',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=False),
    sa.Column('speaker_actor_id', sa.UUID(), nullable=False),
    sa.Column('statement_event_id', sa.UUID(), nullable=False),
    sa.Column('subject_entity_id', sa.UUID(), nullable=True),
    sa.Column('predicate', sa.Text(), nullable=False),
    sa.Column('object_entity_id', sa.UUID(), nullable=True),
    sa.Column('object_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('speaker_stance', sa.String(length=16), nullable=False),
    sa.Column('fidelity', sa.String(length=16), server_default='full', nullable=False),
    sa.Column('deliberate_false', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('about_speaker_self', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('source_fact_id', sa.UUID(), nullable=True),
    sa.Column('source_belief_id', sa.UUID(), nullable=True),
    sa.Column('conveyance_source', sa.String(length=16), nullable=False),
    sa.Column('confidence', sa.Numeric(precision=4, scale=3), server_default=sa.text('1.0'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['object_entity_id'], ['entities.id'], ),
    sa.ForeignKeyConstraint(['source_fact_id'], ['facts.id'], ),
    sa.ForeignKeyConstraint(['speaker_actor_id'], ['actors.id'], ),
    sa.ForeignKeyConstraint(['statement_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['subject_entity_id'], ['entities.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_claims_event', 'claims', ['statement_event_id'], unique=False)
    op.create_index('ix_claims_speaker', 'claims', ['speaker_actor_id'], unique=False)
    op.create_table('relationship_deltas',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('relationship_id', sa.UUID(), nullable=False),
    sa.Column('event_id', sa.UUID(), nullable=False),
    sa.Column('dimension', sa.String(length=16), nullable=False),
    sa.Column('delta', sa.Integer(), nullable=False),
    sa.Column('reason', sa.Text(), server_default='', nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['relationship_id'], ['relationships.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_relationship_deltas_rel', 'relationship_deltas', ['relationship_id'], unique=False)
    op.create_table('beliefs',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=False),
    sa.Column('fact_id', sa.UUID(), nullable=True),
    sa.Column('claim_id', sa.UUID(), nullable=True),
    sa.Column('proposition', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('proposition_key', sa.Text(), nullable=False),
    sa.Column('belief_type', sa.String(length=16), nullable=False),
    sa.Column('confidence', sa.Numeric(precision=4, scale=3), nullable=False),
    sa.Column('source_type', sa.String(length=16), nullable=False),
    sa.Column('source_actor_id', sa.UUID(), nullable=True),
    sa.Column('acquired_event_id', sa.UUID(), nullable=True),
    sa.Column('superseded_event_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default='active', nullable=False),
    sa.Column('salience', sa.Numeric(precision=4, scale=3), server_default=sa.text('0.5'), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("fact_id IS NOT NULL OR claim_id IS NOT NULL OR proposition <> '{}'::jsonb", name='ck_beliefs_has_subject'),
    sa.ForeignKeyConstraint(['acquired_event_id'], ['events.id'], ),
    sa.ForeignKeyConstraint(['actor_id'], ['actors.id'], ),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ),
    sa.ForeignKeyConstraint(['fact_id'], ['facts.id'], ),
    sa.ForeignKeyConstraint(['source_actor_id'], ['actors.id'], ),
    sa.ForeignKeyConstraint(['superseded_event_id'], ['events.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_beliefs_actor_prop', 'beliefs', ['actor_id', 'proposition_key'], unique=False)
    op.create_index('ix_beliefs_actor_status', 'beliefs', ['actor_id', 'status'], unique=False)
    op.create_table('observations',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=False),
    sa.Column('source_event_id', sa.UUID(), nullable=False),
    sa.Column('channel', sa.String(length=32), nullable=False),
    sa.Column('observation_type', sa.String(length=32), nullable=False),
    sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('interpreted_text', sa.Text(), nullable=True),
    sa.Column('confidence', sa.Numeric(precision=4, scale=3), server_default=sa.text('1.0'), nullable=False),
    sa.Column('game_tick', sa.BigInteger(), nullable=False),
    sa.Column('claim_id', sa.UUID(), nullable=True),
    sa.Column('scene_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['actors.id'], ),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ),
    sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ),
    sa.ForeignKeyConstraint(['source_event_id'], ['events.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_observations_actor_tick', 'observations', ['actor_id', 'game_tick'], unique=False)
    op.create_index('ix_observations_event', 'observations', ['source_event_id'], unique=False)
    op.create_foreign_key(
        "fk_claims_source_belief", "claims", "beliefs", ["source_belief_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_claims_source_belief", "claims", type_="foreignkey")
    op.drop_index('ix_observations_event', table_name='observations')
    op.drop_index('ix_observations_actor_tick', table_name='observations')
    op.drop_table('observations')
    op.drop_index('ix_beliefs_actor_status', table_name='beliefs')
    op.drop_index('ix_beliefs_actor_prop', table_name='beliefs')
    op.drop_table('beliefs')
    op.drop_index('ix_relationship_deltas_rel', table_name='relationship_deltas')
    op.drop_table('relationship_deltas')
    op.drop_index('ix_claims_speaker', table_name='claims')
    op.drop_index('ix_claims_event', table_name='claims')
    op.drop_table('claims')
    op.drop_table('relationships')
    op.drop_index('uq_facts_campaign_key', table_name='facts', postgresql_where=sa.text('key IS NOT NULL'))
    op.drop_index('ix_facts_campaign_subject', table_name='facts')
    op.drop_table('facts')
    op.drop_index('ix_identity_knowledge_actor', table_name='entity_identity_knowledge')
    op.drop_table('entity_identity_knowledge')
