"""Durable approvals, notifications, budgets, and runtime supervision.

This service is intentionally independent of any language model: a prompt cannot
self-approve a call, change a permission, or spend beyond a configured budget.
"""
import json
from datetime import datetime, timezone
from app import db
from app.config import get_settings

RISKS={'research':'read','notify':'low','create_task':'low', 'book_appointment':'medium',
       'send_email':'high','initiate_call':'high','permissions':'restricted',
       'linear_create_issue':'medium','google_draft_email':'medium','google_calendar_create':'medium'}
TERMINAL={'approved','rejected','expired'}

class PolicyViolation(ValueError): pass


def _audit(action,target,detail,actor='owner'):
    db.execute('INSERT INTO audit_events VALUES (?,?,?,?,?,?)',
               (db.uid(),actor,action,target,json.dumps(detail,default=str)[:3000],db.now()))


def notify(title,detail='',priority='normal',category='system',related_id=None):
    if priority not in {'informational','normal','important','urgent','critical'}:
        raise PolicyViolation('Invalid notification priority')
    ident=db.uid()
    db.execute('INSERT INTO notifications VALUES (?,?,?,?,?,?,?,?,?)',
               (ident,category,priority,title[:200],detail[:1500],'unread',related_id,db.now(),None))
    return db.one('SELECT * FROM notifications WHERE id=?',(ident,))


def request_approval(agent_id,action,payload,contact_id=None):
    if action not in RISKS or RISKS[action]=='restricted':
        raise PolicyViolation('Action not eligible for delegated approval')
    if not db.one('SELECT id FROM agents WHERE id=?',(agent_id,)):
        raise PolicyViolation('Unknown agent')
    if not isinstance(payload,dict): raise PolicyViolation('Expected structured action payload')
    ident=db.uid()
    db.execute('INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,?,?)',
               (ident,agent_id,contact_id,action,json.dumps(payload)[:4000],'pending',db.now(),None,None,None))
    notify('Agent action requires approval',f'{action} requested by {agent_id}', 'important','approval',ident)
    _audit('approval.request',ident,{'action':action,'agent_id':agent_id})
    return db.one('SELECT * FROM approvals WHERE id=?',(ident,))


def decide(approval_id,approve,actor='owner'):
    with db.connect() as c:
        row=c.execute('SELECT * FROM approvals WHERE id=?',(approval_id,)).fetchone()
        if not row: raise PolicyViolation('Approval not found')
        if row['state']!='pending': raise PolicyViolation('Already decided')
        state='approved' if approve else 'rejected'
        updated=c.execute('UPDATE approvals SET state=?,decided_at=?,decided_by=? WHERE id=? AND state=?',
                          (state,db.now(),actor,approval_id,'pending'))
        if updated.rowcount!=1: raise PolicyViolation('Concurrent approval decision')
    _audit('approval.'+state,approval_id,{},actor)
    return db.one('SELECT * FROM approvals WHERE id=?',(approval_id,))


def require_approved(approval_id,action,agent_id=None):
    row=db.one('SELECT * FROM approvals WHERE id=?',(approval_id,))
    if not row or row['state']!='approved' or row['action']!=action:
        raise PolicyViolation('Approved authorization required')
    if agent_id and row['agent_id']!=agent_id: raise PolicyViolation('Agent mismatch')
    return json.loads(row['payload'])


def usage(agent_id=None,days=30):
    from datetime import timedelta
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
    rows=db.many('SELECT * FROM expenses WHERE occurred_at>=?',(cutoff,))
    if agent_id: rows=[r for r in rows if r['agent_id']==agent_id]
    total=sum(float(r['actual_usd'] if r['actual_usd'] is not None else r['estimated_usd']) for r in rows)
    return {'total_estimated_or_actual_usd':round(total,6),'records':len(rows),'period_days':days}


def ensure_budget(agent_id=None,requested_usd=0.0):
    limit=get_settings().monthly_budget_usd
    if limit<=0: raise PolicyViolation('Workspace monthly budget disabled')
    spent=usage(days=30)['total_estimated_or_actual_usd']
    if spent+requested_usd>limit: raise PolicyViolation('Workspace budget exceeded')
    if agent_id:
        agent_spent=usage(agent_id,30)['total_estimated_or_actual_usd']
        per=get_settings().agent_monthly_budget_usd
        if per>0 and agent_spent+requested_usd>per:
            raise PolicyViolation('Agent budget exceeded')
    return {'workspace_remaining_estimate_usd':round(limit-spent-requested_usd,4)}


def record_cost(provider,operation,estimated_usd=0,actual_usd=None,agent_id=None,call_id=None,mission_id=None):
    if estimated_usd<0 or actual_usd is not None and actual_usd<0:
        raise PolicyViolation('Negative cost')
    ident=db.uid()
    db.execute('INSERT INTO expenses VALUES (?,?,?,?,?,?,?,?,?)',
               (ident,agent_id,call_id,mission_id,provider[:60],operation[:80],estimated_usd,actual_usd,db.now()))
    return ident


def control(call_id,command,instruction=None):
    if command not in {'pause','resume','stop','instruct'}:
        raise PolicyViolation('Unknown call control command')
    row=db.one('SELECT id,status FROM calls WHERE id=?',(call_id,))
    if not row: raise PolicyViolation('Call not found')
    if row['status'] not in {'queued','ringing','in-progress','initiated'}:
        raise PolicyViolation('Call is not active')
    if command=='instruct' and (not instruction or len(instruction)>1000):
        raise PolicyViolation('Instruction must be 1..1000 characters')
    current=db.one('SELECT * FROM runtime_controls WHERE call_id=?',(call_id,))
    paused=int(command=='pause' or command=='instruct' and bool(current and current['paused']))
    if command=='resume': paused=0
    if command=='stop': paused=1
    db.execute('DELETE FROM runtime_controls WHERE call_id=?',(call_id,))
    db.execute('INSERT INTO runtime_controls VALUES (?,?,?,?,?)',
               (call_id,paused,int(command=='stop'),instruction if command=='instruct' else None,db.now()))
    _audit('call.control.'+command,call_id,{'instruction':instruction if command=='instruct' else None})
    return db.one('SELECT * FROM runtime_controls WHERE call_id=?',(call_id,))
