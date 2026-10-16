from test_v3 import auth,client


def test_tool_isolation_and_demo_mode(client):
    news=client.post('/api/v3/agents/from-template',headers=auth(),json={'template':'news'}).json()
    aid=news['agent']['id']
    assert client.post(f"/api/v3/agents/{aid}/releases/{news['draft']['id']}/publish",headers=auth()).status_code==200
    result=client.post('/api/v3/tools/query',headers=auth(),json={
        'agent_id':aid,'name':'news_rss','query':'India AI policy','limit':2})
    assert result.status_code==200,result.text
    assert result.json()['status']=='simulated' and result.json()['results']==[]
    forbidden=client.post('/api/v3/tools/query',headers=auth(),json={
        'agent_id':'receptionist','name':'web_search','query':'NVIDIA earnings'})
    assert forbidden.status_code==403
    write=client.post('/api/v3/tools/query',headers=auth(),json={
        'agent_id':aid,'name':'tasks','query':'delete everything'})
    assert write.status_code==403


def test_tool_returns_attributed_metadata_only(client,monkeypatch):
    from app.config import get_settings
    from app.v3 import tools
    import asyncio
    news=client.post('/api/v3/agents/from-template',headers=auth(),json={'template':'news'}).json()
    aid=news['agent']['id']
    assert client.post(f"/api/v3/agents/{aid}/releases/{news['draft']['id']}/publish",headers=auth()).status_code==200
    monkeypatch.setenv('DEMO_MODE','false');get_settings.cache_clear()
    async def fake_news(query,limit):
        return [{'title':'Example','url':'https://example.test/story','source':'Testing',
                 'description':'Metadata only'}]
    monkeypatch.setattr(tools,'news_rss',fake_news)
    result=client.post('/api/v3/tools/query',headers=auth(),json={
        'agent_id':aid,'name':'news_rss','query':'AI policy news'})
    assert result.status_code==200,result.text
    assert result.json()['verified_article_content'] is False
    assert result.json()['results'][0]['source']=='Testing'
