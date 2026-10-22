import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

from app import db
from app.v3 import registry, memory, governance
from app.v3.api import router as v3_router
from app.v3.advanced_api import router as advanced_router, google_router
from app.v3.voice_sandbox import router as voice_preview_router
from app.v3.intelligence_api import router as intelligence_router
from app.v3.auth import router as auth_router
from app.v3.integrations_api import router as integrations_router
from app.v3.missions import worker_loop
from starlette.middleware.sessions import SessionMiddleware
from app.config import get_settings
from app.models import AgentCreate, CallRequest, PlanEdit, PlanRequest, PreviewTurn, valid_phone
from app.planner import build_plan, extract_phone, preview_reply, openai_completion, OpenAIProviderError
from app.prompts import call_system_prompt
from app.security import require_api_key, require_twilio_http, allow_twilio_websocket
from app.voice import VoiceSession
from app.live_voice import LiveVoiceSession
from app.live_diagnostics import LiveProviderError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('voice-foundry')


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.app_env != 'development' and (s.app_api_key == 'dev-local-only-change-me' or not s.app_api_key):
        raise RuntimeError('Set a unique APP_API_KEY in non-development environments')
    if not s.demo_mode and (not s.app_api_key or s.app_api_key == 'dev-local-only-change-me'):
        raise RuntimeError('Replace the sample APP_API_KEY before enabling live calling')
    if not s.demo_mode and not s.twilio_validate_signatures:
        raise RuntimeError('Twilio signature validation required in live mode')
    db.init_db()
    db.purge_expired(s.transcript_retention_days)
    task = asyncio.create_task(worker_loop()) if s.enable_background_worker else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title='Voice Foundry API', version='4.0.0-alpha2', lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=get_settings().session_secret or get_settings().app_api_key,
                   same_site='lax', https_only=get_settings().auth_mode=='google', max_age=3600*12)
app.include_router(v3_router)
app.include_router(intelligence_router)
app.include_router(advanced_router)
app.include_router(google_router)
app.include_router(voice_preview_router)
app.include_router(auth_router)
app.include_router(integrations_router)

@app.middleware('http')
async def owner_origin_guard(request:Request, call_next):
    s=get_settings()
    if s.auth_mode=='google' and request.method in ('POST','PATCH','PUT','DELETE') and not request.url.path.startswith('/twilio/'):
        origin=request.headers.get('origin')
        if not origin:
            from urllib.parse import urlsplit
            referer=request.headers.get('referer','')
            if referer:
                parsed=urlsplit(referer)
                origin=parsed.scheme+'://'+parsed.netloc
        if not origin or origin.rstrip('/')!=s.base_url:
            return JSONResponse({'detail':'Cross-origin owner action blocked'},status_code=403)
    return await call_next(request)

app.mount('/assets', StaticFiles(directory=str(Path(__file__).resolve().parent.parent / 'web')), name='assets')


def api_auth(_: None = Depends(require_api_key)):
    return None


def client() -> Client:
    s = get_settings()
    return Client(s.twilio_account_sid, s.twilio_auth_token)


def twiml_for_call(call_id: str) -> str:
    s = get_settings()
    response = VoiceResponse()
    stream = response.connect().stream(url=s.base_url.replace('https://', 'wss://', 1) + '/twilio/media')
    stream.parameter(name='call_id', value=call_id)
    return str(response)


@app.get('/', include_in_schema=False)
async def homepage():
    return FileResponse(Path(__file__).resolve().parent.parent / 'web' / 'index.html')


@app.get('/health')
async def health():
    return {'status': 'ok', 'version': '4.0.0-alpha2'}


@app.get('/api/config', dependencies=[Depends(api_auth)])
async def get_config():
    s = get_settings()
    return {
        'name': s.app_name, 'demo_mode': s.demo_mode, 'ready_for_calls': s.ready_for_calls(),
        'openai_enabled': bool(s.openai_api_key), 'model': s.openai_model,
        'voice_engine': s.voice_engine, 'live_model': s.openai_live_model,
        'live_backend_model': s.openai_live_backend_model,
        'ready_by_engine': {k:s.ready_for_calls(k) for k in ('openai_live','deepgram')},
        'allowed_numbers': len(s.outbound_allowlist), 'max_call_seconds': s.max_call_seconds
    }


