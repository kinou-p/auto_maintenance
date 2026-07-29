"""
Tests unitaires pour core/config.py
"""

from pathlib import Path
import pytest
from backend.core.config import Settings, settings


def test_default_settings():
    """Vérifie la valeur par défaut des paramètres."""
    assert settings.app_name == "auto_maintenance"
    assert settings.max_upload_size_mb == 2048
    assert settings.max_upload_size_bytes == 2048 * 1024 * 1024
    assert settings.ddev_php_version == "8.2"
    assert settings.docker_base_port == 8080
    assert settings.vrt_enable_dom_snapshot is True
    assert settings.screenshot_load_timeout == 15000
    assert settings.screenshot_networkidle_timeout == 5000
    assert settings.screenshot_stabilize_delay == 1000



def test_effective_ddev_projects_dir(tmp_path):
    """Vérifie le comportement de effective_ddev_projects_dir."""
    custom_settings = Settings(
        ddev_projects_dir=tmp_path / "default_dir",
        host_ddev_projects=None
    )
    assert custom_settings.effective_ddev_projects_dir == tmp_path / "default_dir"

    custom_settings.host_ddev_projects = tmp_path / "host_dir"
    assert custom_settings.effective_ddev_projects_dir == tmp_path / "host_dir"


def test_expand_path_validator():
    """Vérifie la conversion automatique de string vers Path."""
    custom_settings = Settings(ddev_projects_dir="/tmp/test_dir")
    assert isinstance(custom_settings.ddev_projects_dir, Path)
    assert custom_settings.ddev_projects_dir == Path("/tmp/test_dir")
