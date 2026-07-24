from __future__ import annotations

import json
import importlib
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_root_routes_to_the_formal_smart_bamboo_dashboard(app_client):
    response = app_client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/zhushan-bigdata.html?v=20260716-interaction5"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["clear-site-data"] == '"cache"'


def test_legacy_index_route_cannot_bypass_the_formal_dashboard(app_client):
    response = app_client.get("/index.html", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/zhushan-bigdata.html?v=20260716-interaction5"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["clear-site-data"] == '"cache"'


def test_frontend_version_endpoint_matches_dashboard_release(app_client):
    response = app_client.get("/api/system/frontend-version")

    assert response.status_code == 200
    assert response.json() == {
        "dashboardVersion": "20260716-interaction5",
        "dashboardUrl": "/zhushan-bigdata.html?v=20260716-interaction5",
    }


def test_formal_dashboard_html_is_never_served_from_a_stale_browser_cache(app_client):
    response = app_client.get("/zhushan-bigdata.html")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"


def test_application_scripts_and_styles_are_never_served_from_a_stale_browser_cache(app_client):
    for path in ("/zhushan-bigdata.js", "/zhushan-bigdata.css", "/admin-business-module.js", "/admin.css"):
        response = app_client.get(path)

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store, max-age=0"
        assert response.headers["pragma"] == "no-cache"


def test_browser_clients_use_session_cookies_without_persisting_service_tokens():
    dashboard = read_text("zhushan-bigdata.js")
    mobile = read_text("zhushan-mobile.js")
    manager = read_text("satellite-manager.js")
    sdk = read_text("sdk/remote-sensing-sdk.js")

    assert 'localStorage.getItem("remoteSensingApiToken")' not in dashboard
    assert 'localStorage.getItem("remoteSensingApiToken")' not in mobile
    assert 'credentials: "include"' in dashboard
    assert 'credentials: "include"' in mobile

    for key in (
        "remoteSensingAuthToken",
        "remoteSensingAuthUser",
        "remoteSensingAuthRoles",
        "remoteSensingAuthScope",
    ):
        assert f'localStorage.getItem("{key}")' not in manager
        assert f'localStorage.setItem("{key}"' not in manager
        assert f'localStorage.removeItem("{key}")' in manager

    assert 'csrfToken: () => cookieValue("smart_bamboo_session_csrf")' in manager
    assert 'fetchOptions.credentials ||= this.credentials' in sdk
    assert 'requestHeaders["X-CSRF-Token"] = csrfToken' in sdk
    assert "csrfToken: options.csrfToken" in sdk


def test_docker_compose_uses_mysql_for_platform_data():
    compose = read_text("docker-compose.yml")

    assert "image: mysql:8.4" in compose
    assert 'SMART_BAMBOO_DEPLOYMENT_MODE: "${SMART_BAMBOO_DEPLOYMENT_MODE:-production}"' in compose
    assert 'SMART_BAMBOO_STORAGE_BACKEND: "${SMART_BAMBOO_STORAGE_BACKEND:-mysql}"' in compose
    assert 'SMART_BAMBOO_DATABASE_URL: "${SMART_BAMBOO_DATABASE_URL:?Set SMART_BAMBOO_DATABASE_URL in .env}"' in compose
    assert 'REMOTE_SENSING_CATALOG_BACKEND: "${REMOTE_SENSING_CATALOG_BACKEND:-mysql}"' in compose
    assert 'REMOTE_SENSING_DATABASE_URL: "${REMOTE_SENSING_DATABASE_URL:?Set REMOTE_SENSING_DATABASE_URL in .env}"' in compose
    assert 'REMOTE_SENSING_AUTH_REQUIRED: "${REMOTE_SENSING_AUTH_REQUIRED:-1}"' in compose
    assert 'REMOTE_SENSING_API_TOKENS: "${REMOTE_SENSING_API_TOKENS:?Set REMOTE_SENSING_API_TOKENS in .env}"' in compose
    assert 'REMOTE_SENSING_CORS_ORIGINS: "${REMOTE_SENSING_CORS_ORIGINS:?Set REMOTE_SENSING_CORS_ORIGINS in .env}"' in compose
    assert 'REMOTE_SENSING_DATA_DIR: "${REMOTE_SENSING_DATA_DIR:-/app/data/remote-sensing}"' in compose
    assert 'REMOTE_SENSING_IMPORT_DIRS: "${REMOTE_SENSING_IMPORT_DIRS:-/app/data/remote-sensing/inbox}"' in compose
    assert "curl -f http://127.0.0.1:8010/api/health" in compose


def test_docker_build_context_excludes_local_secrets_and_ui_audit_artifacts():
    dockerignore = read_text(".dockerignore")

    for pattern in [
        ".env",
        "satellite-config.local.js",
        ".edge-*",
        ".codex*",
        ".agents/",
        ".superpowers/",
        ".codex-ui-audit/",
        "ui-check-*.png",
        "server-*.log",
        "tests/",
    ]:
        assert pattern in dockerignore


def test_browser_service_tokens_are_explicitly_disabled_for_human_login_mode():
    dashboard = read_text("zhushan-bigdata.js")
    mobile = read_text("zhushan-mobile.js")
    primary_env = read_text("ops/scripts/generate-primary-env.sh")
    standby_env = read_text("ops/scripts/make-standby-env.sh")
    app_source = read_text("server/app.py")

    assert "ZHUSHAN_SDK_CONFIG.humanLoginEnabled === false" in dashboard
    assert "window.SATELLITE_CONFIG?.humanLoginEnabled === false" in mobile
    assert 'apiToken: "${dashboard_token}"' not in primary_env
    assert 'apiToken: "${dashboard_token}"' not in standby_env
    assert (
        "service_token_enabled = settings.auth_required and not settings.human_auth_enabled"
        in app_source
    )
    assert "dashboard_profile = token_profiles().get(dashboard_token)" in app_source
    assert 'dashboard_profile.user != "dashboard"' in app_source
    assert 'dashboard_profile.roles != {"viewer"}' in app_source


def test_production_python_dependencies_exclude_test_only_packages():
    production = read_text("server/requirements.txt")
    development = read_text("server/requirements-dev.txt")
    dockerfile = read_text("Dockerfile")

    assert "pytest" not in production.lower()
    assert "httpx" not in production.lower()
    assert "-r requirements.txt" in development
    assert "pytest>=8.2" in development
    assert "httpx>=0.27" in development
    assert "server/requirements.txt" in dockerfile
    assert "requirements-dev.txt" not in dockerfile


def test_env_example_documents_required_deployment_variables():
    env_example = read_text(".env.example")

    assert "SMART_BAMBOO_DEPLOYMENT_MODE=production" in env_example
    assert "SMART_BAMBOO_STORAGE_BACKEND=mysql" in env_example
    assert "SMART_BAMBOO_DATABASE_URL=mysql://smart_bamboo:change-me@db:3306/smart_bamboo" in env_example
    assert "REMOTE_SENSING_CATALOG_BACKEND=mysql" in env_example
    assert "REMOTE_SENSING_DATABASE_URL=mysql://smart_bamboo:change-me@db:3306/smart_bamboo" in env_example
    assert "REMOTE_SENSING_DATA_DIR=/app/data/remote-sensing" in env_example
    assert "REMOTE_SENSING_IMPORT_DIRS=/app/data/remote-sensing/inbox" in env_example
    assert "REMOTE_SENSING_AUTH_REQUIRED=1" in env_example
    assert "REMOTE_SENSING_CORS_ORIGINS=https://bamboo.example.gov.cn" in env_example


def test_production_configuration_rejects_json_open_auth_and_placeholder_credentials():
    from server.modules.settings import production_configuration_issues

    issues = production_configuration_issues(
        {
            "SMART_BAMBOO_DEPLOYMENT_MODE": "production",
            "SMART_BAMBOO_STORAGE_BACKEND": "json",
            "SMART_BAMBOO_DATABASE_URL": "mysql://smart_bamboo:change-me@db:3306/smart_bamboo",
            "REMOTE_SENSING_CATALOG_BACKEND": "json",
            "REMOTE_SENSING_DATABASE_URL": "",
            "REMOTE_SENSING_AUTH_REQUIRED": "0",
            "REMOTE_SENSING_API_TOKENS": "",
            "REMOTE_SENSING_CORS_ORIGINS": "*",
        }
    )

    assert {
        "platform_storage_not_mysql",
        "platform_database_placeholder_password",
        "catalog_storage_not_mysql",
        "catalog_database_missing",
        "auth_disabled",
        "auth_tokens_missing",
        "cors_wildcard",
    }.issubset(set(issues))


def test_production_configuration_accepts_mysql_auth_and_restricted_cors():
    from server.modules.settings import production_configuration_issues

    issues = production_configuration_issues(
        {
            "SMART_BAMBOO_DEPLOYMENT_MODE": "production",
            "SMART_BAMBOO_STORAGE_BACKEND": "mysql",
            "SMART_BAMBOO_DATABASE_URL": "mysql://smart_bamboo:Strong%21Pass-2026@db:3306/smart_bamboo",
            "REMOTE_SENSING_CATALOG_BACKEND": "mysql",
            "REMOTE_SENSING_DATABASE_URL": "mysql://smart_bamboo:Strong%21Pass-2026@db:3306/smart_bamboo",
            "REMOTE_SENSING_AUTH_REQUIRED": "1",
            "REMOTE_SENSING_API_TOKENS": '{"admin-token":{"user":"admin","roles":["admin"]}}',
            "REMOTE_SENSING_CORS_ORIGINS": "https://bamboo.example.gov.cn",
        }
    )

    assert issues == []


def test_runtime_human_auth_default_is_disabled_when_environment_is_missing(monkeypatch):
    from server.modules.settings import get_settings

    monkeypatch.delenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().human_auth_enabled is False
    finally:
        get_settings.cache_clear()


def test_production_configuration_rejects_enabled_human_auth_without_https_cookie_and_proxy_controls():
    from server.modules.settings import production_configuration_issues

    issues = production_configuration_issues(
        {
            "SMART_BAMBOO_DEPLOYMENT_MODE": "production",
            "SMART_BAMBOO_STORAGE_BACKEND": "mysql",
            "SMART_BAMBOO_DATABASE_URL": "mysql://smart_bamboo:Strong%21Pass-2026@db:3306/smart_bamboo",
            "REMOTE_SENSING_CATALOG_BACKEND": "mysql",
            "REMOTE_SENSING_DATABASE_URL": "mysql://smart_bamboo:Strong%21Pass-2026@db:3306/smart_bamboo",
            "REMOTE_SENSING_AUTH_REQUIRED": "1",
            "REMOTE_SENSING_API_TOKENS": '{"dashboard-token":{"user":"dashboard","roles":["viewer"]}}',
            "REMOTE_SENSING_CORS_ORIGINS": "https://bamboo.example.gov.cn",
            "SMART_BAMBOO_HUMAN_AUTH_ENABLED": "1",
            "SMART_BAMBOO_AUTH_REQUIRE_HTTPS": "0",
            "SMART_BAMBOO_TRUST_PROXY_HEADERS": "0",
            "SMART_BAMBOO_SESSION_COOKIE_SECURE": "0",
        }
    )

    assert {
        "human_auth_https_not_required",
        "human_auth_proxy_headers_untrusted",
        "human_auth_session_cookie_not_secure",
    }.issubset(set(issues))


def test_deployment_readiness_blocks_enabled_human_auth_until_transport_and_mysql_migration_are_ready(monkeypatch):
    import server.app as app_module
    import server.modules.settings as settings

    writable_dir = {"path": "data", "exists": True, "writable": True}
    deployment = {
        "database": {
            "platform": {"reachable": True, "schemaReady": True, "backend": "mysql"},
            "remoteSensingCatalog": {"reachable": True, "schemaReady": True, "backend": "mysql", "mysqlEnabled": True},
        },
        "smartBamboo": {"storageBackend": "mysql", "mysqlEnabled": True, "jsonData": {"dataDir": writable_dir}},
        "imagery": {"uploadDir": writable_dir, "cogDir": writable_dir, "importDirs": [writable_dir]},
        "auth": {"required": True, "tokensConfigured": 1},
        "apiChecks": [],
    }
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "1")
    monkeypatch.setenv("SMART_BAMBOO_DEPLOYMENT_MODE", "production")
    monkeypatch.setenv("SMART_BAMBOO_AUTH_REQUIRE_HTTPS", "0")
    monkeypatch.setenv("SMART_BAMBOO_TRUST_PROXY_HEADERS", "0")
    monkeypatch.setenv("SMART_BAMBOO_SESSION_COOKIE_SECURE", "0")
    settings.get_settings.cache_clear()
    monkeypatch.setattr(
        app_module,
        "human_auth_storage_readiness",
        lambda: {"backend": "mysql", "reachable": True, "credentialTable": False, "sessionTable": False, "activeAdminCredential": False},
    )

    readiness = app_module.deployment_readiness_summary(deployment)

    assert readiness["status"] == "blocked"
    assert {
        "human_auth_https_not_required",
        "human_auth_proxy_headers_untrusted",
        "human_auth_session_cookie_not_secure",
        "human_auth_credentials_table_missing",
        "human_auth_sessions_table_missing",
        "human_auth_active_admin_credential_missing",
    }.issubset({item["key"] for item in readiness["blockingIssues"]})
    settings.get_settings.cache_clear()


