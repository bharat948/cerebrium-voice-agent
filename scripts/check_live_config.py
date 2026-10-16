#!/usr/bin/env python3
"""Check GPT-Live startup and delayed backend validation without dialing Twilio.

Creates a short, billable OpenAI Live session. No custom tools are executed.
Run from the repository root: python scripts/check_live_config.py --agent-id receptionist
"""
import argparse
import asyncio
import base64
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import websockets
from app import db
from app.config import get_settings
from app.live_diagnostics import LiveProviderError, LiveSessionDiagnostics, wait_for_live_start
from app.live_voice import OPENAI_LIVE_URL, session_start
from app.v3 import registry


async def check(agent_id: str, wait_seconds: float) -> int:
    settings = get_settings()
    if not settings.openai_api_key:
        print('FAIL: OPENAI_API_KEY is not configured.')
        return 1
    agent = db.one('SELECT * FROM agents WHERE id=?', (agent_id,))
    if not agent:
        print('FAIL: Agent does not exist. Use an agent ID from the dashboard.')
        return 1
    config = registry.get_config(agent_id) or {}
    start = session_start(agent, None, settings.openai_live_model,
                          config.get('voice', settings.openai_live_voice),
                          settings.openai_live_backend_model, enable_tools=True)
    # Validate the selected agent's tool schemas without transmitting call history
    # or asking the model to perform any task. Contact-only tools are not tested.
    start['session']['instructions'] = (
        'This is an application configuration check. Remain silent. '
        'Do not delegate, use tools, or take actions.'
    )
    start['session']['input'] = []
    backend = start['session']['delegation']['responses']
    print('Voice model:', settings.openai_live_model)
    print('Backend model:', settings.openai_live_backend_model)
    print('Advertised tools:', ', '.join(t['name'] for t in backend['tools']) or '(none)')
    errors = []
    live_started = False
    finalized = False

    async with websockets.connect(
        OPENAI_LIVE_URL, additional_headers={'Authorization': 'Bearer ' + settings.openai_api_key},
        open_timeout=12, ping_interval=20, ping_timeout=20, max_size=2**22,
    ) as live:
        async def send(event):
            await live.send(json.dumps(event))

        def record(kind, detail):
            if kind == 'error':
                errors.append(detail)
                print('FAIL:', detail)

        # Deliberately test the configured primary model, with fallback disabled.
        diagnostics = LiveSessionDiagnostics(send, backend_model=settings.openai_live_backend_model,
                                             api_key=settings.openai_api_key, record=record)
        silence_task = None
        try:
            await send(start)
            await wait_for_live_start(live, diagnostics)
            live_started = True

            async def silence():
                audio = base64.b64encode(b'\xff' * 160).decode('ascii')
                while True:
                    await send({'type': 'session.input_audio.append', 'audio': audio})
                    await asyncio.sleep(.02)

            silence_task = asyncio.create_task(silence())
            deadline = time.monotonic() + wait_seconds
            while not errors and time.monotonic() < deadline:
                try:
                    event = json.loads(await asyncio.wait_for(live.recv(), deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    break
                await diagnostics.observe(event)
                if event.get('type') == 'session.closed':
                    finalized = True
                    errors.append('Session closed during the configuration check')
                    break
        finally:
            if silence_task:
                silence_task.cancel()
                await asyncio.gather(silence_task, return_exceptions=True)
            if live_started and not finalized:
                await send({'type': 'session.close'})
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    try:
                        event = json.loads(await asyncio.wait_for(live.recv(), deadline - time.monotonic()))
                    except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                        break
                    await diagnostics.observe(event)
                    if event.get('type') == 'session.closed':
                        finalized = True
                        break
    if errors:
        print('Fix the reported model, resource access or tool setting and run this check again.')
        return 1
    print(f'No provider configuration errors observed during {wait_seconds:g} seconds.')
    print('This is a short startup check; it does not verify tool execution or phone-call behavior.')
    if not finalized:
        print('Final usage acknowledgment was not received; check OpenAI usage separately.')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent-id', default='receptionist')
    parser.add_argument('--wait-seconds', type=float, default=3,
                        help='Observe delayed validation for 1 to 30 seconds (default: 3)')
    args = parser.parse_args()
    if not 1 <= args.wait_seconds <= 30:
        parser.error('--wait-seconds must be between 1 and 30')
    logging.basicConfig(level=logging.WARNING)
    try:
        return asyncio.run(check(args.agent_id, args.wait_seconds))
    except LiveProviderError as exc:
        print('FAIL:', str(exc))
        return 1
    except Exception as exc:
        # Connection/DB exception text can include credentials; disclose its type only.
        print('FAIL:', type(exc).__name__, 'Check database connectivity, network and API credentials.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
