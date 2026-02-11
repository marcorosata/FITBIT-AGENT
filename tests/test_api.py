"""Tests for the FastAPI server endpoints."""

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from wearable_agent.api.server import app


@pytest.fixture
async def client():
    """Async test client with lifespan (startup / shutdown) fully executed."""
    async with LifespanManager(app) as manager:
        transport = ASGITransport(app=manager.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_ingest_and_query(client: AsyncClient):
    payload = {
        "participant_id": "P001",
        "device_type": "fitbit",
        "metric_type": "heart_rate",
        "value": 85.0,
        "unit": "bpm",
    }
    resp = await client.post("/ingest", json=payload)
    assert resp.status_code == 201
    assert resp.json()["queued"] is True


@pytest.mark.asyncio
async def test_rules_crud(client: AsyncClient):
    # List existing rules
    resp = await client.get("/rules")
    assert resp.status_code == 200
    initial_count = len(resp.json())

    # Add a new rule
    rule = {
        "metric_type": "heart_rate",
        "condition": "value > 200",
        "severity": "critical",
        "message_template": "Very high HR: {value} bpm.",
    }
    resp = await client.post("/rules", json=rule)
    assert resp.status_code == 201
    rule_id = resp.json()["rule_id"]

    # Verify it was added
    resp = await client.get("/rules")
    assert len(resp.json()) == initial_count + 1

    # Delete it
    resp = await client.delete(f"/rules/{rule_id}")
    assert resp.status_code == 200
