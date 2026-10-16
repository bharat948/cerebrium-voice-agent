"""Recoverable GPT-Live backend errors, shared by phone and browser sessions.

Responses configuration is validated asynchronously. A validation error does
not reject the voice session, and session.updated is not a validation success.
Never log a session payload: it contains instructions and caller context.
"""
import asyncio
import json
import logging
import re
import time
import uuid

log = logging.getLogger(__name__)


def provider_error_detail(event: dict, api_key: str = '') -> str:
    """Retain useful provider fields, with bounded, credential-redacted text."""
    error = event.get('error') or {}
    if not isinstance(error, dict):
        error = {'message': str(error)}
    parts = []
    for field in ('code', 'type', 'param', 'message'):
        value = error.get(field)
        if value is not None:
            parts.append(f'{field}={value}')
    detail = ' '.join(parts) or 'code=unknown'
    if api_key:
        detail = detail.replace(api_key, '[REDACTED]')
    detail = re.sub(r'(?i)\bBearer\s+[^\s,;\'"<>]+', 'Bearer [REDACTED]', detail)
    detail = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[REDACTED]', detail)
    return ' '.join(detail.split())[:1400]


class LiveProviderError(RuntimeError):
    """A safe, actionable error suitable for authenticated call diagnostics."""


class LiveSessionDiagnostics:
    def __init__(self, send, *, backend_model: str, api_key: str = '',
                 fallback_model: str = '', record=None, label: str = ''):
        self.send = send
        self.backend_model = backend_model
        self.api_key = api_key
        self.fallback_model = fallback_model.strip()
        self.record = record or (lambda kind, detail: None)
        self.label = label
        self.started = False
        self.backend_unavailable = False
        self.fallback_attempted = False
        self.fallback_pending = False
        self.fallback_event_id = None
        self.fallback_update_accepted = False
        self.fallback_failed = False
        self.notice_sent = False
        self.last_error = ''

    async def observe(self, event: dict):
        kind = event.get('type')
        if kind == 'error':
            detail = provider_error_detail(event, self.api_key)
            self.last_error = detail
            log.warning('GPT-Live provider error %s backend_model=%s %s',
                        self.label, self.backend_model, detail)
            self.record('error', 'GPT-Live ' + detail)
            error = event.get('error') or {}
            code = error.get('code') if isinstance(error, dict) else None
            client_event_id = error.get('client_event_id') if isinstance(error, dict) else None
            client_event_id = client_event_id or event.get('client_event_id')
            if code == 'responses_validation_failed':
                self.backend_unavailable = True
                if self.fallback_attempted and not self.fallback_pending:
                    self.fallback_failed = True
                # One explicit model fallback; keep the exact authorized tool set.
                if (not self.fallback_attempted and self.fallback_model
                        and self.fallback_model != self.backend_model):
                    self.fallback_attempted = True
                    self.fallback_pending = True
                if self.started:
                    await self._recover_or_notify()
            elif self.fallback_event_id and client_event_id == self.fallback_event_id:
                # A rejected update must not leave the caller silently waiting.
                self.fallback_event_id = None
                self.fallback_failed = True
                await self._notify_unavailable()
        elif kind == 'session.started':
            self.started = True
            if self.backend_unavailable:
                await self._recover_or_notify()
        elif (kind == 'session.updated' and self.fallback_event_id
              and event.get('client_event_id') == self.fallback_event_id):
            self.fallback_update_accepted = True
        elif (kind == 'response.event' and self.backend_unavailable and self.fallback_attempted
              and self.fallback_update_accepted and not self.fallback_failed):
            nested = event.get('event') or {}
            # session.updated is only an acknowledgment. A real backend result
            # provides evidence that the replacement can execute this request.
            if (nested.get('type') == 'response.completed' and
                    (nested.get('response') or {}).get('status', 'completed') == 'completed'):
                self.backend_unavailable = False
                self.fallback_event_id = None
                self.record('state', 'GPT-Live fallback backend returned a completed response')

    async def _recover_or_notify(self):
        if self.fallback_pending:
            self.fallback_pending = False
            self.backend_model = self.fallback_model
            self.fallback_event_id = 'backend_retry_' + uuid.uuid4().hex
            self.record('state', 'Retrying GPT-Live backend configuration with ' + self.backend_model)
            await self.send({
                'type': 'session.update', 'event_id': self.fallback_event_id,
                'session': {'delegation': {'type': 'responses',
                            'responses': {'model': self.backend_model}}},
            })
        else:
            await self._notify_unavailable()

    async def _notify_unavailable(self):
        if self.notice_sent or not self.started:
            return
        self.notice_sent = True
        self.record('state', 'GPT-Live conversation remains open; reasoning and tools are unavailable')
        await self.send({
            'type': 'session.instructions.append', 'event_id': 'backend_notice_' + uuid.uuid4().hex,
            'delegation_id': None,
            'content': (
                'The reasoning and tool backend is unavailable for this call. '
                'Briefly explain the technical problem to the caller once. '
                'You can continue ordinary conversation, but do not delegate tasks or '
                'claim to have searched, booked, emailed, remembered or completed actions. '
                'Do not invent results. Offer to try those tasks again later.'
            ),
        })


async def wait_for_live_start(live, diagnostics: LiveSessionDiagnostics, timeout: float = 15) -> dict:
    """Wait for voice readiness within one deadline, not a timeout per event."""
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LiveProviderError('GPT-Live session_start_timeout: ' +
                                    (diagnostics.last_error or 'session.started was not received'))
        try:
            event = json.loads(await asyncio.wait_for(live.recv(), timeout=remaining))
        except asyncio.TimeoutError:
            raise LiveProviderError('GPT-Live session_start_timeout: ' +
                                    (diagnostics.last_error or 'session.started was not received')) from None
        await diagnostics.observe(event)
        kind = event.get('type')
        if kind == 'session.started':
            return event
        if kind == 'error':
            error = event.get('error') or {}
            code = error.get('code') if isinstance(error, dict) else None
            if code != 'responses_validation_failed':
                raise LiveProviderError('GPT-Live rejected session.start: ' + diagnostics.last_error)
        if kind == 'session.closed':
            raise LiveProviderError('GPT-Live closed before session.started: ' +
                                    (diagnostics.last_error or 'no provider error supplied'))
