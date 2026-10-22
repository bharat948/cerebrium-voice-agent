"""Unit tests for Google Connector integration and OAuth alignment with DailyPilotLab."""
import pytest
from cryptography.fernet import Fernet
from starlette.testclient import TestClient


@pytest.fixture
def google_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "google_test.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("AUTH_MODE", "api_key")
    monkeypatch.setenv("APP_API_KEY", "test-api-key")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://voice-foundry-test.onrender.com")
    monkeypatch.setenv("GOOGLE_CONNECTOR_CLIENT_ID", "daily-pilot-client-id-123.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CONNECTOR_CLIENT_SECRET", "daily-pilot-secret-456")
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())

    from app.config import get_settings
    get_settings.cache_clear()
    from app import db
    db.init_db()
    return db


def test_effective_google_credentials(google_workspace):
    from app.config import get_settings
    s = get_settings()
    assert s.effective_google_client_id == "daily-pilot-client-id-123.apps.googleusercontent.com"
    assert s.effective_google_client_secret == "daily-pilot-secret-456"


def test_google_services_expanded_scopes(google_workspace):
    from app.v3 import google_services
    assert "https://www.googleapis.com/auth/gmail.readonly" in google_services.SCOPES
    assert "https://www.googleapis.com/auth/gmail.compose" in google_services.SCOPES
    assert "https://www.googleapis.com/auth/calendar" in google_services.SCOPES
    assert "https://www.googleapis.com/auth/tasks" in google_services.SCOPES


@pytest.mark.asyncio
async def test_google_workspace_provider_tools(google_workspace):
    from app.integrations.providers.google_workspace import GoogleWorkspaceProvider
    provider = GoogleWorkspaceProvider()
    tools = {t.name: t for t in provider.get_tools()}
    assert "google_search_emails" in tools
    assert "google_draft_email" in tools
    assert "google_calendar_check" in tools
    assert "google_calendar_create" in tools

    # Search emails
    res = await provider.execute_tool("google_search_emails", {"query": "invoices", "limit": 2})
    assert res["status"] == "completed"
    assert len(res["emails"]) <= 2

    # Draft email
    draft_res = await provider.execute_tool("google_draft_email", {
        "to": "client@example.com",
        "subject": "Follow up",
        "body": "Here is the summary of our call."
    })
    assert draft_res["status"] == "completed"
    assert "draft_id" in draft_res

    # Calendar check
    cal_res = await provider.execute_tool("google_calendar_check", {
        "start": "2026-10-23T10:00:00Z",
        "end": "2026-10-23T11:00:00Z"
    })
    assert cal_res["status"] == "completed"
    assert cal_res["available"] is True


def test_auth_google_connect_redirect(google_workspace):
    from app.main import app
    client = TestClient(app, follow_redirects=False)

    # Calling /auth/google/connect with valid API key header
    res = client.get("/auth/google/connect", headers={"X-API-Key": "test-api-key"})
    # Should redirect to accounts.google.com OAuth page, NOT 403 Forbidden
    assert res.status_code == 302
    assert "accounts.google.com" in res.headers["location"]
    assert "daily-pilot-client-id-123.apps.googleusercontent.com" in res.headers["location"]


def test_google_connect_callback_flow(google_workspace, monkeypatch):
    import httpx
    from app.main import app

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data
            self.text = "mocked"
        def json(self):
            return self._json

    async def mock_post(self, url, **kwargs):
        return MockResponse(200, {
            "access_token": "mock-access-token-xyz",
            "refresh_token": "mock-refresh-token-xyz",
            "expires_in": 3600,
            "token_type": "Bearer"
        })

    async def mock_get(self, url, **kwargs):
        return MockResponse(200, {"sub": "user_123", "email": "pilot@example.com"})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    client = TestClient(app, follow_redirects=False)

    # 1. Start flow to set session state
    res_start = client.get("/auth/google/connect", headers={"X-API-Key": "test-api-key"})
    assert res_start.status_code == 302

    # 2. Extract state parameter
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(res_start.headers["location"])
    state = parse_qs(parsed.query)["state"][0]

    # 3. Call callback with state and code
    res_callback = client.get(f"/auth/google/connect/callback?code=test-code-123&state={state}")
    assert res_callback.status_code == 303
    assert res_callback.headers["location"] == "/#integrations"

    # Verify token stored
    from app.v3 import google_services
    assert google_services.connected() is True
