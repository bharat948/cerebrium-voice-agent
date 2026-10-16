from test_v3 import auth, client


def test_rollback_creates_new_draft_and_preserves_old_releases(client):
    r=client.post('/api/v3/agents/from-template',headers=auth(),json={'template':'news'}).json()
    aid=r['agent']['id']
    first=r['draft']
    assert client.post(f"/api/v3/agents/{aid}/releases/{first['id']}/publish",headers=auth()).status_code==200
    second=client.post(f"/api/v3/agents/{aid}/drafts",headers=auth(),json={'changes':{'personality':'Reserved and measured.'}}).json()
    assert client.post(f"/api/v3/agents/{aid}/releases/{second['id']}/publish",headers=auth()).status_code==200
    recovery=client.post(f"/api/v3/agents/{aid}/releases/{first['id']}/restore",headers=auth())
    assert recovery.status_code==200,recovery.text
    draft=recovery.json()['draft']
    assert draft['version']==3 and 'Curious' in draft['configuration']['personality']
    assert 'Reserved' in client.get(f'/api/v3/agents/{aid}/prompt',headers=auth()).json()['compiled_prompt']
    assert client.post(f"/api/v3/agents/{aid}/releases/{draft['id']}/publish",headers=auth()).status_code==200
    assert 'Curious' in client.get(f'/api/v3/agents/{aid}/prompt',headers=auth()).json()['compiled_prompt']
    versions=client.get(f'/api/v3/agents/{aid}/releases',headers=auth()).json()
    assert [v['version'] for v in versions]==[3,2,1]
    assert [v['status'] for v in versions]==['published','archived','archived']
