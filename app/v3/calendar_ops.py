"""Transactional appointment records and optional Google Calendar sync.

Never report a booking as confirmed until the database commit and, if enabled,
Google Calendar API both acknowledge the operation.
"""
from datetime import datetime,timezone
from app import db
from app.config import get_settings
from app.v3 import governance

class AppointmentError(ValueError): pass


def _utc(value):
    try:
        d=datetime.fromisoformat(value.replace('Z','+00:00'))
        if d.tzinfo is None: raise ValueError
        return d.astimezone(timezone.utc)
    except ValueError: raise AppointmentError('Start/end must be timezone-aware ISO 8601') from None


def check(starts_at,ends_at):
    start,end=_utc(starts_at),_utc(ends_at)
    if end<=start: raise AppointmentError('End must be after start')
    if (end-start).total_seconds()>8*3600: raise AppointmentError('Appointment exceeds 8 hours')
    rows=db.many("SELECT id,title,starts_at,ends_at FROM calendar_events WHERE state='confirmed' AND starts_at<? AND ends_at>?",
                 (end.isoformat(),start.isoformat()))
    return {'available':len(rows)==0,'conflicts':rows}


def book(agent_id,title,starts_at,ends_at,contact_id=None,approval_id=None):
    if get_settings().demo_mode: raise AppointmentError('Live bookings disabled in demo mode')
    if not approval_id: raise AppointmentError('Owner approval required')
    payload=governance.require_approved(approval_id,'book_appointment',agent_id)
    required={'title':title,'starts_at':starts_at,'ends_at':ends_at,'contact_id':contact_id}
    if any(payload.get(k)!=v for k,v in required.items()):
        raise AppointmentError('Approval scope does not match the booking')
    if not db.one('SELECT id FROM agents WHERE id=?',(agent_id,)):
        raise AppointmentError('Unknown agent')
    if contact_id and not db.one('SELECT id FROM contacts WHERE id=? AND active=1',(contact_id,)):
        raise AppointmentError('Unknown contact')
    # Idempotency is evaluated *before* conflict checks: repeating an already
    # authorized booking must return the original record, not fail or duplicate.
    used=db.one('SELECT result FROM approvals WHERE id=?',(approval_id,))
    if used and used['result']:
        original=db.one('SELECT * FROM calendar_events WHERE id=?',(used['result'],))
        if original:return original
    if not check(starts_at,ends_at)['available']:
        raise AppointmentError('Slot unavailable')
    with db.connect() as c:
        if db.engine().dialect.name=='postgresql':
            # Serialize overlapping booking checks on a single shared calendar.
            c.execute('SELECT pg_advisory_xact_lock(79434217)')
        used=c.execute('SELECT result FROM approvals WHERE id=?',(approval_id,)).fetchone()
        if used and used['result']:
            previous=c.execute('SELECT * FROM calendar_events WHERE id=?',(used['result'],)).fetchone()
            if previous:return previous
        # In single-instance mode serialized writer + final intersection check.
        conflict=c.execute("SELECT COUNT(*) AS n FROM calendar_events WHERE state='confirmed' AND starts_at<? AND ends_at>?",
                           (_utc(ends_at).isoformat(),_utc(starts_at).isoformat())).fetchone()
        if conflict['n']: raise AppointmentError('Slot became unavailable')
        ident=db.uid()
        c.execute('INSERT INTO calendar_events VALUES (?,?,?,?,?,?,?,?,?)',
                  (ident,agent_id,contact_id,title[:200],_utc(starts_at).isoformat(),_utc(ends_at).isoformat(),'confirmed',None,db.now()))
        c.execute('UPDATE approvals SET result=? WHERE id=? AND result IS NULL',(ident,approval_id))
    return db.one('SELECT * FROM calendar_events WHERE id=?',(ident,))