@app.get('/api/agents', dependencies=[Depends(api_auth)])
async def get_agents():
    return db.many('SELECT * FROM agents ORDER BY created_at ASC')


@app.post('/api/agents', dependencies=[Depends(api_auth)], status_code=201)
async def create_agent(payload: AgentCreate):
    return db.insert_agent(payload.name, payload.role, payload.language, payload.instructions)


@app.get('/api/plans', dependencies=[Depends(api_auth)])
async def get_plans():
    return db.plans()


@app.post('/api/plans', dependencies=[Depends(api_auth)], status_code=201)
async def create_plan(payload: PlanRequest):
    if not db.one('SELECT id FROM agents WHERE id=?', (payload.agent_id,)):
        raise HTTPException(404, 'Agent not found')
    if payload.contact_id:
        contact = db.one('SELECT * FROM contacts WHERE id=? AND active=1',(payload.contact_id,))
        if not contact: raise HTTPException(404,'Contact not found')
        phone = contact['phone']
    else:
        phone = extract_phone(payload.message, payload.phone)
    if not valid_phone(phone):
        raise HTTPException(422, 'Provide recipient phone in E.164 format, e.g. +14155552671')
    try:
        result = await build_plan(payload.message, get_settings())
    except OpenAIProviderError as exc:
        log.warning('Plan generation provider failure: status=%s code=%s', exc.status_code, exc.code)
        raise HTTPException(502, f'Unable to generate plan: {exc}') from None
    except Exception:
        log.exception('Unexpected plan generation failure')
        raise HTTPException(502, 'Unable to generate plan. Check Render logs.') from None
    return db.insert_plan(payload.agent_id, phone, result['goal'], result['agenda'], result['script'], payload.message)


@app.patch('/api/plans/{plan_id}', dependencies=[Depends(api_auth)])
async def edit_plan(plan_id: str, payload: PlanEdit):
    plan = db.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, 'Plan not found')
    if plan['state'] != 'draft':
        raise HTTPException(409, 'Only draft plans can be edited')
    import json
    db.execute('UPDATE plans SET goal=?,agenda=?,script=? WHERE id=?',
               (payload.goal, json.dumps(payload.agenda), payload.script, plan_id))
    return db.get_plan(plan_id)


@app.get('/api/calls', dependencies=[Depends(api_auth)])
async def get_calls():
    return db.many('SELECT * FROM calls ORDER BY created_at DESC LIMIT 100')


@app.get('/api/calls/{call_id}', dependencies=[Depends(api_auth)])
async def get_call(call_id: str):
    call = db.call_details(call_id)
    if not call:
        raise HTTPException(404, 'Call not found')
    return call