def test_deployment_readiness_allows_disabled_human_auth_with_https_pending_warning(monkeypatch):
    import server.app as app_module
    import server.modules.settings as settings

    writable_dir = {"path": "data", "exists": True, "writable": True}
    deployment = {
        "database": {
            "platform": {"reachable": True, "schemaReady": True, "backend": "mysql"},
            "remoteSensingCatalog": {"reachable": True, "schemaReady": True, "backend": "mysql", "mysqlEnabled": True},
        },
        "smartBamboo": {"storageBackend": "mysql", "mysqlEnabled": True, "jsonData": {"dataDir": writable_dir}},
        "imagery": {"uploadDir": writable_dir, "cogDir": writable_dir, "importDirs": [writable_dir]},
        "auth": {"required": True, "tokensConfigured": 1},
        "apiChecks": [],
    }
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "0")
    monkeypatch.setenv("SMART_BAMBOO_DEPLOYMENT_MODE", "production")
    monkeypatch.setenv("SMART_BAMBOO_AUTH_REQUIRE_HTTPS", "1")
    monkeypatch.setenv("SMART_BAMBOO_TRUST_PROXY_HEADERS", "1")
    monkeypatch.setenv("SMART_BAMBOO_SESSION_COOKIE_SECURE", "1")
    settings.get_settings.cache_clear()
    monkeypatch.setattr(app_module.app.state, "startup_errors", [], raising=False)
    monkeypatch.setattr(
        app_module,
        "human_auth_storage_readiness",
        lambda: {"backend": "json", "reachable": False, "credentialTable": False, "sessionTable": False, "activeAdminCredential": False},
    )

    readiness = app_module.deployment_readiness_summary(deployment)

    assert readiness["blockingIssueCount"] == 0
    assert any(item["key"] == "human_auth_pending_https" for item in readiness["warnings"])
    settings.get_settings.cache_clear()


