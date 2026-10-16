"""Regressions for validation arriving before or after voice readiness.

All provider traffic is simulated. These tests do not verify account access.
"""
import asyncio
import base64
import json
import importlib.util
from pathlib import Path

import pytest

from app.live_diagnostics import (
    LiveProviderError, LiveSessionDiagnostics, provider_error_detail, wait_for_live_start,
)


def validation_error(message='Configured backend model is not accessible'):
    return {'type': 'error', 'error': {
        'code': 'responses_validation_failed', 'type': 'invalid_request_error',
        'param': 'delegation.responses.model', 'message': message,
    }}


def recorder(**kwargs):
    sent, records = [], []

    async def send(event):
        sent.append(event)

    diagnostic = LiveSessionDiagnostics(send, backend_model='configured-backend',
                                        record=lambda kind, text: records.append((kind, text)), **kwargs)
    return diagnostic, sent, records


class EventSocket:
    def __init__(self, events=()):
        self.events = asyncio.Queue()
        for event in events:
            self.events.put_nowait(json.dumps(event))

    async def recv(self):
        return await self.events.get()


@pytest.mark.asyncio
@pytest.mark.parametrize('before_started', [True, False])
async def test_validation_does_not_reject_voice_session(before_started):
    diagnostics, sent, records = recorder()
    error = validation_error()
    started = {'type': 'session.started', 'session': {'id': 'live-test'}}
    events = [error, started] if before_started else [started]
    assert await wait_for_live_start(EventSocket(events), diagnostics) == started
    if not before_started:
        await diagnostics.observe(error)
    assert diagnostics.started and diagnostics.backend_unavailable
    assert [event['type'] for event in sent] == ['session.instructions.append']
    assert 'Do not invent results' in sent[0]['content']
    assert any('delegation.responses.model' in text for kind, text in records if kind == 'error')
    assert not any(event['type'] == 'session.close' for event in sent)


@pytest.mark.asyncio
async def test_no_commands_are_sent_before_session_started():
    diagnostics, sent, _ = recorder(fallback_model='explicit-fallback')
    await diagnostics.observe(validation_error())
    assert sent == []
    await diagnostics.observe({'type': 'session.started'})
    assert sent[0]['type'] == 'session.update'
    assert sent[0]['session'] == {'delegation': {'type': 'responses',
                                                'responses': {'model': 'explicit-fallback'}}}
    # Omitted tool and instruction fields keep the original authorized values.
    assert diagnostics.backend_unavailable


@pytest.mark.asyncio
async def test_fallback_is_bounded_and_failed_retry_notifies_caller_once():
    diagnostics, sent, _ = recorder(fallback_model='explicit-fallback')
    await diagnostics.observe({'type': 'session.started'})
    for _ in range(4):
        await diagnostics.observe(validation_error())
    assert len([event for event in sent if event['type'] == 'session.update']) == 1
    assert len([event for event in sent if event['type'] == 'session.instructions.append']) == 1
    assert diagnostics.backend_unavailable


@pytest.mark.asyncio
async def test_update_acknowledgment_is_not_backend_validation_success():
    diagnostics, sent, records = recorder(fallback_model='explicit-fallback')
    await diagnostics.observe({'type': 'session.started'})
    await diagnostics.observe(validation_error())
    await diagnostics.observe({'type': 'session.updated', 'client_event_id': sent[0]['event_id']})
    assert diagnostics.backend_unavailable
    await diagnostics.observe({'type': 'response.event', 'event': {
        'type': 'response.completed', 'response': {'id': 'resp-ok', 'status': 'completed'}}})
    assert not diagnostics.backend_unavailable
    assert any('returned a completed response' in text for _, text in records)


@pytest.mark.asyncio
async def test_unrelated_update_does_not_clear_backend_failure():
    diagnostics, _, _ = recorder()
    await diagnostics.observe({'type': 'session.started'})
    await diagnostics.observe(validation_error())
    await diagnostics.observe({'type': 'session.updated'})
    await diagnostics.observe({'type': 'response.event', 'event': {'type': 'response.completed'}})
    assert diagnostics.backend_unavailable