@app.post('/api/calls', dependencies=[Depends(api_auth)], status_code=201)
async def place_call(payload: CallRequest):
    s = get_settings()
    voice_engine = payload.voice_engine or s.voice_engine
    if voice_engine not in ('openai_live', 'deepgram'):
        raise HTTPException(400, 'Unknown voice engine')
    plan = db.get_plan(payload.plan_id)
    if not plan:
        raise HTTPException(404, 'Plan not found')
    if not payload.confirm:
        raise HTTPException(400, 'Explicit confirm=true required to initiate a call')
    if plan['state'] != 'draft':
        raise HTTPException(409, 'This plan has already been used')
    if not s.demo_mode:
        try:governance.ensure_budget(plan['agent_id'],requested_usd=0.10)
        except governance.PolicyViolation as exc:raise HTTPException(429,str(exc)) from None
        if not s.ready_for_calls(voice_engine):
            raise HTTPException(400, f'{voice_engine} credentials or PUBLIC_BASE_URL not configured')
        contact = db.one('SELECT * FROM contacts WHERE phone=? AND active=1',(plan['phone'],))
        if not (contact and contact['outbound_consent']) and plan['phone'] not in s.outbound_allowlist:
            raise HTTPException(403,'Recipient must have recorded outbound consent in Contacts or be in the legacy allowlist')
        config = registry.get_config(plan['agent_id'])
        if config and config['access']=='private' and plan['agent_id']!='receptionist':
            if not contact or contact['phone'] != s.owner_phone:
                raise HTTPException(403,'Private agent can only call the verified owner phone')
        if config and config['access']=='shared':
            if not contact or not db.one('SELECT agent_id FROM agent_contact_permissions WHERE agent_id=? AND contact_id=?',
                                      (plan['agent_id'],contact['id'])):
                raise HTTPException(403,'Contact not authorized to use shared agent')
        concurrent = db.one("SELECT count(*) AS n FROM calls WHERE status IN ('queued','ringing','in-progress') AND mode='live'")['n']
        if concurrent >= s.max_concurrent_calls:
            raise HTTPException(429, 'Concurrent-call limit reached')
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        hourly = db.one("SELECT count(*) AS n FROM calls WHERE created_at >= ? AND mode='live'", (cutoff,))['n']
        if hourly >= s.max_calls_per_hour:
            raise HTTPException(429, 'Hourly call limit reached')
    # Atomic claim ensures that repeated clicks cannot start the same call twice.
    with db.connect() as c:
        updated = c.execute("UPDATE plans SET state='used' WHERE id=? AND state='draft'", (payload.plan_id,))
        if updated.rowcount != 1:
            raise HTTPException(409, 'This plan has already been used')
    mode = 'demo' if s.demo_mode else 'live'
    call = db.insert_call(plan['id'], plan['agent_id'], plan['phone'], 'outbound', mode,
                          'simulated' if s.demo_mode else 'queued', voice_engine=voice_engine)
    db.add_event(call['id'], 'state', 'Preview created: no phone call was placed' if s.demo_mode
                 else 'Call queued for Twilio')
    if s.demo_mode:
        return db.call_details(call['id'])
    try:
        created = await asyncio.to_thread(
            lambda: client().calls.create(
                to=plan['phone'], from_=s.twilio_phone_number,
                url=s.base_url + '/twilio/voice?call_id=' + call['id'], method='POST',
                status_callback=s.base_url + '/twilio/status', status_callback_method='POST',
                status_callback_event=['initiated', 'ringing', 'answered', 'completed'],
                timeout=25,
            ))
        db.execute('UPDATE calls SET twilio_sid=? WHERE id=?', (created.sid, call['id']))
        db.add_event(call['id'], 'state', 'Twilio accepted outbound call')
        governance.record_cost('voice','outbound_call_reservation',estimated_usd=0.10,agent_id=plan['agent_id'],call_id=call['id'])
    except Exception as exc:
        log.exception('Twilio call creation failed')
        db.execute('UPDATE calls SET status=?,error=?,ended_at=? WHERE id=?',
                   ('failed', type(exc).__name__, db.now(), call['id']))
        db.add_event(call['id'], 'error', f'Twilio failed: {type(exc).__name__}')
        raise HTTPException(502, 'Twilio call creation failed; see server logs')
    return db.call_details(call['id'])


@app.post('/api/calls/{call_id}/preview', dependencies=[Depends(api_auth)])
async def preview_turn(call_id: str, payload: PreviewTurn):
    call = db.call_details(call_id)
    if not call:
        raise HTTPException(404, 'Call not found')
    if call['mode'] != 'demo' or call['status'] != 'simulated':
        raise HTTPException(409, 'Preview is only available on active demo calls')
    agent = db.one('SELECT * FROM agents WHERE id=?', (call['agent_id'],))
    messages = [{'role': 'user' if e['speaker'] == 'caller' else 'assistant', 'content': e['content']}
                for e in call['events'] if e['type'] == 'transcript'
                if e['speaker'] in ('caller', 'assistant')]
    messages.append({'role': 'user', 'content': payload.text})
    response = await preview_reply(messages, call_system_prompt(agent, call['plan']), get_settings())
    db.add_event(call_id, 'transcript', payload.text, 'caller')
    db.add_event(call_id, 'transcript', response, 'assistant')
    return db.call_details(call_id)


