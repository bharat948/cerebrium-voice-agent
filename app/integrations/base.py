"""Base abstractions for 3rd-party integration providers in Voice Foundry."""
from abc import ABC, abstractmethod
from typing import Any, Literal
from pydantic import BaseModel, Field


class IntegrationTool(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    is_write: bool = False
    requires_approval: bool = False


class IntegrationProvider(ABC):
    """Abstract base class for all 3rd-party integration connectors."""
    id: str
    name: str
    category: Literal["communication", "productivity", "project_management", "crm", "developer"]
    auth_type: Literal["oauth2", "api_key"]
    description: str
    icon: str = ""
    docs_url: str = ""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the provider is currently connected and authorized."""
        pass

    @abstractmethod
    async def connect(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Save credentials or initiate auth for this provider."""
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """Revoke and delete credentials for this provider."""
        pass

    @abstractmethod
    def get_tools(self) -> list[IntegrationTool]:
        """Return definitions of tools provided by this integration."""
        pass

    @abstractmethod
    async def execute_tool(
        self,
        action: str,
        params: dict[str, Any],
        context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a tool action provided by this integration."""
        pass
