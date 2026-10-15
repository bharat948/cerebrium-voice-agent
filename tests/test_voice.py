import base64
import pytest


class FakeWebSocket:
    def __init__(self): self.sent=[]
    async def send_json(self, event): self.sent.append(event)


class FakeStream:
    def __init__(self): self.status_code=200
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def raise_for_status(self): pass
    async def aiter_bytes(self):
        yield b'\xff' * 500
        yield b'\xff' * 1100


class FakeHttpClient:
    def __init__(self, *args, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def stream(self, *args, **kwargs): return FakeStream()


@pytest.mark.asyncio
async def test_twilio_pcmu_outbound_and_clear(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'voice-test.db'))
    from app.config import get_settings
    get_settings.cache_clear()
    from app import db
    db.init_db()
    import app.voice as voice
    monkeypatch.setattr(voice.httpx, 'AsyncClient', FakeHttpClient)
    socket = FakeWebSocket()
    v = voice.VoiceSession(socket, {'id': 'unittest-call'},
                           {'id':'receptionist','name':'Ava','role':'Assistant','language':'English',
                            'instructions':'Disclose AI nature'}, None)
    v.stream_sid = 'MZ-test-stream'
    await v.send_audio('Hello.', v.generation)
    media = [x for x in socket.sent if x['event']=='media']
    assert len(media) == 2
    assert all(len(base64.b64decode(x['media']['payload'])) == 800 for x in media)
    assert v.playback_pending
    await v.barge_in()
    assert socket.sent[-1] == {'event':'clear','streamSid':'MZ-test-stream'}
    assert v.generation == 1 and not v.playback_pending
    get_settings.cache_clear()