def test_application_bootstrap_enforces_production_configuration():
    app_source = read_text("server/app.py")

    assert "enforce_production_configuration()" in app_source


def test_deployment_doc_describes_mysql_platform_and_health_probe():
    doc = read_text("docs/deploy-smart-bamboo-platform.md")
    checklist = read_text("docs/smart-bamboo-production-checklist.md")

    assert "SMART_BAMBOO_STORAGE_BACKEND=mysql" in doc
    assert "SMART_BAMBOO_DATABASE_URL" in doc
    assert "MySQL 8" in doc
    assert "遥感影像目录" in doc
    assert "docker compose config" in doc
    assert "app healthcheck" in doc
    assert "deployment.database.platform.reachable" in doc
    assert "deployment.database.remoteSensingCatalog.schemaReady" in doc
    assert "deployment.smartBamboo.jsonData.datasets" in doc
    assert "deployment.imagery.catalog.recordCount" in doc
    assert "deployment.imagery.importDirs" in doc
    assert "deployment.readiness.status" in doc
    assert "deployment.readiness.blockingIssues" in doc
    assert "deployment.readiness.warnings" in doc
    assert "database_credentials_default" in doc
    assert "deployment.apiChecks" in doc
    assert "deployment.database.platform.reachable" in checklist
    assert "deployment.smartBamboo.jsonData.datasets" in checklist
    assert "deployment.imagery.catalog.recordCount" in checklist
    assert "deployment.readiness.status" in checklist
    assert "database_credentials_default" in checklist
    assert "deployment.apiChecks" in checklist
    assert "/api/forest-blocks/{block_id}/versions" in checklist
    assert "/api/forest-blocks/{block_id}/rollback" in checklist
    assert "/api/forest-rights/{right_id}/versions" in checklist
    assert "/api/forest-rights/{right_id}/rollback" in checklist


