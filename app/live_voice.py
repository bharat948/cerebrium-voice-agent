"""GPT-Live-1 primary WebSocket <-> Twilio bidirectional Media Streams.

OpenAI LIVE is distinct from the older Realtime API:
  wss://api.openai.com/v1/live/sessions
  session.start -> session.started
  session.input_audio.append / session.output_audio.delta
Audio is headerless 8kHz G.711 µ-law in both directions. No conversion, STT or TTS hop.

The Twilio bridge sends short audio frames and marks to track buffered playback. During
caller barge-in a lightweight configurable energy gate clears Twilio's playback queue;
GPT-Live independently handles conversational interruptions on its own side.
"""
import asyncio
import base64
import json
import logging
import math
import time
import uuid

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from app import db
from app.config import get_settings
from app.prompts import call_system_prompt
from app.v3 import registry, memory, intelligent_memory, voice_behavior, live_functions

log = logging.getLogger(__name__)
OPENAI_LIVE_URL = 'wss://api.openai.com/v1/live/sessions'


def _pcm_from_ulaw_byte(v: int) -> int:
    v = ~v & 0xff
    magnitude = (((v & 15) << 3) + 132) << ((v >> 4) & 7)
    sample = magnitude - 132
    return -sample if v & 128 else sample


PCM_ULAW = tuple(_pcm_from_ulaw_byte(i) for i in range(256))


def ulaw_rms(data: bytes) -> float:
    """RMS of headerless 8-bit µ-law audio. Used only for Twilio buffer clearing."""
    if not data:
        return 0.0
    return math.sqrt(sum(PCM_ULAW[b] ** 2 for b in data) / len(data))


def session_start(agent: dict, plan: dict | None, model: str, voice: str, backend_model: str = "gpt-4o-mini", contact=None, memories=(), release_id=None, enable_tools=False) -> dict:
    opening = ((plan or {}).get('script') or 'Hello, this is your AI assistant.').strip()
    language = agent.get('language') or 'English'
    pinned=db.one('SELECT configuration FROM agent_releases WHERE id=? AND agent_id=?',(release_id,agent['id'])) if release_id and agent.get('id') else None
    configuration=json.loads(pinned['configuration']) if pinned else (registry.get_config(agent['id']) if agent.get('id') else {})
    advertised=live_functions.definitions(configuration or {},bool(contact)) if enable_tools else []
    return {
        'type': 'session.start',
        'event_id': 'start_' + uuid.uuid4().hex,
        'session': {
            'model': model,
            'instructions': registry.compile_prompt(agent, plan, contact, memories, release_id) + '\n'
                'Backchannel policy: Use short acknowledgments only when useful. '
                'Interruption policy: When the caller interrupts, stop your sentence and listen. '
                'Delegation policy: Only advertised, backend-authorized tools are available. '
                'Never claim a booking or fact was verified without an actual tool result.',
            'input': [{
                'type': 'message', 'role': 'developer',
                'content': [{'type': 'input_text',
                             'text': f'At the start of this telephone call greet first in {language}. '
                                     'Clearly identify yourself as AI, explain the purpose of the call, '
                                     f'and use this approved opening where natural: {opening}. '
                                     'Then pause and listen. Do not wait for caller speech.'}]
            }],
            'audio': {'format': {'type': 'audio/pcmu', 'rate': 8000},
                      'output': {'voice': voice}},
            # Managed backend reasoning. No business tools or external actions are advertised.
            'delegation': {
                'type': 'responses',
                'responses': {
                    'model': backend_model,
                    'instructions': (
                        'Support the spoken AI assistant with brief factual reasoning. '
                        'Use only the supplied conversation and call plan. Do not invent facts, '
                        'appointments, bookings or tool results. Return concise natural-language answers.'
                    ),
                    'tool_choice': 'auto' if advertised else 'none',
                    'tools': advertised,
                },
            },
            'store': False,
        }
    }


