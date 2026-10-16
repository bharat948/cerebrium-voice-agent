"""Trust-tiered, permission-scoped knowledge ingestion and retrieval.

File parsing is done on uploaded bytes only. No arbitrary website fetching/SSRF.
Data from documents is never treated as system instructions.
"""
from __future__ import annotations
import hashlib
import io
import re
from app import db

TIERS={'trusted','attributed','provisional','quarantined'}
VISIBILITY={'shared','private'}
MAX_BYTES=3_000_000

class KnowledgeError(ValueError): pass


def parse_file(filename,raw):
    if len(raw)>MAX_BYTES: raise KnowledgeError('File exceeds 3MB limit')
    suffix=filename.lower().rsplit('.',1)[-1]
    if suffix in {'txt','md','csv'}:
        return raw.decode('utf-8-sig')
    if suffix=='pdf':
        try:
            import fitz
            with fitz.open(stream=raw,filetype='pdf') as pdf:
                if len(pdf)>100: raise KnowledgeError('PDF exceeds 100 pages')
                return '\n'.join(p.get_text() for p in pdf)
        except ImportError: raise KnowledgeError('PDF support unavailable: install pymupdf') from None
    if suffix=='docx':
        try:
            from docx import Document
            document=Document(io.BytesIO(raw))
            return '\n'.join(p.text for p in document.paragraphs)
        except ImportError: raise KnowledgeError('DOCX support unavailable: install python-docx') from None
    raise KnowledgeError('Allowed file types: txt, md, csv, pdf, docx')


