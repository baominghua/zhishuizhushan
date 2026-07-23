from pathlib import Path
import json
import re
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


COMPOSE_VARIABLE = re.compile(r"^\$\{(?P<name>[A-Z0-9_]+)(?::-(?P<default>[^}]*))?\}$")


def compose_app_environment(path: str, environ: dict[str, str] | None = None) -> dict[str, str]:
    compose = yaml.safe_load(read_text(path))
    raw_environment = compose["services"]["app"]["environment"]
    values = dict(environ or {})
    expanded: dict[str, str] = {}
    for key, value in raw_environment.items():
        match = COMPOSE_VARIABLE.match(str(value))
        if match is None:
            expanded[key] = str(value)
        else:
            expanded[key] = values.get(match["name"], match["default"] or "")
    return expanded


def compose_document(path: str) -> dict:
    return yaml.safe_load(read_text(path))


def test_public_deployment_branch_excludes_secrets_and_operational_data():
    gitignore = read_text(".gitignore")
    dockerignore = read_text(".dockerignore")

    for pattern in [
        ".env",
        ".env.*",
        "data/*",
        "!data/samples/",
        "*.sql",
        "*.sql.gz",
        "*.enc",
        "backups/",
        "*.pem",
        "*.key",
    ]:
        assert pattern in gitignore

    for pattern in ["data/", "*.sql", "*.sql.gz", "*.enc", "*.pem", "*.key"]:
        assert pattern in dockerignore


def test_primary_compose_exposes_only_nginx_publicly():
    compose = read_text("ops/compose.primary.yml")

    assert "image: mysql:8.4.9" in compose
    assert "image: nginx:1.30.4-alpine" in compose
    assert "image: docker.osgeo.org/geoserver:2.25.7" in compose
    assert '"192.168.0.32:3306:3306"' in compose
    assert '"127.0.0.1:8010:8010"' in compose
    assert '"127.0.0.1:8080:8080"' in compose
    assert '"0.0.0.0:80:80"' in compose
    assert "/srv/smart-bamboo/mysql:/var/lib/mysql" in compose
    assert "/srv/smart-bamboo/data:/app/data" in compose
    assert "/srv/smart-bamboo/geoserver:/opt/geoserver_data" in compose
    assert "3307:3306" not in compose
    assert "8080:8080" not in compose.replace('"127.0.0.1:8080:8080"', "")


def test_standby_compose_stays_dormant_until_manual_failover():
    compose = read_text("ops/compose.standby.yml")

    assert "image: mysql:8.4.9" in compose
    assert "/srv/smart-bamboo-dr/mysql-replica:/var/lib/mysql" in compose
    assert "/srv/smart-bamboo-dr/data:/app/data" in compose
    assert 'profiles: ["failover"]' in compose
    assert '"127.0.0.1:8010:8010"' in compose
    assert '"0.0.0.0:80:80"' in compose
    assert "3306:3306" not in compose


@pytest.mark.parametrize(
    ("compose_path", "mysql_config"),
    [
        ("ops/compose.primary.yml", "primary.cnf"),
        ("ops/compose.standby.yml", "replica.cnf"),
    ],
)
def test_compose_paths_resolve_from_repository_project_directory(
    compose_path: str,
    mysql_config: str,
):
    compose = read_text(compose_path)

    assert "context: ." in compose
    assert "context: .." not in compose
    assert f"./ops/mysql/{mysql_config}:/etc/mysql/conf.d/replication.cnf:ro" in compose
    assert "./ops/nginx/smart-bamboo.conf:/etc/nginx/conf.d/default.conf:ro" in compose


def test_mysql_replication_configs_use_gtid_and_read_only_replica():
    primary = read_text("ops/mysql/primary.cnf")
    replica = read_text("ops/mysql/replica.cnf")

    assert "server-id=1" in primary
    assert "log_bin=mysql-bin" in primary
    assert "binlog_format=ROW" in primary
    assert "gtid_mode=ON" in primary
    assert "enforce_gtid_consistency=ON" in primary
    assert "server-id=2" in replica
    assert "relay_log=relay-bin" in replica
    assert "read_only=ON" in replica
    assert "super_read_only=ON" in replica
    assert "skip_replica_start=ON" in replica