def test_health_payload_exposes_first_stage_data_inventory(app_client, isolated_env):
    data_dir = isolated_env / "remote-sensing"
    (data_dir / "forest-blocks" / "forest_blocks.json").write_text(
        json.dumps(
            [
                {"id": "block-active", "blockCode": "BLOCK-001"},
                {"id": "block-deleted", "blockCode": "BLOCK-002", "deletedAt": "2026-01-01T00:00:00Z"},
            ]
        ),
        encoding="utf-8",
    )
    (data_dir / "forest-rights" / "forest_rights.json").write_text(
        json.dumps([{"id": "right-active", "archiveCode": "RIGHT-001"}]),
        encoding="utf-8",
    )
    (data_dir / "business" / "farmers.json").write_text(
        json.dumps([{"id": "farmer-active", "recordCode": "FARMER-001"}]),
        encoding="utf-8",
    )
    (data_dir / "map-layers" / "map_layers.json").write_text(
        json.dumps([{"id": "layer-active", "recordCode": "LAYER-001"}]),
        encoding="utf-8",
    )
    (data_dir / "imports" / "import_batches.json").write_text(
        json.dumps([{"id": "batch-active", "fileName": "blocks.kmz"}]),
        encoding="utf-8",
    )
    (data_dir / "catalog.json").write_text(
        json.dumps({"scenes": [{"id": "scene-active"}, {"id": "scene-archived", "deletedAt": "2026-01-01T00:00:00Z"}]}),
        encoding="utf-8",
    )
    (data_dir / "tasks.json").write_text(
        json.dumps({"tasks": [{"id": "task-active"}]}),
        encoding="utf-8",
    )

    response = app_client.get("/api/health")

    assert response.status_code == 200
    deployment = response.json()["deployment"]
    smart_bamboo = deployment["smartBamboo"]
    datasets = {item["key"]: item for item in smart_bamboo["jsonData"]["datasets"]}
    assert datasets["forestBlocks"]["recordCount"] == 1
    assert datasets["forestBlocks"]["deletedCount"] == 1
    assert datasets["forestRights"]["recordCount"] == 1
    assert datasets["mapLayers"]["recordCount"] == 1
    assert datasets["importBatches"]["recordCount"] == 1
    assert datasets["businessRecords"]["recordCount"] == 1
    assert smart_bamboo["jsonData"]["businessModules"][0]["key"] == "farmers"
    assert smart_bamboo["jsonData"]["businessModules"][0]["recordCount"] == 1

    imagery = deployment["imagery"]
    assert imagery["catalog"]["recordCount"] == 1
    assert imagery["catalog"]["deletedCount"] == 1
    assert imagery["tasks"]["recordCount"] == 1
    assert imagery["uploadDir"]["exists"] is True
    assert imagery["cogDir"]["exists"] is True
    assert all(item["exists"] and "writable" in item for item in imagery["importDirs"])