def chunks(text,size=1100,overlap=150):
    normalized=re.sub(r'[ \t]+',' ',text).strip()
    if not normalized: return []
    if len(normalized)>200_000: raise KnowledgeError('Extracted content exceeds 200k characters')
    out=[]; cursor=0
    while cursor<len(normalized):
        end=min(len(normalized),cursor+size)
        if end<len(normalized):
            split=normalized.rfind(' ',cursor+size//2,end)
            if split>cursor: end=split
        out.append(normalized[cursor:end])
        if end>=len(normalized): break
        cursor=max(cursor+1,end-overlap)
    return out


def ingest(filename,raw,agent_id=None,visibility='private',trust_tier='provisional'):
    if visibility not in VISIBILITY or trust_tier not in TIERS: raise KnowledgeError('Invalid visibility/trust tier')
    if visibility=='private' and not agent_id: raise KnowledgeError('Private knowledge requires an agent')
    if agent_id and not db.one('SELECT id FROM agents WHERE id=?',(agent_id,)):
        raise KnowledgeError('Unknown agent')
    digest=hashlib.sha256(raw).hexdigest()
    matches=db.many('SELECT * FROM knowledge_sources WHERE content_hash=? AND visibility=?',(digest,visibility))
    existing=next((row for row in matches if row['agent_id']==agent_id),None)
    if existing: return {'source':existing,'chunks':db.one('SELECT COUNT(*) AS n FROM knowledge_chunks WHERE source_id=?',(existing['id'],))['n'],'duplicate':True}
    parsed=parse_file(filename,raw)
    pieces=chunks(parsed)
    if not pieces: raise KnowledgeError('No extractable text in document')
    source_id=db.uid()
    with db.connect() as c:
        c.execute('INSERT INTO knowledge_sources VALUES (?,?,?,?,?,?,?,?,?,?)',
                  (source_id,agent_id,filename[:200],'file',None,visibility,trust_tier,digest,db.now(),db.now()))
        for n,piece in enumerate(pieces):
            c.execute('INSERT INTO knowledge_chunks VALUES (?,?,?,?,?,?)',
                      (db.uid(),source_id,n,piece,max(1,len(piece)//4),db.now()))
    return {'source':db.one('SELECT * FROM knowledge_sources WHERE id=?',(source_id,)), 'chunks':len(pieces),'duplicate':False}


def search(agent_id,query,limit=5):
    if not db.one('SELECT id FROM agents WHERE id=?',(agent_id,)):
        raise KnowledgeError('Unknown agent')
    terms=[t for t in re.findall(r'[a-zA-Z0-9]{3,}',query.lower()) if t not in {'the','and','with'}][:15]
    if not terms: return []
    rows=db.many('''SELECT k.id,k.content,k.ordinal,s.id AS source_id,s.title,s.trust_tier,s.visibility,
           s.created_at FROM knowledge_chunks k JOIN knowledge_sources s ON k.source_id=s.id
           WHERE s.trust_tier != 'quarantined' AND (s.visibility='shared' OR s.agent_id=?)
           ORDER BY s.updated_at DESC LIMIT 1500''',(agent_id,))
    ranked=[]
    for row in rows:
        lower=row['content'].lower()
        score=sum(min(lower.count(t),4) for t in terms)
        if score: ranked.append((score,row))
    ranked.sort(key=lambda x:(-x[0],-x[1]['ordinal']))
    return [{**r,'score':score,'untrusted_source_content':True} for score,r in ranked[:max(1,min(limit,10))]]


def change_tier(source_id,tier):
    if tier not in TIERS: raise KnowledgeError('Invalid tier')
    count=db.execute('UPDATE knowledge_sources SET trust_tier=?,updated_at=? WHERE id=?',
                     (tier,db.now(),source_id))
    if count!=1: raise KnowledgeError('Source not found')
    return db.one('SELECT * FROM knowledge_sources WHERE id=?',(source_id,))


async def index_embeddings(source_id: str, max_chunks: int = 40):
    """Owner-triggered batch indexing on PostgreSQL; never called during live audio.

    The first 40 chunks are a deliberate spending/scope cap.
    """
    from app.config import get_settings
    import httpx
    s=get_settings()
    if db.engine().dialect.name != 'postgresql':
        raise KnowledgeError('Vector indexing requires PostgreSQL/pgvector')
    if not s.openai_api_key:raise KnowledgeError('OPENAI_API_KEY required for embeddings')
    source=db.one('SELECT * FROM knowledge_sources WHERE id=?',(source_id,))
    if not source or source['trust_tier']=='quarantined':raise KnowledgeError('Source unavailable for indexing')
    if not 1<=max_chunks<=40:raise KnowledgeError('Maximum 40 chunks per batch')
    rows=db.many('SELECT id,content FROM knowledge_chunks WHERE source_id=? ORDER BY ordinal LIMIT ?',
                 (source_id,max_chunks))
    if not rows:return {'indexed':0,'source_id':source_id}
    async with httpx.AsyncClient(timeout=45) as client:
        response=await client.post('https://api.openai.com/v1/embeddings',
            headers={'Authorization':'Bearer '+s.openai_api_key},
            json={'model':'text-embedding-3-small','input':[r['content'][:2000] for r in rows]})
        response.raise_for_status()
    vectors=response.json().get('data',[])
    if len(vectors)!=len(rows):raise KnowledgeError('Unexpected embedding count')
    with db.connect() as conn:
        for row,record in zip(rows,sorted(vectors,key=lambda r:r['index'])):
            arr=record.get('embedding',[])
            if len(arr)!=1536:raise KnowledgeError('Unexpected embedding dimensions')
            literal='['+','.join(str(float(n)) for n in arr)+']'
            conn.execute('''INSERT INTO knowledge_vectors (chunk_id,embedding)
                 VALUES (?,CAST(? AS vector)) ON CONFLICT (chunk_id)
                 DO UPDATE SET embedding=EXCLUDED.embedding''',(row['id'],literal))
    return {'indexed':len(rows),'source_id':source_id,'model':'text-embedding-3-small'}


async def semantic_search(agent_id: str, query: str, limit: int = 5):
    """Mandatory SQL ACL before similarity ranking, lexical fallback on failure."""
    from app.config import get_settings
    import httpx
    s=get_settings()
    if not db.one('SELECT id FROM agents WHERE id=?',(agent_id,)):
        raise KnowledgeError('Unknown agent')
    if db.engine().dialect.name != 'postgresql' or not s.openai_api_key:
        return search(agent_id,query,limit)
    try:
        async with httpx.AsyncClient(timeout=14) as client:
            result=await client.post('https://api.openai.com/v1/embeddings',
                headers={'Authorization':'Bearer '+s.openai_api_key},
                json={'model':'text-embedding-3-small','input':query[:1500]})
            result.raise_for_status()
        values=result.json()['data'][0]['embedding']
        if len(values)!=1536:raise KnowledgeError('Unexpected query embedding size')
        vector='['+','.join(str(float(n)) for n in values)+']'
        hits=db.many('''SELECT k.id,k.content,k.ordinal,s.id AS source_id,s.title,s.trust_tier,
                        s.visibility,s.source_url,
                        v.embedding <=> CAST(? AS vector) AS distance
                    FROM knowledge_vectors v JOIN knowledge_chunks k ON k.id=v.chunk_id
                    JOIN knowledge_sources s ON s.id=k.source_id
                    WHERE s.trust_tier!='quarantined'
                      AND (s.visibility='shared' OR s.agent_id=?)
                    ORDER BY distance ASC LIMIT ?''',(vector,agent_id,max(1,min(limit,10))))
        if hits:return [{**r,'untrusted_source_content':True} for r in hits]
    except (httpx.HTTPError,KeyError,ValueError,TypeError,KnowledgeError):
        pass
    return search(agent_id,query,limit)
