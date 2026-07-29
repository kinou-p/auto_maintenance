"""
Tests unitaires pour backend/managers (y compris DockerEnvManager et la comparaison DOM VRT).
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from backend.managers.hosts_manager import HostsManager, HOSTS_MARKER_START, HOSTS_MARKER_END
from backend.managers.queue_manager import WorkflowQueueManager
from backend.managers.docker_env_manager import DockerEnvManager
from backend.managers.vrt_manager import VRTManager


def test_hosts_manager_build_content():
    """Vérifie la génération du bloc géré dans hosts."""
    hm = HostsManager()
    original = "127.0.0.1 localhost\n::1 localhost\n"
    entries = {"site1.ddev.site": "127.0.0.1", "site2.ddev.site": "127.0.0.1"}

    content = hm._build_hosts_content(original, entries)

    assert HOSTS_MARKER_START in content
    assert HOSTS_MARKER_END in content
    assert "127.0.0.1\tsite1.ddev.site" in content
    assert "127.0.0.1\tsite2.ddev.site" in content
    assert "127.0.0.1 localhost" in content


def test_hosts_manager_get_managed_entries():
    """Vérifie le parsing des entrées gérées."""
    hm = HostsManager()
    content = (
        "127.0.0.1 localhost\n"
        f"{HOSTS_MARKER_START}\n"
        "127.0.0.1\tmyproject.ddev.site\n"
        f"{HOSTS_MARKER_END}\n"
    )
    entries = hm._get_managed_entries(content)
    assert entries == {"myproject.ddev.site": "127.0.0.1"}


def test_workflow_queue_manager_singleton():
    """Vérifie que WorkflowQueueManager est un singleton."""
    qm1 = WorkflowQueueManager()
    qm2 = WorkflowQueueManager()
    assert qm1 is qm2


def test_docker_env_manager_config_generation():
    """Vérifie la génération des fichiers de conf Nginx et Docker Compose."""
    dem = DockerEnvManager("test_project")
    nginx_conf = dem._generate_nginx_config()
    compose_conf = dem._generate_docker_compose(8085)

    assert "server_name localhost;" in nginx_conf
    assert "fastcgi_pass wordpress:9000;" in nginx_conf
    assert "container_name: test_project_wp" in compose_conf
    assert "8085:80" in compose_conf


def test_vrt_manager_dom_tree_comparison():
    """Vérifie le calcul de similarité sur des arbres DOM."""
    vrt = VRTManager("test_project")

    tree1 = {
        "tag": "body",
        "children": [
            {"tag": "h1", "id": "main-title"},
            {"tag": "p", "class": "intro"}
        ]
    }
    tree2 = {
        "tag": "body",
        "children": [
            {"tag": "h1", "id": "main-title"},
            {"tag": "p", "class": "intro"}
        ]
    }
    tree_modified = {
        "tag": "body",
        "children": [
            {"tag": "h1", "id": "main-title"},
            {"tag": "div", "class": "new-banner"}
        ]
    }

    # Identiques => 1.0
    assert vrt._compare_dom_trees(tree1, tree2) == 1.0
    # Différents => < 1.0
    similarity = vrt._compare_dom_trees(tree1, tree_modified)
    assert 0.0 < similarity < 1.0


def test_docker_env_manager_free_port_finder():
    """Vérifie la détection dynamique de port libre sur l'hôte."""
    dem = DockerEnvManager("test_port_project")
    port = dem._find_free_port()
    assert isinstance(port, int)
    assert port >= 8080


@pytest.mark.asyncio
async def test_docker_env_manager_lifecycle():
    """Vérifie le cycle de vie start/stop/exec d'un environnement Docker simulé."""
    dem = DockerEnvManager("test_lifecycle_project")

    with patch("backend.managers.docker_env_manager.run_command", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = MagicMock(success=True, stdout="OK", stderr="")
        
        env_info = await dem.start_environment()
        assert env_info["project_name"] == "test_lifecycle_project"
        assert "http://localhost:" in env_info["url"]
        assert env_info["port"] is not None

        await dem.execute_wp_cli(["core", "version"])
        assert mock_run.called

        await dem.stop_environment()
        assert mock_run.call_count >= 2


@pytest.mark.asyncio
async def test_screenshot_manager_dom_snapshot():
    """Vérifie l'extraction du DOM snapshot via Playwright page evaluate."""
    from backend.managers.screenshot_manager import ScreenshotManager
    sm = ScreenshotManager("test_project")

    mock_page = MagicMock()
    mock_page.evaluate = AsyncMock(return_value={
        "title": "Mon Site WP",
        "url": "http://localhost:8080",
        "tree": {"tag": "body", "children": [{"tag": "h1"}]}
    })

    snapshot = await sm._capture_dom_snapshot(mock_page)
    assert snapshot["title"] == "Mon Site WP"
    assert snapshot["tree"]["tag"] == "body"