def test_health_payload_exposes_deployment_readiness_summary(app_client):
    response = app_client.get("/api/health")

    assert response.status_code == 200
    readiness = response.json()["deployment"]["readiness"]
    assert readiness["status"] == "warning"
    assert readiness["blockingIssueCount"] == 0
    assert readiness["warningCount"] >= 1
    assert {item["key"] for item in readiness["checks"]}.issuperset(
        {
            "platform_database",
            "remote_sensing_catalog",
            "data_root",
            "storage_backend",
            "database_credentials",
            "auth_tokens",
            "imagery_import_dirs",
        }
    )
    assert any(item["key"] == "storage_backend_json" for item in readiness["warnings"])
    assert any(item["key"] == "auth_disabled" for item in readiness["warnings"])


def test_placeholder_database_credentials_are_detected_without_exposing_passwords():
    from server.app import placeholder_database_credential_names

    names = placeholder_database_credential_names(
        {
            "platform": "mysql://smart_bamboo:smart_bamboo_dev@db:3306/smart_bamboo",
            "catalog": "mysql://smart_bamboo:change-me@db:3306/smart_bamboo",
            "secure": "mysql://smart_bamboo:S3cure-Random-Value@db:3306/smart_bamboo",
        }
    )

    assert names == ["catalog", "platform"]


