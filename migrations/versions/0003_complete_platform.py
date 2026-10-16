"""Additional modular-monolith storage. Additive only; never deletes user data."""
from alembic import op
from app.db import schema_statements
revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None

def upgrade():
    for ddl in schema_statements():
        if 'CREATE TABLE IF NOT EXISTS' in ddl or 'CREATE INDEX IF NOT EXISTS' in ddl:
            op.execute(ddl)

def downgrade():
    raise RuntimeError('Restore a verified backup for down-migrations')
