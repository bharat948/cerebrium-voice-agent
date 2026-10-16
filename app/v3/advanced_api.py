"""Authenticated v3 owner API for knowledge, governance, integrations and outcomes."""
import json
from fastapi import APIRouter,Depends,UploadFile,File,Form,HTTPException,Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel,Field
from app import db
from app.config import get_settings
from app.security import require_api_key
from app.v3 import governance,knowledge,calendar_ops,outcomes,google_services,schedules

router=APIRouter(prefix='/api/v3',dependencies=[Depends(require_api_key)],tags=['Voice Foundry Platform'])

class ApprovalIn(BaseModel):
    agent_id:str
    action:str
    contact_id:str|None=None
    payload:dict=Field(default_factory=dict)
class DecisionIn(BaseModel):
    approve:bool
class ControlIn(BaseModel):
    command:str
    instruction:str|None=None
class CalendarSlot(BaseModel):
    starts_at:str
    ends_at:str
class Booking(BaseModel):
    agent_id:str
    contact_id:str|None=None
    title:str=Field(min_length=2,max_length=200)
    starts_at:str
    ends_at:str
    approval_id:str
class FeedbackIn(BaseModel):
    agent_id:str
    release_id:str|None=None
    call_id:str|None=None
    rating:int=Field(ge=1,le=5)
    note:str=Field(default='',max_length=2000)
class KnowledgeTier(BaseModel):
    tier:str
class ScheduleIn(BaseModel):
    agent_id:str
    contact_id:str
    objective:str=Field(min_length=10,max_length=2500)
    interval:str='daily'
    hour:int=Field(default=9,ge=0,le=23)
    minute:int=Field(default=0,ge=0,le=59)
    tz:str='Asia/Kolkata'

class CostIn(BaseModel):
    provider:str
    operation:str
    agent_id:str|None=None
    estimated_usd:float=Field(ge=0,le=10000)

@router.get('/dashboard')
def dashboard():
    return {
      'agents':db.one('SELECT COUNT(*) AS n FROM agents')['n'],
      'active_calls':db.one("SELECT COUNT(*) AS n FROM calls WHERE status IN ('initiated','ringing','in-progress')")['n'],
      'open_missions':db.one("SELECT COUNT(*) AS n FROM missions WHERE state IN ('queued','running','paused','blocked')")['n'],
      'contacts':db.one('SELECT COUNT(*) AS n FROM contacts WHERE active=1')['n'],
      'pending_approvals':db.one("SELECT COUNT(*) AS n FROM approvals WHERE state='pending'")['n'],
      'unread_notifications':db.one("SELECT COUNT(*) AS n FROM notifications WHERE state='unread'")['n'],
      'costs':governance.usage()}

@router.get('/approvals')
def approvals():return db.many('SELECT * FROM approvals ORDER BY requested_at DESC LIMIT 100')

@router.post('/approvals',status_code=201)
def approval(body:ApprovalIn):
    try:return governance.request_approval(**body.model_dump())
    except governance.PolicyViolation as e:raise HTTPException(422,str(e)) from None

@router.post('/approvals/{approval_id}/decision')
def decision(approval_id:str,body:DecisionIn):
    try:return governance.decide(approval_id,body.approve)
    except governance.PolicyViolation as e:raise HTTPException(409,str(e)) from None

@router.get('/notifications')
def notifications():return db.many('SELECT * FROM notifications ORDER BY created_at DESC LIMIT 100')

@router.post('/notifications/{notification_id}/read')
def mark_read(notification_id:str):
    if not db.execute("UPDATE notifications SET state='read',read_at=? WHERE id=?",(db.now(),notification_id)):
        raise HTTPException(404,'Notification missing')
    return {'status':'read'}

@router.get('/costs')
def costs(agent_id:str|None=None,days:int=30):
    if days<1 or days>365:raise HTTPException(422,'days out of range')
    return governance.usage(agent_id,days)

@router.post('/calls/{call_id}/control')
def control(call_id:str,body:ControlIn):
    try:return governance.control(call_id,body.command,body.instruction)
    except governance.PolicyViolation as e:raise HTTPException(409,str(e)) from None

@router.get('/calls/{call_id}/outcome')
def outcome(call_id:str):
    result=db.one('SELECT * FROM outcome_reports WHERE call_id=?',(call_id,))
    if not result:raise HTTPException(404,'Report not yet available')
    return {**result,'details':json.loads(result['details'])}

@router.post('/calls/{call_id}/outcome')
async def extract_outcome(call_id:str):
    if not db.one('SELECT id FROM calls WHERE id=?',(call_id,)):
        raise HTTPException(404,'Call missing')
    return await outcomes.process_call(call_id)

@router.get('/knowledge')
def sources(agent_id:str|None=None):
    if agent_id:
        return db.many("SELECT * FROM knowledge_sources WHERE visibility='shared' OR agent_id=? ORDER BY updated_at DESC LIMIT 100",(agent_id,))
    return db.many('SELECT * FROM knowledge_sources ORDER BY updated_at DESC LIMIT 200')

@router.post('/knowledge/upload',status_code=201)
async def ingest(file:UploadFile=File(...),agent_id:str|None=Form(None),
                 visibility:str=Form('private'),trust_tier:str=Form('provisional')):
    raw=await file.read(knowledge.MAX_BYTES+1)
    try:return knowledge.ingest(file.filename or 'document.txt',raw,agent_id,visibility,trust_tier)
    except knowledge.KnowledgeError as e:raise HTTPException(422,str(e)) from None

