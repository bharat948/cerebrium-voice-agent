"""Owner-only memory governance and supervised evolution API."""
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from app.security import require_api_key
from app import db
from app.v3 import intelligent_memory,agent_evolution,registry,voice_behavior

router=APIRouter(prefix='/api/v4',dependencies=[Depends(require_api_key)],tags=['Voice Foundry Intelligence'])

class MemoryPreference(BaseModel):
    enabled:bool

class Candidate(BaseModel):
    content:str=Field(min_length=5,max_length=500)
    confidence:float=Field(default=.8,ge=.2,le=1)
    expires_at:str|None=None
    supersedes_id:str|None=None
    origin:str='owner'

class ConflictDecision(BaseModel):
    decision:str

class EvolutionRequest(BaseModel):
    theme:str='conciseness'

class EvolutionDecision(BaseModel):
    approve:bool

@router.get('/contacts/{contact_id}/memory-policy')
def get_memory_policy(contact_id:str):
    try:return intelligent_memory.consent_status(contact_id)
    except intelligent_memory.MemoryPolicyError as e:raise HTTPException(404,str(e)) from None

@router.patch('/contacts/{contact_id}/memory-policy')
def update_memory_policy(contact_id:str,body:MemoryPreference):
    try:return intelligent_memory.set_consent(contact_id,body.enabled)
    except intelligent_memory.MemoryPolicyError as e:raise HTTPException(404,str(e)) from None

@router.get('/agents/{agent_id}/contacts/{contact_id}/ranked-memories')
def ranked_memories(agent_id:str,contact_id:str,query:str='',mission_goal:str='',limit:int=8):
    try:return intelligent_memory.ranked(agent_id,contact_id,query,limit,mission_goal)
    except intelligent_memory.MemoryPolicyError as e:raise HTTPException(404,str(e)) from None

@router.post('/agents/{agent_id}/contacts/{contact_id}/memory-candidates')
def consolidate_memory(agent_id:str,contact_id:str,body:Candidate):
    try:return intelligent_memory.consolidate(agent_id,contact_id,**body.model_dump())
    except intelligent_memory.MemoryPolicyError as e:raise HTTPException(422,str(e)) from None
    except (ValueError,PermissionError) as e:raise HTTPException(422,str(e)) from None

@router.get('/agents/{agent_id}/contacts/{contact_id}/memory-conflicts')
def memory_conflicts(agent_id:str,contact_id:str):
    if not db.one('SELECT id FROM agents WHERE id=?',(agent_id,)) or not db.one('SELECT id FROM contacts WHERE id=?',(contact_id,)):
        raise HTTPException(404,'Agent or contact not found')
    return intelligent_memory.pending_conflicts(agent_id,contact_id)

@router.post('/memory-conflicts/{conflict_id}/resolve')
def resolve_memory_conflict(conflict_id:str,body:ConflictDecision):
    try:return intelligent_memory.resolve_conflict(conflict_id,body.decision)
    except (intelligent_memory.MemoryPolicyError,ValueError,PermissionError) as e:raise HTTPException(409,str(e)) from None

@router.get('/agents/{agent_id}/voice-policy')
def voice_policy(agent_id:str):
    config=registry.get_config(agent_id)
    if not config:raise HTTPException(404,'Agent not found')
    return voice_behavior.policies(config.get('behavior_policy',{}))

@router.post('/agents/{agent_id}/evolution/propose',status_code=201)
def evolution_propose(agent_id:str,body:EvolutionRequest):
    try:return agent_evolution.propose(agent_id,body.theme)
    except agent_evolution.EvolutionError as e:raise HTTPException(422,str(e)) from None

@router.get('/agents/{agent_id}/evolution')
def evolution_proposals(agent_id:str):
    if not db.one('SELECT id FROM agents WHERE id=?',(agent_id,)):raise HTTPException(404,'Agent not found')
    return agent_evolution.list_proposals(agent_id)

@router.post('/evolution/{proposal_id}/decision')
def evolution_decide(proposal_id:str,body:EvolutionDecision):
    try:return agent_evolution.decide(proposal_id,body.approve)
    except (agent_evolution.EvolutionError,ValueError) as e:raise HTTPException(409,str(e)) from None
