"""
Tests unitaires pour backend/managers
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.managers.hosts_manager import HostsManager, HOSTS_MARKER_START, HOSTS_MARKER_END
from backend.managers.queue_manager import WorkflowQueueManager, queue_manager


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

