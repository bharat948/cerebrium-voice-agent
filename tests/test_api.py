import os
from fastapi.testclient import TestClient
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'test.db'))
    monkeypatch.setenv('APP_API_KEY','test-key-not-public')
    monkeypatch.setenv('DEMO_MODE','true')
    monkeypatch.setenv('OPENAI_API_KEY','')
    monkeypatch.setenv('PUBLIC_BASE_URL','')
    from app.config import get_settings
    get_settings.cache_clear()
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def auth(): return {'X-API-Key':'test-key-not-public'}


def plan_request(client, phone='+14155552671', agent='receptionist'):
    return client.post('/api/plans', headers=auth(),json={
        'phone':phone,'agent_id':agent,'message':'Ask politely whether they want a callback regarding their appointment.'
    })


def test_health_auth_and_frontend(client):
    assert client.get('/health').status_code == 200
    assert client.get('/').status_code == 200
    assert 'Voice Foundry' in client.get('/').text
    assert client.get('/api/agents').status_code == 401
    assert client.get('/api/agents',headers=auth()).status_code == 200
    assert client.get('/api/config',headers=auth()).json()['demo_mode'] is True


def test_plan_to_preview_and_history(client):
    plan = plan_request(client)
    assert plan.status_code == 201,plan.text
    plan = plan.json()
    assert len(plan['agenda'])>=3
    update=client.patch('/api/plans/'+plan['id'],headers=auth(),json={
        'goal':'Collect availability only','agenda':['Disclose AI identity','Ask availability'],
        'script':'Hello, this is an AI assistant.'})
    assert update.status_code==200
    assert update.json()['goal']=='Collect availability only'
    not_confirmed=client.post('/api/calls',headers=auth(),json={'plan_id':plan['id'],'confirm':False})
    assert not_confirmed.status_code==400
    created=client.post('/api/calls',headers=auth(),json={'plan_id':plan['id'],'confirm':True})
    assert created.status_code==201,created.text
    call=created.json()
    assert call['status']=='simulated' and call['twilio_sid'] is None
    assert 'no phone call' in call['events'][0]['content'].lower()
    duplicate=client.post('/api/calls',headers=auth(),json={'plan_id':plan['id'],'confirm':True})
    assert duplicate.status_code==409
    turn=client.post('/api/calls/'+call['id']+'/preview',headers=auth(),json={'text':'Friday afternoon works.'})
    assert turn.status_code==200
    events=turn.json()['events']
    assert any(e['speaker']=='caller' for e in events)
    assert any(e['speaker']=='assistant' for e in events)
    summary=client.post('/api/calls/'+call['id']+'/summary',headers=auth())
    assert summary.status_code == 200
    assert 'no external business action' in summary.json()['summary'].lower()
    stop=client.post('/api/calls/'+call['id']+'/hangup',headers=auth())
    assert stop.status_code==200 and stop.json()['status']=='completed'
    cannot_continue=client.post('/api/calls/'+call['id']+'/preview',headers=auth(),json={'text':'Hi'})
    assert cannot_continue.status_code==409


def test_agent_and_phone_validation(client):
    resp=client.post('/api/agents',headers=auth(),json={'name':'Mira','role':'Customer support',
       'language':'English','instructions':'You ask short, respectful questions.'})
    assert resp.status_code==201
    assert plan_request(client,'not-a-phone').status_code==422
    missing=plan_request(client,agent='unknown')
    assert missing.status_code==404


def test_twilio_rejects_unsigned_webhook(client):
    response=client.post('/twilio/voice',data={'CallSid':'CAinvalid'})
    assert response.status_code==403
    response=client.post('/twilio/status',data={'CallSid':'CAinvalid','CallStatus':'completed'})
    assert response.status_code==403


def test_plan_route_exposes_safe_diagnostic(client, monkeypatch):
    from app import main, planner

    async def fail(_message, _settings):
        raise planner.OpenAIProviderError(429, 'insufficient_quota')

    monkeypatch.setattr(main, 'build_plan', fail)
    response = client.post('/api/plans', headers={'X-API-Key': 'test-key-not-public'}, json={
        'phone': '+14155552671', 'agent_id': 'receptionist', 'message': 'Ask about availability.'
    })
    assert response.status_code == 502
    assert '429' in response.json()['detail']
    assert 'billing' in response.json()['detail'].lower()