def test_deployment_readiness_warns_when_mysql_uses_placeholder_credentials(monkeypatch):
    import server.app as app_module

    monkeypatch.setenv(
        "SMART_BAMBOO_DATABASE_URL",
        "mysql://smart_bamboo:smart_bamboo_dev@db:3306/smart_bamboo",
    )
    monkeypatch.setenv(
        "REMOTE_SENSING_DATABASE_URL",
        "mysql://smart_bamboo:change-me@db:3306/smart_bamboo",
    )
    writable_dir = {"path": "data", "exists": True, "writable": True}
    deployment = {
        "database": {
            "platform": {"reachable": True, "schemaReady": True, "backend": "mysql"},
            "remoteSensingCatalog": {
                "reachable": True,
                "schemaReady": True,
                "backend": "mysql",
                "mysqlEnabled": True,
            },
        },
        "smartBamboo": {
            "storageBackend": "mysql",
            "mysqlEnabled": True,
            "jsonData": {"dataDir": writable_dir},
        },
        "imagery": {
            "uploadDir": writable_dir,
            "cogDir": writable_dir,
            "importDirs": [writable_dir],
        },
        "auth": {"required": True, "tokensConfigured": 1},
        "apiChecks": [],
    }

    readiness = app_module.deployment_readiness_summary(deployment)

    issue = next(item for item in readiness["warnings"] if item["key"] == "database_credentials_default")
    assert readiness["status"] == "warning"
    assert "catalog" in issue["message"]
    assert "platform" in issue["message"]
    assert "smart_bamboo_dev" not in issue["message"]
    assert "change-me" not in issue["message"]


def test_health_payload_exposes_core_api_deployment_checks(app_client):
    response = app_client.get("/api/health")

    assert response.status_code == 200
    deployment = response.json()["deployment"]
    api_checks = {item["key"]: item for item in deployment["apiChecks"]}
    assert api_checks["forest_blocks"]["path"] == "/api/forest-blocks"
    assert api_checks["forest_blocks"]["group"] == "spatial-rights"
    assert api_checks["forest_blocks"]["groupLabel"] == "空间与权属"
    assert api_checks["forest_block_aggregates"]["path"] == "/api/map/forest-blocks/aggregates"
    assert api_checks["forest_block_aggregates"]["group"] == "spatial-rights"
    assert api_checks["forest_block_aggregates"]["permission"] == "forest.blocks.view"
    assert api_checks["forest_rights"]["path"] == "/api/forest-rights"
    assert api_checks["map_layers"]["path"] == "/api/map-layers"
    assert api_checks["import_batches"]["path"] == "/api/imports/forest-blocks/batches"
    assert api_checks["import_batches"]["group"] == "imports"
    assert api_checks["import_batches"]["groupLabel"] == "成果入库"
    assert api_checks["import_batch_targets"]["path"] == "/api/imports/{batch_id}/targets"
    assert api_checks["delivery_packages"]["path"] == "/api/imports/forest-blocks/delivery-packages"
    assert api_checks["import_workflow_summary"]["path"] == "/api/imports/forest-blocks/workflow-summary"
    assert api_checks["import_operation_queue"]["path"] == "/api/imports/forest-blocks/operation-queue"
    assert api_checks["import_quality_issues"]["path"] == "/api/imports/forest-blocks/quality-issues"
    assert api_checks["dashboard_satellite_track"]["path"] == "/api/dashboard/satellite-track"
    assert api_checks["dashboard_satellite_track"]["group"] == "dashboard"
    assert api_checks["dashboard_satellite_track"]["permission"] == "公开只读"
    assert api_checks["dashboard_workflow_status"]["path"] == "/api/dashboard/workflow-status"
    assert api_checks["dashboard_workflow_status"]["group"] == "dashboard"
    assert api_checks["dashboard_workflow_status"]["permission"] == "公开只读"
    assert api_checks["imagery_scenes"]["path"] == "/api/scenes"
    assert api_checks["imagery_scenes"]["group"] == "imagery"
    assert api_checks["imagery_scenes"]["groupLabel"] == "影像管理"
    assert api_checks["imagery_workflow_summary"]["path"] == "/api/scenes/workflow-summary"
    assert api_checks["imagery_operation_queue"]["path"] == "/api/scenes/operation-queue"
    assert api_checks["imagery_quality_issues"]["path"] == "/api/scenes/quality-issues"
    assert api_checks["permission_catalog"]["path"] == "/api/admin/permission-catalog"
    assert api_checks["permission_catalog"]["group"] == "permission-system"
    assert api_checks["permission_catalog"]["groupLabel"] == "权限系统"
    assert api_checks["role_operation_queue"]["path"] == "/api/admin/roles/operation-queue"
    assert api_checks["role_operation_queue"]["permission"] == "system.roles.manage"
    assert api_checks["user_operation_queue"]["path"] == "/api/admin/users/operation-queue"
    assert api_checks["user_operation_queue"]["permission"] == "system.users.manage"
    assert all(item["available"] for item in api_checks.values())

    readiness_checks = {item["key"]: item for item in deployment["readiness"]["checks"]}
    assert readiness_checks["core_api_routes"]["status"] == "pass"
    assert "delivery_packages" in readiness_checks["core_api_routes"]["message"]
    assert "import_operation_queue" in readiness_checks["core_api_routes"]["message"]
    assert "imagery_operation_queue" in readiness_checks["core_api_routes"]["message"]
    assert "dashboard_satellite_track" in readiness_checks["core_api_routes"]["message"]
    assert "role_operation_queue" in readiness_checks["core_api_routes"]["message"]
    assert "user_operation_queue" in readiness_checks["core_api_routes"]["message"]


