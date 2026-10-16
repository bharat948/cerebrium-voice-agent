"""Contact lifecycle, memory and mission timelines.

Revision ID: 0002
Revises: 0001

Safe to run against either the original alpha schema or a fresh schema created
by idempotent schema_statements(). No destructive DDL.
"""
from alembic import op
from sqlalchemy import inspect

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    if 'contacts' in inspector.get_table_names():
        cols = {c['name'] for c in inspector.get_columns('contacts')}
        if 'active' not in cols:
            op.execute('ALTER TABLE contacts ADD COLUMN active INTEGER NOT NULL DEFAULT 1')
    op.execute('''CREATE TABLE IF NOT EXISTS memory_events (
        id TEXT PRIMARY KEY, memory_id TEXT NOT NULL, agent_id TEXT NOT NULL,
        contact_id TEXT NOT NULL, kind TEXT NOT NULL, replacement_id TEXT,
        created_at TEXT NOT NULL)''')
    op.execute('CREATE INDEX IF NOT EXISTS idx_memory_events ON memory_events(agent_id,contact_id,created_at)')
    op.execute('''CREATE TABLE IF NOT EXISTS mission_events (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, event_type TEXT NOT NULL,
        detail TEXT NOT NULL, created_at TEXT NOT NULL)''')
    op.execute('CREATE INDEX IF NOT EXISTS idx_mission_events ON mission_events(mission_id,created_at)')


def downgrade():
    raise RuntimeError('Use database backup for rollback; no destructive downgrade')
