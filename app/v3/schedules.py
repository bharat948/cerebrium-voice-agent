"""Durable daily/weekly research scheduling with exactly-once queue creation.

Scheduling a mission is not permission to call someone. This component never
initiates telephone calls. It only queues a consent-checked research task.
"""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from app import db

class ScheduleError(ValueError): pass


def next_occurrence(interval,hour,minute,tz,after=None):
    if interval not in ('daily','weekly'):raise ScheduleError('Only daily/weekly intervals are supported')
    if not 0<=hour<=23 or not 0<=minute<=59:raise ScheduleError('Invalid schedule time')
    try:local=ZoneInfo(tz)
    except (ZoneInfoNotFoundError,KeyError):raise ScheduleError('Unknown timezone') from None
    now=(after or datetime.now(timezone.utc)).astimezone(local)
    # 1 week means same local weekday as creation. DST transitions are normalized
    # by evaluating local dates, not by accumulating fixed UTC durations.
    for offset in range(0,9):
        day=(now+timedelta(days=offset)).date()
        if interval=='weekly' and day.weekday()!=now.date().weekday():continue
        value=datetime(day.year,day.month,day.day,hour,minute,tzinfo=local)
        if value>now:return value.astimezone(timezone.utc).isoformat()
    raise ScheduleError('Unable to calculate next run')


def create(agent_id,contact_id,objective,interval='daily',hour=9,minute=0,tz='Asia/Kolkata'):
    if not db.one('SELECT id FROM agents WHERE id=?',(agent_id,)):
        raise ScheduleError('Unknown agent')
    contact=db.one('SELECT * FROM contacts WHERE id=? AND active=1',(contact_id,))
    if not contact or not contact['email'] or not contact['email_consent']:
        raise ScheduleError('Contact must have an authorized research email')
    if not 10<=len(objective)<=2500:raise ScheduleError('Objective length out of range')
    when=next_occurrence(interval,hour,minute,tz)
    id_=db.uid()
    db.execute('INSERT INTO mission_schedules VALUES (?,?,?,?,?,?,?,?,?,?,?)',
               (id_,agent_id,contact_id,objective,interval,hour,minute,tz,when,1,db.now()))
    return db.one('SELECT * FROM mission_schedules WHERE id=?',(id_,))


def deactivate(schedule_id):
    return bool(db.execute('UPDATE mission_schedules SET active=0 WHERE id=?',(schedule_id,)))


def tick():
    """Safely enqueue due occurrences after restart. No duplicate mission per slot."""
    count=0
    rows=db.many('SELECT * FROM mission_schedules WHERE active=1 AND next_run_at<=? LIMIT 20',(db.now(),))
    for r in rows:
        contact=db.one('SELECT id FROM contacts WHERE id=? AND active=1 AND email_consent=1',(r['contact_id'],))
        if not contact:
            deactivate(r['id']);continue
        due=datetime.fromisoformat(r['next_run_at'])
        nxt=next_occurrence(r['interval'],r['hour_local'],r['minute_local'],r['tz'],due)
        with db.connect() as c:
            already=c.execute('SELECT mission_id FROM schedule_occurrences WHERE schedule_id=? AND due_at=?',
                              (r['id'],r['next_run_at'])).fetchone()
            if not already:
                mission=db.uid()
                c.execute('INSERT INTO missions (id,agent_id,contact_id,kind,objective,payload,state,attempts,lease_until,next_run_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                          (mission,r['agent_id'],r['contact_id'],'research',r['objective'],'{}','queued',0,None,db.now(),db.now(),db.now()))
                c.execute('INSERT INTO schedule_occurrences VALUES (?,?,?)',(r['id'],r['next_run_at'],mission))
                count+=1
            c.execute('UPDATE mission_schedules SET next_run_at=? WHERE id=? AND next_run_at=?',
                      (nxt,r['id'],r['next_run_at']))
    return count