class LiveVoiceSession:
    def __init__(self, websocket: WebSocket, call: dict, agent: dict, plan: dict | None):
        self.ws = websocket
        self.call = call
        self.agent = agent
        self.plan = plan
        release=call.get('agent_release_id')
        agent_id=agent.get('id') or call.get('agent_id','')
        snapshot=db.one('SELECT configuration FROM agent_releases WHERE id=? AND agent_id=?',(release,agent_id)) if release else None
        self.session_config=json.loads(snapshot['configuration']) if snapshot else (registry.get_config(agent_id) or {})
        contact = db.one('SELECT * FROM contacts WHERE phone=?',(call['phone'],))
        self.contact = contact if contact and contact.get('active') else None
        self.memories = intelligent_memory.ranked(agent['id'],self.contact['id'],plan['goal'] if plan else '',limit=6) if self.contact else []
        self.s = get_settings()
        self.behavior = voice_behavior.policies(self.session_config.get('behavior_policy',{}))
        self.stream_sid = ''
        self.twilio_lock = asyncio.Lock()
        self.live = None
        self.pending_marks: set[str] = set()
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
        self.audio_task: asyncio.Task | None = None
        self.stopped = asyncio.Event()
        self.finalized = False
        self.transcript = {'caller': '', 'assistant': ''}
        self.transcript_updated = {'caller': 0., 'assistant': 0.}
        self.last_clear = 0.
        self.speech_frames = 0
        self.barge_active = False
        self.output_muted_until = 0.
        self.frames_sent = 0
        self.live_ready_at = 0.0
        self.first_output_recorded = False
        self.send_live_lock = asyncio.Lock()
        self.delegation_calls = {}
        self.delegation_tasks = set()
        self.runtime_poll_at = 0.
        self.runtime_control = {}
        self.tool_calls_count = 0

    async def live_send(self,payload:dict):
        async with self.send_live_lock:
            await self.live.send(json.dumps(payload))

    async def execute_delegated_calls(self, calls):
        """Respond to every completed function call, then resume Responses once."""
        current=registry.get_config(self.agent['id']) or {}
        configuration=dict(self.session_config)
        # Security revocations take effect immediately, even if a call pins a release.
        configuration['tools']=list(set(configuration.get('tools',[])) & set(current.get('tools',[])))
        for item in calls:
            if self.tool_calls_count>=15:
                result={'status':'denied','reason':'Per-call tool limit reached'}
            else:
                self.tool_calls_count+=1
                result=await live_functions.run(self.agent['id'],self.contact,item['name'],item['arguments'],configuration)
            db.add_event(self.call['id'],'tool',json.dumps({'tool':item['name'],'status':result.get('status')})[:900])
            await self.live_send({'type':'response.item.create','event_id':'tool_'+uuid.uuid4().hex,
                'item':{'type':'function_call_output','call_id':item['call_id'],
                        'output':json.dumps(result,ensure_ascii=False)[:6000]}})
        await self.live_send({'type':'response.create','event_id':'continue_'+uuid.uuid4().hex})

    async def refresh_runtime_controls(self):
        # Poll no more often than once per second, avoiding DB queries per audio frame.
        if time.monotonic()-self.runtime_poll_at < 1.0:return
        self.runtime_poll_at=time.monotonic()
        self.runtime_control=db.one('SELECT * FROM runtime_controls WHERE call_id=?',(self.call['id'],)) or {}
        if self.runtime_control.get('stop_requested'):
            self.stopped.set()
        instruction=self.runtime_control.get('pending_instruction')
        if instruction:
            await self.live_send({'type':'session.instructions.append','event_id':'owner_'+uuid.uuid4().hex,
                                  'delegation_id':None,'content':instruction[:1500]})
            db.execute('UPDATE runtime_controls SET pending_instruction=NULL WHERE call_id=? AND pending_instruction=?',
                       (self.call['id'],instruction))
            db.add_event(self.call['id'],'intervention','Owner instruction sent to Live session')

    async def twilio_send(self, payload: dict):
        async with self.twilio_lock:
            await self.ws.send_json(payload)

    def flush_transcript(self, speaker: str):
        message = self.transcript[speaker].strip()
        if message:
            db.add_event(self.call['id'], 'transcript', message[:3000], speaker)
            self.transcript[speaker] = ''

    def accept_transcript(self, event: dict, speaker: str):
        delta = event.get('delta')
        if not isinstance(delta, str) or not delta:
            return
        # GPT-Live transcript deltas are approximate captions without a done event.
        self.transcript[speaker] += delta
        self.transcript_updated[speaker] = time.monotonic()
        if len(self.transcript[speaker]) >= 2400:
            self.flush_transcript(speaker)

    async def clear_twilio(self):
        if not self.stream_sid or not self.pending_marks:
            return
        self.pending_marks.clear()
        await self.twilio_send({'event': 'clear', 'streamSid': self.stream_sid})
        # Discard audio already queued for playback. The live model handles interruption.
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
            except asyncio.QueueEmpty:
                break
        self.output_muted_until = time.monotonic() + .25
        self.last_clear = time.monotonic()
        db.add_event(self.call['id'], 'interruption', 'Caller interrupted outgoing speech; cleared Twilio buffer')

    async def maybe_barge_in(self, mulaw: bytes):
        if self.s.live_barge_in_rms <= 0 or not self.pending_marks:
            self.speech_frames = 0
            return
        # Calibrated speech energy gate, not a full VAD. Off by setting RMS=0.
        if ulaw_rms(mulaw) >= self.s.live_barge_in_rms:
            self.speech_frames += max(1, len(mulaw) // 160)
            if (self.speech_frames >= max(1, min(self.s.live_barge_in_frames, self.behavior['barge_in_frames']))
                    and time.monotonic() - self.last_clear > self.behavior['barge_cooldown_seconds']):
                await self.clear_twilio()
                self.speech_frames = 0
        else:
            self.speech_frames = 0

    async def send_audio_loop(self):
        """20–40ms packets limit Twilio buffering. Tracks playback using mark acknowledgements."""
        try:
            while not self.stopped.is_set():
                chunk = await self.audio_queue.get()
                try:
                    await self.refresh_runtime_controls()
                    if self.runtime_control.get('paused') or time.monotonic() < self.output_muted_until:
                        continue
                    # Twilio accepts arbitrary headerless µ-law payload sizes. 40ms max.
                    for pos in range(0, len(chunk), 320):
                        frame = chunk[pos:pos+320]
                        if not frame or self.stopped.is_set():
                            break
                        await self.twilio_send({
                            'event': 'media', 'streamSid': self.stream_sid,
                            'media': {'payload': base64.b64encode(frame).decode('ascii')}
                        })
                        self.frames_sent += 1
                        # Marks allow us to estimate playback pending; each one is unique.
                        marker = 'live-' + uuid.uuid4().hex[:12]
                        self.pending_marks.add(marker)
                        await self.twilio_send({
                            'event': 'mark', 'streamSid': self.stream_sid,
                            'mark': {'name': marker}
                        })
                        # Pace output to prevent the provider from building a long audio backlog.
                        await asyncio.sleep(len(frame) / 8000)
                finally:
                    self.audio_queue.task_done()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Twilio output failed, call=%s', self.call['id'])
            self.stopped.set()

    async def forward_twilio_audio(self, start_message: dict):
        try:
            next_message = start_message
            while not self.stopped.is_set():
                if next_message is not None:
                    msg, next_message = next_message, None
                else:
                    try:
                        msg = json.loads(await asyncio.wait_for(self.ws.receive_text(), timeout=10))
                    except asyncio.TimeoutError:
                        continue
                kind = msg.get('event')
                if kind == 'start':
                    if msg.get('start', {}).get('streamSid') != self.stream_sid:
                        raise ValueError('Twilio Stream SID changed')
                elif kind == 'media':
                    if msg.get('streamSid') != self.stream_sid:
                        raise ValueError('Unexpected stream SID')
                    encoded = msg.get('media', {}).get('payload', '')
                    if encoded:
                        decoded = base64.b64decode(encoded, validate=True)
                        await self.maybe_barge_in(decoded)
                        await self.live.send(json.dumps({'type':'session.input_audio.append','audio':encoded}))
                elif kind == 'mark':
                    if msg.get('streamSid') == self.stream_sid:
                        self.pending_marks.discard(msg.get('mark', {}).get('name'))
                elif kind == 'stop':
                    break
        except WebSocketDisconnect:
            pass
        finally:
            self.stopped.set()

    async def forward_live_events(self):
        try:
            async for raw in self.live:
                event = json.loads(raw)
                await self.refresh_runtime_controls()
                function=live_functions.completed_function_call(event)
                if function:
                    grouping=function['response_id'] or function['delegation_id'] or 'default'
                    self.delegation_calls.setdefault(grouping,[]).append(function)
                nested=event.get('event') if event.get('type')=='response.event' else None
                if nested and nested.get('type')=='response.completed':
                    grouping=(nested.get('response') or {}).get('id') or event.get('delegation_id') or 'default'
                    batch=self.delegation_calls.pop(grouping,[])
                    if not batch and event.get('delegation_id'):
                        batch=self.delegation_calls.pop(event['delegation_id'],[])
                    if batch:
                        task=asyncio.create_task(self.execute_delegated_calls(batch))
                        self.delegation_tasks.add(task)
                        task.add_done_callback(self.delegation_tasks.discard)
                kind = event.get('type')
                if kind == 'session.output_audio.delta':
                    if not self.first_output_recorded:
                        self.first_output_recorded = True
                        if self.live_ready_at:
                            elapsed = round((time.monotonic()-self.live_ready_at)*1000)
                            db.add_event(self.call['id'], 'metric',
                                         f'First output audio after Live readiness: {elapsed} ms (startup only, not turn latency)')
                    if self.stopped.is_set():
                        break
                    if self.runtime_control.get('paused'):continue
                    encoded = event.get('delta', '')
                    if encoded and time.monotonic() >= self.output_muted_until:
                        frame = base64.b64decode(encoded, validate=True)
                        # Block reader if buffer grows beyond 8 seconds; fail rather than drop words.
                        await asyncio.wait_for(self.audio_queue.put(frame), timeout=5)
                elif kind == 'session.input_transcript.delta':
                    self.accept_transcript(event, 'caller')
                elif kind == 'session.output_transcript.delta':
                    self.accept_transcript(event, 'assistant')
                elif kind == 'session.closed':
                    self.finalized = True
                    usage = event.get('usage') or {}
                    db.add_event(self.call['id'], 'usage', json.dumps(usage)[:2000])
                    break
                elif kind == 'error':
                    err = event.get('error') or {}
                    code = err.get('code', 'unknown') if isinstance(err, dict) else 'unknown'
                    log.warning('GPT-Live runtime error call=%s code=%s', self.call['id'], code)
                    db.add_event(self.call['id'], 'error', 'GPT-Live event: ' + str(code)[:100])
                    # Live may continue after a rejected command. Fatal errors close the socket.
        except asyncio.CancelledError:
            raise
        finally:
            self.stopped.set()

    async def run(self, start_message: dict):
        self.stream_sid = start_message.get('start', {}).get('streamSid', '')
        if not self.stream_sid:
            raise ValueError('Missing Twilio streamSid')
        db.execute('UPDATE calls SET status=?,started_at=COALESCE(started_at,?) WHERE id=?',
                   ('in-progress', db.now(), self.call['id']))
        start = session_start(self.agent, self.plan, self.s.openai_live_model,
                              self.session_config.get('voice',self.s.openai_live_voice),
                              self.s.openai_live_backend_model, self.contact, self.memories, self.call.get('agent_release_id'),enable_tools=True)
        try:
            async with websockets.connect(
                OPENAI_LIVE_URL,
                additional_headers={'Authorization': f'Bearer {self.s.openai_api_key}'},
                open_timeout=12, ping_interval=20, ping_timeout=20, max_size=2**22,
            ) as live:
                self.live = live
                await self.live_send(start)
                # LIVE protocol requires session.started before we send the first audio frame.
                while True:
                    received = json.loads(await asyncio.wait_for(live.recv(), timeout=15))
                    if received.get('type') == 'session.started':
                        self.live_ready_at = time.monotonic()
                        db.add_event(self.call['id'], 'state', 'GPT-Live session started: ' +
                                     str((received.get('session') or {}).get('id',''))[:90])
                        break
                    if received.get('type') == 'error':
                        raise RuntimeError('GPT-Live rejected session.start: ' +
                                           str((received.get('error') or {}).get('code', 'unknown')))
                input_task = asyncio.create_task(self.forward_twilio_audio(start_message))
                output_task = asyncio.create_task(self.forward_live_events())
                self.audio_task = asyncio.create_task(self.send_audio_loop())
                try:
                    finished, _ = await asyncio.wait(
                        [input_task, output_task, self.audio_task], return_when=asyncio.FIRST_COMPLETED)
                    for task in finished:
                        exc = task.exception()
                        if exc:
                            raise exc
                finally:
                    self.stopped.set()
                    for task in (input_task, self.audio_task):
                        task.cancel()
                    await asyncio.gather(input_task, self.audio_task, return_exceptions=True)
                    if not output_task.done():
                        try:
                            await live.send(json.dumps({'type':'session.close'}))
                            # Capture session.closed to account for voice usage.
                            await asyncio.wait_for(output_task, timeout=5)
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                            output_task.cancel()
                    await asyncio.gather(output_task, return_exceptions=True)
                    for task in self.delegation_tasks:task.cancel()
                    await asyncio.gather(*self.delegation_tasks,return_exceptions=True)
        finally:
            self.flush_transcript('caller')
            self.flush_transcript('assistant')
            if not self.finalized:
                db.add_event(self.call['id'], 'state', 'GPT-Live session ended without confirmed final usage')
