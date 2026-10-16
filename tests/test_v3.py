"""v3 domain integration tests with isolated SQLite test databases."""

def auth(): return {"X-API-Key":"test-key-not-public"}

import pytest
from fastapi.testclient import TestClient

@pytest.fixture()
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'test_v3.db'))
    monkeypatch.setenv('DATABASE_URL','')
    monkeypatch.setenv('APP_API_KEY','test-key-not-public')
    monkeypatch.setenv('DEMO_MODE','true')
    monkeypatch.setenv('OPENAI_API_KEY','')
    monkeypatch.setenv('ENABLE_BACKGROUND_WORKER','false')
    from app.config import get_settings
    get_settings.cache_clear()
    from app.main import app
    with TestClient(app) as tc: yield tc
    get_settings.cache_clear()



def create_contact(client, name='Rahul', phone='+919876543210', call=True, email=False):
    return client.post('/api/v3/contacts', headers=auth(), json={
        'name':name,'phone':phone,'email':'rahul@example.test','language':'Hinglish',
        'outbound_consent':call,'email_consent':email
    })


def test_templates_release_lifecycle_and_stable_prompts(client):
    templates=client.get('/api/v3/templates',headers=auth())
    assert templates.status_code==200 and {'news','markets','appointments','tasks'} <= set(templates.json())
    result=client.post('/api/v3/agents/from-template',headers=auth(),json={'template':'news'})
    assert result.status_code==201,result.text
    a=result.json()['agent'];draft=result.json()['draft']
    assert draft['status']=='draft'
    published=client.post(f"/api/v3/agents/{a['id']}/releases/{draft['id']}/publish",headers=auth())
    assert published.status_code==200
    prompt=client.get(f"/api/v3/agents/{a['id']}/prompt",headers=auth())
    assert 'PLATFORM RULES' in prompt.json()['compiled_prompt']
    assert 'News research specialist' in prompt.json()['compiled_prompt']
    bad=client.post(f"/api/v3/agents/{a['id']}/drafts",headers=auth(),json={'changes':{'danger':'yes'}})
    assert bad.status_code==422
    second=client.post(f"/api/v3/agents/{a['id']}/drafts",headers=auth(),json={'changes':{'personality':'Calm and careful.'}})
    assert second.status_code==201
    assert 'Curious' in client.get(f"/api/v3/agents/{a['id']}/prompt",headers=auth()).json()['compiled_prompt']
    client.post(f"/api/v3/agents/{a['id']}/releases/{second.json()['id']}/publish",headers=auth())
    assert 'Calm and careful.' in client.get(f"/api/v3/agents/{a['id']}/prompt",headers=auth()).json()['compiled_prompt']


def test_contacts_permissions_memories_and_isolation(client):
    c=create_contact(client)
    assert c.status_code==201,c.text
    cid=c.json()['id']
    duplicate=create_contact(client)
    assert duplicate.status_code==422
    others=create_contact(client,'Simran','+919876543211')
    assert others.status_code==201
    m=client.post('/api/v3/memories',headers=auth(),json={
        'agent_id':'receptionist','contact_id':cid,'content':'Prefers short Hinglish explanations'})
    assert m.status_code==201,m.text
    mid=m.json()['id']
    forbidden=client.post('/api/v3/memories',headers=auth(),json={
        'agent_id':'receptionist','contact_id':cid,'content':'Has a medical appointment',
        'sensitivity':'health','consent':False})
    assert forbidden.status_code==403
    restricted=client.post('/api/v3/memories',headers=auth(),json={
        'agent_id':'receptionist','contact_id':cid,'content':'OTP is 123456'})
    assert restricted.status_code==422
    assert len(client.get('/api/v3/memories',headers=auth(),params={'agent_id':'receptionist','contact_id':cid}).json())==1
    assert not client.get('/api/v3/memories',headers=auth(),params={'agent_id':'receptionist','contact_id':others.json()['id']}).json()
    assert client.delete(f'/api/v3/memories/{mid}',params={'contact_id':cid},headers=auth()).status_code==200
    assert not client.get('/api/v3/memories',headers=auth(),params={'agent_id':'receptionist','contact_id':cid}).json()
    permission=client.put(f'/api/v3/agents/receptionist/contacts/{cid}/permission',headers=auth(),json={'allowed':True})
    assert permission.status_code==200