def test_route_inventory_uses_fastapi_effective_route_contexts(monkeypatch):
    import server.app as app_module

    class LazyRouteContext:
        path = "/api/lazy-router-endpoint"
        methods = {"GET", "HEAD"}

    monkeypatch.setattr(app_module.app.router, "routes", [object()])
    monkeypatch.setattr(
        app_module,
        "fastapi_iter_route_contexts",
        lambda routes: [LazyRouteContext()],
        raising=False,
    )

    assert app_module.route_methods_by_path() == {
        "/api/lazy-router-endpoint": {"GET", "HEAD"},
    }


def test_deployment_report_can_be_exported_with_view_permission(app_client):
    denied = app_client.get(
        "/api/deployment/report.json",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    exported = app_client.get(
        "/api/deployment/report.json",
        headers={"X-RS-Roles": "system.deployment.view"},
    )

    assert denied.status_code == 403
    assert "system.deployment.view" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert "deployment-report.json" in exported.headers["content-disposition"]
    body = exported.json()
    assert body["service"] == "remote-sensing-cog"
    assert "deployment" in body
    assert "readiness" in body["deployment"]
    assert "dependencies" in body


def test_health_payload_marks_readiness_blocked_when_mysql_is_unreachable(
    isolated_env, monkeypatch
):
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "mysql")
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "mysql://invalid:invalid@invalid-host:3306/smart_bamboo")
    monkeypatch.setenv("REMOTE_SENSING_CATALOG_BACKEND", "json")
    monkeypatch.delenv("REMOTE_SENSING_DATABASE_URL", raising=False)

    import server.modules.settings as settings
    import server.modules.database as database
    import server.app as app_module

    settings.get_settings.cache_clear()
    importlib.reload(settings)
    importlib.reload(database)
    importlib.reload(app_module)
    settings.get_settings.cache_clear()
    client = TestClient(app_module.app)

    response = client.get("/api/health")

    assert response.status_code == 503
    readiness = response.json()["deployment"]["readiness"]
    assert readiness["status"] == "blocked"
    assert readiness["blockingIssueCount"] >= 1
    assert any(item["key"] == "platform_database_unreachable" for item in readiness["blockingIssues"])


