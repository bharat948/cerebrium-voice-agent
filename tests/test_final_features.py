"""Pure/offline acceptance tests. Real-provider smoke tests live in docs/VALIDATION.md."""
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_URL','')
    monkeypatch.setenv('DB_PATH',str(tmp_path/'final.db'))
    monkeypatch.setenv('DEMO_MODE','true')
    monkeypatch.setenv('APP_API_KEY','test-secret')
    monkeypatch.setenv('AUTH_MODE','api_key')
    from app.config import get_settings
    get_settings.cache_clear()
    from app import db
    db.init_db()
    from app.v3 import contacts
    user=contacts.register('Rahul','+919876543210','rahul@example.com',outbound_consent=True,email_consent=True)
    return db,user


def test_private_knowledge_not_leaked(setup):
    db,user=setup
    from app.v3 import knowledge
    x=db.insert_agent('Aria','News researcher','Hinglish','Research and cite sources')
    y=db.insert_agent('Kuber','Market analyst','Hinglish','Stick to evidence')
    doc=knowledge.ingest('private.md',b'Private uranium robotic supply chain notes',x['id'])
    assert doc['chunks']==1
    assert knowledge.search(x['id'],'robotic')
    assert not knowledge.search(y['id'],'robotic')
    knowledge.ingest('shared.md',b'Public electric vehicle finance metrics',x['id'],'shared','trusted')
    assert knowledge.search(y['id'],'finance')[0]['trust_tier']=='trusted'
    assert knowledge.ingest('private.md',b'Private uranium robotic supply chain notes',x['id'])['duplicate']


def test_pdf_file_blocking_and_empty(setup):
    from app.v3 import knowledge
    with pytest.raises(knowledge.KnowledgeError):knowledge.parse_file('image.exe',b'MZ')
    with pytest.raises(knowledge.KnowledgeError):knowledge.parse_file('huge.txt',b'x'*3_000_001)
    with pytest.raises(knowledge.KnowledgeError):knowledge.ingest('empty.md',b'    ',agent_id='receptionist')


def test_owner_approval_idempotent_and_isolated(setup):
    db,user=setup
    from app.v3 import governance
    request=governance.request_approval('receptionist','book_appointment',{'title':'Consultation'},user['id'])
    with pytest.raises(governance.PolicyViolation):governance.require_approved(request['id'],'book_appointment')
    decided=governance.decide(request['id'],True)
    assert decided['state']=='approved'
    assert governance.require_approved(request['id'],'book_appointment')['title']=='Consultation'
    with pytest.raises(governance.PolicyViolation):governance.decide(request['id'],False)
    with pytest.raises(governance.PolicyViolation):governance.require_approved(request['id'],'send_email')


def test_calendar_conflict_and_approval_scope(setup,monkeypatch):
    db,user=setup
    from app.v3 import governance,calendar_ops
    monkeypatch.setenv('DEMO_MODE','false')
    from app.config import get_settings
    get_settings.cache_clear()
    start=(datetime.now(timezone.utc)+timedelta(days=3)).replace(microsecond=0)
    end=start+timedelta(minutes=30)
    data={'title':'Consultation','starts_at':start.isoformat(),'ends_at':end.isoformat(),'contact_id':user['id']}
    req=governance.request_approval('receptionist','book_appointment',data,user['id'])
    governance.decide(req['id'],True)
    result=calendar_ops.book('receptionist',approval_id=req['id'],**data)
    assert result['state']=='confirmed'
    assert not calendar_ops.check(data['starts_at'],data['ends_at'])['available']
    assert calendar_ops.book('receptionist',approval_id=req['id'],**data)['id']==result['id']
    with pytest.raises(calendar_ops.AppointmentError):
        calendar_ops.book('receptionist',approval_id=req['id'],title='Other',starts_at=data['starts_at'],ends_at=data['ends_at'],contact_id=user['id'])


def test_cost_budget_protection(setup,monkeypatch):
    from app.v3 import governance
    governance.record_cost('openai','test',estimated_usd=0.4,agent_id='receptionist')
    assert governance.usage('receptionist')['total_estimated_or_actual_usd']==0.4
    monkeypatch.setenv('MONTHLY_BUDGET_USD','0.5')
    from app.config import get_settings
    get_settings.cache_clear()
    with pytest.raises(governance.PolicyViolation):governance.ensure_budget('receptionist',0.2)


