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


@pytest.mark.asyncio
async def test_vrt_manager_asymmetric_and_workflow_urls(tmp_path, monkeypatch):
    """Vérifie que les URLs incluent le workflow_id et que les captures asymétriques échouent."""
    from backend.core.config import Settings
    monkeypatch.setattr(Settings, "screenshots_dir", property(lambda self: tmp_path / "screenshots"))
    monkeypatch.setattr(Settings, "reports_dir", property(lambda self: tmp_path / "reports"))

    vrt = VRTManager("test_proj", workflow_id=42)

    # Créer les répertoires before et after
    base_dir = tmp_path / "screenshots" / "test_proj" / "42"
    before_dir = base_dir / "before"
    after_dir = base_dir / "after"
    before_dir.mkdir(parents=True, exist_ok=True)
    after_dir.mkdir(parents=True, exist_ok=True)

    # 1 paire normale (home_desktop.png)
    from PIL import Image
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    img.save(before_dir / "home_desktop.png")
    img.save(after_dir / "home_desktop.png")

    # 1 capture dans before absente dans after (crash de la page blog)
    img.save(before_dir / "blog_desktop.png")

    # 1 capture dans after absente dans before (nouvelle page)
    img.save(after_dir / "contact_mobile.png")

    report = await vrt.compare_all()

    # Vérifications
    assert report["total_pages"] == 3
    assert report["total_passed"] == 1
    assert report["total_failed"] == 2  # blog (manquant after) + contact (manquant before)

    items_by_page = {item["page_name"]: item for item in report["items"]}

    # URL du screenshot commun
    home_item = items_by_page["home"]
    assert home_item["passed"] is True
    assert home_item["before_path"] == "/static/data/screenshots/test_proj/42/before/home_desktop.png"
    assert home_item["after_path"] == "/static/data/screenshots/test_proj/42/after/home_desktop.png"
    assert home_item["diff_image"] == "/static/data/screenshots/test_proj/42/diff/diff_home_desktop.png"

    # Vérification capture manquante post-mise à jour
    blog_item = items_by_page["blog"]
    assert blog_item["passed"] is False
    assert blog_item["after_path"] is None
    assert blog_item["before_path"] == "/static/data/screenshots/test_proj/42/before/blog_desktop.png"
    assert "manquante" in blog_item["error"]


@pytest.mark.asyncio
async def test_backup_manager_lifecycle_and_orphan_cleanup(tmp_path):
    """Vérifie le cycle création/restauration/nettoyage de BackupManager et la purge des fichiers orphelins."""
    from backend.managers.backup_manager import BackupManager
    from backend.utils.command import CommandResult

    # Préparer une arborescence WordPress simulée
    wp_root = tmp_path / "wordpress"
    plugins_dir = wp_root / "wp-content" / "plugins" / "my-plugin"
    themes_dir = wp_root / "wp-content" / "themes" / "my-theme"
    core_dir = wp_root / "wp-admin"
    plugins_dir.mkdir(parents=True)
    themes_dir.mkdir(parents=True)
    core_dir.mkdir(parents=True)

    (plugins_dir / "plugin.php").write_text("<?php // v1.0", encoding="utf-8")
    (themes_dir / "style.css").write_text("/* theme v1.0 */", encoding="utf-8")
    (core_dir / "admin.php").write_text("<?php // admin core", encoding="utf-8")
    (wp_root / "index.php").write_text("<?php // index", encoding="utf-8")
    (wp_root / "wp-config.php").write_text("<?php // db config", encoding="utf-8")

    # Mocker DDEV
    mock_ddev = MagicMock()
    mock_ddev.create_snapshot = AsyncMock(return_value=CommandResult(returncode=0, stdout="Snapshot created", stderr="", command="ddev snapshot"))
    mock_ddev.restore_snapshot = AsyncMock(return_value=CommandResult(returncode=0, stdout="Snapshot restored", stderr="", command="ddev snapshot restore"))

    bm = BackupManager(
        project_name="test_proj",
        project_dir=wp_root,
        ddev=mock_ddev,
        workflow_id=123,
    )

    # 1. Création du backup
    backup_res = await bm.create_backup("pre_test_snap", backup_core=True)
    assert backup_res.success is True
    assert backup_res.tar_path is not None
    assert backup_res.tar_path.exists()
    assert mock_ddev.create_snapshot.called

    # 2. Simuler une mise à jour qui ajoute un fichier parasite/orphelin (ex: nouveau script ou version corrompue)
    (plugins_dir / "plugin.php").write_text("<?php // v2.0 (MODIFIED)", encoding="utf-8")
    (plugins_dir / "malicious_or_orphan.php").write_text("<?php // added file", encoding="utf-8")
    assert (plugins_dir / "malicious_or_orphan.php").exists()

    # 3. Restauration du backup
    restore_res = await bm.restore_backup(backup_res)
    assert restore_res.success is True
    assert restore_res.db_restored is True
    assert restore_res.files_restored is True
    assert mock_ddev.restore_snapshot.called

    # Le fichier originel doit être restauré à son état v1.0
    assert (plugins_dir / "plugin.php").read_text(encoding="utf-8") == "<?php // v1.0"
    # Le fichier orphelin ajouté par la mise à jour doit avoir été totalement supprimé
    assert not (plugins_dir / "malicious_or_orphan.php").exists()
    # wp-config.php ne doit pas avoir été corrompu
    assert (wp_root / "wp-config.php").read_text(encoding="utf-8") == "<?php // db config"

    # 4. Nettoyage
    await bm.cleanup_backup(backup_res)
    assert not backup_res.tar_path.exists()