def test_disk_bootstrap_requires_explicit_empty_disk_confirmation():
    script = read_text("ops/scripts/prepare-data-disk.sh")

    assert 'DEVICE="${DEVICE:-/dev/sdb}"' in script
    assert 'CONFIRM_FORMAT_EMPTY_DISK="YES"' in script
    assert "lsblk" in script
    assert "wipefs -n" in script
    assert "findmnt" in script
    assert "mklabel gpt" in script
    assert "mkfs.xfs" in script
    assert "/srv/smart-bamboo" in script
    assert "/srv/smart-bamboo-dr" in script
    assert "UUID=" in script
    assert "/etc/fstab" in script
    assert 'label="bamboo-pri"' in script
    assert 'label="bamboo-dr"' in script


def test_bclinux_install_script_installs_pinned_docker_tooling():
    script = read_text("ops/scripts/install-docker-bclinux.sh")

    assert "BigCloud Enterprise Linux" in script
    assert "download.docker.com/linux/rhel/8/x86_64/stable/Packages" in script
    assert "docker-ce-29.6.2-1.el8.x86_64.rpm" in script
    assert "docker-ce-cli-29.6.2-1.el8.x86_64.rpm" in script
    assert "containerd.io-2.2.6-1.el8.x86_64.rpm" in script
    assert "docker-buildx-plugin-0.35.0-1.el8.x86_64.rpm" in script
    assert "docker-compose-plugin-5.3.1-1.el8.x86_64.rpm" in script
    assert "--retry-all-errors" in script
    assert "download.docker.com/linux/rhel/gpg" in script
    assert "060A61C51B558A7F742B77AAC52FEB6B621E9F35" in script
    assert "--show-keys" in script
    assert "rpm --import" in script
    assert "rpm -Kv" in script
    assert "--disablerepo=docker-ce-stable" in script
    assert "systemctl enable --now docker" in script
    assert "docker compose version" in script


def test_cluster_operations_cover_replication_backup_monitoring_and_failover():
    initialize = read_text("ops/scripts/initialize-replica.sh")
    verify = read_text("ops/scripts/verify-cluster.sh")
    backup = read_text("ops/scripts/backup-mysql.sh")
    watch = read_text("ops/scripts/health-watch.sh")
    promote = read_text("ops/scripts/promote-standby.sh")
    migrate = read_text("ops/scripts/migrate-private-data.sh")

    assert "SOURCE_AUTO_POSITION=1" in initialize
    assert "START REPLICA" in initialize
    assert "RESET BINARY LOGS AND GTIDS" in initialize
    assert "Replica_IO_Running" in verify
    assert "Replica_SQL_Running" in verify
    assert "super_read_only" in verify
    assert "mysqldump" in backup
    assert "sha256sum" in backup
    assert "/api/health" in watch
    assert "STOP REPLICA" in promote
    assert "RESET REPLICA ALL" in promote
    assert "CONFIRM_PRIMARY_UNAVAILABLE=YES" in promote
    assert "--build" not in promote
    assert "sha256sum -c" in migrate
    assert "migrate_json_to_mysql.py" in migrate


def test_cloud_runbook_is_checkpointed_for_console_execution():
    runbook = read_text("ops/README.md")

    for heading in [
        "检查点 0：安全组与云服务",
        "检查点 1：磁盘与 Docker",
        "检查点 2：高配主节点",
        "检查点 3：低配热备节点",
        "检查点 4：私有数据迁移",
        "检查点 5：备份与容灾演练",
    ]:
        assert heading in runbook
    assert "未经检查不得继续下一检查点" in runbook
    assert "36.140.138.117" in runbook
    assert "36.137.23.53" in runbook
    assert "192.168.0.32" in runbook
    assert "192.168.0.104" in runbook


def test_private_bundle_round_trip_encrypts_data_and_excludes_generated_cache(tmp_path):
    from ops.tools.private_bundle import create_bundle, extract_bundle

    source = tmp_path / "data"
    (source / "forest-rights").mkdir(parents=True)
    (source / "forest-rights" / "rights.json").write_text("secret-right", encoding="utf-8")
    (source / "remote-sensing" / "basemap-cache").mkdir(parents=True)
    (source / "remote-sensing" / "basemap-cache" / "tile.png").write_bytes(b"cache")
    (source / "remote-sensing" / "server.log").write_text("generated", encoding="utf-8")
    bundle = tmp_path / "private-data.sbbundle"

    create_bundle(source, bundle, "correct horse battery staple")
    assert bundle.read_bytes()[:4] == b"SBB1"
    assert (tmp_path / "private-data.sbbundle.sha256").is_file()

    destination = tmp_path / "restored"
    extract_bundle(bundle, destination, "correct horse battery staple")
    assert (destination / "data" / "forest-rights" / "rights.json").read_text(encoding="utf-8") == "secret-right"
    assert not (destination / "data" / "remote-sensing" / "basemap-cache").exists()
    assert not (destination / "data" / "remote-sensing" / "server.log").exists()

    with pytest.raises(ValueError, match="passphrase|authentication"):
        extract_bundle(bundle, tmp_path / "wrong", "wrong passphrase")


