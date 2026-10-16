from test_v3 import auth, create_contact, client

def test_contact_edit_revoke_and_soft_delete(client):
    contact=create_contact(client,email=True).json()
    cid=contact['id']
    res=client.patch(f'/api/v3/contacts/{cid}',headers=auth(),json={'email':'different@example.test'})
    assert res.status_code==200,res.text
    assert res.json()['email_consent']==0
    res=client.patch(f'/api/v3/contacts/{cid}',headers=auth(),json={'email_consent':True,'outbound_consent':False})
    assert res.status_code==200
    assert res.json()['outbound_consent']==0
    grant=client.put(f'/api/v3/agents/receptionist/contacts/{cid}/permission',headers=auth(),json={'allowed':True})
    assert grant.status_code==200
    removed=client.delete(f'/api/v3/contacts/{cid}',headers=auth())
    assert removed.status_code==200
    assert client.get('/api/v3/contacts',headers=auth()).json()==[]
    assert client.patch(f'/api/v3/contacts/{cid}',headers=auth(),json={'name':'Other'}).status_code==422
    from app import db
    assert db.one('SELECT outbound_consent,email_consent,active FROM contacts WHERE id=?',(cid,))=={'outbound_consent':0,'email_consent':0,'active':0}
    assert db.one('SELECT * FROM agent_contact_permissions WHERE contact_id=?',(cid,)) is None
