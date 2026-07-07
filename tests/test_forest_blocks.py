from server.modules.settings import get_settings


def test_platform_settings_use_json_fallback(isolated_env):
    settings = get_settings()
    assert settings.storage_backend == "json"
    assert settings.database_url == ""
    assert settings.data_dir.name == "remote-sensing"


def test_health_includes_platform_schema_status(app_client):
    response = app_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "deployment" in body
    assert "smartBamboo" in body["deployment"]
