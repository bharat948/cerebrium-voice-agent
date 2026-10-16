"""Legacy v2 query facade backed by the shared SQLAlchemy engine.

Designed to keep the proven voice routes working as persistence moves from SQLite
into PostgreSQL. New v3 modules use this same engine, avoiding split-brain data.
"""
import json
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from app.config import get_settings


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid.uuid4())

_engine = None
_engine_url = None


def engine():
    global _engine, _engine_url
    s = get_settings()
    url = s.database_url or f'sqlite:///{s.db_path}'
    if url.startswith('postgresql://'):
        url = 'postgresql+psycopg://' + url.removeprefix('postgresql://')
    if url != _engine_url:
        if _engine is not None:
            _engine.dispose()
        if url.startswith('sqlite:///') and ':memory:' not in url:
            Path(url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, pool_pre_ping=True,
                                connect_args={'timeout': 15} if url.startswith('sqlite:') else {},
                                **({'poolclass': StaticPool} if url.endswith('/:memory:') else {}))
        _engine_url = url
    return _engine


def _bind(sql, params):
    if isinstance(params, dict):
        return text(sql), params
    parts = sql.split('?')
    if len(parts) - 1 != len(params):
        raise ValueError('SQL parameter count mismatch')
    statement = ''.join(s + (f':p{i}' if i < len(parts) - 1 else '') for i, s in enumerate(parts))
    return text(statement), {f'p{i}': value for i, value in enumerate(params)}


class Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class Result:
    def __init__(self, result):
        self.rowcount = result.rowcount
        if result.returns_rows:
            self.rows = [Row(dict(r._mapping)) for r in result.fetchall()]
        else:
            self.rows = []
    def fetchone(self):
        return self.rows.pop(0) if self.rows else None
    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows
    def __iter__(self):
        return iter(self.rows)


class Connection:
    def __init__(self, conn):
        self.conn = conn
    def execute(self, sql, params=()):
        statement, args = _bind(sql, params)
        return Result(self.conn.execute(statement, args))


@contextmanager
def connect():
    with engine().begin() as connection:
        yield Connection(connection)


