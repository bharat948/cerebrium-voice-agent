"""Offline Live protocol/codec tests. Does not connect to OpenAI or Twilio."""
import asyncio
import base64
import json
import sqlite3

import pytest

from app.live_voice import LiveVoiceSession, session_start, ulaw_rms


class FakeTwilio:
    def __init__(self):
        self.sent = []
        self.reads = 0

    async def send_json(self, event):
        self.sent.append(event)

    async def receive_text(self):
        self.reads += 1
        if self.reads == 1:
            return json.dumps({'event': 'media', 'streamSid': 'MZ1',
                               'media': {'payload': base64.b64encode(b'\xff' * 160).decode()}})
        await asyncio.sleep(.25)
        return json.dumps({'event': 'stop', 'streamSid': 'MZ1'})


class FakeOpenAI:
    def __init__(self):
        self.sent = []
        self.messages = asyncio.Queue()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def send(self, raw):
        event = json.loads(raw)
        self.sent.append(event)
        if event['type'] == 'session.start':
            await self.messages.put(json.dumps({'type': 'session.started', 'session': {'id': 'live-test'}}))
            await self.messages.put(json.dumps({'type': 'session.output_audio.delta',
                    'delta': base64.b64encode(b'\xff' * 320).decode()}))
            await self.messages.put(json.dumps({'type': 'session.input_transcript.delta', 'delta': 'Hello there.'}))
            await self.messages.put(json.dumps({'type': 'session.output_transcript.delta', 'delta': 'Hi!'}))
        if event['type'] == 'session.close':
            await self.messages.put(json.dumps({'type': 'session.closed', 'usage': {'seconds': 2}}))

    async def recv(self):
        return await self.messages.get()

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.recv()


@pytest.mark.asyncio
async def test_live_audio_bridging_and_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'live.db'))
    monkeypatch.setenv('OPENAI_API_KEY', 'fake-key')
    from app.config import get_settings
    get_settings.cache_clear()
    from app import db
    db.init_db()
    call = db.insert_call(None, 'receptionist', '+14155552671', 'outbound', 'live', 'ringing', 'openai_live')
    agent = db.one('SELECT * FROM agents WHERE id=?', ('receptionist',))
    fake_live = FakeOpenAI()
    monkeypatch.setattr('app.live_voice.websockets.connect', lambda *args, **kwargs: fake_live)
    twilio = FakeTwilio()
    stream = LiveVoiceSession(twilio, call, agent, None)
    await stream.run({'event': 'start', 'start': {'streamSid': 'MZ1'}})
    assert fake_live.sent[0]['type'] == 'session.start'
    assert fake_live.sent[0]['session']['model'] == 'gpt-live-1'
    assert fake_live.sent[0]['session']['audio']['format'] == {'type':'audio/pcmu','rate':8000}
    assert any(e['type']=='session.input_audio.append' for e in fake_live.sent)
    assert any(e['type']=='session.close' for e in fake_live.sent)
    assert any(e['event']=='media' for e in twilio.sent)
    assert any(e['event']=='mark' for e in twilio.sent)
    assert all(base64.b64decode(e['media']['payload'])==b'\xff'*320 for e in twilio.sent if e['event']=='media')
    events = db.call_details(call['id'])['events']
    assert any(e['speaker']=='caller' and e['content']=='Hello there.' for e in events)
    assert any(e['speaker']=='assistant' and e['content']=='Hi!' for e in events)
    assert any(e['type']=='usage' for e in events)
    assert stream.finalized
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_live_local_barge_in_clears_buffer(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'barge.db'))
    monkeypatch.setenv('LIVE_BARGE_IN_RMS', '300')
    monkeypatch.setenv('LIVE_BARGE_IN_FRAMES', '2')
    from app.config import get_settings
    get_settings.cache_clear()
    from app import db
    db.init_db()
    fake = FakeTwilio()
    call = db.insert_call(None, 'receptionist', '+14155552671','outbound','live','ringing','openai_live')
    stream = LiveVoiceSession(fake, call, {}, None)
    stream.stream_sid = 'MZ1'
    stream.pending_marks.add('m1')
    # µ-law byte 0x00 is high-amplitude waveform, 0xff is silence.
    assert ulaw_rms(b'\x00'*160) > 1000
    assert ulaw_rms(b'\xff'*160) == 0
    await stream.maybe_barge_in(b'\x00'*160)
    await stream.maybe_barge_in(b'\x00'*160)
    assert fake.sent[-1] == {'event':'clear','streamSid':'MZ1'}
    assert not stream.pending_marks
    assert any(e['type']=='interruption' for e in db.call_details(call['id'])['events'])
    get_settings.cache_clear()


def test_startup_prompt_includes_approved_agenda():
    msg = session_start({'name':'Ava','role':'Receptionist','language':'Hindi',
                         'instructions':'Ask one question at a time'},
                        {'goal':'Confirm a visit','agenda':['Greet','Ask preferred day'],
                         'script':'Namaste, I am a virtual assistant.'},
                        'gpt-live-1','marin')
    assert msg['type']=='session.start'
    assert 'Confirm a visit' in msg['session']['instructions']
    assert 'Namaste' in msg['session']['input'][0]['content'][0]['text']
    assert msg['session']['delegation']['type']=='responses'


def test_existing_sqlite_migrates_to_engine_column(tmp_path, monkeypatch):
    db_path = tmp_path / 'old.db'
    with sqlite3.connect(db_path) as con:
        con.execute('CREATE TABLE calls (id TEXT PRIMARY KEY, plan_id TEXT, agent_id TEXT, phone TEXT, '
                    'direction TEXT, mode TEXT, status TEXT, twilio_sid TEXT, error TEXT, '
                    'started_at TEXT, ended_at TEXT, created_at TEXT)')
        con.execute('INSERT INTO calls (id,agent_id,phone,direction,mode,status,created_at) '
                    "VALUES ('old1','receptionist','+14155552671','outbound','live','completed','2026-10-01')")
    monkeypatch.setenv('DB_PATH', str(db_path))
    from app.config import get_settings
    get_settings.cache_clear()
    from app import db
    db.init_db()
    assert db.one('SELECT voice_engine FROM calls WHERE id=?', ('old1',))['voice_engine']=='deepgram'
    db.init_db()  # idempotent
    get_settings.cache_clear()
