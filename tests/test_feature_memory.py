from test_v3 import auth,client,create_contact


def test_memory_correction_version_and_scope(client):
    a=create_contact(client).json()['id']
    b=create_contact(client,name='Other',phone='+919876543212').json()['id']
    created=client.post('/api/v3/memories',headers=auth(),json={
        'agent_id':'receptionist','contact_id':a,'content':'Prefers detailed analysis'}).json()
    mid=created['id']
    assert client.post(f'/api/v3/memories/{mid}/correct',headers=auth(),json={
        'contact_id':b,'content':'Prefers concise answers'}).status_code==422
    revised=client.post(f'/api/v3/memories/{mid}/correct',headers=auth(),json={
        'contact_id':a,'content':'Prefers concise answers'})
    assert revised.status_code==200,revised.text
    records=client.get('/api/v3/memories',headers=auth(),params={
        'agent_id':'receptionist','contact_id':a}).json()
    assert len(records)==1 and records[0]['content']=='Prefers concise answers'
    history=client.get('/api/v3/memories/history',headers=auth(),params={
        'agent_id':'receptionist','contact_id':a}).json()
    assert any(x['kind']=='corrected' and x['replacement_id']==revised.json()['id'] for x in history)
    assert client.delete(f"/api/v3/memories/{revised.json()['id']}",headers=auth(),params={'contact_id':a}).status_code==200
    assert client.get('/api/v3/memories',headers=auth(),params={
        'agent_id':'receptionist','contact_id':a}).json()==[]


def test_sensitive_correction_requires_fresh_consent(client):
    cid=create_contact(client).json()['id']
    m=client.post('/api/v3/memories',headers=auth(),json={
        'agent_id':'receptionist','contact_id':cid,'content':'Prefers morning calls',
        'sensitivity':'health','consent':True}).json()
    denied=client.post(f"/api/v3/memories/{m['id']}/correct",headers=auth(),json={
        'contact_id':cid,'content':'Prefers evening calls'})
    assert denied.status_code==403
