"""V3 domain APIs: owner authenticated, server-validated, conservative write operations."""
import json
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from app import db
from app.security import require_api_key
from app.v3 import contacts, memory, missions, registry, tools, tool_gateway, architect

router=APIRouter(prefix='/api/v3',dependencies=[Depends(require_api_key)],tags=['Voice Foundry v3'])

class ContactIn(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    phone:str
    email:str|None=None
    language:str='Hinglish'
    outbound_consent:bool=False
    email_consent:bool=False

class ContactPatch(BaseModel):
    name:str|None=None
    email:str|None=None
    language:str|None=None
    outbound_consent:bool|None=None
    email_consent:bool|None=None

class ArchitectIn(BaseModel):
    brief:str=Field(min_length=20,max_length=2000)

class ArchitectCreate(BaseModel):
    proposal:dict

class DraftIn(BaseModel):
    changes:dict=Field(default_factory=dict)
    template:str|None=None

class MemoryIn(BaseModel):
    agent_id:str
    contact_id:str
    content:str=Field(min_length=3,max_length=1000)
    category:str='preference'
    sensitivity:str='routine'
    consent:bool=False

class MemoryCorrection(BaseModel):
    contact_id:str
    content:str=Field(min_length=3,max_length=1000)
    consent:bool=False

class MissionIn(BaseModel):
    agent_id:str
    contact_id:str
    objective:str=Field(min_length=10,max_length=3000)

class ToolQueryIn(BaseModel):
    agent_id:str
    name:str
    query:str=Field(min_length=3,max_length=200)
    limit:int=Field(default=5,ge=1,le=10)

class MissionRevision(BaseModel):
    objective:str=Field(min_length=10,max_length=3000)

class TaskIn(BaseModel):
    title:str=Field(min_length=2,max_length=300)
    agent_id:str='receptionist'
    contact_id:str|None=None
    due_at:str|None=None

class PermissionIn(BaseModel):
    allowed:bool

@router.post('/architect/propose')
async def propose_agent(body:ArchitectIn):
    try: return await architect.propose(body.brief)
    except ValueError as e: raise HTTPException(422,str(e)) from None
    except Exception as exc: raise HTTPException(502,f'Agent architect provider unavailable ({type(exc).__name__})') from None

@router.post('/architect/create',status_code=201)
async def create_architect_draft(body:ArchitectCreate):
    proposal=architect.validate(body.proposal)
    agent=db.insert_agent(proposal['name'][:60],proposal['role'][:160],proposal['language'][:60],proposal['instructions'][:5000])
    changes={k:v for k,v in proposal.items() if k!='template'}
    try: draft=registry.create_draft(agent['id'],changes,template=proposal['template'])
    except ValueError as e: raise HTTPException(422,str(e)) from None
    return {'agent':agent,'draft':draft,'published':False}

@router.get('/templates')
async def list_templates(): return registry.TEMPLATES

@router.post('/agents/from-template',status_code=201)
async def template_agent(body:dict):
    kind=str(body.get('template',''))
    if kind not in registry.TEMPLATES: raise HTTPException(422,'Unknown template')
    t=registry.TEMPLATES[kind]
    agent=db.insert_agent(str(body.get('name') or t['name'])[:60],t['role'],t['language'],
                          f"You are {t['name']}. {t['personality']}")
    draft=registry.create_draft(agent['id'],{},template=kind)
    return {'agent':agent,'draft':draft}

@router.get('/agents/{agent_id}/releases')
async def releases(agent_id:str):
    return db.many('SELECT id,agent_id,version,status,configuration,created_at FROM agent_releases WHERE agent_id=? ORDER BY version DESC',(agent_id,))

@router.post('/agents/{agent_id}/drafts',status_code=201)
async def create_draft(agent_id:str,payload:DraftIn):
    try: return registry.create_draft(agent_id,payload.changes,payload.template)
    except ValueError as e: raise HTTPException(422,str(e)) from None

@router.post('/agents/{agent_id}/releases/{release_id}/publish')
async def publish(agent_id:str,release_id:str):
    try: return registry.publish(agent_id,release_id)
    except ValueError as e: raise HTTPException(409,str(e)) from None

@router.post('/agents/{agent_id}/releases/{release_id}/restore')
async def restore_agent_release(agent_id:str,release_id:str):
    try: return registry.rollback_to(agent_id,release_id)
    except ValueError as e: raise HTTPException(409,str(e)) from None

@router.get('/agents/{agent_id}/prompt')
async def prompt_preview(agent_id:str):
    agent=db.one('SELECT * FROM agents WHERE id=?',(agent_id,))
    if not agent: raise HTTPException(404,'Agent not found')
    return {'compiled_prompt':registry.compile_prompt(agent),'configuration':registry.get_config(agent_id)}

@router.get('/contacts')
async def list_contacts(search:str=''):
    rows=db.many('SELECT * FROM contacts WHERE active=1 ORDER BY name LIMIT 1000')
    return [r for r in rows if search.lower() in (r['name']+' '+r['phone']).lower()]

@router.post('/contacts',status_code=201)
async def add_contact(payload:ContactIn):
    try: return contacts.register(**payload.model_dump())
    except ValueError as e: raise HTTPException(422,str(e)) from None

@router.patch('/contacts/{contact_id}')
async def edit_contact(contact_id:str,body:ContactPatch):
    try: return contacts.update(contact_id,**body.model_dump(exclude_unset=True))
    except ValueError as e: raise HTTPException(422,str(e)) from None

@router.delete('/contacts/{contact_id}')
async def remove_contact(contact_id:str):
    if not contacts.deactivate(contact_id): raise HTTPException(404,'Contact not found or inactive')
    return {'status':'deactivated','consent_revoked':True}

@router.post('/contacts/import')
async def csv_import(file:UploadFile=File(...)):
    if not (file.filename or '').lower().endswith('.csv'): raise HTTPException(422,'CSV required')
    raw=await file.read(250_001)
    if len(raw)>250_000: raise HTTPException(413,'CSV too large')
    try: return contacts.import_csv(raw.decode('utf-8-sig'))
    except (UnicodeError,ValueError) as e: raise HTTPException(422,str(e)) from None

@router.put('/agents/{agent_id}/contacts/{contact_id}/permission')
async def set_contact_access(agent_id:str,contact_id:str,payload:PermissionIn):
    if not db.one('SELECT id FROM agents WHERE id=?',(agent_id,)) or not db.one('SELECT id FROM contacts WHERE id=? AND active=1',(contact_id,)):
        raise HTTPException(404,'Agent/contact missing')
    db.execute('DELETE FROM agent_contact_permissions WHERE agent_id=? AND contact_id=?',(agent_id,contact_id))
    if payload.allowed:
        db.execute('INSERT INTO agent_contact_permissions (agent_id,contact_id) VALUES (?,?)',(agent_id,contact_id))
    return {'agent_id':agent_id,'contact_id':contact_id,'allowed':payload.allowed}

@router.get('/memories')
async def memories(agent_id:str,contact_id:str,query:str=''):
    return memory.relevant(agent_id,contact_id,query,include_sensitive=True)

@router.post('/memories',status_code=201)
async def add_memory(payload:MemoryIn):
    try:
        row=memory.store(**payload.model_dump())
        # A failed external embedding request must never lose a valid memory record.
        try: await memory.index_embedding(row['id'])
        except Exception: pass
        return row
    except PermissionError as e: raise HTTPException(403,str(e)) from None
    except ValueError as e: raise HTTPException(422,str(e)) from None

@router.get('/memories/search')
async def search_memories(agent_id:str,contact_id:str,query:str):
    return await memory.semantic_relevant(agent_id,contact_id,query)

@router.get('/memories/history')
async def memory_history(agent_id:str,contact_id:str):
    return memory.timeline(agent_id,contact_id)

@router.post('/memories/{memory_id}/correct')
async def correct_memory(memory_id:str,body:MemoryCorrection):
    try: return memory.correct(memory_id,body.contact_id,body.content,body.consent)
    except PermissionError as e: raise HTTPException(403,str(e)) from None
    except ValueError as e: raise HTTPException(422,str(e)) from None

@router.delete('/memories/{memory_id}')
async def delete_memory(memory_id:str,contact_id:str):
    if not memory.forget(memory_id,contact_id): raise HTTPException(404,'Memory not found')
    return {'status':'inactive'}

@router.get('/missions')
async def list_missions():
    return db.many('SELECT * FROM missions ORDER BY created_at DESC LIMIT 100')

@router.post('/missions',status_code=201)
async def create_mission(payload:MissionIn):
    try: return missions.enqueue(**payload.model_dump())
    except ValueError as e: raise HTTPException(422,str(e)) from None

@router.get('/missions/{mission_id}')
async def mission_detail(mission_id:str):
    result=missions.detail(mission_id)
    if not result: raise HTTPException(404,'Mission not found')
    return result

@router.post('/missions/{mission_id}/{action}')
async def control_mission(mission_id:str,action:str):
    if action not in ('pause','resume','cancel'): raise HTTPException(404,'Unknown action')
    try: return missions.transition(mission_id,action)
    except ValueError as e: raise HTTPException(409,str(e)) from None

@router.patch('/missions/{mission_id}')
async def revise_mission(mission_id:str,revision:MissionRevision):
    try: return missions.transition(mission_id,'revise',revision.objective)
    except ValueError as e: raise HTTPException(409,str(e)) from None

@router.get('/tools')
async def list_tools(): return tools.CATALOG

@router.post('/tools/query')
async def query_readonly_tool(payload:ToolQueryIn):
    try:
        return await tool_gateway.execute_readonly(tool_gateway.ToolRequest(**payload.model_dump()))
    except tool_gateway.ToolPolicyError as e: raise HTTPException(403,str(e)) from None
    except tools.ToolUnavailable as e: raise HTTPException(503,str(e)) from None

@router.get('/tasks')
async def list_tasks(): return db.many('SELECT * FROM tasks ORDER BY created_at DESC LIMIT 100')

@router.post('/tasks',status_code=201)
async def create_task(payload:TaskIn):
    if not db.one('SELECT id FROM agents WHERE id=?',(payload.agent_id,)):
        raise HTTPException(404,'Agent not found')
    return tools.create_task(**payload.model_dump())
