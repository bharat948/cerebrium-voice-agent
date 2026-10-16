"""Optional PostgreSQL pgvector embeddings for document knowledge.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
revision='0004'
down_revision='0003'
branch_labels=None
depends_on=None


def upgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('CREATE EXTENSION IF NOT EXISTS vector')
        op.execute('CREATE TABLE IF NOT EXISTS knowledge_vectors (chunk_id TEXT PRIMARY KEY, embedding vector(1536) NOT NULL)')


def downgrade():
    raise RuntimeError('Destructive downgrade prohibited: restore a verified database backup')