def schema_statements():
    return [
        '''CREATE TABLE IF NOT EXISTS agents (
           id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
           language TEXT NOT NULL, instructions TEXT NOT NULL, created_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS plans (
           id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, phone TEXT NOT NULL,
           goal TEXT NOT NULL, agenda TEXT NOT NULL, script TEXT NOT NULL,
           state TEXT NOT NULL, source_message TEXT NOT NULL, created_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS calls (
           id TEXT PRIMARY KEY, plan_id TEXT, agent_id TEXT NOT NULL, phone TEXT NOT NULL,
           direction TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL,
           twilio_sid TEXT, error TEXT, started_at TEXT, ended_at TEXT,
           created_at TEXT NOT NULL, voice_engine TEXT NOT NULL DEFAULT 'deepgram')''',
        'CREATE INDEX IF NOT EXISTS idx_calls_created ON calls(created_at DESC)',
        'CREATE INDEX IF NOT EXISTS idx_calls_sid ON calls(twilio_sid)',
        '''CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, call_id TEXT NOT NULL, type TEXT NOT NULL,
            speaker TEXT, content TEXT NOT NULL, created_at TEXT NOT NULL)''',
        'CREATE INDEX IF NOT EXISTS idx_events_call ON events(call_id, created_at)',
        '''CREATE TABLE IF NOT EXISTS contacts (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL UNIQUE,
            email TEXT, language TEXT NOT NULL DEFAULT 'Hinglish',
            outbound_consent INTEGER NOT NULL DEFAULT 0,
            email_consent INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1)''',
        '''CREATE TABLE IF NOT EXISTS agent_contact_permissions (
            agent_id TEXT NOT NULL, contact_id TEXT NOT NULL,
            PRIMARY KEY (agent_id,contact_id))''',
        '''CREATE TABLE IF NOT EXISTS agent_releases (
            id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, version INTEGER NOT NULL,
            status TEXT NOT NULL, configuration TEXT NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(agent_id,version))''',
        '''CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, contact_id TEXT NOT NULL,
            content TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'preference',
            sensitivity TEXT NOT NULL DEFAULT 'routine', source_call_id TEXT,
            confidence REAL NOT NULL DEFAULT 1.0, active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL)''',
        'CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(agent_id,contact_id,active)',
        '''CREATE TABLE IF NOT EXISTS memory_events (
            id TEXT PRIMARY KEY, memory_id TEXT NOT NULL, agent_id TEXT NOT NULL,
            contact_id TEXT NOT NULL, kind TEXT NOT NULL, replacement_id TEXT,
            created_at TEXT NOT NULL)''',
        'CREATE INDEX IF NOT EXISTS idx_memory_events ON memory_events(agent_id,contact_id,created_at)',
        '''CREATE TABLE IF NOT EXISTS missions (
            id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, contact_id TEXT,
            kind TEXT NOT NULL, objective TEXT NOT NULL, payload TEXT NOT NULL,
            state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            lease_until TEXT, next_run_at TEXT NOT NULL, result TEXT,
            error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
        'CREATE INDEX IF NOT EXISTS idx_missions_due ON missions(state,next_run_at)',
        '''CREATE TABLE IF NOT EXISTS mission_events (
            id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, event_type TEXT NOT NULL,
            detail TEXT NOT NULL, created_at TEXT NOT NULL)''',
        'CREATE INDEX IF NOT EXISTS idx_mission_events ON mission_events(mission_id,created_at)',
        '''CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL,
            target TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL,
            due_at TEXT, agent_id TEXT, contact_id TEXT, created_at TEXT NOT NULL)''',
        # Final product modules; all keys remain text for SQLite/PostgreSQL compatibility.
        """CREATE TABLE IF NOT EXISTS knowledge_sources (
            id TEXT PRIMARY KEY, agent_id TEXT, title TEXT NOT NULL, kind TEXT NOT NULL,
            source_url TEXT, visibility TEXT NOT NULL DEFAULT 'private',
            trust_tier TEXT NOT NULL DEFAULT 'provisional', content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
            content TEXT NOT NULL, token_estimate INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL)""",
        'CREATE INDEX IF NOT EXISTS idx_knowledge_source ON knowledge_chunks(source_id,ordinal)',
        """CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, contact_id TEXT,
            action TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL,
            requested_at TEXT NOT NULL, decided_at TEXT, decided_by TEXT,
            result TEXT)""",
        'CREATE INDEX IF NOT EXISTS idx_approvals_state ON approvals(state,requested_at)',
        """CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY, category TEXT NOT NULL, priority TEXT NOT NULL,
            title TEXT NOT NULL, detail TEXT NOT NULL, state TEXT NOT NULL,
            related_id TEXT, created_at TEXT NOT NULL, read_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS expenses (
            id TEXT PRIMARY KEY, agent_id TEXT, call_id TEXT, mission_id TEXT,
            provider TEXT NOT NULL, operation TEXT NOT NULL, estimated_usd REAL NOT NULL,
            actual_usd REAL, occurred_at TEXT NOT NULL)""",
        'CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(occurred_at,agent_id)',
        """CREATE TABLE IF NOT EXISTS runtime_controls (
            call_id TEXT PRIMARY KEY, paused INTEGER NOT NULL DEFAULT 0,
            stop_requested INTEGER NOT NULL DEFAULT 0,
            pending_instruction TEXT, updated_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS outcome_reports (
            id TEXT PRIMARY KEY, call_id TEXT NOT NULL UNIQUE, agent_id TEXT NOT NULL,
            outcome TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS agent_feedback (
            id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, release_id TEXT,
            call_id TEXT, rating INTEGER NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS mail_deliveries (
            id TEXT PRIMARY KEY, mission_id TEXT NOT NULL UNIQUE, contact_id TEXT NOT NULL,
            recipient TEXT NOT NULL, state TEXT NOT NULL, subject TEXT NOT NULL,
            sent_at TEXT, error TEXT, created_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS calendar_events (
            id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, contact_id TEXT,
            title TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
            state TEXT NOT NULL, external_id TEXT, created_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS integrations (
            provider TEXT PRIMARY KEY, encrypted_credentials TEXT NOT NULL,
            scopes TEXT NOT NULL, updated_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS worker_steps (
            id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
            kind TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL,
            result TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
        'CREATE INDEX IF NOT EXISTS idx_worker_steps ON worker_steps(mission_id,ordinal)',
        """CREATE TABLE IF NOT EXISTS mission_schedules (
            id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, contact_id TEXT NOT NULL,
            objective TEXT NOT NULL, interval TEXT NOT NULL, hour_local INTEGER NOT NULL,
            minute_local INTEGER NOT NULL, tz TEXT NOT NULL, next_run_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS schedule_occurrences (
            schedule_id TEXT NOT NULL, due_at TEXT NOT NULL, mission_id TEXT NOT NULL,
            PRIMARY KEY (schedule_id,due_at))""",
        """CREATE TABLE IF NOT EXISTS memory_conflicts (
            id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, contact_id TEXT NOT NULL,
            existing_memory_id TEXT NOT NULL, proposed_content TEXT NOT NULL,
            source_call_id TEXT, state TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL, resolved_at TEXT)""",
        'CREATE INDEX IF NOT EXISTS idx_memory_conflicts_scope ON memory_conflicts(agent_id,contact_id,state)',
        """CREATE TABLE IF NOT EXISTS agent_improvement_proposals (
            id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, source TEXT NOT NULL,
            evidence TEXT NOT NULL, changes TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending', draft_id TEXT,
            created_at TEXT NOT NULL, reviewed_at TEXT)""",
        'CREATE INDEX IF NOT EXISTS idx_improvement_agent ON agent_improvement_proposals(agent_id,state,created_at)',

    ]


def init_db():
    """Create current compatible schema; Alembic records the matching baseline revision."""
    statements=schema_statements()
    # pgvector is optional until configured by the PostgreSQL host.
    if engine().dialect.name == 'postgresql':
        with engine().begin() as c:
            c.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        statements.append('CREATE TABLE IF NOT EXISTS memory_vectors (memory_id TEXT PRIMARY KEY, embedding vector(1536) NOT NULL)')
        statements.append('CREATE TABLE IF NOT EXISTS knowledge_vectors (chunk_id TEXT PRIMARY KEY, embedding vector(1536) NOT NULL)')
    with connect() as conn:
        for stmt in statements:
            conn.execute(stmt)
        from sqlalchemy import inspect
        columns = {col['name'] for col in inspect(conn.conn).get_columns('calls')}
        if 'voice_engine' not in columns:
            conn.execute("ALTER TABLE calls ADD COLUMN voice_engine TEXT NOT NULL DEFAULT 'deepgram'")
        if 'agent_release_id' not in columns:
            conn.execute("ALTER TABLE calls ADD COLUMN agent_release_id TEXT")
        contact_columns = {col['name'] for col in inspect(conn.conn).get_columns('contacts')}
        if 'active' not in contact_columns:
            conn.execute("ALTER TABLE contacts ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
        if 'memory_opt_in' not in contact_columns:
            conn.execute("ALTER TABLE contacts ADD COLUMN memory_opt_in INTEGER NOT NULL DEFAULT 1")
        memory_columns = {col['name'] for col in inspect(conn.conn).get_columns('memories')}
        for col, ddl in {
            'valid_from': 'TEXT', 'expires_at': 'TEXT',
            'strength': 'INTEGER NOT NULL DEFAULT 1',
            'origin': "TEXT NOT NULL DEFAULT 'owner'", 'supersedes_id': 'TEXT'
        }.items():
            if col not in memory_columns:
                conn.execute(f'ALTER TABLE memories ADD COLUMN {col} {ddl}')
        row = conn.execute('SELECT count(*) AS n FROM agents').fetchone()
        if row['n'] == 0:
            conn.execute('INSERT INTO agents VALUES (?,?,?,?,?,?)', (
                'receptionist', 'Ava', 'Appointment coordinator', 'English',
                'You are a concise AI appointment coordinator. Disclose your AI identity. '
                'Never invent availability or claim an appointment was booked without a verified tool result. '
                'Ask one question at a time and respect requests to end the call.', now()))


def one(sql, args=()):
    with connect() as c:
        return c.execute(sql, args).fetchone()


def many(sql, args=()):
    with connect() as c:
        return c.execute(sql, args).fetchall()


def execute(sql, args=()):
    with connect() as c:
        return c.execute(sql, args).rowcount


def insert_agent(name, role, language, instructions):
    id_ = uid()
    execute('INSERT INTO agents VALUES (?,?,?,?,?,?)', (id_, name, role, language, instructions, now()))
    return one('SELECT * FROM agents WHERE id=?', (id_,))


def insert_plan(agent_id, phone, goal, agenda, script, source):
    id_ = uid()
    execute('INSERT INTO plans VALUES (?,?,?,?,?,?,?,?,?)',
            (id_, agent_id, phone, goal, json.dumps(agenda), script, 'draft', source, now()))
    return get_plan(id_)


def get_plan(id_):
    row = one('SELECT * FROM plans WHERE id=?', (id_,))
    if row:
        row['agenda'] = json.loads(row['agenda'])
    return row


def plans():
    rows = many('SELECT * FROM plans ORDER BY created_at DESC LIMIT 100')
    for row in rows:
        row['agenda'] = json.loads(row['agenda'])
    return rows


def insert_call(plan_id, agent_id, phone, direction, mode, status, voice_engine='deepgram'):
    id_ = uid()
    release = one("SELECT id FROM agent_releases WHERE agent_id=? AND status='published' ORDER BY version DESC LIMIT 1",(agent_id,))
    execute('INSERT INTO calls (id,plan_id,agent_id,phone,direction,mode,status,created_at,voice_engine,agent_release_id) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (id_, plan_id, agent_id, phone, direction, mode, status, now(), voice_engine, release['id'] if release else None))
    return one('SELECT * FROM calls WHERE id=?', (id_,))


def call_details(id_):
    call = one('SELECT * FROM calls WHERE id=?', (id_,))
    if call:
        call['events'] = many('SELECT id,type,speaker,content,created_at FROM events WHERE call_id=? ORDER BY created_at,id', (id_,))
        call['plan'] = get_plan(call['plan_id']) if call['plan_id'] else None
    return call


def add_event(call_id, type_, content, speaker=None):
    execute('INSERT INTO events VALUES (?,?,?,?,?,?)', (uid(), call_id, type_, speaker, content, now()))


def purge_expired(days):
    before = (datetime.now(timezone.utc) - timedelta(days=max(1,days))).isoformat()
    execute('DELETE FROM events WHERE created_at < ?', (before,))