def test_systemd_units_schedule_backup_upload_and_health_monitoring():
    backup_service = read_text("ops/systemd/smart-bamboo-backup.service")
    backup_timer = read_text("ops/systemd/smart-bamboo-backup.timer")
    health_service = read_text("ops/systemd/smart-bamboo-health.service")
    health_timer = read_text("ops/systemd/smart-bamboo-health.timer")
    installer = read_text("ops/scripts/install-systemd-units.sh")
    uploader = read_text("ops/scripts/upload-backups.sh")

    assert "backup-mysql.sh" in backup_service
    assert "upload-backups.sh" in backup_service
    assert "OnCalendar=*-*-* 02:15:00" in backup_timer
    assert "Persistent=true" in backup_timer
    assert "health-watch.sh" in health_service
    assert "OnUnitActiveSec=60s" in health_timer
    assert "systemctl enable --now smart-bamboo-backup.timer" in installer
    assert "systemctl enable --now smart-bamboo-health.timer" in installer
    assert "RCLONE_BACKUP_REMOTE" in uploader
    assert "rclone/rclone:" in uploader


def test_production_frontends_use_same_origin_and_a_read_only_dashboard_token():
    primary_compose = read_text("ops/compose.primary.yml")
    primary_env = read_text("ops/scripts/generate-primary-env.sh")
    standby_env = read_text("ops/scripts/make-standby-env.sh")
    admin_common = read_text("admin-common.js")
    admin_login = read_text("admin-login.js")
    dashboard = read_text("zhushan-bigdata.js")
    mobile_html = read_text("zhushan-mobile.html")
    mobile = read_text("zhushan-mobile.js")

    assert "SMART_BAMBOO_DASHBOARD_TOKEN" in primary_env
    assert '"roles":["viewer"]' in primary_env
    assert "satellite-config.local.js" in primary_env
    assert "satellite-config.local.js" in standby_env
    assert "/srv/smart-bamboo/config/satellite-config.local.js:/app/satellite-config.local.js:ro" in primary_compose
    assert 'SKIP_DEMO_DATA: "true"' in primary_compose
    assert 'RUN_UNPRIVILEGED: "true"' in primary_compose
    assert 'window.location.origin' in admin_common
    assert 'window.location.origin' in admin_login
    assert "function zhushanApiFetch" in dashboard
    assert "Authorization" in dashboard
    assert "token: ZHUSHAN_API_TOKEN" in dashboard
    assert 'src="satellite-config.local.js' in mobile_html
    assert "function mobileApiFetch" in mobile
    assert "Authorization" in mobile


def test_primary_human_auth_configuration_keeps_http_acceptance_mode_but_locks_security_controls():
    environment = compose_app_environment("ops/compose.primary.yml")
    env_generator = read_text("ops/scripts/generate-primary-env.sh")
    nginx = read_text("ops/nginx/smart-bamboo.conf")

    assert {
        "SMART_BAMBOO_HUMAN_AUTH_ENABLED": "0",
        "SMART_BAMBOO_AUTH_REQUIRE_HTTPS": "1",
        "SMART_BAMBOO_TRUST_PROXY_HEADERS": "1",
        "SMART_BAMBOO_SESSION_COOKIE_SECURE": "1",
    }.items() <= environment.items()
    assert "SMART_BAMBOO_HUMAN_AUTH_ENABLED=0" in env_generator
    assert "SMART_BAMBOO_AUTH_REQUIRE_HTTPS=1" in env_generator
    assert "SMART_BAMBOO_TRUST_PROXY_HEADERS=1" in env_generator
    assert "SMART_BAMBOO_SESSION_COOKIE_SECURE=1" in env_generator
    assert "admin-token.txt" not in env_generator
    assert '"roles":["viewer"]' in env_generator
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in nginx
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in nginx


