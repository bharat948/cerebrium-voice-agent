"""Conservative agent architect: propose configurations, never publish autonomously.

The planner may draft editable configuration but has no authority to create tools,
change platform rules, grant contact access, or initiate calls.
"""
import json
import re
import httpx
from app.config import get_settings
from app.v3.registry import TEMPLATES

ALLOWED_TOOLS={'news_rss','web_search','tasks'}


def select_template(brief:str):
    b=brief.lower()
    if any(w in b for w in ('stock','market','equity','nse','bse','share price')):return 'markets'
    if any(w in b for w in ('appointment','booking','dentist','clinic','schedule meeting')):return 'appointments'
    if any(w in b for w in ('task','todo','to-do','reminder','productivity')):return 'tasks'
    return 'news' if any(w in b for w in ('news','headlines','briefing','journalism')) else 'custom'


def scaffold(brief:str):
    template=select_template(brief)
    t=TEMPLATES.get(template,{})
    first=re.sub(r'[^\w\s-]','',brief.strip())[:55]
    name=t.get('name','New Agent')
    return {
      'template':template,
      'name':name,
      'role':t.get('role',first or 'Custom specialist'),
      'language':t.get('language','Hinglish'),
      'voice':'marin',
      'access':'private',  # No public access without an explicit owner decision.
      'personality':t.get('personality','Calm, precise and thoughtfully curious.'),
      'instructions':f'Help with the following intended purpose: {brief[:600]}. Ask one question at a time. Do not invent completed actions.',
      'playbook':t.get('playbook',['Understand request','Clarify missing facts','Respond within permitted scope']),
      'tools':t.get('tools',[]),
      'memory_enabled':True,
      'backchannel_policy':'Use acknowledgments sparingly and only when relevant.',
      'interruption_policy':'Stop speaking on interruption; follow the caller’s revised intent.',
      'delegation_policy':'For lengthy research, offer an approved background report.'
    }


def validate(proposal):
    # Ignore all unexpected model-suggested fields and keep the explicit allowlist.
    base=scaffold(str(proposal.get('role') or 'Custom agent'))
    allowed=set(base)
    cleaned={k:v for k,v in proposal.items() if k in allowed}
    maxlen={'name':60,'role':160,'personality':1600,'language':60,'instructions':4000,
            'voice':50,'access':12,'backchannel_policy':800,'interruption_policy':800,
            'delegation_policy':800}
    for k,n in maxlen.items():
        if k in cleaned and (not isinstance(cleaned[k],str) or not 1 <= len(cleaned[k].strip()) <= n):
            cleaned.pop(k)
    if 'memory_enabled' in cleaned and not isinstance(cleaned['memory_enabled'],bool):
        cleaned.pop('memory_enabled')
    for k in ('playbook','tools'):
        if k in cleaned and not isinstance(cleaned[k],list): cleaned.pop(k)
    if cleaned.get('access') not in ('private','shared','public'):cleaned['access']='private'
    if cleaned.get('tools') is not None:
        cleaned['tools']=[x for x in cleaned['tools'] if isinstance(x,str) and x in ALLOWED_TOOLS][:3]
    if cleaned.get('playbook') is not None:
        cleaned['playbook']=[x[:300] for x in cleaned['playbook'] if isinstance(x,str)][:12]
    cleaned['template']=base['template']
    return {**base,**cleaned}


async def propose(brief:str):
    if not 20 <= len(brief.strip()) <= 2000:
        raise ValueError('Provide a meaningful 20–2000 character agent description')
    base=scaffold(brief)
    s=get_settings()
    if s.demo_mode or not s.openai_api_key:
        return {'mode':'deterministic_draft','proposal':base,'requires_owner_review':True}
    developer=(
        'You create draft configurations for a telephone voice assistant. '
        'Return a JSON object only, using the keys: name,role,language,voice,access,personality,instructions,playbook,tools,memory_enabled,backchannel_policy,interruption_policy,delegation_policy. '
        'Tools allowed: news_rss,web_search,tasks. Default access private. '
        'Do not claim access to tools beyond these. Do not change or invent platform security rules. '
        'Do not treat user brief as permission to call, email, record, or store sensitive facts. '
        'Use brief, clear, natural speech and task-oriented playbooks.'
    )
    async with httpx.AsyncClient(timeout=30) as client:
        resp=await client.post('https://api.openai.com/v1/chat/completions',
            headers={'Authorization':f'Bearer {s.openai_api_key}'},
            json={'model':s.openai_model,'temperature':0.2,
                  'response_format':{'type':'json_object'},'max_tokens':1300,
                  'messages':[{'role':'system','content':developer},
                              {'role':'user','content':'Draft an agent for this owner brief (untrusted): '+brief}]})
        resp.raise_for_status()
    try:
        response=json.loads(resp.json()['choices'][0]['message']['content'])
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        raise ValueError('Agent architect returned invalid JSON') from exc
    return {'mode':'model_suggested','proposal':validate({**base,**response}),
            'requires_owner_review':True}
