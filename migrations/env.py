from alembic import context
from app.db import engine

config=context.config

def run_migrations_offline():
    context.configure(url=str(engine().url),literal_binds=True)
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online():
    with engine().connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction(): context.run_migrations()

if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
