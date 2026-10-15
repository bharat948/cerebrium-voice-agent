"""Local voice runtime: Twilio 8k μ-law <-> Deepgram Nova streaming <-> OpenAI <-> Deepgram Aura.

This deliberately avoids Pipecat version coupling and retains the same clean provider boundaries.
No recording is stored. Text transcript events are persisted.
"""
import asyncio
import base64
import json
import logging
import re
from urllib.parse import urlencode

import httpx
import websockets
from fastapi import WebSocket, WebSocketDisconnect
from app import db
from app.config import get_settings
from app.prompts import call_system_prompt

log = logging.getLogger(__name__)
SENTENCE_BREAK = re.compile(r'(?<=[.!?])\s+')


class VoiceSession:
    def __init__(self, websocket: WebSocket, call: dict, agent: dict, plan: dict | None):
        self.ws = websocket
        self.call = call
        self.agent = agent
        self.plan = plan
        self.s = get_settings()
        self.stream_sid = ''
        self.deepgram = None
        self.send_lock = asyncio.Lock()
        self.user_parts: list[str] = []
        self.history: list[dict] = []
        self.reply_task: asyncio.Task | None = None
        self.generation = 0
        self.closed = False
        self.playback_pending = False
        self.stop_requested = asyncio.Event()

    async def twilio_send(self, obj: dict):
        async with self.send_lock:
            await self.ws.send_json(obj)

    async def barge_in(self):
        # Cancel model/TTS even when Twilio already buffered audio after generation ended.
        active = self.reply_task and not self.reply_task.done()
        if active or self.playback_pending:
            self.generation += 1
            if active:
                self.reply_task.cancel()
                await asyncio.gather(self.reply_task, return_exceptions=True)
            if self.stream_sid:
                try:
                    await self.twilio_send({'event': 'clear', 'streamSid': self.stream_sid})
                except Exception:
                    pass  # Twilio may have hung up while we were canceling.
            self.playback_pending = False
            db.add_event(self.call['id'], 'interruption', 'Caller interrupted buffered agent audio')
        self.reply_task = None

    async def send_audio(self, sentence: str, generation: int):
        """Stream headerless μ-law in 100ms chunks directly into Twilio's jitter buffer."""
        url = 'https://api.deepgram.com/v1/speak'
        params = {'model': self.s.deepgram_tts_model, 'encoding': 'mulaw',
                  'sample_rate': '8000', 'container': 'none'}
        pending = b''
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, read=35.0)) as client:
            async with client.stream('POST', url, params=params,
                                     headers={'Authorization': f'Token {self.s.deepgram_api_key}'},
                                     json={'text': sentence}) as response:
                response.raise_for_status()
                async for data in response.aiter_bytes():
                    if generation != self.generation:
                        return
                    pending += data
                    while len(pending) >= 800:  # 100ms x 8kHz, 8-bit μ-law
                        chunk, pending = pending[:800], pending[800:]
                        self.playback_pending = True
                        await self.twilio_send({
                            'event': 'media', 'streamSid': self.stream_sid,
                            'media': {'payload': base64.b64encode(chunk).decode('ascii')}
                        })
                if pending and generation == self.generation:
                    self.playback_pending = True
                    await self.twilio_send({
                        'event': 'media', 'streamSid': self.stream_sid,
                        'media': {'payload': base64.b64encode(pending).decode('ascii')}
                    })

    async def respond(self, user_text: str | None = None):
        generation = self.generation
        try:
            if user_text:
                self.history.append({'role': 'user', 'content': user_text})
                db.add_event(self.call['id'], 'transcript', user_text, 'caller')
                if len(self.history) > 22:
                    self.history = self.history[-20:]
            messages = [{'role': 'system', 'content': call_system_prompt(self.agent, self.plan)}]
            if not self.history:
                messages.append({'role': 'user', 'content': 'The call has connected. Introduce yourself and begin.'})
            messages += self.history
            text = ''
            buffer = ''
            async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, read=40.0)) as http:
                async with http.stream('POST', 'https://api.openai.com/v1/chat/completions',
                                       headers={'Authorization': 'Bearer ' + self.s.openai_api_key},
                                       json={'model': self.s.openai_model, 'messages': messages,
                                             'stream': True, 'max_tokens': self.s.openai_max_output_tokens,
                                             'temperature': 0.4}) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if generation != self.generation:
                            return
                        if not line.startswith('data: '):
                            continue
                        data = line[6:].strip()
                        if data == '[DONE]':
                            break
                        delta_obj = json.loads(data)
                        choices = delta_obj.get('choices') or []
                        delta = (choices[0].get('delta', {}).get('content') or '') if choices else ''
                        text += delta
                        buffer += delta
                        # Speech starts at the first sentence rather than waiting for full response.
                        split = SENTENCE_BREAK.split(buffer)
                        if len(split) > 1:
                            for sentence in split[:-1]:
                                sentence = sentence.strip()
                                if sentence:
                                    await self.send_audio(sentence, generation)
                            buffer = split[-1]
                        elif len(buffer) >= 150 and buffer.endswith((' ', ',', ';')):
                            await self.send_audio(buffer.strip(), generation)
                            buffer = ''
            if buffer.strip() and generation == self.generation:
                await self.send_audio(buffer.strip(), generation)
            if text.strip() and generation == self.generation:
                self.history.append({'role': 'assistant', 'content': text.strip()})
                db.add_event(self.call['id'], 'transcript', text.strip(), 'assistant')
                await self.twilio_send({'event': 'mark', 'streamSid': self.stream_sid,
                                        'mark': {'name': f'reply-{generation}'}})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception('Voice response failed, call_id=%s', self.call['id'])
            db.add_event(self.call['id'], 'error', f'Response failed: {type(exc).__name__}')

    async def listen_deepgram(self):
        """Nova streaming transcript finalization. Interim content triggers interruption."""
        try:
            async for raw in self.deepgram:
                payload = json.loads(raw)
                if payload.get('type') == 'UtteranceEnd' and self.user_parts:
                    utterance = ' '.join(self.user_parts).strip()
                    self.user_parts.clear()
                    if utterance:
                        self.reply_task = asyncio.create_task(self.respond(utterance))
                    continue
                if payload.get('type') != 'Results':
                    continue
                alt = (payload.get('channel', {}).get('alternatives') or [{}])[0]
                transcript = (alt.get('transcript') or '').strip()
                if not transcript:
                    continue
                if (self.reply_task and not self.reply_task.done()) or self.playback_pending:
                    await self.barge_in()
                if payload.get('is_final'):
                    self.user_parts.append(transcript)
                if payload.get('speech_final'):
                    utterance = ' '.join(self.user_parts).strip()
                    self.user_parts.clear()
                    if utterance:
                        # Start reply in background; STT read stays responsive to barge-in.
                        self.reply_task = asyncio.create_task(self.respond(utterance))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception('Deepgram receive error, call=%s', self.call['id'])
            db.add_event(self.call['id'], 'error', f'STT disconnected: {type(exc).__name__}')
            self.stop_requested.set()

    async def run(self, start_message: dict):
        s = self.s
        ws_params = urlencode({
            'model': s.deepgram_stt_model, 'encoding': 'mulaw', 'sample_rate': 8000,
            'channels': 1, 'interim_results': 'true', 'endpointing': 350,
            'smart_format': 'true', 'punctuate': 'true'
        })
        dg_url = 'wss://api.deepgram.com/v1/listen?' + ws_params
        try:
            async with websockets.connect(dg_url, additional_headers={
                'Authorization': f'Token {s.deepgram_api_key}'}, ping_interval=20,
                max_size=2 ** 20, open_timeout=12) as dg:
                self.deepgram = dg
                stt_reader = asyncio.create_task(self.listen_deepgram())
                try:
                    # Start is authenticated by the WebSocket handler before this pipeline runs.
                    initial = start_message
                    while not self.stop_requested.is_set():
                        try:
                            if initial is not None:
                                msg, initial = initial, None
                            else:
                                msg = json.loads(await asyncio.wait_for(self.ws.receive_text(), timeout=10))
                        except asyncio.TimeoutError:
                            continue
                        except WebSocketDisconnect:
                            break
                        event = msg.get('event')
                        if event == 'start':
                            self.stream_sid = msg['start']['streamSid']
                            db.execute('UPDATE calls SET status=?,started_at=COALESCE(started_at,?) WHERE id=?',
                                       ('in-progress', db.now(), self.call['id']))
                            db.add_event(self.call['id'], 'state', 'Connected to real-time audio stream')
                            self.reply_task = asyncio.create_task(self.respond())
                        elif event == 'media' and self.stream_sid:
                            if msg.get('streamSid') != self.stream_sid:
                                break
                            media = msg.get('media', {}).get('payload', '')
                            if media:
                                await dg.send(base64.b64decode(media))
                        elif event == 'mark':
                            self.playback_pending = False
                        elif event == 'stop':
                            break
                finally:
                    stt_reader.cancel()
                    await asyncio.gather(stt_reader, return_exceptions=True)
                    await self.barge_in()
                    try:
                        await dg.send(json.dumps({'type': 'CloseStream'}))
                    except Exception:
                        pass
        except asyncio.CancelledError:
            raise
        finally:
            self.closed = True
