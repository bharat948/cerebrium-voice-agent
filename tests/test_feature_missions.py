from test_v3 import auth,client,create_contact


def mission(client):
    cid=create_contact(client,email=True).json()['id']
    m=client.post('/api/v3/missions',headers=auth(),json={
        'agent_id':'receptionist','contact_id':cid,'objective':'Research available AI news sources in India.'})
    assert m.status_code==201,m.text
    return m.json()['id']


def test_pause_revise_resume_cancel_and_events(client):
    mid=mission(client)
    pause=client.post(f'/api/v3/missions/{mid}/pause',headers=auth())
    assert pause.status_code==200
    assert pause.json()['state']=='paused'
    revised=client.patch(f'/api/v3/missions/{mid}',headers=auth(),json={
        'objective':'Research two verified releases from the Indian market.'})
    assert revised.status_code==200
    assert 'Indian market' in revised.json()['objective']
    resumed=client.post(f'/api/v3/missions/{mid}/resume',headers=auth())
    assert resumed.status_code==200
    cancelled=client.post(f'/api/v3/missions/{mid}/cancel',headers=auth())
    assert cancelled.status_code==200
    assert cancelled.json()['state']=='canceled'
    assert client.post(f'/api/v3/missions/{mid}/resume',headers=auth()).status_code==409
    assert [e['event_type'] for e in cancelled.json()['events']]==['created','pause','revise','resume','cancel']


def test_running_mission_cancelled_before_email_dispatch(client,monkeypatch):
    from app.v3 import missions
    import asyncio
    mid=mission(client)
    claimed=missions.claim()
    assert claimed['id']==mid
    monkeypatch.setenv('DEMO_MODE','false')
    from app.config import get_settings
    get_settings.cache_clear()
    async def research(_,agent_id):
        missions.transition(mid,'cancel')
        return 'Research is complete'
    def fail_send(*a):
        raise AssertionError('Email should not be sent after cancellation')
    monkeypatch.setattr(missions,'_research',research)
    monkeypatch.setattr(missions,'_send_email',fail_send)
    asyncio.run(missions.process(claimed))
    assert missions.detail(mid)['state']=='canceled'
