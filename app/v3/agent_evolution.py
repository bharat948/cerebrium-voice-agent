"""Owner-reviewed evolution: proposals only, no autonomous prompt edits.

Feedback is untrusted. The generated change is chosen from a fixed allowlist,
not copied from a caller utterance, document, or human review text.
"""
import json
from app import db
from app.v3 import registry

class EvolutionError(ValueError):pass

SAFE_CHANGES={
 'conciseness':{'backchannel_policy':
     'Use brief acknowledgments sparingly. Keep responses concise and avoid repeating questions already answered.'},
 'turn_taking':{'interruption_policy':
     'Stop speaking when the caller interrupts. Allow reflection pauses and ask one clarifying question when necessary.'},
 'uncertainty':{'delegation_policy':
     'For complex or delayed research, state uncertainty, request consent for background reporting, and never invent tool results.'},
}


def propose(agent_id:str,theme:str='conciseness'):
    if not db.one('SELECT id FROM agents WHERE id=?',(agent_id,)):
        raise EvolutionError('Agent not found')
    if theme not in SAFE_CHANGES:
        raise EvolutionError('Unsupported proposal theme')
    feedback=db.many('SELECT id,rating,created_at FROM agent_feedback WHERE agent_id=? ORDER BY created_at DESC LIMIT 30',(agent_id,))
    if not feedback:
        raise EvolutionError('At least one human voice review is required')
    # No automatic release edits: review criteria and evidence remain visible.
    evidence={'feedback_count':len(feedback),
              'average_rating':round(sum(r['rating'] for r in feedback)/len(feedback),2),
              'feedback_ids':[r['id'] for r in feedback[:12]], 'theme':theme}
    id_=db.uid()
    db.execute('INSERT INTO agent_improvement_proposals (id,agent_id,source,evidence,changes,state,created_at) VALUES (?,?,?,?,?,?,?)',
               (id_,agent_id,'human_feedback',json.dumps(evidence),json.dumps(SAFE_CHANGES[theme]),'pending',db.now()))
    return {'id':id_,'agent_id':agent_id,'state':'pending','evidence':evidence,'changes':SAFE_CHANGES[theme]}


def list_proposals(agent_id:str):
    rows=db.many('SELECT * FROM agent_improvement_proposals WHERE agent_id=? ORDER BY created_at DESC',(agent_id,))
    return [{**r,'evidence':json.loads(r['evidence']),'changes':json.loads(r['changes'])} for r in rows]


def decide(proposal_id:str,approve:bool):
    with db.connect() as c:
        row=c.execute("SELECT * FROM agent_improvement_proposals WHERE id=? AND state='pending'",(proposal_id,)).fetchone()
        if not row:raise EvolutionError('Pending proposal not found')
        n=c.execute("UPDATE agent_improvement_proposals SET state='processing',reviewed_at=? WHERE id=? AND state='pending'",
                    (db.now(),proposal_id)).rowcount
        if n!=1:raise EvolutionError('Proposal already handled')
    if not approve:
        db.execute("UPDATE agent_improvement_proposals SET state='rejected' WHERE id=?",(proposal_id,))
        return {'state':'rejected','proposal_id':proposal_id}
    changes=json.loads(row['changes'])
    if not any(changes==v for v in SAFE_CHANGES.values()):
        db.execute("UPDATE agent_improvement_proposals SET state='rejected' WHERE id=?",(proposal_id,))
        raise EvolutionError('Proposal changes fail allowlist validation')
    try:
        draft=registry.create_draft(row['agent_id'],changes)
    except Exception:
        db.execute("UPDATE agent_improvement_proposals SET state='pending',reviewed_at=NULL WHERE id=?",(proposal_id,))
        raise
    db.execute("UPDATE agent_improvement_proposals SET state='draft_created',draft_id=? WHERE id=?",
               (draft['id'],proposal_id))
    return {'state':'draft_created','proposal_id':proposal_id,'draft':draft,
            'published':False,'note':'Test and publish explicitly in Agent Studio.'}
