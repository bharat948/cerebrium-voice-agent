"""Explicit owner-connected Google Contacts/Calendar, encrypted token storage.

Never store access/refresh tokens in browser sessions, logs or model context.
"""
import json
import time
import httpx
from app import db
from app.config import get_settings
from app.v3 import contacts

SCOPES='openid email profile https://www.googleapis.com/auth/contacts.readonly https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.readonly'

class GoogleIntegrationError(ValueError): pass


def _cipher():
    from cryptography.fernet import Fernet
    key=get_settings().integration_encryption_key
    if not key: raise GoogleIntegrationError('Configure INTEGRATION_ENCRYPTION_KEY before connecting Google')
    try:return Fernet(key.encode())
    except (ValueError,TypeError):raise GoogleIntegrationError('Integration encryption key must be a valid Fernet key') from None


def put_token(token):
    from cryptography.fernet import Fernet
    if not token.get('refresh_token'):
        previous=db.one("SELECT encrypted_credentials FROM integrations WHERE provider='google'")
        if previous:
            old=json.loads(_cipher().decrypt(previous['encrypted_credentials'].encode()))
            token['refresh_token']=old.get('refresh_token')
    encrypted=_cipher().encrypt(json.dumps({k:v for k,v in token.items() if k in
                     ('access_token','refresh_token','expires_at','token_type','scope')}).encode()).decode()
    with db.connect() as c:
        c.execute("DELETE FROM integrations WHERE provider='google'")
        c.execute('INSERT INTO integrations VALUES (?,?,?,?)',('google',encrypted,token.get('scope',SCOPES),db.now()))


def connected():
    return bool(db.one("SELECT provider FROM integrations WHERE provider='google'"))


async def access_token():
    row=db.one("SELECT encrypted_credentials FROM integrations WHERE provider='google'")
    if not row:raise GoogleIntegrationError('Google services not connected')
    data=json.loads(_cipher().decrypt(row['encrypted_credentials'].encode()).decode())
    if float(data.get('expires_at') or 0)>time.time()+90:return data['access_token']
    refresh=data.get('refresh_token')
    if not refresh:raise GoogleIntegrationError('Google refresh token unavailable: reconnect')
    s=get_settings()
    async with httpx.AsyncClient(timeout=12) as client:
        result=await client.post('https://oauth2.googleapis.com/token',data={
            'client_id':s.google_client_id,'client_secret':s.google_client_secret,
            'refresh_token':refresh,'grant_type':'refresh_token'})
        if result.status_code!=200:raise GoogleIntegrationError('Google authorization expired: reconnect')
    token=result.json();token['expires_at']=time.time()+int(token.get('expires_in',3600))
    token['refresh_token']=refresh
    put_token(token)
    return token['access_token']


async def api_get(url,params=None):
    if not url.startswith('https://people.googleapis.com/v1/') and not url.startswith('https://www.googleapis.com/calendar/v3/'):
        raise GoogleIntegrationError('Unsupported Google API URL')
    async with httpx.AsyncClient(timeout=15) as client:
        result=await client.get(url,params=params,headers={'Authorization':'Bearer '+await access_token()})
        if result.status_code>=400:raise GoogleIntegrationError(f'Google API returned {result.status_code}')
    return result.json()


async def import_contacts(limit=250):
    if not 1<=limit<=1000:raise GoogleIntegrationError('Invalid contact import limit')
    result={'imported':0,'skipped':0,'errors':[]};page=None
    while result['imported']+result['skipped']<limit:
        params={'personFields':'names,phoneNumbers,emailAddresses','pageSize':min(100,limit-result['imported']-result['skipped'])}
        if page:params['pageToken']=page
        payload=await api_get('https://people.googleapis.com/v1/people/me/connections',params)
        persons=payload.get('connections',[])
        for person in persons:
            phones=person.get('phoneNumbers') or []
            if not phones: continue
            name=((person.get('names') or [{}])[0].get('displayName') or 'Contact')
            email=((person.get('emailAddresses') or [{}])[0].get('value'))
            # Google data does not confer consent to call or email.
            phone=(phones[0].get('canonicalForm') or phones[0].get('value') or '')
            try:
                contacts.register(name,phone,email)
                result['imported']+=1
            except ValueError as exc:
                result['skipped']+=1
                if len(result['errors'])<10:result['errors'].append(str(exc))
        page=payload.get('nextPageToken')
        if not page:break
    return result


async def calendar_events(time_min,time_max,limit=30):
    params={'timeMin':time_min,'timeMax':time_max,'maxResults':min(limit,100),
            'singleEvents':'true','orderBy':'startTime'}
    data=await api_get('https://www.googleapis.com/calendar/v3/calendars/primary/events',params)
    return [{'id':e.get('id'),'title':e.get('summary','Busy'), 'start':e.get('start'),
             'end':e.get('end'), 'status':e.get('status')} for e in data.get('items',[])]
