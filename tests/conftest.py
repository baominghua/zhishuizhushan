import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "human_auth_enabled: build the shared app client with human session authentication enabled",
    )


@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("REMOTE_SENSING_DATA_DIR", str(tmp_path / "remote-sensing"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REMOTE_SENSING_DATABASE_URL", raising=False)
    monkeypatch.delenv("SMART_BAMBOO_DATABASE_URL", raising=False)
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "json")
    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "0")
    yield tmp_path


@pytest.fixture()
def reload_platform_modules():
    def _reload():
        import server.modules.database as database
        import server.modules.settings as settings

        settings.get_settings.cache_clear()
        importlib.reload(settings)
        importlib.reload(database)
        settings.get_settings.cache_clear()
        return settings, database

    return _reload


@pytest.fixture()
def app_client(isolated_env, monkeypatch, request):
    import server.modules.settings as settings
    import server.modules.database as database

    human_auth_enabled = request.node.get_closest_marker("human_auth_enabled") is not None
    monkeypatch.setenv(
        "SMART_BAMBOO_HUMAN_AUTH_ENABLED",
        "1" if human_auth_enabled else "0",
    )
    settings.get_settings.cache_clear()
    importlib.reload(settings)
    importlib.reload(database)
    settings.get_settings.cache_clear()
    import server.app as app_module

    importlib.reload(app_module)
    settings.get_settings.cache_clear()
    import server.modules.auth as auth_module
    import server.modules.human_auth as human_auth_module

    auth_module.platform_settings.get_settings.cache_clear()
    human_auth_module.get_settings.cache_clear()
    return TestClient(app_module.app)
