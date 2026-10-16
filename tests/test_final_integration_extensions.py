"""Provider-independent tests of final v3 feature integrations."""
import pytest
from datetime import datetime, timedelta, timezone


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', '')
    monkeypatch.setenv('DB_PATH', str(tmp_path/'features.db'))
    monkeypatch.setenv('DEMO_MODE', 'true')
    monkeypatch.setenv('AUTH_MODE', 'api_key')
    monkeypatch.setenv('OPENAI_API_KEY', '')
    from app.config import get_settings
    get_settings.cache_clear()
    from app import db
    from app.v3 import contacts
    db.init_db()
    contact = contacts.register('Test caller', '+919876543210', 'test@example.org', email_consent=True)
    return db, contact


@pytest.mark.asyncio
async def test_local_appointment_functions_are_proposals_not_bookings(workspace):
    db, contact = workspace
    from app.v3 import registry, live_functions
    agent = db.insert_agent('Mira', 'Appointment manager', 'English', 'Check times before booking')
    draft = registry.create_draft(agent['id'], {}, template='appointments')
    registry.publish(agent['id'], draft['id'])
    config = registry.get_config(agent['id'])
    enabled = {tool['name'] for tool in live_functions.definitions(config, True)}
    assert 'calendar_check' in enabled and 'appointment_proposal' in enabled
    assert 'appointment_proposal' not in {tool['name'] for tool in live_functions.definitions(config, False)}
    start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0)
    details = {'title': 'Consultation', 'starts_at': start.isoformat(),
               'ends_at': (start+timedelta(minutes=30)).isoformat()}
    availability = await live_functions.run(agent['id'], contact, 'calendar_check', details, config)
    assert availability['status'] == 'completed' and availability['available'] is True
    proposed = await live_functions.run(agent['id'], contact, 'appointment_proposal', details, config)
    assert proposed['status'] == 'approval_required'
    assert db.one('SELECT COUNT(*) AS n FROM calendar_events')['n'] == 0
    assert db.one('SELECT state FROM approvals WHERE id=?',(proposed['approval_id'],))['state'] == 'pending'


@pytest.mark.asyncio
async def test_knowledge_semantic_search_lexical_fallback(workspace):
    db, contact = workspace
    from app.v3 import knowledge
    x = db.insert_agent('Knowledge agent', 'Research', 'English', 'Cite sources')
    knowledge.ingest('notes.md',b'Indian public market analysis and earnings',agent_id=x['id'])
    results = await knowledge.semantic_search(x['id'], 'earnings')
    assert len(results)==1 and results[0]['trust_tier']=='provisional'
    with pytest.raises(knowledge.KnowledgeError):
        await knowledge.index_embeddings('none')


def test_durable_schedule_enqueue_is_not_duplicated(workspace):
    db, contact=workspace
    from app.v3 import schedules
    row=schedules.create('receptionist',contact['id'],'Review the latest AI robotics research',hour=9)
    due=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
    db.execute('UPDATE mission_schedules SET next_run_at=? WHERE id=?',(due,row['id']))
    assert schedules.tick()==1
    assert schedules.tick()==0
    assert db.one('SELECT COUNT(*) AS n FROM schedule_occurrences')['n']==1
    assert db.one('SELECT COUNT(*) AS n FROM missions')['n']==1


def test_google_connection_tokens_encrypted_and_not_exposed(workspace, monkeypatch):
    db, contact=workspace
    from app.v3 import google_services
    from app.config import get_settings
    from cryptography.fernet import Fernet
    monkeypatch.setenv('INTEGRATION_ENCRYPTION_KEY',Fernet.generate_key().decode())
    get_settings.cache_clear()
    google_services.put_token({'access_token':'dummy-secret','refresh_token':'offline-secret',
                               'expires_at':9999999999})
    item=db.one("SELECT * FROM integrations WHERE provider='google'")
    assert google_services.connected()
    assert 'dummy-secret' not in item['encrypted_credentials']
    assert 'offline-secret' not in item['encrypted_credentials']