@app.post('/api/calls/{call_id}/summary', dependencies=[Depends(api_auth)])
async def summarize_call(call_id: str):
    call = db.call_details(call_id)
    if not call:
        raise HTTPException(404, 'Call not found')
    old = [e for e in call['events'] if e['type'] == 'summary']
    if old:
        return {'summary': old[-1]['content'], 'call_id': call_id}
    utterances = [e for e in call['events'] if e['type'] == 'transcript']
    if not utterances:
        raise HTTPException(409, 'No transcript is available yet')
    transcript = '\n'.join(f"{e['speaker']}: {e['content']}" for e in utterances)[:14000]
    s = get_settings()
    if s.openai_api_key:
        try:
            response = await openai_completion(s.openai_api_key, {
                'model': s.openai_model, 'max_tokens': 320,
                'messages': [
                    {'role': 'system', 'content': ('Summarize a telephone transcript in under 130 words. '
                       'Include the purpose, what the recipient actually said, and next steps. '
                       'Never claim any booking, transaction, or external action was completed '
                       'unless an independently verified tool result is provided. '
                       'No tools are provided here. Clearly label any unconfirmed request.')},
                    {'role': 'user', 'content': transcript}
                ]
            })
            summary = (response['choices'][0]['message']['content'] or '').strip()
        except Exception as exc:
            log.exception('Summary generation failed')
            raise HTTPException(502, f'Summary provider failure ({type(exc).__name__})')
    else:
        caller_lines = [e['content'] for e in utterances if e['speaker']=='caller']
        summary = ('Preview/transcript highlights: ' + ' | '.join(caller_lines[-4:])[:900] +
                   '. No external business action or appointment booking was verified.')
    if not summary:
        raise HTTPException(502, 'Summarizer returned empty result')
    db.add_event(call_id, 'summary', summary)
    return {'call_id': call_id, 'summary': summary}


@app.post('/api/calls/{call_id}/hangup', dependencies=[Depends(api_auth)])
async def hangup_call(call_id: str):
    call = db.one('SELECT * FROM calls WHERE id=?', (call_id,))
    if not call:
        raise HTTPException(404, 'Call not found')
    if call['status'] in ('completed', 'failed', 'canceled', 'busy', 'no-answer'):
        return db.call_details(call_id)
    if call['mode'] == 'live' and call['twilio_sid']:
        try:
            await asyncio.to_thread(lambda: client().calls(call['twilio_sid']).update(status='completed'))
        except Exception:
            log.exception('Unable to end Twilio call')
            raise HTTPException(502, 'Twilio could not end this call')
    db.execute('UPDATE calls SET status=?,ended_at=? WHERE id=?', ('completed', db.now(), call_id))
    db.add_event(call_id, 'state', 'Call ended by operator')
    return db.call_details(call_id)


@app.post('/twilio/voice', include_in_schema=False)
async def twilio_voice(request: Request):
    values = await require_twilio_http(request)
    s = get_settings()
    if s.demo_mode:
        raise HTTPException(503, 'Live calls disabled')
    call_id = request.query_params.get('call_id')
    if not call_id:
        if not s.twilio_allow_inbound:
            response = VoiceResponse()
            response.say('This number is not accepting calls right now.')
            return Response(str(response), media_type='application/xml')
        caller = str(values.get('From', 'unknown'))
        agent_id = 'receptionist'
        contact = db.one('SELECT * FROM contacts WHERE phone=? AND active=1',(caller,))
        if contact:
            permissions=db.many('SELECT agent_id FROM agent_contact_permissions WHERE contact_id=? ORDER BY agent_id',(contact['id'],))
            if len(permissions)==1:
                candidate=permissions[0]['agent_id']
                config=registry.get_config(candidate)
                if config and config['access']=='shared': agent_id=candidate
        plan = db.insert_plan(agent_id, caller, 'Help caller with their request',
                              ['Disclose AI identity and greet the caller', 'Understand their request',
                               'Answer questions without inventing commitments', 'Summarize next steps'],
                              'Hello, I am Ava, an AI assistant. How can I help?', 'Incoming call')
        call = db.insert_call(plan['id'], agent_id, caller, 'inbound', 'live', 'ringing', voice_engine=s.voice_engine)
        call_id = call['id']
        db.add_event(call_id, 'state', 'Incoming telephone call')
    call = db.one('SELECT * FROM calls WHERE id=?', (call_id,))
    if not call or call['mode'] != 'live' or call['status'] in ('completed','failed','canceled'):
        raise HTTPException(404, 'Call not active')
    if not s.ready_for_calls(call.get('voice_engine') or 'deepgram'):
        raise HTTPException(503, 'Selected voice engine unavailable')
    sid = str(values.get('CallSid', ''))
    if call['twilio_sid'] and sid != call['twilio_sid']:
        raise HTTPException(403, 'Twilio Call SID mismatch')
    db.execute('UPDATE calls SET twilio_sid=COALESCE(twilio_sid,?),status=? WHERE id=?',
               (sid, 'ringing', call_id))
    return Response(twiml_for_call(call_id), media_type='application/xml')


