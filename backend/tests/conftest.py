"""
Fixtures pytest pour les tests backend de l'application Auto Maintenance.
"""

import sys
from pathlib import Path
import pytest
import pytest_asyncio

# Ajouter auto_maintenance au path Python pour que backend.* soit résolu
auto_maintenance_dir = Path(__file__).resolve().parent.parent.parent
if str(auto_maintenance_dir) not in sys.path:
    sys.path.insert(0, str(auto_maintenance_dir))

from backend.core.config import settings

# S'assurer que la BDD pointe sur une base en mémoire avec répertoires isolés pour TOUS les imports
settings.database_url = "sqlite+aiosqlite:///:memory:"
settings.data_dir.mkdir(parents=True, exist_ok=True)

from httpx import ASGITransport, AsyncClient
import backend.models.database as db_mod
from backend.main import app


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path):
    """Configure un environnement temporaire isolé pour chaque test."""
    original_projects_dir = settings.ddev_projects_dir
    settings.ddev_projects_dir = tmp_path / "ddev-projects"
    settings.ddev_projects_dir.mkdir(parents=True, exist_ok=True)
    
    yield
    
    settings.ddev_projects_dir = original_projects_dir


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Initialise les tables dans la BDD pour les tests."""
    await db_mod.init_db()
    yield


@pytest_asyncio.fixture
async def async_client():
    """Client de test HTTP asynchrone pour FastAPI."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