@pytest.mark.asyncio
async def test_backup_manager_db_failure(tmp_path):
    """Vérifie que BackupManager échoue immédiatement si le snapshot DB échoue."""
    from backend.managers.backup_manager import BackupManager
    from backend.utils.command import CommandResult

    mock_ddev = MagicMock()
    mock_ddev.create_snapshot = AsyncMock(return_value=CommandResult(returncode=1, stdout="", stderr="MariaDB locked", command="ddev snapshot"))

    bm = BackupManager(
        project_name="fail_proj",
        project_dir=tmp_path,
        ddev=mock_ddev,
    )

    backup_res = await bm.create_backup("pre_fail_snap")
    assert backup_res.success is False
    assert "MariaDB locked" in backup_res.error
    assert backup_res.tar_path is None


@pytest.mark.asyncio
async def test_backup_manager_missing_archive_fails(tmp_path):
    """Vérifie qu'une archive inexistante est explicitement rejetée et n'est pas faussement déclarée restaurée."""
    from backend.managers.backup_manager import BackupManager, BackupResult
    from backend.utils.command import CommandResult

    mock_ddev = MagicMock()
    mock_ddev.restore_snapshot = AsyncMock(return_value=CommandResult(returncode=0, stdout="restored", stderr="", command="ddev snapshot restore"))

    bm = BackupManager(
        project_name="missing_tar_proj",
        project_dir=tmp_path,
        ddev=mock_ddev,
    )

    fake_backup = BackupResult(
        success=True,
        snapshot_name="test_snap",
        tar_path=tmp_path / "non_existent_archive.tar.gz",
        archived_folders=["wp-content/plugins"],
    )

    restore_res = await bm.restore_backup(fake_backup)
    assert restore_res.success is False
    assert restore_res.files_restored is False
    assert restore_res.db_restored is False
    assert not mock_ddev.restore_snapshot.called
    assert "introuvable" in restore_res.error


@pytest.mark.asyncio
async def test_backup_manager_corrupted_archive_does_not_amputate_site(tmp_path):
    """Vérifie qu'une archive corrompue n'ampute pas le site (aucun dossier n'est supprimé avant validation)."""
    from backend.managers.backup_manager import BackupManager, BackupResult
    from backend.utils.command import CommandResult

    mock_ddev = MagicMock()

    # Créer un dossier plugin avec un fichier sain
    plugin_dir = tmp_path / "wp-content" / "plugins" / "my-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.php").write_text("<?php // existing code", encoding="utf-8")

    # Créer une archive corrompue (fichier tar tronqué ou invalide)
    corrupted_tar = tmp_path / "corrupted.tar.gz"
    corrupted_tar.write_bytes(b"invalid gzip header random junk data 123456")

    bm = BackupManager(
        project_name="corrupt_proj",
        project_dir=tmp_path,
        ddev=mock_ddev,
    )

    corrupted_backup = BackupResult(
        success=True,
        snapshot_name="test_snap",
        tar_path=corrupted_tar,
        archived_folders=["wp-content/plugins"],
    )

    restore_res = await bm.restore_backup(corrupted_backup)
    assert restore_res.success is False
    assert restore_res.files_restored is False
    assert "corrompue" in restore_res.error.lower() or "impossible" in restore_res.error.lower()

    # Le site ne doit pas avoir été amputé : plugin.php doit toujours exister
    assert (plugin_dir / "plugin.php").exists()
    assert (plugin_dir / "plugin.php").read_text(encoding="utf-8") == "<?php // existing code"


@pytest.mark.asyncio
async def test_workflow_orchestrator_project_name_property():
    """Vérifie que WorkflowOrchestrator possède bien l'attribut/property project_name."""
    from backend.managers.workflow_orchestrator import WorkflowOrchestrator

    orchestrator = WorkflowOrchestrator(project_id=1, workflow_id=99)
    # Ne doit pas lever d'AttributeError
    assert hasattr(orchestrator, "project_name")
    assert orchestrator.project_name == ""

    # Test avec assignation
    orchestrator.project_name = "mon_super_projet"
    assert orchestrator.project_name == "mon_super_projet"

    # Test de fallback sur _wp si self._project_name est None
    orchestrator._project_name = None
    mock_wp = MagicMock()
    mock_wp.project_name = "fallback_project"
    orchestrator._wp = mock_wp
    assert orchestrator.project_name == "fallback_project"




