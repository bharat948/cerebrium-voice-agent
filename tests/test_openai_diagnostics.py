"""Exercise provider failures without any external network calls or API credentials."""
import asyncio

import httpx
import pytest

from app import planner


@pytest.mark.parametrize('status,code,expected', [
    (401, 'invalid_api_key', 'OPENAI_API_KEY'),
    (429, 'insufficient_quota', 'billing'),
    (429, 'rate_limit_exceeded', 'rate limits'),
    (400, 'model_not_found', 'OPENAI_MODEL'),
])
def test_openai_error_reports_safe_status(monkeypatch, status, code, expected):
    original_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(lambda request: httpx.Response(
            status, json={'error': {'code': code, 'message': 'PRIVATE PROVIDER DATA SHOULD NOT LEAK'}}
        ))
        return original_client(*args, **kwargs)

    monkeypatch.setattr(planner.httpx, 'AsyncClient', make_client)
    with pytest.raises(planner.OpenAIProviderError) as info:
        asyncio.run(planner.openai_completion('fake-secret-token', {'model': 'gpt-4o-mini'}))
    assert info.value.status_code == status
    assert code in str(info.value)
    assert expected.lower() in str(info.value).lower()
    assert 'fake-secret-token' not in str(info.value)
    assert 'PRIVATE PROVIDER DATA' not in str(info.value)