@app.post('/twilio/status', include_in_schema=False)
async def twilio_status(request: Request):
    values = await require_twilio_http(request)
    sid, status = values.get('CallSid'), values.get('CallStatus')
    if not sid or not status:
        return Response(status_code=204)
    call = db.one('SELECT * FROM calls WHERE twilio_sid=?', (sid,))
    if call:
        allowed = {'queued', 'initiated', 'ringing', 'in-progress', 'completed', 'failed', 'busy', 'no-answer', 'canceled'}
        if status in allowed:
            # Avoid moving finished calls back into a nonterminal state from delayed events.
            terminal = {'completed','failed','busy','no-answer','canceled'}
            if call['status'] not in terminal:
                db.execute('UPDATE calls SET status=?,ended_at=CASE WHEN ? THEN ? ELSE ended_at END WHERE id=?',
                           (status, int(status in terminal), db.now(), call['id']))
                db.add_event(call['id'], 'state', 'Twilio call status: ' + status)
    return Response(status_code=204)


@app.websocket('/twilio/media')
async def twilio_media(ws: WebSocket):
    s = get_settings()
    if s.demo_mode or not allow_twilio_websocket(ws):
        await ws.close(code=1008)
        return
    await ws.accept()
    call_id = None
    try:
        # Receive connected + start before routing to a call session.
        connected = await asyncio.wait_for(ws.receive_json(), timeout=10)
        started = await asyncio.wait_for(ws.receive_json(), timeout=10)
        if connected.get('event') != 'connected' or started.get('event') != 'start':
            await ws.close(code=1008)
            return
        meta = started['start']
        call_id = (meta.get('customParameters') or {}).get('call_id')
        sid = meta.get('callSid')
        call = db.one('SELECT * FROM calls WHERE id=?', (call_id,)) if call_id else None
        if not call or call['mode'] != 'live' or not call['twilio_sid'] or sid != call['twilio_sid']:
            await ws.close(code=1008)
            return
        agent = db.one('SELECT * FROM agents WHERE id=?', (call['agent_id'],))
        plan = db.get_plan(call['plan_id']) if call['plan_id'] else None
        engine = call.get('voice_engine') or 'deepgram'
        if not s.ready_for_calls(engine):
            db.add_event(call_id, 'error', 'Selected voice engine unavailable')
            await ws.close(code=1011)
            return
        session_class = LiveVoiceSession if engine == 'openai_live' else VoiceSession
        session = session_class(ws, call, agent, plan)
        db.add_event(call_id, 'state', f'Voice runtime starting: {engine}')
        try:
            await asyncio.wait_for(session.run(started), timeout=s.max_call_seconds)
        except asyncio.TimeoutError:
            db.add_event(call_id, 'state', 'Maximum call duration reached')
            await asyncio.to_thread(lambda: client().calls(sid).update(status='completed'))
        except Exception as exc:
            log.exception('Audio runtime failed call_id=%s', call_id)
            detail = str(exc) if isinstance(exc, LiveProviderError) else type(exc).__name__
            db.add_event(call_id, 'error', f'Voice runtime error: {detail}')
            db.execute('UPDATE calls SET status=?,error=? WHERE id=?',
                       ('failed', detail, call_id))
        finally:
            current = db.one('SELECT status FROM calls WHERE id=?', (call_id,))
            if current and current['status'] not in ('completed','failed','busy','no-answer','canceled'):
                db.execute('UPDATE calls SET status=?,ended_at=? WHERE id=?', ('completed', db.now(), call_id))
            db.add_event(call_id, 'state', 'Media stream ended')
    except Exception:
        log.exception('Twilio WebSocket handshake error, call=%s', call_id)
        if call_id:
            db.add_event(call_id, 'error', 'Media stream handshake failed')
        try:
            await ws.close(code=1011)
        except Exception:
            pass
