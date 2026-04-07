from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import create_app
from app.providers.registry import ProviderRegistry


@pytest.fixture
def app():
    application = create_app()
    settings = get_settings()
    # Force mock providers in tests regardless of .env API keys
    settings.data.ALLOW_SIMULATION = True
    registry = ProviderRegistry(settings)
    registry.initialize()
    application.state.settings = settings
    application.state.provider_registry = registry
    return application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