def test_human_auth_rollout_has_tls_token_sync_and_failover_guards():
    primary_env = read_text("ops/scripts/generate-primary-env.sh")
    standby_env = read_text("ops/scripts/make-standby-env.sh")
    verify = read_text("ops/scripts/verify-cluster.sh")
    promote = read_text("ops/scripts/promote-standby.sh")
    tls_compose = read_text("ops/compose.tls.yml")
    tls_nginx = read_text("ops/nginx/smart-bamboo-tls.conf")
    rotate_break_glass = read_text("ops/scripts/rotate-break-glass-token.py")
    runbook = read_text("docs/admin-password-authentication-runbook.md")

    assert "SMART_BAMBOO_BREAK_GLASS_TOKEN" in primary_env
    assert '"break_glass"' in primary_env
    assert "SMART_BAMBOO_RELEASE_COMMIT" in primary_env
    assert "SMART_BAMBOO_HUMAN_AUTH_ENABLED" in standby_env
    assert "REMOTE_SENSING_API_TOKENS" in standby_env
    assert "--allow-human-auth-pending" in verify
    assert "human_auth_pending_https" in verify
    assert '!= "warning"' in verify
    assert "CONFIRM_HUMAN_AUTH_ENABLED=1" in promote
    assert "SMART_BAMBOO_HUMAN_AUTH_ENABLED" in promote
    assert '"0.0.0.0:443:443"' in tls_compose
    assert "SMART_BAMBOO_TLS_CERT_PATH" in tls_compose
    assert "listen 443 ssl" in tls_nginx
    assert "X-Forwarded-Proto https" in tls_nginx
    assert "SMART_BAMBOO_BREAK_GLASS_TOKEN" in rotate_break_glass
    assert "REMOTE_SENSING_API_TOKENS" in rotate_break_glass
    assert "Temporary password" not in rotate_break_glass
    assert "SMART_BAMBOO_RELEASE_COMMIT" in runbook
    assert "--allow-human-auth-pending" in runbook
    assert "system.users.setPassword" in runbook
    assert "system.users.revokeSessions" in runbook
    assert "admin_user_credentials" in runbook
    assert runbook.index("SMART_BAMBOO_HUMAN_AUTH_ENABLED=1") < runbook.index("以 bootstrap 管理员登录")


def test_break_glass_rotation_replaces_a_bom_prefixed_legacy_token(tmp_path):
    env_file = tmp_path / "primary.env"
    profiles = {
        "dashboard-token": {"user": "dashboard", "roles": ["viewer"], "projects": ["*"], "areas": ["*"]},
        "old-break-glass": {"user": "break_glass", "roles": ["admin"], "projects": ["*"], "areas": ["*"]},
    }
    env_file.write_text(
        "\n".join(
            [
                "SMART_BAMBOO_BREAK_GLASS_TOKEN=old-break-glass",
                "REMOTE_SENSING_API_TOKENS='" + json.dumps(profiles, separators=(",", ":")) + "'",
            ]
        )
        + "\n",
        encoding="utf-8-sig",
    )

    result = subprocess.run(
        [sys.executable, str(ROOT / "ops/scripts/rotate-break-glass-token.py"), "--env-file", str(env_file)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("Break-glass token") == 1
    lines = env_file.read_text(encoding="utf-8").splitlines()
    break_glass_lines = [line for line in lines if line.startswith("SMART_BAMBOO_BREAK_GLASS_TOKEN=")]
    assert len(break_glass_lines) == 1
    assert break_glass_lines[0] != "SMART_BAMBOO_BREAK_GLASS_TOKEN=old-break-glass"
    encoded_profiles = next(line for line in lines if line.startswith("REMOTE_SENSING_API_TOKENS=")).split("=", 1)[1].strip("'")
    profiles = json.loads(encoded_profiles)
    assert "old-break-glass" not in profiles
    assert sorted(profile["user"] for profile in profiles.values()) == ["break_glass", "dashboard"]


@pytest.mark.parametrize(
    ("compose_path", "trusted_proxy_headers"),
    [
        ("docker-compose.yml", "0"),
        ("ops/compose.primary.yml", "1"),
        ("ops/compose.standby.yml", "1"),
    ],
)
def test_compose_human_auth_defaults_follow_proxy_topology(compose_path, trusted_proxy_headers):
    environment = compose_app_environment(compose_path)

    assert {
        "SMART_BAMBOO_HUMAN_AUTH_ENABLED": "0",
        "SMART_BAMBOO_AUTH_REQUIRE_HTTPS": "1",
        "SMART_BAMBOO_TRUST_PROXY_HEADERS": trusted_proxy_headers,
        "SMART_BAMBOO_SESSION_COOKIE_SECURE": "1",
    }.items() <= environment.items()

    compose = compose_document(compose_path)
    app_ports = compose["services"]["app"].get("ports", [])
    if trusted_proxy_headers == "1":
        assert "nginx" in compose["services"]
        assert app_ports
        assert all(str(port).startswith("127.0.0.1:") for port in app_ports)
    else:
        assert "nginx" not in compose["services"]
        assert app_ports == ["${SMART_BAMBOO_APP_PORT:-8010}:8010"]
