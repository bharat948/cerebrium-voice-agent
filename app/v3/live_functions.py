"""Builtin GPT-Live Responses-delegation function tools.

Keep the function definitions and the executor in one allowlisted catalog.
Caller speech and model arguments are untrusted. Read-only tools can execute
according to agent access; writes become owner approval proposals.
"""
import asyncio
import json
import logging
from app import db
from app.v3 import knowledge,memory,intelligent_memory,governance,tool_gateway
from app.config import get_settings
log=logging.getLogger(__name__)

DEFINITIONS={
 'news_rss':('Find recent news headlines and source links for a topic',{'query':{'type':'string'}}),
 'web_search':('Search public websites and return source metadata',{'query':{'type':'string'}}),
 'knowledge_search':('Search the agent authorized document knowledge base',{'query':{'type':'string'}}),
 'memory_search':('Find the caller routine preferences and previous context, if authorized',{'query':{'type':'string'}}),
 'research_email':('Prepare a background research mission for an opted-in contact. Email only to the registered address.',{'objective':{'type':'string'}}),
 'task_proposal':('Propose creating a personal task for owner approval',{'title':{'type':'string'}}),
 'market_quote':('Retrieve an exchange-labeled and timestamped NSE or BSE share quote',{'query':{'type':'string'}}),
 'calendar_check':('Check local appointment calendar availability, not external Google calendar',{'starts_at':{'type':'string'},'ends_at':{'type':'string'}}),
 'appointment_proposal':('Request owner approval to book a local calendar appointment; never claim booking is confirmed',{'title':{'type':'string'},'starts_at':{'type':'string'},'ends_at':{'type':'string'}}),
}


def definitions(config,recognized_contact=False):
    tools=set(config.get('tools',[]))
    tools |= {'knowledge_search'}
    if recognized_contact and config.get('memory_enabled'):tools.add('memory_search')
    if recognized_contact and config.get('tools') and any(x in tools for x in ('news_rss','web_search')):
        tools.add('research_email')
    if 'tasks' in tools:tools.add('task_proposal')
    if 'calendar' in tools:
        tools.add('calendar_check')
        if recognized_contact:tools.add('appointment_proposal')
    defs = [
      {'type':'function','name':name,'description':desc,
       'parameters':{'type':'object','properties':props,'required':list(props),'additionalProperties':False},
       'strict':True}
      for name,(desc,props) in DEFINITIONS.items() if name in tools
    ]
    # Add tools from authorized integrations
    try:
        from app.integrations import manager as int_mgr
        agent_id = config.get('id') or config.get('agent_id')
        assigned_integrations = config.get('integrations')
        if assigned_integrations is not None:
            for p_id in assigned_integrations:
                p = int_mgr.get_provider(p_id)
                if p and p.is_connected():
                    for t in p.get_tools():
                        defs.append({
                            'type':'function',
                            'name':t.name,
                            'description':t.description,
                            'parameters':t.parameters,
                            'strict':False
                        })
        elif agent_id:
            for t in int_mgr.get_agent_permitted_tools(agent_id):
                defs.append({
                    'type':'function',
                    'name':t['name'],
                    'description':t['description'],
                    'parameters':t['parameters'],
                    'strict':False
                })
    except Exception:
        pass
    return defs


