"""
Tests d'intégration API avec client AsyncClient pour FastAPI.
"""

import pytest
from unittest.mock import patch, AsyncMock
from backend.utils.command import CommandResult


@pytest.mark.asyncio
async def test_health_check(async_client):
    """Vérifie l'endpoint /api/health."""
    response = await async_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_list_projects_empty(async_client):
    """Vérifie la liste des projets quand la BDD est vide."""
    response = await async_client.get("/api/projects/")
    assert response.status_code == 200
    data = response.json()
    assert "projects" in data
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_create_project_api(async_client):
    """Vérifie l'endpoint de création de projet /api/projects/."""
    payload = {"name": "test-api-project"}
    response = await async_client.post("/api/projects/", data=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "test-api-project"
    assert data["status"] == "created"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_list_containers_api(async_client):
    """Vérifie l'endpoint system/containers avec mock ddev."""
    mock_ddev_output = '{"raw": [{"name": "site1", "status": "running", "approot": "/tmp/site1"}]}'
    
    with patch("backend.api.system.run_command", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = CommandResult(
            returncode=0, stdout=mock_ddev_output, stderr="", command="ddev list -j"
        )
        response = await async_client.get("/api/system/containers")
        assert response.status_code == 200
        containers = response.json()
        assert len(containers) == 1
        assert containers[0]["name"] == "site1"
        assert containers[0]["status"] == "running"
