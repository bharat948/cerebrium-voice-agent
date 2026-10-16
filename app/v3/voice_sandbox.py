"""Owner-only browser microphone preview using GPT-Live PCMU frames.

Test sessions never create production calls, memories or external tool actions.
They use one-time, short-lived signed preview tokens, no permanent storage.
"""
import asyncio
import json
import logging
from urllib.parse import urlsplit
import websockets
from fastapi import APIRouter,WebSocket,WebSocketDisconnect,HTTPException,Depends
from itsdangerous import URLSafeTimedSerializer,BadSignature,SignatureExpired
from app.config import get_settings
from app.security import require_api_key
from app import db
from app.live_voice import OPENAI_LIVE_URL, session_start
from app.v3 import registry
log=logging.getLogger(__name__)
router=APIRouter(prefix='/api/v3/voice',tags=['Voice Sandbox'])

def _signer():
    return URLSafeTimedSerializer(get_settings().session_secret or get_settings().app_api_key,salt='voice-preview-v1')

@router.post('/preview-token',dependencies=[Depends(require_api_key)])
async def preview_token(payload:dict):
    agent_id=str(payload.get('agent_id',''))
    if not db.one('SELECT id FROM agents WHERE id=?',(agent_id,)):raise HTTPException(404,'Unknown agent')
    return {'token':_signer().dumps({'agent_id':agent_id}), 'expires_in_seconds':60}

@router.websocket('/preview')
async def browser_preview(ws:WebSocket):
    # Token bound to specific agent and issued after authenticated owner API request.
    try:
        claims=_signer().loads(ws.query_params.get('token',''),max_age=60)
        agent_id=claims['agent_id']
        agent=db.one('SELECT * FROM agents WHERE id=?',(agent_id,))
        if not agent:raise ValueError('Unknown agent')
        s=get_settings()
        origin=ws.headers.get('origin','')
        # Protect against cross-site WebSocket hijacking.
        if s.base_url and origin and urlsplit(origin).netloc!=urlsplit(s.base_url).netloc:
            raise ValueError('Unexpected WebSocket origin')
    except (BadSignature,SignatureExpired,KeyError,ValueError):
        await ws.close(code=1008);return
    await ws.accept()
    if s.demo_mode:
        await ws.send_json({'type':'info','detail':'Demo voice preview: no audio provider is contacted'})
        try:
            while True:
                payload=await ws.receive_json()
                if payload.get('type')=='stop':break
        except WebSocketDisconnect:pass
        return
    if not s.openai_api_key:
        await ws.send_json({'type':'error','detail':'OPENAI_API_KEY unavailable'});await ws.close(code=1011);return
    started=session_start(agent,None,s.openai_live_model,
                          (registry.get_config(agent_id) or {}).get('voice',s.openai_live_voice),
                          s.openai_live_backend_model)
    # Browser sandbox cannot call tools and never persist personal information.
    started['session']['instructions']+='\nSANDBOX: Never call real tools or save private facts; this session is a temporary test.'
    try:
        async with websockets.connect(OPENAI_LIVE_URL,
            additional_headers={'Authorization':'Bearer '+s.openai_api_key},
            open_timeout=15,ping_interval=20,max_size=2**22) as live:
            await live.send(json.dumps(started))
            response=json.loads(await asyncio.wait_for(live.recv(),timeout=15))
            if response.get('type')!='session.started':
                raise RuntimeError('Live session start failed')
            await ws.send_json({'type':'ready','format':'pcmu','sample_rate':8000})
            async def incoming():
                while True:
                    event=await ws.receive_json()
                    if event.get('type')=='audio':
                        chunk=event.get('audio','')
                        if isinstance(chunk,str) and len(chunk)<=24000:
                            await live.send(json.dumps({'type':'session.input_audio.append','audio':chunk}))
                    if event.get('type')=='stop':
                        await live.send(json.dumps({'type':'session.close'}));return
            async def outgoing():
                async for event in live:
                    data=json.loads(event)
                    typ=data.get('type')
                    if typ=='session.output_audio.delta':
                        await ws.send_json({'type':'audio','audio':data.get('delta','')})
                    elif typ in ('session.input_transcript.delta','session.output_transcript.delta'):
                        await ws.send_json({'type':'caption','speaker':'caller' if 'input_' in typ else 'assistant',
                                            'delta':data.get('delta','')})
                    elif typ=='session.closed':return
            tasks=[asyncio.create_task(incoming()),asyncio.create_task(outgoing())]
            done,pending=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            for t in pending:t.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
    except (WebSocketDisconnect,asyncio.CancelledError):pass
    except Exception as exc:
        log.warning('Voice sandbox failure %s',type(exc).__name__)
        try:await ws.send_json({'type':'error','detail':'Voice provider unavailable'})
        except Exception:pass
    finally:
        try:await ws.close()
        except Exception:pass
