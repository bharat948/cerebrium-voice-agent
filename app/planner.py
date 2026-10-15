import json
import re
import httpx
from app.config import Settings
from app.models import valid_phone

PHONE_IN_TEXT = re.compile(r'\+[1-9]\d{7,14}')


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
        'max_tokens': 480,
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
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.post('https://api.openai.com/v1/chat/completions',
                                     headers={'Authorization': 'Bearer ' + api_key}, json=payload)
        response.raise_for_status()
        return response.json()
