import json
import re
import httpx
from app.config import Settings
from app.models import valid_phone

PHONE_IN_TEXT = re.compile(r'\+[1-9]\d{7,14}')


class OpenAIProviderError(Exception):
    """Safe, actionable OpenAI failure without exposing provider response bodies or keys."""

    def __init__(self, status_code: int | None, code: str = ''):
        self.status_code = status_code
        self.code = code if re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', code) else ''
        if status_code == 401:
            action = 'Check OPENAI_API_KEY in Render > Environment; generate a new API key if necessary.'
        elif status_code == 403:
            action = 'Check that your API project has permission to use OPENAI_MODEL.'
        elif status_code == 404:
            action = 'Check OPENAI_MODEL and whether that model is available to your API project.'
        elif status_code == 429:
            if self.code in {
                'insufficient_quota', 'credit_balance_exhausted',
                'organization_spend_limit_exceeded', 'project_spend_limit_exceeded',
                'organization_usage_limit_exceeded',
            }:
                action = 'Check OpenAI API billing, prepaid credits, and project usage limits (separate from ChatGPT).'
            else:
                action = 'Check OpenAI API rate limits, credit balance, and project spending limits.'
        elif status_code == 400:
            action = 'Check OPENAI_MODEL and its Chat Completions request compatibility.'
        elif status_code is None:
            action = 'Check network connectivity to api.openai.com and try again.'
        else:
            action = 'Check OpenAI service status and Render logs, then retry.'
        label = f'OpenAI API HTTP {status_code}' if status_code else 'OpenAI connection failure'
        if self.code:
            label += f' ({self.code})'
        super().__init__(f'{label}. {action}')


def extract_phone(text: str, supplied: str) -> str:
    if supplied:
        return supplied.strip()
    match = PHONE_IN_TEXT.search(text)
    return match.group(0) if match else ''


def fallback_plan(message: str) -> dict:
    goal = message.strip()[:500]
    return {
        'goal': goal,
        'agenda': [
            'Introduce yourself as an AI assistant and identify the purpose of the call.',
            'Ask the recipient if they are available to discuss the requested topic.',
            'Discuss the task: ' + goal[:220],
            'Confirm the response and any next action without inventing commitments.',
            'Thank the recipient and end the call politely.'
        ],
        'script': 'Hello, I am an AI assistant calling about ' + goal[:170] + '. Is this a good time to speak?'
    }


async def build_plan(message: str, settings: Settings) -> dict:
    if not settings.openai_api_key:
        return fallback_plan(message)
    request_payload = {
        'model': settings.openai_model,
        'response_format': {'type': 'json_object'},
        'temperature': 0.25,
        'max_completion_tokens': 480,
        'messages': [
            {'role': 'system', 'content': (
                'Return a JSON object with exactly goal (string), agenda (array of 3-6 short strings), '
                'and script (short opening sentence). The user gives an outbound phone call task. '
                'The recipient must be informed they are speaking to an AI assistant. '
                'Do not promise bookings, payments, or actions that have not occurred. '
                'No instructions to harass, misrepresent identity, or collect secrets. '
                'Never place the call; plan only. Avoid inventing facts.')},
            {'role': 'user', 'content': message}
        ]
    }
    resp = await openai_completion(settings.openai_api_key, request_payload)
    try:
        data = json.loads(resp['choices'][0]['message']['content'] or '{}')
        goal = str(data['goal']).strip()[:1200]
        agenda = [str(s).strip()[:300] for s in data['agenda'] if str(s).strip()][:10]
        script = str(data['script']).strip()[:2000]
        if not goal or not agenda or not script:
            raise ValueError('Missing content')
        return {'goal': goal, 'agenda': agenda, 'script': script}
    except (KeyError, ValueError, TypeError):
        return fallback_plan(message)


async def preview_reply(history: list[dict], system: str, settings: Settings) -> str:
    if not settings.openai_api_key:
        return ('Thanks for sharing. I can ask follow-up questions based on the agenda, '
                'but OpenAI must be configured for a realistic preview.')
    result = await openai_completion(settings.openai_api_key, {
        'model': settings.openai_model, 'max_tokens': settings.openai_max_output_tokens,
        'messages': [{'role': 'system', 'content': system}] + history[-16:]
    })
    return (result['choices'][0]['message']['content'] or '').strip()[:1200]


async def openai_completion(api_key: str, payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post('https://api.openai.com/v1/chat/completions',
                                         headers={'Authorization': 'Bearer ' + api_key}, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        # Never expose the full provider response or request headers in API errors.
        code = ''
        try:
            error = exc.response.json().get('error', {})
            if isinstance(error, dict):
                code = str(error.get('code') or error.get('type') or '')
        except (ValueError, TypeError, AttributeError):
            pass
        raise OpenAIProviderError(exc.response.status_code, code) from None
    except httpx.RequestError:
        raise OpenAIProviderError(None) from None
