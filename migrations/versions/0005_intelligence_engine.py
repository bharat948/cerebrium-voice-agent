"""Temporal memory, contact opt-outs and supervised agent evolution.

Revision ID: 0005; Revises: 0004
"""
from alembic import op
from sqlalchemy import inspect

revision='0005'
down_revision='0004'
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    contact_cols={col['name'] for col in inspect(bind).get_columns('contacts')}
    if 'memory_opt_in' not in contact_cols:
        op.execute('ALTER TABLE contacts ADD COLUMN memory_opt_in INTEGER NOT NULL DEFAULT 1')
    memory_cols={col['name'] for col in inspect(bind).get_columns('memories')}
    for name,ddl in {'valid_from':'TEXT','expires_at':'TEXT','strength':'INTEGER NOT NULL DEFAULT 1',
                     'origin':"TEXT NOT NULL DEFAULT 'owner'",'supersedes_id':'TEXT'}.items():
        if name not in memory_cols:op.execute(f'ALTER TABLE memories ADD COLUMN {name} {ddl}')
    op.execute("""CREATE TABLE IF NOT EXISTS memory_conflicts (
        id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, contact_id TEXT NOT NULL,
        existing_memory_id TEXT NOT NULL, proposed_content TEXT NOT NULL,
        source_call_id TEXT, state TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL, resolved_at TEXT)""")
    op.execute('CREATE INDEX IF NOT EXISTS idx_memory_conflicts_scope ON memory_conflicts(agent_id,contact_id,state)')
    op.execute("""CREATE TABLE IF NOT EXISTS agent_improvement_proposals (
        id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, source TEXT NOT NULL,
        evidence TEXT NOT NULL, changes TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending', draft_id TEXT,
        created_at TEXT NOT NULL, reviewed_at TEXT)""")
    op.execute('CREATE INDEX IF NOT EXISTS idx_improvement_agent ON agent_improvement_proposals(agent_id,state,created_at)')

def downgrade():
    raise RuntimeError('Destructive downgrade not supported; restore backup')
