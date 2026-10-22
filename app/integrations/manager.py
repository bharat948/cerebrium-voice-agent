"""Integration Manager for 3rd-party services and agent permissions."""
import json
import time
from typing import Any
from cryptography.fernet import Fernet

from app import db
from app.config import get_settings
from app.integrations.base import IntegrationProvider, IntegrationTool


_PROVIDERS: dict[str, IntegrationProvider] = {}
_FALLBACK_KEY: str | None = None


def _cipher() -> Fernet:
    global _FALLBACK_KEY
    key = get_settings().integration_encryption_key
    if not key:
        s = get_settings()
        if s.demo_mode:
            if not _FALLBACK_KEY:
                _FALLBACK_KEY = Fernet.generate_key().decode()
            key = _FALLBACK_KEY
        else:
            raise ValueError("Configure INTEGRATION_ENCRYPTION_KEY before managing integrations")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise ValueError("Integration encryption key must be a valid Fernet key") from exc


def encrypt_credentials(payload: dict[str, Any]) -> str:
    """Encrypt credential payload into ciphertext string."""
    data_str = json.dumps(payload)
    return _cipher().encrypt(data_str.encode()).decode()


def decrypt_credentials(encrypted_str: str) -> dict[str, Any]:
    """Decrypt ciphertext string into credential payload dict."""
    try:
        decrypted = _cipher().decrypt(encrypted_str.encode()).decode()
        return json.loads(decrypted)
    except Exception as exc:
        raise ValueError("Failed to decrypt credentials") from exc


def register_provider(provider: IntegrationProvider):
    """Register a provider instance in the global registry."""
    _PROVIDERS[provider.id] = provider


def get_provider(provider_id: str) -> IntegrationProvider | None:
    """Retrieve a registered provider by its ID."""
    return _PROVIDERS.get(provider_id)


# Upcoming catalog definitions for UI exploration and future extensions
UPCOMING_CATALOG = [
    {
        "id": "outlook",
        "name": "Microsoft Outlook",
        "category": "communication",
        "auth_type": "oauth2",
        "description": "Email, calendars, and contacts across Microsoft 365",
        "icon": "mail",
        "status": "catalog",
    },
    {
        "id": "teams",
        "name": "Microsoft Teams",
        "category": "communication",
        "auth_type": "oauth2",
        "description": "Channels, direct messages, and call recap notifications",
        "icon": "message-square",
        "status": "catalog",
    },
    {
        "id": "notion",
        "name": "Notion",
        "category": "productivity",
        "auth_type": "api_key",
        "description": "Team workspaces, pages, databases, and meeting notes",
        "icon": "book-open",
        "status": "catalog",
    },
    {
        "id": "jira",
        "name": "Jira Software",
        "category": "project_management",
        "auth_type": "api_key",
        "description": "Atlassian issue tracking, sprints, and release tickets",
        "icon": "check-circle",
        "status": "catalog",
    },
]


def list_providers() -> list[dict[str, Any]]:
    """List all registered and catalog integrations with their connection & agent counts."""
    results = []
    # 1. Active registered providers
    for p_id, provider in _PROVIDERS.items():
        connected = provider.is_connected()
        permitted_count = db.count_integration_agents(p_id)
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
        results.append({
            "id": provider.id,
            "name": provider.name,
            "category": provider.category,
            "auth_type": provider.auth_type,
            "description": provider.description,
            "icon": provider.icon,
            "docs_url": provider.docs_url,
            "connected": connected,
            "status": "active",
            "tools_count": len(tools),
            "tools": tools,
            "permitted_agents_count": permitted_count,
        })

    # 2. Add upcoming catalog providers if not already registered
    registered_ids = set(_PROVIDERS.keys())
    for item in UPCOMING_CATALOG:
        if item["id"] not in registered_ids:
            results.append({
                **item,
                "connected": False,
                "tools_count": 0,
                "tools": [],
                "permitted_agents_count": 0,
            })

    return results


def is_agent_authorized(agent_id: str, integration_id: str) -> bool:
    """Check if an agent has permission to use a specific integration."""
    permitted = db.get_agent_integrations(agent_id)
    return integration_id in permitted


def get_agent_permitted_tools(agent_id: str, is_owner: bool = False) -> list[dict[str, Any]]:
    """Get all tools provided by connected integrations that this agent is authorized to use."""
    permitted_integration_ids = db.get_agent_integrations(agent_id)
    tools = []
    for p_id in permitted_integration_ids:
        provider = _PROVIDERS.get(p_id)
        if provider and provider.is_connected():
            for t in provider.get_tools():
                # If tool requires approval and is_owner is false, still expose definition
                # but live_functions will route it to an approval requirement.
                tools.append({
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                    "is_write": t.is_write,
                    "requires_approval": t.requires_approval,
                    "integration_id": p_id,
                })
    return tools


async def execute_agent_tool(
    agent_id: str,
    action: str,
    params: dict[str, Any],
    context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Execute a tool for an agent, checking permissions and approval requirements."""
    # Find which provider supplies this action
    target_provider: IntegrationProvider | None = None
    target_tool: IntegrationTool | None = None

    for provider in _PROVIDERS.values():
        for t in provider.get_tools():
            if t.name == action:
                target_provider = provider
                target_tool = t
                break
        if target_provider:
            break

    if not target_provider or not target_tool:
        raise ValueError(f"Unknown integration tool: {action}")

    # Check permission
    if not is_agent_authorized(agent_id, target_provider.id):
        raise PermissionError(f"Agent '{agent_id}' does not have access to integration '{target_provider.id}'")

    if not target_provider.is_connected():
        raise RuntimeError(f"Integration '{target_provider.id}' is not connected")

    # Safety check: if tool requires approval, generate approval record rather than executing immediately
    if target_tool.requires_approval:
        from app.v3 import governance
        contact_id = context.get('contact', {}).get('id') if context and context.get('contact') else None
        proposal = governance.request_approval(agent_id, action, params, contact_id=contact_id)
        return {
            "status": "approval_required",
            "approval_id": proposal["id"],
            "message": f"Action '{action}' requires owner approval before execution.",
            "action": action,
            "params": params,
        }

    # Execute read-only or pre-approved action
    return await target_provider.execute_tool(action, params, context)