def test_contact_csv_import_is_not_implicit_consent(client):
    from io import BytesIO
    csv=b'name,phone,email\nTest A,+919000000001,a@example.test\nTest B,+919000000002,b@example.test\n'
    response=client.post('/api/v3/contacts/import',headers=auth(),files={'file':('contacts.csv',BytesIO(csv),'text/csv')})
    assert response.status_code==200,response.text
    assert response.json()['imported']==2
    rows=client.get('/api/v3/contacts',headers=auth()).json()
    assert all(row['outbound_consent']==0 for row in rows)


def test_durable_research_mission_demo_mode(client):
    from app.v3 import missions
    c=create_contact(client,email=True)
    m=client.post('/api/v3/missions',headers=auth(),json={
        'agent_id':'receptionist','contact_id':c.json()['id'],
        'objective':'Research five recent AI news announcements in India.'})
    assert m.status_code==201,m.text
    job=missions.claim()
    assert job['id']==m.json()['id']
    import asyncio
    asyncio.run(missions.process(job))
    from app import db
    assert db.one('SELECT state FROM missions WHERE id=?',(job['id'],))['state']=='simulated'


def test_private_contact_cannot_reach_other_memories_by_default(client):
    # For v3, the database lookup always scopes by both contact ID and agent ID.
    from app.v3.memory import relevant
    assert relevant('receptionist','missing') == []


def test_contact_opt_in_required_for_live_call(client,monkeypatch):
    from app.config import get_settings
    c=create_contact(client,call=False)
    assert c.status_code==201
    plan=client.post('/api/plans',headers=auth(),json={
        'contact_id':c.json()['id'],'phone':'','agent_id':'receptionist',
        'message':'Discuss a proposed appointment and ask for availability.'})
    assert plan.status_code==201
    monkeypatch.setenv('DEMO_MODE','false')
    monkeypatch.setenv('OPENAI_API_KEY','test-openai')
    monkeypatch.setenv('TWILIO_ACCOUNT_SID','ACfake')
    monkeypatch.setenv('TWILIO_AUTH_TOKEN','fake')
    monkeypatch.setenv('TWILIO_PHONE_NUMBER','+14155551000')
    monkeypatch.setenv('PUBLIC_BASE_URL','https://example.test')
    get_settings.cache_clear()
    response=client.post('/api/calls',headers=auth(),json={'plan_id':plan.json()['id'],'confirm':True})
    assert response.status_code==403
    assert 'consent' in response.json()['detail'].lower()


def test_published_configuration_pinned_to_existing_call(client):
    from app import db
    from app.v3.registry import compile_prompt
    created=client.post('/api/v3/agents/from-template',headers=auth(),json={'template':'news'}).json()
    a=created['agent']; release=created['draft']
    client.post(f"/api/v3/agents/{a['id']}/releases/{release['id']}/publish",headers=auth())
    call=db.insert_call(None,a['id'],'+919999999999','inbound','demo','simulated','openai_live')
    draft=client.post(f"/api/v3/agents/{a['id']}/drafts",headers=auth(),json={
        'changes':{'personality':'Only direct factual headlines.'}}).json()
    client.post(f"/api/v3/agents/{a['id']}/releases/{draft['id']}/publish",headers=auth())
    old=compile_prompt(a,release_id=call['agent_release_id'])
    new=compile_prompt(a)
    assert 'Curious, concise' in old
    assert 'Only direct factual headlines' in new
    assert 'Only direct factual headlines' not in old


def test_lease_recovery_is_safe_around_email_delivery(client):
    from app import db
    from app.v3.missions import recover_expired
    c=create_contact(client,email=True).json()
    rows=[]
    for state in ('running','sending'):
        mission=db.uid()
        db.execute('INSERT INTO missions (id,agent_id,contact_id,kind,objective,payload,state,attempts,lease_until,next_run_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                   (mission,'receptionist',c['id'],'research_email','Research a news topic thoroughly','{}',state,1,'2020-01-01T00:00:00+00:00',db.now(),db.now(),db.now()))
        rows.append(mission)
    recover_expired()
    assert db.one('SELECT state FROM missions WHERE id=?',(rows[0],))['state']=='queued'
    assert db.one('SELECT state FROM missions WHERE id=?',(rows[1],))['state']=='sending'