async def run(agent_id,contact,requested_name,arguments,config):
    """Always return a structured tool result, never uncontrolled provider exceptions."""
    allowed={item['name'] for item in definitions(config,bool(contact))}
    if requested_name not in allowed:return {'status':'denied','reason':'Tool is not assigned to this agent'}
    if not isinstance(arguments,dict):return {'status':'invalid','reason':'Arguments must be an object'}

    # 1. Route integration tools first
    try:
        from app.integrations import manager as int_mgr
        target_provider = None
        for p in int_mgr._PROVIDERS.values():
            if any(t.name == requested_name for t in p.get_tools()):
                target_provider = p
                break
        if target_provider:
            config_integrations = config.get('integrations')
            if config_integrations is not None:
                if target_provider.id not in config_integrations:
                    return {'status':'denied','reason':f"Integration '{target_provider.id}' not assigned to this agent"}
            elif not int_mgr.is_agent_authorized(agent_id, target_provider.id):
                return {'status':'denied','reason':f"Integration '{target_provider.id}' not assigned to this agent"}
            return await int_mgr.execute_agent_tool(agent_id, requested_name, arguments, context={'contact':contact})
    except Exception as exc:
        log.warning('Integration tool error agent=%s tool=%s: %s', agent_id, requested_name, exc)
        return {'status':'unavailable','reason':str(exc)}

    # 2. Built-in tools
    if requested_name in {'calendar_check','appointment_proposal'}:
        required=['starts_at','ends_at'] + (['title'] if requested_name=='appointment_proposal' else [])
        if any(not isinstance(arguments.get(k),str) or not 2 <= len(arguments[k]) <= 500 for k in required):
            return {'status':'invalid','reason':'Invalid appointment fields'}
        value=''
    else:
        key='objective' if requested_name=='research_email' else 'title' if requested_name=='task_proposal' else 'query'
        value=arguments.get(key)
        if not isinstance(value,str) or not 3<=len(value.strip())<=500:
            return {'status':'invalid','reason':'Invalid '+key}
    try:
        if requested_name in {'news_rss','web_search'}:
            result=await tool_gateway.execute_readonly(tool_gateway.ToolRequest(agent_id,requested_name,value[:200],limit=4))
            return result
        if requested_name=='market_quote':
            from app.v3.market import quote
            parts=value.strip().split()
            if not 1<=len(parts)<=2:return {'status':'invalid','reason':'Use SYMBOL [NSE|BSE]'}
            return {'status':'completed','quote':await quote(parts[0],parts[1] if len(parts)==2 else 'NSE')}
        if requested_name in ('calendar_check','appointment_proposal'):
            from app.v3 import calendar_ops
            slot=calendar_ops.check(arguments['starts_at'],arguments['ends_at'])
            if requested_name=='calendar_check':
                return {'status':'completed','source':'Voice Foundry local calendar only',**slot}
            if not contact or not contact['active']:
                return {'status':'denied','reason':'Registered contact required for appointment proposals'}
            if not slot['available']:
                return {'status':'unavailable','reason':'Local calendar slot is occupied','conflicts':slot['conflicts']}
            data={'title':arguments['title'],'starts_at':arguments['starts_at'],
                  'ends_at':arguments['ends_at'],'contact_id':contact['id']}
            proposal=governance.request_approval(agent_id,'book_appointment',data,contact['id'])
            return {'status':'approval_required','approval_id':proposal['id'],
                    'note':'This only creates a proposal. No calendar booking has been made.'}
        if requested_name=='knowledge_search':
            hits=await knowledge.semantic_search(agent_id,value,limit=4)
            return {'status':'completed','untrusted_source_data':True,
                    'results':[{'title':h['title'],'trust_tier':h['trust_tier'],
                                'excerpt':h['content'][:650]} for h in hits]}
        if requested_name=='memory_search':
            if not contact:return {'status':'denied','reason':'Caller is not a registered contact'}
            rows=intelligent_memory.ranked(agent_id,contact['id'],value,limit=5)
            return {'status':'completed','results':[r['content'][:240] for r in rows],
                    'note':'Routine memories only; caller identity has not been verified for sensitive details'}
        if requested_name=='research_email':
            if not contact or not contact['active'] or not contact['email_consent'] or not contact['email']:
                return {'status':'needs_consent','reason':'Caller email delivery consent not verified'}
            from app.v3 import missions
            if get_settings().demo_mode:return {'status':'simulated','note':'Research was not actually started'}
            mission=missions.enqueue(agent_id=agent_id,contact_id=contact['id'],objective=value)
            return {'status':'queued','mission_id':mission['id'], 'note':'Report will be emailed only after research completes'}
        if requested_name=='task_proposal':
            if not contact:return {'status':'denied','reason':'Unregistered caller'}
            proposal=governance.request_approval(agent_id,'create_task',{'title':value,'contact_id':contact['id']},contact['id'])
            return {'status':'approval_required','approval_id':proposal['id'],
                    'note':'Task was NOT created; owner approval is pending'}
    except Exception as exc:
        log.warning('Tool error agent=%s tool=%s exception=%s',agent_id,requested_name,type(exc).__name__)
        return {'status':'unavailable','reason':'Tool temporarily unavailable'}
    return {'status':'denied'}


def completed_function_call(event):
    """Extract the Responses function call from the nested Live event."""
    if event.get('type')!='response.event':return None
    detail=event.get('event') or {}
    if detail.get('type')!='response.output_item.done':return None
    item=detail.get('item') or {}
    if item.get('type')!='function_call':return None
    name=item.get('name')
    call_id=item.get('call_id')
    if not isinstance(name,str) or not isinstance(call_id,str):return None
    try:arguments=json.loads(item.get('arguments') or '{}')
    except json.JSONDecodeError:arguments={}
    return {'name':name,'call_id':call_id,'arguments':arguments,'delegation_id':event.get('delegation_id'),
            'response_id':detail.get('response_id')}
