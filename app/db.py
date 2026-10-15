import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from app.config import get_settings


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def connect():
    db_path = get_settings().db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA busy_timeout=15000')
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, language TEXT NOT NULL,
            instructions TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS plans (
            id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, phone TEXT NOT NULL, goal TEXT NOT NULL,
            agenda TEXT NOT NULL, script TEXT NOT NULL, state TEXT NOT NULL,
            source_message TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS calls (
            id TEXT PRIMARY KEY, plan_id TEXT, agent_id TEXT NOT NULL, phone TEXT NOT NULL,
            direction TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL,
            twilio_sid TEXT, error TEXT, started_at TEXT, ended_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_calls_created ON calls(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_calls_sid ON calls(twilio_sid);
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, call_id TEXT NOT NULL, type TEXT NOT NULL,
            speaker TEXT, content TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_call ON events(call_id, created_at);
        ''')
        count = c.execute('SELECT count(*) FROM agents').fetchone()[0]
        if not count:
            c.execute('INSERT INTO agents VALUES (?,?,?,?,?,?)', (
                'receptionist', 'Ava', 'Appointment coordinator', 'English',
                'You are a polite and concise appointment coordinator. Clearly disclose you are an AI assistant. '
                'Confirm facts without inventing availability. Do not claim a booking occurred unless a verified booking tool succeeds. '
                'Ask one question at a time. Respect requests to stop calling or end the call.', now()))


def one(sql: str, args: tuple = ()) -> dict | None:
    with connect() as c:
        row = c.execute(sql, args).fetchone()
        return dict(row) if row else None


def many(sql: str, args: tuple = ()) -> list[dict]:
    with connect() as c:
        return [dict(row) for row in c.execute(sql, args).fetchall()]


def execute(sql: str, args: tuple = ()) -> None:
    with connect() as c:
        c.execute(sql, args)


def insert_agent(name: str, role: str, language: str, instructions: str) -> dict:
    id_ = uid()
    execute('INSERT INTO agents VALUES (?,?,?,?,?,?)', (id_, name, role, language, instructions, now()))
    return one('SELECT * FROM agents WHERE id=?', (id_,))


def insert_plan(agent_id: str, phone: str, goal: str, agenda: list[str], script: str, source: str) -> dict:
    id_ = uid()
    execute('INSERT INTO plans VALUES (?,?,?,?,?,?,?,?,?)',
            (id_, agent_id, phone, goal, json.dumps(agenda), script, 'draft', source, now()))
    return get_plan(id_)


def get_plan(id_: str) -> dict | None:
    row = one('SELECT * FROM plans WHERE id=?', (id_,))
    if row:
        row['agenda'] = json.loads(row['agenda'])
    return row


def plans() -> list[dict]:
    rows = many('SELECT * FROM plans ORDER BY created_at DESC LIMIT 100')
    for row in rows:
        row['agenda'] = json.loads(row['agenda'])
    return rows


def insert_call(plan_id: str | None, agent_id: str, phone: str, direction: str, mode: str, status: str) -> dict:
    id_ = uid()
    execute('INSERT INTO calls (id,plan_id,agent_id,phone,direction,mode,status,created_at) VALUES (?,?,?,?,?,?,?,?)',
            (id_, plan_id, agent_id, phone, direction, mode, status, now()))
    return one('SELECT * FROM calls WHERE id=?', (id_,))


def call_details(id_: str) -> dict | None:
    call = one('SELECT * FROM calls WHERE id=?', (id_,))
    if call:
        call['events'] = many('SELECT id,type,speaker,content,created_at FROM events WHERE call_id=? ORDER BY created_at,id', (id_,))
        call['plan'] = get_plan(call['plan_id']) if call['plan_id'] else None
    return call


def add_event(call_id: str, type_: str, content: str, speaker: str | None = None):
    execute('INSERT INTO events VALUES (?,?,?,?,?,?)', (uid(), call_id, type_, speaker, content, now()))


def purge_expired(days: int):
    before = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).isoformat()
    execute('DELETE FROM events WHERE created_at < ?', (before,))
