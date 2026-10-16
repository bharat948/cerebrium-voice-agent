"""Scoped, consent-aware long-term memory; no implicit sensitive data collection."""
import re
from app import db

SENSITIVE = {'financial','health','government_id','relationships','employment'}
RESTRICTED = re.compile(r'(?i)(password|one.time.pass(word|code)|\botp\b|api[_ -]?key|cvv|private[_ -]?key)')


def store(agent_id,contact_id,content,category='preference',sensitivity='routine',consent=False,source_call_id=None):
    if not db.one('SELECT id FROM agents WHERE id=?',(agent_id,)):
        raise ValueError('Unknown agent')
    if not db.one('SELECT id FROM contacts WHERE id=? AND active=1 AND memory_opt_in=1',(contact_id,)):
        raise ValueError('Unknown contact')
    if RESTRICTED.search(content): raise ValueError('Restricted secret detected')
    if sensitivity in SENSITIVE and not consent: raise PermissionError('Explicit consent required for sensitive memory')
    if sensitivity not in ('routine',*SENSITIVE): raise ValueError('Unknown sensitivity')
    id_=db.uid()
    db.execute('INSERT INTO memories (id,agent_id,contact_id,content,category,sensitivity,source_call_id,created_at) VALUES (?,?,?,?,?,?,?,?)',
        (id_,agent_id,contact_id,content.strip()[:1000],category,sensitivity,source_call_id,db.now()))
    track(id_,agent_id,contact_id,'created')
    return db.one('SELECT * FROM memories WHERE id=?',(id_,))

def relevant(agent_id,contact_id,query='',limit=8,include_sensitive=False):
    if not db.one('SELECT id FROM contacts WHERE id=? AND active=1 AND memory_opt_in=1',(contact_id,)):
        return []
    rows=db.many('SELECT * FROM memories WHERE agent_id=? AND contact_id=? AND active=1 ORDER BY created_at DESC LIMIT 150', (agent_id,contact_id))
    if not include_sensitive: rows=[r for r in rows if r['sensitivity']=='routine']
    terms=set(re.findall(r'[\w]{3,}',query.lower()))
    def rank(m):
        text=m['content'].lower()
        return (sum(t in text for t in terms), m['confidence'],m['created_at'])
    return sorted(rows,key=rank,reverse=True)[:max(1,min(limit,20))]

def track(memory_id,agent_id,contact_id,kind,replacement_id=None):
    db.execute('INSERT INTO memory_events VALUES (?,?,?,?,?,?,?)',
               (db.uid(),memory_id,agent_id,contact_id,kind,replacement_id,db.now()))


def forget(memory_id,contact_id):
    """Tombstone memory and delete associated vector. Backups follow retention policy."""
    row=db.one('SELECT id,agent_id FROM memories WHERE id=? AND contact_id=? AND active=1',(memory_id,contact_id))
    if not row: return False
    with db.connect() as c:
        updated=c.execute('UPDATE memories SET active=0 WHERE id=? AND contact_id=? AND active=1',(memory_id,contact_id)).rowcount
        if updated and db.engine().dialect.name=='postgresql':
            c.execute('DELETE FROM memory_vectors WHERE memory_id=?',(memory_id,))
    if updated: track(memory_id,row['agent_id'],contact_id,'forgotten')
    return bool(updated)


def correct(memory_id,contact_id,content,consent=False):
    """Correction creates a new immutable memory and supersedes the old one.

    Preserves provenance for audit but prevents obsolete facts from retrieval.
    """
    original=db.one('SELECT * FROM memories WHERE id=? AND contact_id=? AND active=1',(memory_id,contact_id))
    if not original: raise ValueError('Memory not found')
    replacement=store(original['agent_id'],contact_id,content,category=original['category'],
                      sensitivity=original['sensitivity'],consent=consent,source_call_id=original['source_call_id'])
    if not forget(memory_id,contact_id):
        forget(replacement['id'],contact_id)
        raise ValueError('Memory was concurrently removed')
    track(memory_id,original['agent_id'],contact_id,'corrected',replacement['id'])
    return replacement


def timeline(agent_id,contact_id):
    return db.many('SELECT id,memory_id,kind,replacement_id,created_at FROM memory_events WHERE agent_id=? AND contact_id=? ORDER BY created_at,id',
                   (agent_id,contact_id))

async def index_embedding(memory_id):
    """Optional pgvector index. No API key -> lexical retrieval remains operational."""
    from app.config import get_settings
    s=get_settings()
    if not (s.database_url.startswith('postgresql') and s.openai_api_key): return False
    import httpx
    row=db.one('SELECT m.content FROM memories m JOIN contacts c ON m.contact_id=c.id WHERE m.id=? AND m.active=1 AND c.active=1 AND c.memory_opt_in=1',(memory_id,))
    if not row: return False
    async with httpx.AsyncClient(timeout=15) as client:
        result=await client.post('https://api.openai.com/v1/embeddings',
              headers={'Authorization':'Bearer '+s.openai_api_key},
              json={'model':'text-embedding-3-small','input':row['content']})
        result.raise_for_status()
    import json
    vector='['+','.join(str(n) for n in result.json()['data'][0]['embedding'])+']'
    db.execute('INSERT INTO memory_vectors (memory_id,embedding) VALUES (?,CAST(? AS vector)) ON CONFLICT (memory_id) DO UPDATE SET embedding=EXCLUDED.embedding',
               (memory_id,vector))
    return True

async def semantic_relevant(agent_id,contact_id,query,limit=8):
    """Vector rank with mandatory scope and sensitivity checks, lexical fallback."""
    from app.config import get_settings
    s=get_settings()
    if not (s.database_url.startswith('postgresql') and s.openai_api_key):
        from app.v3.intelligent_memory import ranked
        return ranked(agent_id,contact_id,query,limit)
    from app.v3.intelligent_memory import consent_status
    if not consent_status(contact_id)['memory_enabled']:
        return []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            result=await client.post('https://api.openai.com/v1/embeddings',
                  headers={'Authorization':'Bearer '+s.openai_api_key},
                  json={'model':'text-embedding-3-small','input':query[:1000]})
            result.raise_for_status()
        vector='['+','.join(str(n) for n in result.json()['data'][0]['embedding'])+']'
        return db.many('SELECT m.* FROM memories m JOIN memory_vectors v ON m.id=v.memory_id WHERE m.agent_id=? AND m.contact_id=? AND m.active=1 AND m.sensitivity=\'routine\' AND (m.expires_at IS NULL OR m.expires_at > ?) ORDER BY v.embedding <=> CAST(? AS vector) LIMIT 8',
                       (agent_id,contact_id,db.now(),vector))
    except Exception:
        from app.v3.intelligent_memory import ranked
        return ranked(agent_id,contact_id,query,limit)