@pytest.mark.asyncio
async def test_rejected_fallback_update_notifies_without_another_retry():
    diagnostics, sent, _ = recorder(fallback_model='explicit-fallback')
    await diagnostics.observe({'type': 'session.started'})
    await diagnostics.observe(validation_error())
    await diagnostics.observe({'type': 'error', 'error': {
        'code': 'invalid_request_error', 'message': 'Update was rejected',
        'client_event_id': sent[0]['event_id']}})
    assert [event['type'] for event in sent] == ['session.update', 'session.instructions.append']
    assert diagnostics.backend_unavailable


@pytest.mark.asyncio
async def test_late_backend_result_does_not_override_rejected_fallback():
    diagnostics, sent, _ = recorder(fallback_model='explicit-fallback')
    await diagnostics.observe({'type': 'session.started'})
    await diagnostics.observe(validation_error())
    await diagnostics.observe({'type': 'session.updated', 'client_event_id': sent[0]['event_id']})
    await diagnostics.observe(validation_error('Fallback model is also inaccessible'))
    await diagnostics.observe({'type': 'response.event', 'event': {'type': 'response.completed'}})
    assert diagnostics.backend_unavailable


@pytest.mark.asyncio
async def test_same_model_is_not_retried():
    diagnostics, sent, _ = recorder(fallback_model='configured-backend')
    await diagnostics.observe({'type': 'session.started'})
    await diagnostics.observe(validation_error())
    assert not diagnostics.fallback_attempted
    assert [event['type'] for event in sent] == ['session.instructions.append']


@pytest.mark.asyncio
async def test_fatal_startup_error_has_provider_detail_without_credentials():
    diagnostics, _, _ = recorder(api_key='private-test-key')
    event = {'type': 'error', 'error': {'code': 'invalid_api_key', 'param': 'Authorization',
                                      'message': 'Invalid key private-test-key'}}
    with pytest.raises(LiveProviderError) as info:
        await wait_for_live_start(EventSocket([event]), diagnostics)
    assert 'invalid_api_key' in str(info.value) and 'Authorization' in str(info.value)
    assert 'private-test-key' not in str(info.value)


@pytest.mark.asyncio
async def test_missing_started_event_has_bounded_timeout_and_last_diagnostic():
    diagnostics, sent, _ = recorder()
    with pytest.raises(LiveProviderError, match='session_start_timeout.*responses_validation_failed'):
        await wait_for_live_start(EventSocket([validation_error()]), diagnostics, timeout=.02)
    assert not sent


@pytest.mark.asyncio
async def test_session_closed_before_ready_is_reported_immediately():
    diagnostics, _, _ = recorder()
    with pytest.raises(LiveProviderError, match='closed before session.started'):
        await wait_for_live_start(EventSocket([{'type': 'session.closed'}]), diagnostics)


def test_provider_diagnostic_is_bounded_redacted_and_single_line():
    error = validation_error('Bad Bearer abc-secret, key sk-other-secret\n' + 'x' * 3000)
    error['session'] = {'instructions': 'PRIVATE CALLER CONTEXT'}
    detail = provider_error_detail(error)
    assert len(detail) <= 1400 and '\n' not in detail
    assert 'abc-secret' not in detail and 'sk-other-secret' not in detail
    assert 'PRIVATE CALLER CONTEXT' not in detail


