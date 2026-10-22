"""API endpoints for managing 3rd-party integrations and agent permissions."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Any

from app import db
from app.security import require_api_key
from app.integrations import manager


router = APIRouter(prefix="/api/v3", dependencies=[Depends(require_api_key)], tags=["Integrations"])


class ConnectPayload(BaseModel):
    api_key: str | None = None
    default_team: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    scope: str | None = None


class AgentIntegrationsPayload(BaseModel):
    integrations: list[str] = Field(default_factory=list)


class ToggleIntegrationPayload(BaseModel):
    integration_id: str
    enabled: bool = True


@router.get("/integrations")
def list_integrations():
    """List all available and connected 3rd-party integrations."""
    return manager.list_providers()


@router.get("/integrations/{provider_id}")
def get_integration(provider_id: str):
    """Get details for a specific integration provider."""
    provider = manager.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Integration provider '{provider_id}' not found")
    tools = [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
            "is_write": t.is_write,
            "requires_approval": t.requires_approval,
        }
        for t in provider.get_tools()
    ]
    return {
        "id": provider.id,
        "name": provider.name,
        "category": provider.category,
        "auth_type": provider.auth_type,
        "description": provider.description,
        "icon": provider.icon,
        "docs_url": provider.docs_url,
        "connected": provider.is_connected(),
        "tools": tools,
        "permitted_agents": db.get_integration_agents(provider.id),
    }


@router.post("/integrations/{provider_id}/connect")
async def connect_integration(provider_id: str, payload: ConnectPayload):
    """Save credentials or establish connection for an integration."""
    provider = manager.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Integration provider '{provider_id}' not found")
    try:
        result = await provider.connect(payload.model_dump())
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/integrations/{provider_id}/disconnect")
async def disconnect_integration(provider_id: str):
    """Revoke credentials and disconnect an integration."""
    provider = manager.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Integration provider '{provider_id}' not found")
    try:
        success = await provider.disconnect()
        return {"status": "disconnected", "provider": provider_id, "success": success}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/integrations/{provider_id}/tools")
def get_integration_tools(provider_id: str):
    """List tools supplied by an integration."""
    provider = manager.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Integration provider '{provider_id}' not found")
    return [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
            "is_write": t.is_write,
            "requires_approval": t.requires_approval,
        }
        for t in provider.get_tools()
    ]


@router.get("/agents/{agent_id}/integrations")
def get_agent_integrations(agent_id: str):
    """Get the list of integrations permitted for this agent."""
    agent = db.one("SELECT id, name FROM agents WHERE id=?", (agent_id,))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    permitted = db.get_agent_integrations(agent_id)
    return {
        "agent_id": agent_id,
        "name": agent["name"],
        "integrations": permitted,
    }


@router.post("/agents/{agent_id}/integrations")
def set_agent_integrations(agent_id: str, payload: AgentIntegrationsPayload):
    """Update all integrations permitted for this agent."""
    agent = db.one("SELECT id, name FROM agents WHERE id=?", (agent_id,))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.set_agent_integrations(agent_id, payload.integrations)
    return {
        "agent_id": agent_id,
        "integrations": db.get_agent_integrations(agent_id),
        "status": "updated",
    }


@router.post("/agents/{agent_id}/integrations/toggle")
def toggle_agent_integration(agent_id: str, payload: ToggleIntegrationPayload):
    """Toggle a single integration on or off for this agent."""
    agent = db.one("SELECT id, name FROM agents WHERE id=?", (agent_id,))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    current = set(db.get_agent_integrations(agent_id))
    if payload.enabled:
        current.add(payload.integration_id)
    else:
        current.discard(payload.integration_id)
    db.set_agent_integrations(agent_id, list(current))
    return {
        "agent_id": agent_id,
        "integrations": sorted(current),
        "toggled": payload.integration_id,
        "enabled": payload.enabled,
    }
