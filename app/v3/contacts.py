"""Registered recipients; explicit outbound consent is independent of mere address-book presence."""
import csv
import io
import re
from app import db
from app.models import valid_phone

def register(name,phone,email=None,language='Hinglish',outbound_consent=False,email_consent=False):
    if not valid_phone(phone): raise ValueError('Phone must be E.164')
    if not isinstance(name,str) or not name.strip(): raise ValueError('Name is required')
    if email and (len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email)):
        raise ValueError('Invalid email address')
    id_=db.uid()
    existing=db.one('SELECT id FROM contacts WHERE phone=?',(phone,))
    if existing: raise ValueError('Phone number already registered')
    db.execute('INSERT INTO contacts (id,name,phone,email,language,outbound_consent,email_consent,created_at) VALUES (?,?,?,?,?,?,?,?)',
               (id_,name.strip()[:120],phone,email,language[:40],int(outbound_consent),int(email_consent),db.now()))
    return db.one('SELECT * FROM contacts WHERE id=?',(id_,))

def update(contact_id, *, name=None, email=None, language=None, outbound_consent=None, email_consent=None):
    existing=db.one('SELECT * FROM contacts WHERE id=? AND active=1',(contact_id,))
    if not existing: raise ValueError('Contact not found')
    changes={}
    if name is not None:
        if not name.strip() or len(name)>120: raise ValueError('Invalid contact name')
        changes['name']=name.strip()
    if email is not None:
        if email and (len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email)):
            raise ValueError('Invalid email address')
        changes['email']=email or None
        # Switching email addresses automatically revokes previous authorization.
        if email != existing['email']: changes['email_consent']=0
    if language is not None:
        if not language.strip() or len(language)>40: raise ValueError('Invalid language')
        changes['language']=language.strip()
    if outbound_consent is not None: changes['outbound_consent']=int(outbound_consent)
    if email_consent is not None:
        if email_consent and not (changes.get('email',existing['email'])):
            raise ValueError('Cannot consent to email without an address')
        # Never automatically re-grant consent after an email address has changed.
        if changes.get('email') is not None and changes.get('email')!=existing['email'] and email_consent:
            raise ValueError('Reconfirm email consent after changing address')
        changes['email_consent']=int(email_consent)
    if changes:
        cols=', '.join(f'{k}=?' for k in changes)
        db.execute(f'UPDATE contacts SET {cols} WHERE id=? AND active=1',tuple(changes.values())+(contact_id,))
    return db.one('SELECT * FROM contacts WHERE id=?',(contact_id,))


def deactivate(contact_id):
    with db.connect() as c:
        changed=c.execute('UPDATE contacts SET active=0,outbound_consent=0,email_consent=0 WHERE id=? AND active=1',(contact_id,)).rowcount
        if changed:
            c.execute('DELETE FROM agent_contact_permissions WHERE contact_id=?',(contact_id,))
            # Pending research delivery must not proceed after contact deactivation.
            c.execute("UPDATE missions SET state='canceled',updated_at=? WHERE contact_id=? AND state IN ('queued','blocked','awaiting_consent')",(db.now(),contact_id))
    return bool(changed)


def import_csv(raw):
    reader=csv.DictReader(io.StringIO(raw))
    if not {'name','phone'}.issubset(set(reader.fieldnames or [])):
        raise ValueError('CSV must include name,phone columns')
    result={'imported':0,'skipped':0,'errors':[]}
    for n,row in enumerate(reader,2):
        if n>1002: raise ValueError('Maximum 1000 contacts per import')
        try:
            register(row['name'],row['phone'],row.get('email') or None,row.get('language') or 'Hinglish')
            result['imported']+=1
        except (ValueError,KeyError) as e:
            result['skipped']+=1
            if len(result['errors'])<10: result['errors'].append({'row':n,'reason':str(e)})
    return result