def test_voice_tool_catalog_contact_permission(setup):
    db,user=setup
    from app.v3 import live_functions,registry
    agent=db.insert_agent('Aria','News','Hindi','Ask one question at a time')
    draft=registry.create_draft(agent['id'],{'tools':['news_rss']},template='news')
    registry.publish(agent['id'],draft['id'])
    config=registry.get_config(agent['id'])
    names={x['name'] for x in live_functions.definitions(config,True)}
    assert 'news_rss' in names and 'web_search' not in names  # only published tools
    assert 'research_email' in names and 'memory_search' in names
    assert 'task_proposal' not in names
    assert 'memory_search' not in {x['name'] for x in live_functions.definitions(config,False)}
    event={'type':'response.event','delegation_id':'del1','event':{'type':'response.output_item.done','item':{
        'type':'function_call','call_id':'c1','name':'news_rss','arguments':'{"query":"latest AI"}'}}}
    call=live_functions.completed_function_call(event)
    assert call['arguments']['query']=='latest AI'


@pytest.mark.asyncio
async def test_real_time_function_denies_unassigned_tool(setup):
    from app.v3 import live_functions,registry
    config=registry.get_config('receptionist')
    r=await live_functions.run('receptionist',None,'send_email',{'objective':'Private information'},config)
    assert r['status']=='denied'
    r=await live_functions.run('receptionist',None,'knowledge_search',{'query':'robotics'},config)
    assert r['status']=='completed'


def test_live_session_tool_contract(setup):
    from app.live_voice import session_start
    from app import db
    agent=db.one('SELECT * FROM agents WHERE id=?',('receptionist',))
    start=session_start(agent,None,'gpt-live-1','marin',enable_tools=True)
    assert start['session']['delegation']['responses']['tool_choice']=='auto'
    tools=start['session']['delegation']['responses']['tools']
    assert any(t['name']=='knowledge_search' for t in tools)
    assert all(t['type']=='function' and t['strict'] for t in tools)
    for tool in tools:
        params = tool['parameters']
        assert params['type'] == 'object'
        assert isinstance(params['properties'], dict)
        assert isinstance(params['required'], list)
        assert set(params['properties'].keys()) == set(params['required'])
    ks = next(t for t in tools if t['name'] == 'knowledge_search')
    assert ks['parameters']['properties'] == {'query': {'type': 'string'}}
    assert ks['parameters']['required'] == ['query']
    assert ks['description'] == 'Search the agent authorized document knowledge base'


def test_advanced_api_requires_auth(setup):
    from app.main import app
    with TestClient(app) as client:
        assert client.get('/api/v3/dashboard').status_code==401
        h={'X-API-Key':'test-secret'}
        assert client.get('/api/v3/dashboard',headers=h).status_code==200
        payload={'agent_id':'receptionist','action':'create_task','payload':{'title':'Test task'}}
        approval=client.post('/api/v3/approvals',json=payload,headers=h)
        assert approval.status_code==201
        assert client.get('/api/v3/approvals',headers=h).status_code==200
        decide=client.post('/api/v3/approvals/'+approval.json()['id']+'/decision',
                           json={'approve':True},headers=h)
        assert decide.status_code==200
        result=client.post('/api/v3/knowledge/upload',headers=h,files={'file':('hello.txt',b'Useful robotics systems guide','text/plain')},
                           data={'agent_id':'receptionist','visibility':'private'})
        assert result.status_code==201,result.text
        found=client.get('/api/v3/knowledge/search',headers=h,
                         params={'agent_id':'receptionist','query':'robotics'})
        assert found.status_code==200 and len(found.json())==1


def test_postcall_conservative_fallback(setup):
    from app import db
    from app.v3 import outcomes
    c=db.insert_call(None,'receptionist','+919876543210','outbound','demo','completed','openai_live')
    r=outcomes.fallback_report(c,[])
    assert r['status']=='unknown'
    assert not r['confirmed_facts']
