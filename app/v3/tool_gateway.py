"""Fixed, typed tool gateway. Read-only execution is isolated from write actions.

All tool results are untrusted and must not be inserted into prompt instruction slots.
The gateway is deliberately not an arbitrary URL fetcher or MCP proxy.
"""
import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from app import db
from app.config import get_settings
from app.v3 import registry, tools

class ToolPolicyError(Exception):
    pass


@dataclass(frozen=True)
class ToolRequest:
    agent_id:str
    name:str
    query:str
    limit:int=5


def authorize(request: ToolRequest):
    if request.name not in ('news_rss','web_search','market_quote'):
        raise ToolPolicyError('Only fixed read-only research tools are exposed here')
    if not (3 <= len(request.query.strip()) <= 200):
        raise ToolPolicyError('Search query must be 3 to 200 characters')
    if not 1 <= request.limit <= 10:
        raise ToolPolicyError('Tool result limit must be 1 to 10')
    config=registry.get_config(request.agent_id)
    if not config:
        raise ToolPolicyError('Unknown agent')
    if request.name not in config.get('tools',[]):
        raise ToolPolicyError('Agent is not authorized to use this tool')
    return config


def audit(agent_id,name,status,count=0):
    db.execute('INSERT INTO audit_events (id,actor,action,target,detail,created_at) VALUES (?,?,?,?,?,?)',
               (db.uid(),'agent:'+agent_id,'tool.'+status,name,json.dumps({'count':count}),db.now()))


async def execute_readonly(request: ToolRequest):
    authorize(request)
    if get_settings().demo_mode:
        audit(request.agent_id,request.name,'simulated')
        return {'status':'simulated','tool':request.name,'results':[],
                'message':'Demo mode: no external tool provider contacted'}
    try:
        if request.name=='market_quote':
            from app.v3.market import quote
            parts=request.query.strip().split()
            if len(parts) not in (1,2):raise ToolPolicyError('Expected SYMBOL [NSE|BSE]')
            result=await asyncio.wait_for(quote(parts[0],parts[1] if len(parts)==2 else 'NSE'),timeout=12.0)
            audit(request.agent_id,request.name,'succeeded',1)
            return {'status':'completed','tool':'market_quote','results':[result]}
        source=tools.news_rss if request.name=='news_rss' else tools.web_search
        results=await asyncio.wait_for(source(request.query,request.limit),timeout=12.0)
    except Exception as exc:
        audit(request.agent_id,request.name,'failed')
        raise tools.ToolUnavailable(f'Tool {request.name} unavailable ({type(exc).__name__})') from exc
    clean=[]
    for item in results[:request.limit]:
        clean.append({k:str(item.get(k,''))[:900] for k in ('title','url','published','description','source')})
    audit(request.agent_id,request.name,'succeeded',len(clean))
    return {'status':'completed','tool':request.name,'retrieved_at':datetime.now(timezone.utc).isoformat(),
            'results':clean,'verified_article_content':False}