def test_admin_overview_surfaces_deployment_summary_and_links_to_diagnostics():
    html = read_text("admin.html")
    js = read_text("admin-dashboard.js")

    assert 'id="metricHealth"' in html
    assert 'id="metricStorage"' in html
    assert 'id="metricCatalog"' in html
    assert 'href="admin-deployment.html"' in html
    assert 'id="deploymentHealthPanel"' not in html
    assert 'id="deploymentHealthRows"' not in html
    assert "/api/health" in js
    assert "function renderDeploymentHealth" in js
    assert "deployment.database.platform" in js
    assert "deployment.database.remoteSensingCatalog" in js
    assert "deployment.smartBamboo.storageBackend" in js
    assert "deployment.imagery.catalog" in js


def test_admin_overview_metrics_include_import_batches_and_imagery_scenes():
    html = read_text("admin.html")
    js = read_text("admin-dashboard.js")

    assert 'id="metricImports"' in html
    assert 'id="metricScenes"' in html
    assert "/api/imports/forest-blocks/batches?limit=1" in js
    assert "/api/scenes?limit=1" in js
    assert "metricImports" in js
    assert "metricScenes" in js


def test_admin_overview_surfaces_import_and_imagery_work_queue():
    html = read_text("admin.html")
    js = read_text("admin-dashboard.js")
    css = read_text("admin.css")

    assert 'id="platformWorkQueue"' in html
    assert 'id="refreshWorkQueue"' in html
    assert 'id="workQueueRows"' in html
    assert "work-queue-table-wrap" in html
    assert ".work-queue-table-wrap table" in css
    assert "table-layout: fixed;" in css
    assert ".work-queue-table-wrap {" in css
    assert "overflow-x: hidden;" in css
    assert "function loadWorkQueue" in js
    assert "function renderWorkQueueRows" in js
    assert "/api/imports/forest-blocks/batches?reviewStatus=pending&limit=5" in js
    assert "/api/imports/forest-blocks/quality-issues?status=open&limit=5" in js
    assert "/api/scenes/operation-queue?limit=3" in js
    assert "function imageryOperationQueueRows" in js
    assert "admin-imports.html?batchId=" in js
    assert "qualityIssueId=" in js
    assert "admin-imagery.html?taskId=" in js
    assert "admin-imagery.html?sceneId=" in js
    assert "imageryIssueId=" in js
    assert "renderWorkQueueRows(rows)" in js


def test_admin_overview_metric_requests_are_permission_tolerant():
    js = read_text("admin-dashboard.js")

    assert "async function loadMetricTotal" in js
    assert "await loadMetricTotal(\"/api/forest-blocks?limit=1\")" in js
    assert "await loadMetricTotal(\"/api/imports/forest-blocks/batches?limit=1\")" in js
    assert "return 0" in js
    assert "Promise.all([" not in js


def test_admin_deployment_module_is_independent_permission_page():
    html = read_text("admin-deployment.html")
    js = read_text("admin-deployment.js")

    assert 'data-admin-module="deployment"' in html
    assert 'data-permission="system.deployment.view"' in html
    assert 'href="admin-deployment.html"' in html
    assert 'id="deploymentRows"' in html
    assert 'id="dependencyRows"' in html
    assert 'id="datasetRows"' in html
    assert 'id="cacheRows"' in html
    assert 'id="apiCheckPanel"' in html
    assert 'id="apiCheckRows"' in html
    assert 'id="readinessRows"' in html
    assert html.index('id="deploymentRows"') < html.index('id="apiCheckPanel"') < html.index('id="dependencyRows"')
    assert 'id="reloadDeployment"' in html
    assert 'id="exportDeploymentReport"' in html
    assert "/api/health" in js
    assert "/api/deployment/report.json" in js
    assert "function fetchDeploymentHealth" in js
    assert "function exportDeploymentReport" in js
    assert "function renderReadinessRows" in js
    assert "deployment.readiness" in js
    assert "function renderDeploymentRows" in js
    assert "function renderDependencyRows" in js
    assert "function renderDatasetRows" in js
    assert "function renderCacheRows" in js
    assert "function renderApiCheckRows" in js
    assert "deployment.apiChecks" in js
    assert "deployment.database.platform" in js
    assert "deployment.smartBamboo.jsonData.datasets" in js
    assert "deployment.imagery.catalog" in js
    assert "deployment.tileCache" in js
    assert "system.deployment.view" in js
    assert '$("#exportDeploymentReport")?.addEventListener("click", exportDeploymentReport)' in js
