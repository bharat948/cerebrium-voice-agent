import secrets
from fastapi import HTTPException, Header, Request, WebSocket
from twilio.request_validator import RequestValidator
from app.config import get_settings


def require_api_key(request: Request, x_api_key: str | None = Header(default=None)):
    s = get_settings()
    if s.auth_mode == 'google':
        if s.google_owner_sub and request.session.get('owner_sub') == s.google_owner_sub:
            return
        raise HTTPException(status_code=401, detail='Owner Google login required')
    expected = s.app_api_key
    provided = x_api_key or request.query_params.get('api_key') or request.session.get('api_key')
    if not expected or not secrets.compare_digest(provided or '', expected):
        raise HTTPException(status_code=401, detail='Invalid API key')


def validate_twilio_request(url: str, data: dict, signature: str | None) -> bool:
    s = get_settings()
    if not s.twilio_validate_signatures:
        # Deliberate development escape hatch. Strongly discouraged on public endpoints.
        return s.app_env == 'development'
    if not (s.twilio_auth_token and signature):
        return False
    return RequestValidator(s.twilio_auth_token).validate(url, data, signature)


async def require_twilio_http(request: Request) -> dict:
    data = dict(await request.form())
    url = get_settings().base_url + request.url.path
    if request.url.query:
        url += '?' + request.url.query
    if not validate_twilio_request(url, data, request.headers.get('x-twilio-signature')):
        raise HTTPException(status_code=403, detail='Invalid Twilio signature')
    return data


def allow_twilio_websocket(ws: WebSocket) -> bool:
    s = get_settings()
    base = s.base_url.replace('https://', 'wss://', 1)
    if not base.startswith('wss://'):
        return False
    url = base + ws.url.path
    signature = ws.headers.get('x-twilio-signature')
    # The Twilio WS handshake URL occasionally has a normalized trailing slash.
    return any(validate_twilio_request(candidate, {}, signature) for candidate in (url, url + '/'))