@pytest.mark.asyncio
@pytest.mark.parametrize('before_started', [True, False])
async def test_phone_audio_continues_after_backend_validation_error(tmp_path, monkeypatch, before_started):
    from app import db
    from app.config import get_settings
    from app.live_voice import LiveVoiceSession
    from test_live_voice import FakeOpenAI, FakeTwilio

    monkeypatch.setenv('DATABASE_URL', '')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'validation-call.db'))
    monkeypatch.setenv('OPENAI_API_KEY', 'private-test-key')
    monkeypatch.setenv('OPENAI_LIVE_FALLBACK_BACKEND_MODEL', '')
    get_settings.cache_clear()
    db.init_db()
    call = db.insert_call(None, 'receptionist', '+14155552671', 'outbound', 'live', 'ringing', 'openai_live')
    agent = db.one('SELECT * FROM agents WHERE id=?', ('receptionist',))

    class ValidationSocket(FakeOpenAI):
        async def send(self, raw):
            event = json.loads(raw)
            if event['type'] == 'session.start':
                self.sent.append(event)
                error = validation_error('Backend inaccessible; key private-test-key')
                ready = {'type': 'session.started', 'session': {'id': 'live-test'}}
                for item in ([error, ready] if before_started else [ready, error]):
                    await self.messages.put(json.dumps(item))
                await self.messages.put(json.dumps({'type': 'session.output_audio.delta',
                    'delta': base64.b64encode(b'\xff' * 320).decode()}))
            else:
                await super().send(raw)

    socket = ValidationSocket()
    monkeypatch.setattr('app.live_voice.websockets.connect', lambda *args, **kwargs: socket)
    twilio = FakeTwilio()
    stream = LiveVoiceSession(twilio, call, agent, None)
    try:
        await asyncio.wait_for(stream.run({'event': 'start', 'start': {'streamSid': 'MZ1'}}), timeout=3)
        assert any(event['event'] == 'media' for event in twilio.sent)
        assert any(event['type'] == 'session.input_audio.append' for event in socket.sent)
        events = db.call_details(call['id'])['events']
        assert any('Backend inaccessible' in event['content'] for event in events)
        assert not any('private-test-key' in event['content'] for event in events)
        assert stream.finalized
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_no_business_tool_executes_while_backend_is_unavailable(tmp_path, monkeypatch):
    from app import db
    from app.config import get_settings
    from app.live_voice import LiveVoiceSession
    from test_live_voice import FakeOpenAI, FakeTwilio

    monkeypatch.setenv('DATABASE_URL', '')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'unavailable-tool.db'))
    get_settings.cache_clear()
    db.init_db()
    call = db.insert_call(None, 'receptionist', '+14155552671', 'outbound', 'live', 'ringing', 'openai_live')
    agent = db.one('SELECT * FROM agents WHERE id=?', ('receptionist',))
    stream = LiveVoiceSession(FakeTwilio(), call, agent, None)
    stream.live = FakeOpenAI()
    stream.diagnostics.backend_unavailable = True

    async def unexpected_tool(*args):
        raise AssertionError('Business tools must not run during backend validation failure')

    monkeypatch.setattr('app.live_voice.live_functions.run', unexpected_tool)
    try:
        await stream.execute_delegated_calls([{'name': 'task_proposal', 'call_id': 'function-1',
                                              'arguments': {'title': 'Do work'}}])
        result = json.loads(stream.live.sent[0]['item']['output'])
        assert result['status'] == 'unavailable'
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize('backend_error', [True, False])
async def test_configuration_probe_observes_late_validation_without_dialing(
        tmp_path, monkeypatch, capsys, backend_error):
    from app import db
    from app.config import get_settings
    from test_live_voice import FakeOpenAI

    script = Path(__file__).resolve().parents[1] / 'scripts' / 'check_live_config.py'
    spec = importlib.util.spec_from_file_location('live_config_probe', script)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    monkeypatch.setenv('DATABASE_URL', '')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'probe.db'))
    monkeypatch.setenv('OPENAI_API_KEY', 'private-probe-key')
    get_settings.cache_clear()
    db.init_db()

    class ProbeSocket(FakeOpenAI):
        async def send(self, raw):
            event = json.loads(raw)
            self.sent.append(event)
            if event['type'] == 'session.start':
                await self.messages.put(json.dumps({'type': 'session.started'}))
                if backend_error:
                    await self.messages.put(json.dumps(validation_error('Model inaccessible private-probe-key')))
            elif event['type'] == 'session.close':
                await self.messages.put(json.dumps({'type': 'session.closed'}))

    socket = ProbeSocket()
    monkeypatch.setattr(probe.websockets, 'connect', lambda *args, **kwargs: socket)
    try:
        status = await probe.check('receptionist', .03)
        assert status == (1 if backend_error else 0)
        output = capsys.readouterr().out
        assert 'private-probe-key' not in output
        if backend_error:
            assert 'responses_validation_failed' in output and 'Model inaccessible' in output
        assert any(event['type'] == 'session.close' for event in socket.sent)
        assert not any(event['type'] == 'session.update' for event in socket.sent)
        assert db.one('SELECT COUNT(*) AS n FROM calls')['n'] == 0
    finally:
        get_settings.cache_clear()
