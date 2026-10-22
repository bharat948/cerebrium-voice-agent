"""Unit and integration tests for Voice Foundry 3rd-Party Integrations Framework."""
import pytest
from cryptography.fernet import Fernet


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "integrations_test.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("AUTH_MODE", "api_key")
    monkeypatch.setenv("APP_API_KEY", "test-key-12345")
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())

    from app.config import get_settings
    get_settings.cache_clear()

    from app import db
    from app.v3 import contacts
    db.init_db()

    contact = contacts.register("Integration Tester", "+919999999999", "tester@example.com", email_consent=True)
    return db, contact


def test_list_providers_and_catalog(workspace):
    from app.integrations import manager

    providers = manager.list_providers()
    provider_ids = [p["id"] for p in providers]

    # Active providers
    assert "google" in provider_ids
    assert "linear" in provider_ids

    # Upcoming catalog providers
    assert "outlook" in provider_ids
    assert "teams" in provider_ids
    assert "notion" in provider_ids
    assert "jira" in provider_ids

    linear = next(p for p in providers if p["id"] == "linear")
    assert linear["category"] == "project_management"
    assert linear["auth_type"] == "api_key"
    assert len(linear["tools"]) >= 3


@pytest.mark.asyncio
async def test_linear_connection_and_encryption(workspace):
    db, _ = workspace
    from app.integrations import manager

    linear = manager.get_provider("linear")
    assert linear is not None

    # Connect with API key
    await linear.connect({"api_key": "lin_api_secret_token_12345", "default_team": "ENG"})
    assert linear.is_connected() is True

    # Verify encrypted in DB and plaintext not stored
    row = db.one("SELECT * FROM integrations WHERE provider='linear'")
    assert row is not None
    assert "lin_api_secret_token_12345" not in row["encrypted_credentials"]

    # Verify decryption
    creds = manager.decrypt_credentials(row["encrypted_credentials"])
    assert creds["api_key"] == "lin_api_secret_token_12345"
    assert creds["default_team"] == "ENG"

    # Disconnect
    await linear.disconnect()
    assert linear.is_connected() is False
    assert db.one("SELECT * FROM integrations WHERE provider='linear'") is None


@pytest.mark.asyncio
async def test_agent_permission_and_tool_execution(workspace):
    db, contact = workspace
    from app.integrations import manager

    agent_a = db.insert_agent("Ava Ops", "Ops Coordinator", "English", "Help manage engineering operations")
    agent_b = db.insert_agent("Ava Sales", "Sales Coordinator", "English", "Help sales team")

    # Connect Linear
    linear = manager.get_provider("linear")
    await linear.connect({"api_key": "secret", "default_team": "ENG"})

    # Initially neither agent has linear permission
    assert manager.is_agent_authorized(agent_a["id"], "linear") is False
    assert len(manager.get_agent_permitted_tools(agent_a["id"])) == 0

    # Grant Linear to Agent A only
    db.set_agent_integrations(agent_a["id"], ["linear"])
    assert manager.is_agent_authorized(agent_a["id"], "linear") is True
    assert manager.is_agent_authorized(agent_b["id"], "linear") is False

    permitted_tools = manager.get_agent_permitted_tools(agent_a["id"])
    tool_names = {t["name"] for t in permitted_tools}
    assert "linear_list_issues" in tool_names
    assert "linear_create_issue" in tool_names

    # Agent A executes read-only tool successfully
    read_res = await manager.execute_agent_tool(agent_a["id"], "linear_list_issues", {"query": "audio"})
    assert read_res["status"] == "completed"
    assert len(read_res["issues"]) >= 1

    # Agent B attempts to execute linear tool -> permission denied
    with pytest.raises(PermissionError):
        await manager.execute_agent_tool(agent_b["id"], "linear_list_issues", {})

    # Agent A executes write tool -> safety governance creates approval proposal
    write_res = await manager.execute_agent_tool(
        agent_a["id"],
        "linear_create_issue",
        {"title": "Test Issue", "description": "Needs review"}
    )
    assert write_res["status"] == "approval_required"
    assert "approval_id" in write_res

    approval_row = db.one("SELECT * FROM approvals WHERE id=?", (write_res["approval_id"],))
    assert approval_row is not None
    assert approval_row["state"] == "pending"
    assert approval_row["action"] == "linear_create_issue"


@pytest.mark.asyncio
async def test_live_functions_integration(workspace):
    db, contact = workspace
    from app.integrations import manager
    from app.v3 import live_functions, registry

    agent = db.insert_agent("Ava Live", "Live Coordinator", "English", "Live testing")
    linear = manager.get_provider("linear")
    await linear.connect({"api_key": "dummy-token"})

    # Create draft with integrations=['linear']
    draft = registry.create_draft(agent["id"], {"integrations": ["linear"]})
    registry.publish(agent["id"], draft["id"])
    config = registry.get_config(agent["id"])

    # Check function definitions include linear tools
    tools = live_functions.definitions(config, recognized_contact=True)
    tool_names = {t["name"] for t in tools}
    assert "linear_list_issues" in tool_names
    assert "linear_create_issue" in tool_names

    # Execute via live_functions.run
    res = await live_functions.run(
        agent["id"],
        contact,
        "linear_list_issues",
        {"query": "audio"},
        config
    )
    assert res["status"] == "completed"
    assert len(res["issues"]) >= 1


@pytest.mark.asyncio
async def test_rest_api_integrations_routes(workspace):
    db, _ = workspace
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    headers = {"X-API-Key": "test-key-12345"}

    # 1. List integrations
    res = client.get("/api/v3/integrations", headers=headers)
    assert res.status_code == 200
    providers = res.json()
    assert any(p["id"] == "linear" for p in providers)

    # 2. Connect Linear via REST API
    res = client.post(
        "/api/v3/integrations/linear/connect",
        json={"api_key": "api_test_key_rest", "default_team": "OPS"},
        headers=headers
    )
    assert res.status_code == 200
    assert res.json()["status"] == "connected"

    # 3. Create an agent and assign integrations via REST API
    agent = db.insert_agent("Agent API", "Role", "English", "Prompt")
    res = client.post(
        f"/api/v3/agents/{agent['id']}/integrations",
        json={"integrations": ["linear", "google"]},
        headers=headers
    )
    assert res.status_code == 200
    assert set(res.json()["integrations"]) == {"linear", "google"}

    # 4. Get agent integrations
    res = client.get(f"/api/v3/agents/{agent['id']}/integrations", headers=headers)
    assert res.status_code == 200
    assert set(res.json()["integrations"]) == {"linear", "google"}

    # 5. Toggle single integration
    res = client.post(
        f"/api/v3/agents/{agent['id']}/integrations/toggle",
        json={"integration_id": "google", "enabled": False},
        headers=headers
    )
    assert res.status_code == 200
    assert res.json()["integrations"] == ["linear"]

    # 6. Disconnect
    res = client.post("/api/v3/integrations/linear/disconnect", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "disconnected"
