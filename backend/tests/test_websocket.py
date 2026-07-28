"""
Tests unitaires pour core/websocket.py
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.core.websocket import ConnectionManager, WorkflowLogger


@pytest.mark.asyncio
async def test_connection_manager_connect_disconnect():
    """Vérifie l'ajout et le retrait de connexions WebSocket."""
    manager = ConnectionManager()
    mock_ws = AsyncMock()

    await manager.connect(mock_ws, project_id=1)
    assert 1 in manager._connections
    assert mock_ws in manager._connections[1]

    await manager.disconnect(mock_ws, project_id=1)
    assert 1 not in manager._connections


@pytest.mark.asyncio
async def test_connection_manager_send_to_project():
    """Vérifie l'envoi de message à un projet spécifique."""
    manager = ConnectionManager()
    mock_ws = AsyncMock()

    await manager.connect(mock_ws, project_id=42)
    msg = {"type": "test", "content": "hello"}
    await manager.send_to_project(42, msg)

    mock_ws.send_text.assert_called_once()
    assert '"type": "test"' in mock_ws.send_text.call_args[0][0]


@pytest.mark.asyncio
async def test_workflow_logger_records_logs():
    """Vérifie le fonctionnement de WorkflowLogger et l'accumulation des logs."""
    wf_logger = WorkflowLogger(project_id=10, workflow_id=100)

    await wf_logger.info("Démarrage du processus", step="init")
    await wf_logger.warning("Avertissement mineur", step="step1")
    await wf_logger.success("Succès final", step="done")

    logs = wf_logger.get_logs()
    assert len(logs) == 3
    assert logs[0]["level"] == "info"
    assert logs[0]["step"] == "init"
    assert logs[1]["level"] == "warning"
    assert logs[2]["level"] == "success"
