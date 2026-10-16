"""Voice Foundry v3-compatible foundation; idempotent with existing v2 bootstrap.

Revision ID: 0001
Revises:
"""
from alembic import op
from app.db import schema_statements

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    for statement in schema_statements():
        op.execute(statement)
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('CREATE EXTENSION IF NOT EXISTS vector')
        op.execute('CREATE TABLE IF NOT EXISTS memory_vectors (memory_id TEXT PRIMARY KEY, embedding vector(1536) NOT NULL)')


def downgrade():
    raise RuntimeError('Destructive downgrade intentionally unsupported: restore a verified database backup')
