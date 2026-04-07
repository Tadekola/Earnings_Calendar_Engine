from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("HEALTHY", "DEGRADED", "CRITICAL")
    assert "providers" in data
    assert "environment" in data
    assert "operating_mode" in data


@pytest.mark.asyncio
async def test_liveness(client):
    response = await client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


@pytest.mark.asyncio
async def test_readiness(client):
    response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ready", "not_ready")
    assert "checks" in data


@pytest.mark.asyncio
async def test_adapter_health(client):
    response = await client.get("/health/adapters")
    assert response.status_code == 200
    data = response.json()
    assert "earnings" in data
    assert "price" in data
    assert "options" in data
    assert "volatility" in data
