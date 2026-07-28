"""
Tests unitaires pour models/schemas.py et models/database.py
"""

from datetime import datetime
import pytest
from pydantic import ValidationError
from backend.models.schemas import (
    ProjectCreate,
    ProjectResponse,
    WorkflowStart,
    UpdateItem,
    UpdatesApplyRequest,
    VRTReportItem,
    LogMessage,
)


def test_project_create_validation():
    """Vérifie la validation des noms de projet."""
    valid_proj = ProjectCreate(name="valid-name_123")
    assert valid_proj.name == "valid-name_123"

    with pytest.raises(ValidationError):
        ProjectCreate(name="invalid name with spaces!")

    with pytest.raises(ValidationError):
        ProjectCreate(name="a")  # Moins de 2 caractères


def test_update_item_schema():
    """Vérifie le schéma UpdateItem."""
    item = UpdateItem(
        name="woocommerce",
        type="plugin",
        current_version="8.0.0",
        new_version="8.5.0",
    )
    assert item.status == "available"
    assert item.name == "woocommerce"


def test_updates_apply_request_defaults():
    """Vérifie les valeurs par défaut de UpdatesApplyRequest."""
    req = UpdatesApplyRequest(project_id=1)
    assert req.update_core is False
    assert req.plugin_names == []
    assert req.theme_names == []


def test_log_message_schema():
    """Vérifie le schéma LogMessage."""
    log = LogMessage(
        timestamp=datetime.now().isoformat(),
        level="info",
        step="ddev_setup",
        message="DDEV container ready",
        progress=50.0,
    )
    assert log.level == "info"
    assert log.progress == 50.0
