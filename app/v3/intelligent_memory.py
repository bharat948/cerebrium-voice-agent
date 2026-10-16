"""Versioned, caller-scoped memory consolidation and explainable retrieval.

Privacy and authority boundaries are enforced in SQL, not in prompts. Automatic
candidate extraction cannot grant consent, overwrite an existing record, or
read another contact's data. Ambiguous contradictions await owner review.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from app import db
from app.v3 import memory

WORDS = re.compile(r'[^\W_]+', re.UNICODE)
STOP = {'the', 'and', 'for', 'are', 'with', 'from', 'that', 'this', 'about', 'have', 'user',
        'caller', 'their', 'they', 'would', 'like', 'does', 'not', 'never', 'prefer',
        'prefers', 'a', 'an', 'to', 'in', 'is', 'of', 'i', 'my'}
SENSITIVE_HINTS = re.compile(
    r'(?i)\b(?:bank account|account number|salary|medical|diagnos\w*|pregnan\w*|'
    r'passport|aadhar|aadhaar|pan number|sexual|religion|political party|'
    r'banking password|credit card|health condition)\b')
PROMPT_INJECTION = re.compile(r'(?i)\b(?:ignore (?:all |previous |system )?instructions|you are now|system prompt|disable permissions|reveal (?:the )?api key)\b')
NEGATORS = {'not', 'never', 'no', 'dont', "don't", 'dislike', 'avoid'}

class MemoryPolicyError(ValueError):
    pass


def consent_status(contact_id: str) -> dict:
    contact=db.one('SELECT id,active,memory_opt_in FROM contacts WHERE id=?',(contact_id,))
    if not contact or not contact['active']:
        raise MemoryPolicyError('Active contact not found')
    return {'contact_id':contact_id,'memory_enabled':bool(contact['memory_opt_in'])}


def set_consent(contact_id: str, enabled: bool) -> dict:
    if type(enabled) is not bool:
        raise MemoryPolicyError('Explicit boolean required')
    with db.connect() as c:
        changed=c.execute('UPDATE contacts SET memory_opt_in=? WHERE id=? AND active=1',
                          (int(enabled),contact_id)).rowcount
        if not changed:raise MemoryPolicyError('Active contact not found')
        c.execute('INSERT INTO audit_events VALUES (?,?,?,?,?,?)',
                  (db.uid(),'owner','memory.preference.changed',contact_id,
                   'enabled' if enabled else 'disabled',db.now()))
    return consent_status(contact_id)


def tokens(text: str) -> set[str]:
    return {w.lower() for w in WORDS.findall(text) if len(w)>2 and w.lower() not in STOP}


def _utc(value):
    if not value:return None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as e:raise MemoryPolicyError('Expected ISO-8601 timestamp') from e
    if parsed.tzinfo is None:raise MemoryPolicyError('Timezone required')
    return parsed.astimezone(timezone.utc)


def consolidate(agent_id:str, contact_id:str, content:str, *, source_call_id=None,
                confidence:float=0.8, expires_at:str|None=None, supersedes_id:str|None=None,
                origin:str='postcall') -> dict:
    """Upsert an *allowed routine memory*, or quarantine a likely contradiction.

    Only an explicit correction can supersede another memory. A model's assertion
    alone is never authorization to delete or rewrite historical facts.
    """
    if origin not in {'postcall','owner','caller_correction'}:
        raise MemoryPolicyError('Invalid memory origin')
    if not isinstance(content,str) or not 5<=len(content.strip())<=500:
        raise MemoryPolicyError('Memory length must be between 5 and 500 characters')
    content=' '.join(content.split())
    if not isinstance(confidence,(int,float)) or not math.isfinite(confidence) or not .2<=confidence<=1:
        raise MemoryPolicyError('Confidence must be between 0.2 and 1')
    if memory.RESTRICTED.search(content) or SENSITIVE_HINTS.search(content) or PROMPT_INJECTION.search(content):
        raise MemoryPolicyError('Automatic memory cannot contain secrets or sensitive details')
    expiry=_utc(expires_at)
    if expiry and expiry<=datetime.now(timezone.utc):
        raise MemoryPolicyError('Expiration must be in the future')
    if not db.one('SELECT id FROM agents WHERE id=?',(agent_id,)):
        raise MemoryPolicyError('Unknown agent')
    consent_status_value=consent_status(contact_id)
    if not consent_status_value['memory_enabled']:
        return {'status':'skipped','reason':'contact_memory_disabled'}
    if source_call_id:
        if not db.one('SELECT calls.id FROM calls JOIN contacts ON contacts.phone=calls.phone WHERE calls.id=? AND calls.agent_id=? AND contacts.id=?',(source_call_id,agent_id,contact_id)):
            raise MemoryPolicyError('Invalid call provenance')
    current=db.many("SELECT * FROM memories WHERE agent_id=? AND contact_id=? AND active=1 AND sensitivity='routine'",
                    (agent_id,contact_id))
    if supersedes_id:
        original=next((r for r in current if r['id']==supersedes_id),None)
        if not original:raise MemoryPolicyError('Cannot supersede memory outside this scope')
        if origin not in {'owner','caller_correction'}:
            raise MemoryPolicyError('Automatic extraction cannot supersede a memory')
        replacement=memory.correct(supersedes_id,contact_id,content)
        db.execute('UPDATE memories SET supersedes_id=?,origin=?,confidence=?,expires_at=? WHERE id=?',
                   (supersedes_id,origin,confidence,expiry.isoformat() if expiry else None,replacement['id']))
        return {'status':'superseded','memory':db.one('SELECT * FROM memories WHERE id=?',(replacement['id'],))}
    normalized=content.casefold()
    for item in current:
        if ' '.join(item['content'].split()).casefold()==normalized:
            with db.connect() as c:
                c.execute('UPDATE memories SET strength=CASE WHEN strength < 20 THEN strength+1 ELSE 20 END WHERE id=? AND active=1',
                          (item['id'],))
                c.execute('INSERT INTO memory_events VALUES (?,?,?,?,?,?,?)',
                          (db.uid(),item['id'],agent_id,contact_id,'reinforced',None,db.now()))
            return {'status':'reinforced','memory':db.one('SELECT * FROM memories WHERE id=?',(item['id'],))}
    # Conservative contradiction detector; it flags a possible contradiction,
    # never decides which statement is true. Owner resolves separately.
    new_tokens=tokens(content)
    for item in current:
        old_tokens=tokens(item['content'])
        if (len(new_tokens & old_tokens)>=2 and
            len(new_tokens & old_tokens)/max(len(new_tokens),len(old_tokens),1)>=.65 and
            bool(NEGATORS & {w.lower() for w in WORDS.findall(content)}) !=
            bool(NEGATORS & {w.lower() for w in WORDS.findall(item['content'])})):
            id_=db.uid()
            db.execute('INSERT INTO memory_conflicts (id,agent_id,contact_id,existing_memory_id,proposed_content,source_call_id,state,created_at) VALUES (?,?,?,?,?,?,?,?)',
                       (id_,agent_id,contact_id,item['id'],content,source_call_id,'pending',db.now()))
            return {'status':'conflict','conflict_id':id_,'existing_memory_id':item['id']}
    row=memory.store(agent_id,contact_id,content,category='preference',sensitivity='routine',source_call_id=source_call_id)
    db.execute('UPDATE memories SET origin=?,confidence=?,expires_at=? WHERE id=?',
               (origin,confidence,expiry.isoformat() if expiry else None,row['id']))
    return {'status':'created','memory':db.one('SELECT * FROM memories WHERE id=?',(row['id'],))}


def ranked(agent_id:str, contact_id:str, query:str='', limit:int=8, mission_goal:str='') -> list[dict]:
    if not consent_status(contact_id)['memory_enabled']:
        return []
    candidates=db.many("SELECT * FROM memories WHERE agent_id=? AND contact_id=? AND active=1 AND sensitivity='routine'",
                       (agent_id,contact_id))
    now=datetime.now(timezone.utc)
    target=tokens(query+' '+mission_goal)
    scores=[]
    for m in candidates:
        expires=_utc(m.get('expires_at'))
        effective=_utc(m.get('valid_from'))
        if expires and expires<=now or effective and effective>now:continue
        memory_tokens=tokens(m['content'])
        overlap=len(target & memory_tokens)
        if target and overlap==0:continue
        match=overlap/max(1,len(target))
        age=max(0,(now-_utc(m['created_at'])).total_seconds()/86400)
        recency=2**(-age/90)
        score=(match*5 if target else 1)+recency*.75+min(m.get('strength') or 1,10)*.08+float(m['confidence'])*.7
        scores.append((score,m))
    scores.sort(key=lambda x:(-x[0],x[1]['id']))
    return [{**row,'retrieval_score':round(score,4)} for score,row in scores[:max(1,min(20,limit))]]


def pending_conflicts(agent_id:str,contact_id:str) -> list[dict]:
    return db.many("SELECT * FROM memory_conflicts WHERE agent_id=? AND contact_id=? AND state='pending' ORDER BY created_at",
                   (agent_id,contact_id))


def resolve_conflict(conflict_id:str,decision:str) -> dict:
    if decision not in {'reject','supersede'}:raise MemoryPolicyError('Invalid resolution')
    with db.connect() as c:
        row=c.execute("SELECT * FROM memory_conflicts WHERE id=? AND state='pending'",(conflict_id,)).fetchone()
        if not row:raise MemoryPolicyError('Pending conflict not found')
        updated=c.execute("UPDATE memory_conflicts SET state=?,resolved_at=? WHERE id=? AND state='pending'",
                          ('rejected' if decision=='reject' else 'accepted',db.now(),conflict_id)).rowcount
        if updated!=1:raise MemoryPolicyError('Concurrent resolution')
    if decision=='supersede':
        try:
            result=consolidate(row['agent_id'],row['contact_id'],row['proposed_content'],
                               supersedes_id=row['existing_memory_id'],origin='owner')
        except Exception:
            db.execute("UPDATE memory_conflicts SET state='pending',resolved_at=NULL WHERE id=?",(conflict_id,))
            raise
        return {'state':'accepted','memory':result['memory']}
    return {'state':'rejected'}