@router.get('/knowledge/search')
def knowledge_search(agent_id:str,query:str,limit:int=5):
    try:return knowledge.search(agent_id,query,limit)
    except knowledge.KnowledgeError as e:raise HTTPException(422,str(e)) from None

@router.post('/knowledge/{source_id}/index')
async def index_knowledge(source_id:str):
    try:return await knowledge.index_embeddings(source_id)
    except knowledge.KnowledgeError as e:raise HTTPException(422,str(e)) from None

@router.get('/knowledge/semantic-search')
async def semantic_knowledge_search(agent_id:str,query:str,limit:int=5):
    try:return await knowledge.semantic_search(agent_id,query,limit)
    except knowledge.KnowledgeError as e:raise HTTPException(422,str(e)) from None

@router.patch('/knowledge/{source_id}/tier')
def change_tier(source_id:str,body:KnowledgeTier):
    try:return knowledge.change_tier(source_id,body.tier)
    except knowledge.KnowledgeError as e:raise HTTPException(422,str(e)) from None

@router.get('/calendar')
def calendar():return db.many('SELECT * FROM calendar_events ORDER BY starts_at DESC LIMIT 100')

@router.post('/calendar/check')
def availability(body:CalendarSlot):
    try:return calendar_ops.check(**body.model_dump())
    except calendar_ops.AppointmentError as e:raise HTTPException(422,str(e)) from None

@router.post('/calendar/book',status_code=201)
def booking(body:Booking):
    try:return calendar_ops.book(**body.model_dump())
    except (calendar_ops.AppointmentError,governance.PolicyViolation) as e:
        raise HTTPException(409,str(e)) from None

@router.post('/agents/{agent_id}/feedback',status_code=201)
def add_feedback(agent_id:str,body:FeedbackIn):
    if agent_id!=body.agent_id:raise HTTPException(422,'Agent mismatch')
    if not db.one('SELECT id FROM agents WHERE id=?',(agent_id,)):raise HTTPException(404,'Agent missing')
    ident=db.uid()
    db.execute('INSERT INTO agent_feedback VALUES (?,?,?,?,?,?,?)',
               (ident,agent_id,body.release_id,body.call_id,body.rating,body.note,db.now()))
    return {'id':ident,'agent_id':agent_id,'rating':body.rating}

@router.get('/agents/{agent_id}/feedback')
def feedback(agent_id:str):
    return db.many('SELECT * FROM agent_feedback WHERE agent_id=? ORDER BY created_at DESC LIMIT 100',(agent_id,))

@router.get('/integrations/google/status')
def google_status():return {'connected':google_services.connected()}

@router.post('/integrations/google/import-contacts')
async def google_import_contacts(limit:int=250):
    try:return await google_services.import_contacts(limit)
    except google_services.GoogleIntegrationError as e:raise HTTPException(503,str(e)) from None

@router.get('/integrations/google/calendar')
async def google_calendar(start:str,end:str):
    try:return await google_services.calendar_events(start,end)
    except google_services.GoogleIntegrationError as e:raise HTTPException(503,str(e)) from None

# Explicit provider-connection flow. This path is owner-session authenticated,
# and the callback uses a fresh signed OAuth state verified by Authlib.
google_router=APIRouter(tags=['Google owner integrations'])
@google_router.get('/auth/google/connect')
async def connect_google(request:Request,_=Depends(require_api_key)):
    s=get_settings()
    if s.auth_mode!='google':raise HTTPException(403,'Connect requires Google owner session')
    google_services._cipher()
    from authlib.integrations.starlette_client import OAuth
    oauth=OAuth()
    oauth.register(name='vf_google_services',client_id=s.google_client_id,
        client_secret=s.google_client_secret,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope':google_services.SCOPES,'access_type':'offline','prompt':'consent'})
    request.session['google_connect_state']='requested'
    return await oauth.vf_google_services.authorize_redirect(request,s.base_url+'/auth/google/connect/callback',
                                                             access_type='offline',prompt='consent')

@google_router.get('/auth/google/connect/callback')
async def connected_google(request:Request):
    if request.session.get('owner_sub')!=get_settings().google_owner_sub or \
            request.session.get('google_connect_state')!='requested':
        raise HTTPException(403,'Owner authentication required')
    from authlib.integrations.starlette_client import OAuth
    s=get_settings();oauth=OAuth()
    oauth.register(name='vf_google_services',client_id=s.google_client_id,
        client_secret=s.google_client_secret,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope':google_services.SCOPES})
    token=await oauth.vf_google_services.authorize_access_token(request)
    user=token.get('userinfo') or {}
    if user.get('sub')!=s.google_owner_sub:
        raise HTTPException(403,'Google account mismatch')
    google_services.put_token(token)
    request.session.pop('google_connect_state',None)
    return RedirectResponse('/',status_code=303)

@router.get('/schedules')
def list_schedules():
    return db.many('SELECT * FROM mission_schedules ORDER BY created_at DESC LIMIT 100')

@router.post('/schedules',status_code=201)
def new_schedule(body:ScheduleIn):
    try:return schedules.create(**body.model_dump())
    except schedules.ScheduleError as e:raise HTTPException(422,str(e)) from None

@router.delete('/schedules/{schedule_id}')
def disable_schedule(schedule_id:str):
    if not schedules.deactivate(schedule_id):raise HTTPException(404,'Schedule not found')
    return {'status':'disabled'}
