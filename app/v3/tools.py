"""Curated built-in tools. No arbitrary URL fetching, dynamic code, or MCP loading."""
from urllib.parse import quote
import httpx
import xml.etree.ElementTree as ET
from app import db
from app.config import get_settings

class ToolUnavailable(Exception): pass

async def news_rss(query: str, limit: int=5):
    # Google News RSS is a discovery source; articles still require verification.
    url=f'https://news.google.com/rss/search?q={quote(query[:120])}&hl=en-IN&gl=IN&ceid=IN:en'
    async with httpx.AsyncClient(timeout=8,follow_redirects=False) as client:
        r=await client.get(url);r.raise_for_status()
    root=ET.fromstring(r.content[:1_000_000])
    return [{'title':(x.findtext('title') or '')[:260],
             'url':(x.findtext('link') or '')[:900],
             'published':x.findtext('pubDate') or '',
             'source':'Google News RSS (aggregated, not independently verified)'}
            for x in root.findall('.//channel/item')[:max(1,min(limit,10))]]

async def web_search(query:str, limit:int=5):
    key=get_settings().brave_search_api_key
    if not key: raise ToolUnavailable('BRAVE_SEARCH_API_KEY is not configured')
    async with httpx.AsyncClient(timeout=9) as client:
        r=await client.get('https://api.search.brave.com/res/v1/web/search',
             params={'q':query[:200],'count':min(limit,10)},
             headers={'X-Subscription-Token':key,'Accept':'application/json'})
        r.raise_for_status()
    return [{'title':i.get('title','')[:250], 'url':i.get('url','')[:900],
             'description':i.get('description','')[:700], 'source':'Brave Search result'}
            for i in r.json().get('web',{}).get('results',[])[:limit]]

def create_task(title:str,agent_id:str,contact_id=None,due_at=None):
    id_=db.uid()
    db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',
               (id_,title[:300],'open',due_at,agent_id,contact_id,db.now()))
    return db.one('SELECT * FROM tasks WHERE id=?',(id_,))

CATALOG={
    'news_rss':{'read_only':True,'description':'Google News RSS source discovery'},
    'web_search':{'read_only':True,'description':'Brave API web search (needs API key)'},
    'market_quote':{'read_only':True,'description':'Timestamped Indian equity data via Twelve Data (requires API key)'},
    'calendar':{'read_only':False,'description':'Local appointment availability and owner-approved proposals'},
    'tasks':{'read_only':False,'description':'Create and list personal tasks (write permission enforced)'},
}
