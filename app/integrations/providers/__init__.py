"""Built-in integration providers registration."""
from app.integrations import manager
from app.integrations.providers.google_workspace import GoogleWorkspaceProvider
from app.integrations.providers.linear import LinearProvider

# Register providers
google_provider = GoogleWorkspaceProvider()
linear_provider = LinearProvider()

manager.register_provider(google_provider)
manager.register_provider(linear_provider)
