from pathlib import Path
import hashlib
import json
import os
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
    assert '"0.0.0.0:18080:80"' in compose
    assert '"0.0.0.0:18081:81"' not in compose
    assert "/srv/smart-bamboo/mysql:/var/lib/mysql" in compose
    assert "/srv/smart-bamboo/data:/app/data" in compose
    assert "/srv/smart-bamboo/geoserver:/opt/geoserver_data" in compose
    assert "3307:3306" not in compose
    assert "8080:8080" not in compose.replace('"127.0.0.1:8080:8080"', "")


def test_nginx_separates_v1_and_v2_public_entry_ports():
    nginx = read_text("ops/nginx/smart-bamboo.conf")

    assert "listen 80 default_server;" in nginx
    assert "listen 81;" in nginx
    assert "absolute_redirect off;" in nginx
    assert "return 302 /v2/workspace;" in nginx
    assert "return 302 /admin-login.html?returnTo=/v2/workspace;" in nginx
    assert "location /v2/" in nginx
    assert "location /api/" in nginx
    assert "location = /admin-login.html" in nginx
    assert "location / {\n        return 404;\n    }" in nginx


def test_nginx_compresses_v2_text_assets_on_http_and_https_edges():
    for path in (
        "ops/nginx/smart-bamboo.conf",
        "ops/nginx/smart-bamboo-v2-secure.conf",
    ):
        nginx = read_text(path)
        assert "gzip on;" in nginx
        assert "gzip_vary on;" in nginx
        assert "gzip_proxied any;" in nginx
        assert "application/javascript" in nginx
        assert "application/json" in nginx


def test_versioned_port_activation_recreates_public_and_admin_edges():
    script = read_text("ops/scripts/activate-versioned-http-ports.sh")

    assert 'up -d --no-deps --force-recreate nginx nginx-v2-secure' in script
    assert "http://127.0.0.1:18080/zhushan-bigdata.html" in script
    assert "https://127.0.0.1:18081/v2/workspace" in script
    assert "/admin-login.html?returnTo=/v2/workspace" in script
    assert "SMART_BAMBOO_VERSIONED_HTTP_PORTS_READY" in script
    assert "up -d app" not in script
    assert "up -d db-primary" not in script


def test_secure_v2_password_login_uses_an_isolated_https_entry():
    compose = read_text("ops/compose.v2-secure.yml")
    nginx = read_text("ops/nginx/smart-bamboo-v2-secure.conf")
    script = read_text("ops/scripts/enable-v2-test-password-login.sh")

    assert "file: ops/compose.primary.yml" in compose
    assert '"0.0.0.0:18081:443"' in compose
    assert "https://127.0.0.1:18081/api/auth/config" in script
    assert "app-v2-secure:" in compose
    assert 'SMART_BAMBOO_HUMAN_AUTH_ENABLED: "1"' in compose
    assert "ports: !reset []" in compose
    assert "nginx-v2-secure:" in compose
    assert "listen 443 ssl default_server;" in nginx
    assert "proxy_set_header X-Forwarded-Proto https;" in nginx
    assert "location /v2/" in nginx
    assert "location /api/" in nginx
    assert "return 404;" in nginx
    assert "read -r -s -p \"Custom password: \" password" in script
    assert "bootstrap-admin-password.py" in script
    assert 'c[\"mustChangePassword\"]=False' in script
    assert "configure-v2-password-env.py" in script
    assert "up -d --no-deps app-v2-secure" in script
    assert "force-recreate app" not in script
    assert "SMART_BAMBOO_V2_PASSWORD_LOGIN_READY" in script


def test_secure_v2_environment_writer_only_updates_tls_paths():
    script = read_text("ops/scripts/configure-v2-password-env.py")

    assert '"SMART_BAMBOO_TLS_ENABLED": "1"' in script
    assert '"SMART_BAMBOO_HUMAN_AUTH_ENABLED"' not in script
    assert "os.replace(temporary, path)" in script


def test_standby_compose_stays_dormant_until_manual_failover():
    compose = read_text("ops/compose.standby.yml")

    assert "image: mysql:8.4.9" in compose
    assert "/srv/smart-bamboo-dr/mysql-replica:/var/lib/mysql" in compose
    assert "/srv/smart-bamboo-dr/data:/app/data" in compose
    assert 'profiles: ["failover"]' in compose
    assert '"127.0.0.1:8010:8010"' in compose
    assert '"0.0.0.0:80:80"' in compose
    assert '"0.0.0.0:18080:80"' in compose
    assert '"0.0.0.0:18081:81"' in compose
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
    assert "skip_replica_start=OFF" in replica
    assert "skip_replica_start=ON" not in replica


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
    assert "RESET REPLICA ALL" not in promote
    assert "GTID_SUBSET" in promote
    assert "CONFIRM_PRIMARY_UNAVAILABLE=YES" in promote
    assert "--build" not in promote
    assert "sha256sum -c" in migrate
    assert "migrate_json_to_mysql.py" in migrate


def test_replica_initialization_bootstraps_writable_then_restores_read_only():
    initialize = read_text("ops/scripts/initialize-replica.sh")
    disk_prepare = read_text("ops/scripts/prepare-data-disk.sh")

    assert 'role_override="/srv/smart-bamboo-dr/config/role-override.cnf"' in initialize
    assert "read_only=OFF\nsuper_read_only=OFF\nskip_replica_start=ON" in initialize
    assert "read_only=ON\nsuper_read_only=ON\nskip_replica_start=OFF" in initialize
    assert "trap restore_read_only EXIT" in initialize
    assert 'exec mysql -uroot -N -B -e "SELECT 1;"' in initialize
    assert "mysqladmin ping" not in initialize
    assert 'chmod 644 "${temporary}"' in initialize
    assert 'chmod 0644 "${mount_point}/config/role-override.cnf"' in disk_prepare
    assert initialize.index("install_bootstrap_override") < initialize.index(
        '"${compose[@]}" up -d db-replica'
    )
    assert initialize.index("START REPLICA;") < initialize.index(
        "SET GLOBAL read_only=ON;"
    )


def test_replication_password_generation_and_validation_respect_mysql_limit():
    generator = read_text("ops/scripts/generate-primary-env.sh")
    primary = read_text("ops/scripts/configure-primary-replication.sh")
    standby = read_text("ops/scripts/initialize-replica.sh")

    assert 'replication_password="$(openssl rand -hex 16)"' in generator
    for script in (primary, standby):
        assert "^[A-Fa-f0-9]{1,32}$" in script
        assert "replication password must contain 1-32 hexadecimal characters" in script


def test_primary_replication_uses_mysql_84_binary_log_status_command():
    primary = read_text("ops/scripts/configure-primary-replication.sh")

    assert "SHOW BINARY LOG STATUS;" in primary
    assert "SHOW MASTER STATUS;" not in primary


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
    handoff_file = tmp_path / "break-glass.token"
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
        [
            sys.executable,
            str(ROOT / "ops/scripts/rotate-break-glass-token.py"),
            "--env-file",
            str(env_file),
            "--token-output-file",
            str(handoff_file),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Break-glass token written once" in result.stdout
    assert handoff_file.read_text(encoding="utf-8").strip()
    lines = env_file.read_text(encoding="utf-8").splitlines()
    break_glass_lines = [line for line in lines if line.startswith("SMART_BAMBOO_BREAK_GLASS_TOKEN=")]
    assert len(break_glass_lines) == 1
    assert break_glass_lines[0] != "SMART_BAMBOO_BREAK_GLASS_TOKEN=old-break-glass"
    encoded_profiles = next(line for line in lines if line.startswith("REMOTE_SENSING_API_TOKENS=")).split("=", 1)[1].strip("'")
    profiles = json.loads(encoded_profiles)
    assert "old-break-glass" not in profiles
    assert sorted(profile["user"] for profile in profiles.values()) == ["break_glass", "dashboard"]


def test_second_review_hardens_tls_promotion_and_environment_lifecycle():
    generate = read_text("ops/scripts/generate-primary-env.sh")
    standby = read_text("ops/scripts/make-standby-env.sh")
    enable_tls = read_text("ops/scripts/enable-tls.sh")
    promote = read_text("ops/scripts/promote-standby.sh")
    verify = read_text("ops/scripts/verify-cluster.sh")
    rotate = read_text("ops/scripts/rotate-break-glass-token.py")
    upgrade = read_text("ops/scripts/upgrade-primary-env.py")
    runbook = read_text("docs/admin-password-authentication-runbook.md")
    cloud_runbook = read_text("ops/README.md")

    assert "config --quiet" in enable_tls
    assert "/tmp/" not in enable_tls
    assert "SMART_BAMBOO_TLS_ENABLED" in promote
    assert 'compose+=( -f "${repo_root}/ops/compose.tls.yml" )' in promote
    assert promote.index("rev-parse HEAD") < promote.index("STOP REPLICA")
    assert "openssl x509" in promote
    assert "docker image inspect" in promote
    assert "config --quiet" in promote
    assert "/srv/smart-bamboo-dr/tls" in standby
    assert "mktemp" in standby
    assert "mv -f" in standby
    assert "CONFIRM_REPLACE_PRIMARY_ENV=YES" in generate
    assert "--replace" in generate
    assert "SMART_BAMBOO_RELEASE_COMMIT" in upgrade
    assert "SMART_BAMBOO_BREAK_GLASS_TOKEN" in upgrade
    assert "--token-output-file" in rotate
    assert "current_break_glass_token" in rotate
    assert "role must be primary or standby" in verify
    assert "primary only" in enable_tls
    assert "CONFIRM_HUMAN_AUTH_ENABLED=1" in cloud_runbook
    assert "443" in cloud_runbook
    assert "交互式" in runbook
    assert "does not prove TLS" in runbook


def test_third_review_requires_gtid_convergence_tls_key_match_and_safe_handoffs():
    promote = read_text("ops/scripts/promote-standby.sh")
    rotate = read_text("ops/scripts/rotate-break-glass-token.py")
    upgrade = read_text("ops/scripts/upgrade-primary-env.py")
    standby = read_text("ops/scripts/make-standby-env.sh")
    runbook = read_text("docs/admin-password-authentication-runbook.md")
    cloud_runbook = read_text("ops/README.md")

    assert "SHOW REPLICA STATUS" in promote
    assert "Replica_SQL_Running" in promote
    assert "Last_SQL_Error" in promote
    assert "STOP REPLICA IO_THREAD" in promote
    assert "WAIT_FOR_EXECUTED_GTID_SET" in promote
    assert "GTID_SUBSET" in promote
    assert "RESET REPLICA ALL" not in promote
    assert promote.index("openssl x509 -in") < promote.index("STOP REPLICA IO_THREAD")
    assert "openssl x509 -in \"${tls_cert_path}\" -pubkey" in promote
    assert "openssl pkey -in \"${tls_key_path}\" -pubout" in promote
    assert "docker.osgeo.org/geoserver:2.25.7" in promote
    assert "nginx:1.30.4-alpine" in promote
    assert "--token-output-file is required" in rotate
    assert rotate.index("write_handoff") < rotate.index("os.replace(temporary, path)")
    assert "unlink(missing_ok=True)" in rotate
    assert "valid_break_glass_profile" in upgrade
    assert upgrade.index("write_handoff") < upgrade.index("os.replace(temporary, path)")
    assert "rollback_pair" in standby
    assert "backup_env" in standby
    assert "TLS_ENABLED=1" in runbook
    assert "Retrieved_Gtid_Set" in runbook
    assert "source-side RPO" in runbook
    assert "CONFIRM_HUMAN_AUTH_ENABLED=1" in cloud_runbook
    assert "auth0" in cloud_runbook


def test_fourth_review_hardens_promotion_recovery_state_and_safe_env_parsing():
    promote = read_text("ops/scripts/promote-standby.sh")
    enable_tls = read_text("ops/scripts/enable-tls.sh")
    runbook = read_text("docs/admin-password-authentication-runbook.md")

    assert "source \"${env_file}\"" not in promote
    assert "read-protected-env.py" in promote
    assert "trap restore_io_on_failure EXIT" in promote
    assert promote.index("STOP REPLICA IO_THREAD") < promote.index("trap restore_io_on_failure EXIT")
    assert promote.index("trap restore_io_on_failure EXIT") < promote.index("WAIT_FOR_EXECUTED_GTID_SET")
    assert "START REPLICA IO_THREAD" in promote
    assert "recovery-failed" in promote
    assert "commit-intent" in promote
    assert "database-promoted" in promote
    assert "services-started" in promote
    assert "promotion-state" in promote
    assert "unsafe, indeterminate database read-only state" in promote
    assert "read-replica-status.py" in promote
    assert "tail -n 1" not in promote
    assert "source \"${env_file}\"" not in enable_tls
    assert "promotion-state" in runbook
    assert "fail-forward" in runbook


def test_fifth_review_makes_power_loss_boundaries_durable_and_recovery_role_aware():
    promote = read_text("ops/scripts/promote-standby.sh")
    durable_writer = read_text("ops/scripts/durable-atomic-write.py")

    assert "durable-atomic-write.py" in promote
    assert "durable_write \"${state_file}\" 0600" in promote
    assert "durable_write \"${role_override}\" 0644" in promote
    assert "os.fchmod(handle.fileno(), args.mode)" in durable_writer
    assert durable_writer.index("os.fchmod(handle.fileno(), args.mode)") < durable_writer.index("os.fsync(handle.fileno())")
    assert durable_writer.index("os.fsync(handle.fileno())") < durable_writer.index("os.replace(temporary, args.target)")
    assert "os.chmod(temporary, args.mode)" not in durable_writer
    assert durable_writer.index("os.replace(temporary, args.target)") < durable_writer.index("fsync_directory(args.target.parent)")
    assert "io_restart_is_healthy" in promote
    assert '"${io}" == "Connecting"' in promote
    assert "Replica_SQL_Running" in promote
    assert "Last_SQL_Error" in promote

    transition = promote[promote.index("write_state commit-intent") :]
    assert transition.index("write_state commit-intent") < transition.index("trap - EXIT")
    assert transition.index("trap - EXIT") < transition.index("ensure_database_promoted")
    promotion_step = promote[promote.index("ensure_database_promoted()") : promote.index("finish_services()")]
    assert promotion_step.index("mysql_exec \"STOP REPLICA; SET GLOBAL") < promotion_step.index("install_role_override")
    assert promotion_step.index("install_role_override") < promotion_step.index("write_state database-promoted")
    assert promote.index("write_state database-promoted") < promote.index("--profile failover up -d")

    recovery = promote[promote.index("draining|recovery-failed)") : promote.index("preflight)")]
    assert 'case "$(database_role)" in' in recovery
    assert "1,1) resume_io_or_fail" in recovery
    assert "database became writable before RPO acceptance" in recovery
    assert "START REPLICA IO_THREAD" not in recovery
    database_promoted = promote[promote.index("database-promoted)") : promote.index("commit-intent)")]
    assert "ensure_database_promoted" in database_promoted
    assert "1,1) mysql_exec \"STOP REPLICA; SET GLOBAL" in promote


def test_durable_atomic_writer_replaces_target_without_leaving_temp_content(tmp_path):
    target = tmp_path / "promotion-state"
    target.write_text("phase=preflight\n", encoding="utf-8")
    payload = b"phase=database-promoted\nrelease_commit=" + b"d" * 40 + b"\n"

    result = subprocess.run(
        [sys.executable, str(ROOT / "ops/scripts/durable-atomic-write.py"), str(target), "0600"],
        input=payload,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode()
    assert target.read_bytes() == payload
    assert not list(tmp_path.glob(".promotion-state.*"))


def test_protected_env_parser_never_executes_shell_syntax(tmp_path):
    env_file = tmp_path / "standby.env"
    marker = tmp_path / "should-not-exist"
    payload = f"$(touch {marker});`touch {marker}`;literal"
    env_file.write_text(
        "MYSQL_ROOT_PASSWORD='" + payload + "'\n"
        "SMART_BAMBOO_RELEASE_COMMIT=" + "c" * 40 + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "ops/scripts/read-protected-env.py"),
            str(env_file),
            "MYSQL_ROOT_PASSWORD",
            "SMART_BAMBOO_RELEASE_COMMIT",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [payload, "c" * 40]
    assert not marker.exists()


def test_replica_status_parser_rejects_multiple_channels_and_duplicate_fields():
    status = """*************************** 1. row ***************************
Replica_SQL_Running: Yes
Last_SQL_Error:
*************************** 2. row ***************************
Replica_SQL_Running: Yes
Last_SQL_Error:
"""
    result = subprocess.run(
        [sys.executable, str(ROOT / "ops/scripts/read-replica-status.py"), "Replica_SQL_Running"],
        input=status,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "exactly one" in result.stderr


def test_break_glass_rotation_refuses_to_change_env_without_new_handoff_file(tmp_path):
    env_file = tmp_path / "primary.env"
    env_file.write_text(
        "SMART_BAMBOO_BREAK_GLASS_TOKEN=old\n"
        "REMOTE_SENSING_API_TOKENS='{\"old\":{\"user\":\"break_glass\",\"roles\":[\"admin\"],\"projects\":[\"*\"],\"areas\":[\"*\"]}}'\n",
        encoding="utf-8",
    )
    original = env_file.read_text(encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(ROOT / "ops/scripts/rotate-break-glass-token.py"), "--env-file", str(env_file)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--token-output-file is required" in result.stderr
    assert env_file.read_text(encoding="utf-8") == original


def test_primary_env_upgrade_replaces_invalid_break_glass_pointer_with_handoff(tmp_path):
    env_file = tmp_path / "primary.env"
    handoff_file = tmp_path / "break-glass.token"
    profiles = {
        "bad-pointer": {"user": "operator", "roles": ["viewer"], "projects": ["*"], "areas": ["*"]},
        "dashboard-token": {"user": "dashboard", "roles": ["viewer"], "projects": ["*"], "areas": ["*"]},
    }
    env_file.write_text(
        "SMART_BAMBOO_BREAK_GLASS_TOKEN=bad-pointer\n"
        + "REMOTE_SENSING_API_TOKENS='" + json.dumps(profiles, separators=(",", ":")) + "'\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "ops/scripts/upgrade-primary-env.py"),
            "--env-file",
            str(env_file),
            "--release-commit",
            "b" * 40,
            "--token-output-file",
            str(handoff_file),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    updated = env_file.read_text(encoding="utf-8")
    encoded_profiles = next(line for line in updated.splitlines() if line.startswith("REMOTE_SENSING_API_TOKENS=")).split("=", 1)[1].strip("'")
    upgraded_profiles = json.loads(encoded_profiles)
    new_token = next(line for line in updated.splitlines() if line.startswith("SMART_BAMBOO_BREAK_GLASS_TOKEN=")).split("=", 1)[1]
    assert "bad-pointer" not in upgraded_profiles
    assert upgraded_profiles[new_token]["user"] == "break_glass"
    assert upgraded_profiles[new_token]["roles"] == ["admin"]
    assert upgraded_profiles[new_token]["projects"] == ["*"]
    assert upgraded_profiles[new_token]["areas"] == ["*"]
    assert handoff_file.read_text(encoding="utf-8").strip() == new_token


def test_primary_env_upgrade_is_idempotent_and_does_not_rotate_database_secrets(tmp_path):
    env_file = tmp_path / "primary.env"
    token_file = tmp_path / "break-glass.token"
    profiles = {"dashboard-token": {"user": "dashboard", "roles": ["viewer"], "projects": ["*"], "areas": ["*"]}}
    env_file.write_text(
        "\n".join(
            [
                "MYSQL_PASSWORD=unchanged-mysql-password",
                "MYSQL_ROOT_PASSWORD=unchanged-root-password",
                "REMOTE_SENSING_API_TOKENS='" + json.dumps(profiles, separators=(",", ":")) + "'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    command = [
        sys.executable,
        str(ROOT / "ops/scripts/upgrade-primary-env.py"),
        "--env-file",
        str(env_file),
        "--release-commit",
        "a" * 40,
        "--token-output-file",
        str(token_file),
    ]

    first = subprocess.run(command, text=True, capture_output=True, check=False)
    after_first = env_file.read_text(encoding="utf-8")
    second = subprocess.run(command[:-2], text=True, capture_output=True, check=False)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "MYSQL_PASSWORD=unchanged-mysql-password" in after_first
    assert "MYSQL_ROOT_PASSWORD=unchanged-root-password" in after_first
    assert "SMART_BAMBOO_RELEASE_COMMIT=" + "a" * 40 in after_first
    assert "SMART_BAMBOO_HUMAN_AUTH_ENABLED=0" in after_first
    assert "SMART_BAMBOO_AUTH_REQUIRE_HTTPS=1" in after_first
    assert "SMART_BAMBOO_TRUST_PROXY_HEADERS=1" in after_first
    assert "SMART_BAMBOO_SESSION_COOKIE_SECURE=1" in after_first
    assert after_first.count("SMART_BAMBOO_BREAK_GLASS_TOKEN=") == 1
    assert "os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600" in (ROOT / "ops/scripts/upgrade-primary-env.py").read_text(encoding="utf-8")
    if os.name != "nt":
        assert token_file.stat().st_mode & 0o777 == 0o600
    assert token_file.read_text(encoding="utf-8").strip()


def test_break_glass_rotation_revokes_current_token_and_all_emergency_profiles(tmp_path):
    env_file = tmp_path / "primary.env"
    token_file = tmp_path / "break-glass.token"
    profiles = {
        "current-pointer": {"user": "operator", "roles": ["viewer"], "projects": ["*"], "areas": ["*"]},
        "old-break-glass": {"user": "break_glass", "roles": ["admin"], "projects": ["*"], "areas": ["*"]},
        "dashboard-token": {"user": "dashboard", "roles": ["viewer"], "projects": ["*"], "areas": ["*"]},
    }
    env_file.write_text(
        "SMART_BAMBOO_BREAK_GLASS_TOKEN=current-pointer\n"
        + "REMOTE_SENSING_API_TOKENS='" + json.dumps(profiles, separators=(",", ":")) + "'\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(ROOT / "ops/scripts/rotate-break-glass-token.py"), "--env-file", str(env_file), "--token-output-file", str(token_file)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "current-pointer" not in env_file.read_text(encoding="utf-8")
    encoded_profiles = next(line for line in env_file.read_text(encoding="utf-8").splitlines() if line.startswith("REMOTE_SENSING_API_TOKENS=")).split("=", 1)[1].strip("'")
    rotated_profiles = json.loads(encoded_profiles)
    assert "current-pointer" not in rotated_profiles
    assert "old-break-glass" not in rotated_profiles
    assert sorted(profile["user"] for profile in rotated_profiles.values()) == ["break_glass", "dashboard"]
    assert "os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600" in (ROOT / "ops/scripts/rotate-break-glass-token.py").read_text(encoding="utf-8")
    if os.name != "nt":
        assert token_file.stat().st_mode & 0o777 == 0o600


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


def test_login_endpoint_is_rate_limited_at_both_nginx_edges():
    for path in (
        "ops/nginx/smart-bamboo.conf",
        "ops/nginx/smart-bamboo-tls.conf",
    ):
        nginx = read_text(path)
        assert "limit_req_zone" in nginx
        assert "limit_req_status 429" in nginx
        assert "location = /api/auth/login" in nginx
        assert "limit_req zone=" in nginx
        assert "client_max_body_size 16k" in nginx


def test_standby_replication_health_and_restart_are_fail_closed():
    compose = read_text("ops/compose.standby.yml")
    replica = read_text("ops/mysql/replica.cnf")
    healthcheck = read_text("ops/mysql/replica-healthcheck.sh")
    disk_prepare = read_text("ops/scripts/prepare-data-disk.sh")
    runbook = read_text("docs/admin-password-authentication-runbook.md")

    assert "skip_replica_start=OFF" in replica
    assert "read_only=ON\nsuper_read_only=ON\nskip_replica_start=OFF" in disk_prepare
    assert "replica-healthcheck.sh:/usr/local/bin/replica-healthcheck.sh:ro" in compose
    assert "/usr/local/bin/replica-healthcheck.sh" in compose
    assert "Replica_IO_Running" in healthcheck
    assert "Replica_SQL_Running" in healthcheck
    assert "Last_IO_Error" in healthcheck
    assert "Last_SQL_Error" in healthcheck
    assert "Auto_Position" in healthcheck
    assert "read_only" in healthcheck
    assert "super_read_only" in healthcheck
    assert '"${Replica_IO_Running}" == "Yes"' in healthcheck
    assert 'Replica_IO_Running}" == "Connecting"' not in healthcheck
    assert "role-override.cnf" in runbook
    assert "skip_replica_start=OFF" in runbook


def test_standby_promotion_requires_provider_fencing_replication_integrity_and_rpo_gate():
    promote = read_text("ops/scripts/promote-standby.sh")
    runbook = read_text("docs/admin-password-authentication-runbook.md")

    assert "SMART_BAMBOO_FENCE_ADAPTER" in promote
    assert "SMART_BAMBOO_PRIMARY_INSTANCE_ID" in promote
    assert "verify-fence-proof.py" in promote
    assert "stat -c" in promote
    assert "fence adapter must be owned by root" in promote
    assert "group/world writable" in promote
    assert "FENCE_PROOF_VERIFIED" in promote
    assert "http://192.168.0.32/api/health" not in promote
    assert "CONFIRM_FORCE_SPLIT_BRAIN_RISK" not in promote
    assert "Replica_IO_Running" in promote
    assert "Last_IO_Error" in promote
    assert "Auto_Position" in promote
    assert '"${initial_io_running}" == "Connecting"' in promote
    assert '"${initial_io_running}" == "No"' in promote
    assert 'initial_auto_position" == "1"' in promote
    assert "CONFIRM_SOURCE_RPO_ACCEPTED" in promote
    assert "CONFIRM_SOURCE_RPO_EVIDENCE_SHA256" in promote
    assert "rpo-evidence" in promote
    assert "rpo-review" in promote
    assert promote.index("run_fence_adapter") < promote.index('mysql_exec "STOP REPLICA IO_THREAD;"')
    assert promote.index("write_rpo_evidence") < promote.index("require_source_rpo_acceptance")
    assert promote.index("require_source_rpo_acceptance") < promote.index("ensure_database_promoted")
    assert "移动云" in runbook
    assert "provider-backed" in runbook
    assert "关停" in runbook or "隔离" in runbook
    assert "HTTP" in runbook
    assert "fencing" in runbook.lower()


def test_fence_proof_verifier_rejects_wrong_target_and_accepts_explicit_provider_proof():
    verifier = ROOT / "ops/scripts/verify-fence-proof.py"
    proof = {
        "fenced": True,
        "provider": "mobile-cloud",
        "instanceId": "ECS-98299861",
        "state": "stopped",
        "nonce": "nonce-123",
        "proofId": "provider-request-456",
    }
    command = [
        sys.executable,
        str(verifier),
        "--expected-instance",
        "ECS-98299861",
        "--expected-nonce",
        "nonce-123",
    ]

    accepted = subprocess.run(
        command,
        input=json.dumps(proof),
        text=True,
        capture_output=True,
        check=False,
    )
    proof["instanceId"] = "wrong-instance"
    rejected = subprocess.run(
        command,
        input=json.dumps(proof),
        text=True,
        capture_output=True,
        check=False,
    )

    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout.strip() == "FENCE_PROOF_VERIFIED"
    assert rejected.returncode != 0


def test_promotion_validates_break_glass_profile_without_exposing_mysql_password_in_argv():
    promote = read_text("ops/scripts/promote-standby.sh")
    verifier = read_text("ops/scripts/verify-break-glass-env.py")

    assert "verify-break-glass-env.py" in promote
    assert "REMOTE_SENSING_API_TOKENS" in verifier
    assert "SMART_BAMBOO_BREAK_GLASS_TOKEN" in verifier
    assert '"break_glass"' in verifier
    assert '"admin"' in verifier
    assert '"*"' in verifier
    assert '-p"${mysql_root_password}"' not in promote
    assert "MYSQL_PWD" in promote
    assert "read -r MYSQL_PWD" in promote


def test_promotion_binds_auth_environment_to_replicated_runtime_digest():
    promote = read_text("ops/scripts/promote-standby.sh")
    make_standby = read_text("ops/scripts/make-standby-env.sh")
    schema = read_text("server/modules/mysql_schema.py")
    database = read_text("server/modules/database.py")

    assert "platform_runtime_config" in schema
    assert "publish_runtime_auth_config" in database
    assert "auth_config_digest" in make_standby
    assert "platform_runtime_config" in promote
    assert "AUTH_CONFIG_DIGEST_VERIFIED" in promote


def test_fence_adapter_requires_trusted_parent_chain_and_executes_a_snapshot():
    promote = read_text("ops/scripts/promote-standby.sh")

    assert "realpath -e" in promote
    assert "getfacl" in promote
    assert "fence adapter parent path" in promote
    assert "fence_adapter_snapshot" in promote
    assert '"${fence_adapter_snapshot}" --instance-id' in promote


def test_rpo_acceptance_is_bound_to_the_final_fence_proof_without_refencing_after_acceptance():
    promote = read_text("ops/scripts/promote-standby.sh")
    flow = promote[promote.rindex('phase="${promotion_phase}"') :]

    assert "verify-rpo-acceptance.py" in promote
    assert '--fence-proof "${fence_proof_file}"' in promote
    assert '--expected-evidence-sha256 "${expected_digest}"' in promote
    assert 'read_state\nphase="${promotion_phase}"' in promote
    assert flow.index("run_fence_adapter") < flow.index("require_source_rpo_acceptance")
    assert flow.count("run_fence_adapter") == 1
    assert flow.index("require_source_rpo_acceptance") < flow.index("write_state commit-intent")


def test_rpo_acceptance_verifier_rejects_replaced_final_fence_proof(tmp_path):
    verifier = ROOT / "ops/scripts/verify-rpo-acceptance.py"
    release_commit = "a" * 40
    instance_id = "ECS-98299861"
    retrieved = "source-uuid:1-12"
    executed = "source-uuid:1-12"
    proof_path = tmp_path / "fence-proof.json"
    evidence_path = tmp_path / "rpo-evidence"
    state_path = tmp_path / "promotion-state"

    proof_path.write_text(
        json.dumps(
            {
                "fenced": True,
                "provider": "mobile-cloud",
                "instanceId": instance_id,
                "state": "stopped",
                "nonce": "final-fence-nonce",
                "proofId": "provider-request-final",
            }
        ),
        encoding="utf-8",
    )
    proof_digest = hashlib.sha256(proof_path.read_bytes()).hexdigest()
    evidence_path.write_text(
        "\n".join(
            [
                f"release_commit={release_commit}",
                f"primary_instance_id={instance_id}",
                f"retrieved_gtid_set={retrieved}",
                f"executed_gtid_set={executed}",
                "io_state=No",
                f"io_error_sha256={'0' * 64}",
                "sql_state=Yes",
                f"fence_proof_sha256={proof_digest}",
                "captured_at=2026-07-24T00:00:00Z",
                "",
            ]
        ),
        encoding="utf-8",
    )
    evidence_digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    state_path.write_text(
        "\n".join(
            [
                "phase=rpo-review",
                f"release_commit={release_commit}",
                f"primary_instance_id={instance_id}",
                f"fence_adapter_sha256={'1' * 64}",
                f"fence_proof_sha256={proof_digest}",
                f"rpo_evidence_sha256={evidence_digest}",
                "accepted_rpo_evidence_sha256=",
                "",
            ]
        ),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        str(verifier),
        "--state",
        str(state_path),
        "--evidence",
        str(evidence_path),
        "--fence-proof",
        str(proof_path),
        "--release-commit",
        release_commit,
        "--primary-instance-id",
        instance_id,
        "--expected-evidence-sha256",
        evidence_digest,
        "--current-retrieved-gtid-set",
        retrieved,
        "--current-executed-gtid-set",
        executed,
    ]

    accepted = subprocess.run(command, capture_output=True, text=True, check=False)
    proof_path.write_text('{"fenced": false}\n', encoding="utf-8")
    rejected = subprocess.run(command, capture_output=True, text=True, check=False)

    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout.strip() == "RPO_EVIDENCE_VERIFIED"
    assert rejected.returncode != 0
    assert "final fence proof digest" in rejected.stderr


def test_promotion_state_binds_primary_adapter_fence_and_accepted_rpo_identity():
    promote = read_text("ops/scripts/promote-standby.sh")

    for field in (
        "primary_instance_id",
        "fence_adapter_sha256",
        "fence_proof_sha256",
        "rpo_evidence_sha256",
        "accepted_rpo_evidence_sha256",
    ):
        assert f"{field}=" in promote
    assert "promotion state primary instance does not match" in promote
    assert "promotion state fence adapter does not match" in promote
    assert "promotion state fence proof does not match" in promote
    assert "accepted RPO evidence digest is missing or changed" in promote


def test_pre_acceptance_recovery_phases_never_resume_from_a_writable_database():
    promote = read_text("ops/scripts/promote-standby.sh")
    recovery_flow = promote[
        promote.index('draining|recovery-failed)') : promote.index("  preflight)")
    ]

    assert '0,0) install_role_override' not in recovery_flow
    assert "database became writable before RPO acceptance" in recovery_flow


def test_disaster_recovery_scripts_never_put_mysql_password_in_process_argv():
    for path in (
        "ops/scripts/backup-mysql.sh",
        "ops/scripts/configure-primary-replication.sh",
        "ops/scripts/initialize-replica.sh",
        "ops/scripts/promote-standby.sh",
        "ops/scripts/verify-cluster.sh",
    ):
        script = read_text(path)
        assert '-p"${MYSQL_ROOT_PASSWORD}"' not in script
        assert '-p"${mysql_root_password}"' not in script
        assert "MYSQL_PWD" in script


def test_primary_mysql_healthcheck_never_puts_root_password_in_process_argv():
    compose = read_text("ops/compose.primary.yml")

    assert "-p$$MYSQL_ROOT_PASSWORD" not in compose
    assert "MYSQL_PWD=$$MYSQL_ROOT_PASSWORD mysqladmin ping" in compose


def test_primary_env_upgrade_rejects_role_names_that_only_contain_admin(tmp_path):
    env_file = tmp_path / "primary.env"
    handoff_file = tmp_path / "break-glass.token"
    invalid_token = "invalid-break-glass"
    env_file.write_text(
        "\n".join(
            [
                "MYSQL_ROOT_PASSWORD=unchanged-root-password",
                f"SMART_BAMBOO_BREAK_GLASS_TOKEN={invalid_token}",
                "REMOTE_SENSING_API_TOKENS='"
                + json.dumps(
                    {
                        invalid_token: {
                            "user": "break_glass",
                            "roles": "notadmin",
                            "projects": ["*"],
                            "areas": ["*"],
                        }
                    },
                    separators=(",", ":"),
                )
                + "'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "ops/scripts/upgrade-primary-env.py"),
            "--env-file",
            str(env_file),
            "--release-commit",
            "a" * 40,
            "--token-output-file",
            str(handoff_file),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert handoff_file.exists()
    assert f"SMART_BAMBOO_BREAK_GLASS_TOKEN={invalid_token}" not in env_file.read_text(
        encoding="utf-8"
    )


def test_primary_release_rollout_is_exact_scoped_and_preserves_the_public_proxy():
    script = read_text("ops/scripts/deploy-primary-release.sh")
    runbook = read_text("ops/README.md")

    assert 'EXPECTED_HOST="${EXPECTED_HOST:-ecs-98299861}"' in script
    assert 'EXPECTED_IP="${EXPECTED_IP:-192.168.0.32}"' in script
    assert 'PUBLIC_BRANCH="${PUBLIC_BRANCH:-production-deploy}"' in script
    assert 'refs/remotes/origin/${PUBLIC_BRANCH}' in script
    assert "TARGET_COMMIT must be a full 40-character Git commit" in script
    assert "git merge --ff-only" in script
    assert "git merge-base --is-ancestor" in script
    assert "flock -n 9" in script
    assert "another primary release is already running" in script
    assert "SMART_BAMBOO_HUMAN_AUTH_ENABLED=0" in script
    assert "REMOTE_SENSING_API_TOKENS" in script
    assert "SMART_BAMBOO_DASHBOARD_TOKEN" in script
    assert "config --quiet" in script
    assert 'echo "=== CACHE BASE IMAGES ==="' in script
    assert 'docker image inspect "${base_image}"' in script
    assert 'timeout --foreground "${BASE_IMAGE_PULL_TIMEOUT_SECONDS}"' in script
    assert 'docker pull "${base_image}"' in script
    assert "The running application remains online" in script
    assert "BUILDKIT_PROGRESS=plain" in script
    assert "build app" in script
    assert 'application_services+=(app-v2-secure)' in script
    assert 'up -d --no-deps --no-build "${application_services[@]}"' in script
    assert "rollback_application" in script
    assert 'rm -f "${env_backup}" "${env_tmp:-}"' in script
    assert 'current_app_container="$("${compose[@]}" ps -q app)"' in script
    assert "--format='{{.Config.Image}}'" in script
    assert 'old_release_tag="${old_app_image#smart-bamboo-app:}"' in script
    assert 'docker image inspect "${old_app_image}"' in script
    assert "The running application is not healthy" in script
    assert "old_release_tag_line=" not in script
    assert 'print "SMART_BAMBOO_RELEASE_TAG=" rollback_tag' in script
    assert "verify-deployment-readiness.py" in script
    assert "--allow-human-auth-pending" in script
    assert "satellite-config.local.js" in script
    assert "humanLoginEnabled: false" in script
    assert "https://127.0.0.1:18081/api/health" in script
    assert '"humanLoginEnabled":true' in script
    assert "nginx" not in "\n".join(
        line for line in script.splitlines() if "up -d" in line
    )
    assert "deploy-primary-release.sh" in runbook
    assert "--branch production-deploy" in runbook
    assert "--branch codex/production-deploy" not in runbook
    assert "TARGET_COMMIT=" in runbook
    assert "RELEASE_TAG=" in runbook
    assert "不会重建 Nginx" in runbook


def test_dji_material_publisher_shortcut_is_safe_for_windows_chinese_paths():
    launcher = (ROOT / "ops/scripts/发布大疆素材到智慧竹山.cmd").read_bytes()
    installer = (ROOT / "ops/scripts/install-dji-material-publisher.ps1").read_bytes()
    publisher = (ROOT / "ops/scripts/publish-dji-materials.ps1").read_text(
        encoding="utf-8-sig"
    )
    installer_text = installer.decode("utf-8-sig")

    assert all(byte < 128 for byte in launcher)
    assert b"%LOCALAPPDATA%" not in launcher
    assert launcher.count(b"%~dp0") == 1
    assert installer.startswith(b"\xef\xbb\xbf")
    assert 'Join-Path $env:LOCALAPPDATA "SmartBamboo\\Tools"' in installer_text
    assert "[Text.Encoding]::ASCII" in installer_text
    assert 'CreateShortcut($shortcutPath)' in installer_text
    assert '[AllowEmptyString()][string[]]$Arguments' in publisher
    assert '"-N", \'""\'' in publisher
    assert '"smart_bamboo_release_ed25519"' in publisher
    assert "Test-Path -LiteralPath $releaseKeyPath" in publisher
    assert '$shortcut.TargetPath = $env:ComSpec' in installer_text
    assert '$shortcut.Arguments = "/d /c' in installer_text


def test_local_release_publisher_uses_verified_git_bundle_and_stable_shortcut():
    deploy_script = read_text("ops/scripts/deploy-primary-release.sh")
    dockerfile = read_text("Dockerfile")
    publisher_bytes = (ROOT / "ops/scripts/publish-primary-release.ps1").read_bytes()
    installer_bytes = (
        ROOT / "ops/scripts/install-primary-release-publisher.ps1"
    ).read_bytes()
    publisher = publisher_bytes.decode("utf-8-sig")
    installer = installer_bytes.decode("utf-8-sig")
    guide = read_text("docs/LOCAL_DIRECT_RELEASE.md")

    assert publisher_bytes.startswith(b"\xef\xbb\xbf")
    assert installer_bytes.startswith(b"\xef\xbb\xbf")
    assert '"bundle", "create", $bundlePath, "HEAD"' in publisher
    assert "function Get-Sha256Hex" in publisher
    assert "function ConvertTo-WslPath" in publisher
    assert 'return "/mnt/$drive/$relativePath"' in publisher
    assert "$bundleHash = Get-Sha256Hex -Path $bundlePath" in publisher
    assert "$imageHash = Get-Sha256Hex -Path $imageArchivePath" in publisher
    assert 'git bundle verify "`$bundle"' in publisher
    assert 'git merge --ff-only "`$target_commit"' in publisher
    assert 'RELEASE_BUNDLE="`$bundle"' in publisher
    assert '"--build-arg", "SMART_BAMBOO_BUILD_COMMIT=$TargetCommit"' in publisher
    assert '"archive", "--format=tar"' in publisher
    assert '"/var/tmp/smart-bamboo-release.XXXXXX"' in publisher
    assert '"tar", "-xf", $linuxSourceArchive' in publisher
    assert '"docker", "image", "inspect", $imageName' in publisher
    assert "ConvertFrom-Json -InputObject $imageInspectJson" in publisher
    assert "Labels.'org.opencontainers.image.revision'" in publisher
    assert '"--format", \'{{index .Config.Labels "org.opencontainers.image.revision"}}\'' not in publisher
    assert "[AllowEmptyString()][string[]]$Arguments" in publisher
    assert '"-N", \'""\'' in publisher
    assert "grep -Fqx -f ~/.ssh/.smart_bamboo_release_key" in publisher
    assert 'key=`$(printf' not in publisher
    assert '"docker", "save"' not in publisher
    assert "docker save $(ConvertTo-BashSingleQuoted -Value $imageName)" in publisher
    assert "gzip -dc \"`$image_archive\" | docker load" in publisher
    assert 'PREBUILT_IMAGE="$image_name"' in publisher
    assert 'Join-Path $env:LOCALAPPDATA "SmartBamboo\\Tools"' in installer
    assert "[Text.Encoding]::ASCII" in installer
    assert "-IncludeImage" in installer
    assert '$shortcut.TargetPath = $env:ComSpec' in installer
    assert '$shortcut.Arguments = "/d /c' in installer
    assert 'RELEASE_BUNDLE="${RELEASE_BUNDLE:-}"' in deploy_script
    assert 'PREBUILT_IMAGE="${PREBUILT_IMAGE:-}"' in deploy_script
    assert 'release_source=local_bundle' in deploy_script
    assert 'git bundle verify "${resolved_release_bundle}"' in deploy_script
    assert 'echo "=== VERIFY PREBUILT APPLICATION IMAGE ==="' in deploy_script
    assert 'prebuilt_image_verified=${PREBUILT_IMAGE}' in deploy_script
    assert 'org.opencontainers.image.revision="${SMART_BAMBOO_BUILD_COMMIT}"' in dockerfile
    assert "NPM_CONFIG_FETCH_TIMEOUT=600000" in dockerfile
    assert "COREPACK_NPM_REGISTRY=${NPM_REGISTRY}" in dockerfile
    assert 'pnpm config set registry "${NPM_REGISTRY}"' in dockerfile
    assert "id=smart-bamboo-pnpm-store" in dockerfile
    assert "https://registry.npmmirror.com" in dockerfile
    assert "id=smart-bamboo-pip-cache" in dockerfile
    assert "https://pypi.tuna.tsinghua.edu.cn/simple" in dockerfile
    assert "ENV PATH=/opt/conda/envs/pdal/bin:${PATH}" in dockerfile
    assert "绕过服务器访问 GitHub、Docker Hub" in guide


def test_primary_release_readiness_accepts_only_the_http_rollout_warning():
    validator = ROOT / "ops/scripts/verify-deployment-readiness.py"
    readiness = {
        "ok": True,
        "deployment": {
            "readiness": {
                "status": "warning",
                "blockingIssues": [],
                "warnings": [{"key": "human_auth_pending_https"}],
            }
        },
    }

    accepted = subprocess.run(
        [sys.executable, str(validator), "--allow-human-auth-pending"],
        input=json.dumps(readiness),
        capture_output=True,
        text=True,
        check=False,
    )
    assert accepted.returncode == 0, accepted.stderr

    readiness["deployment"]["readiness"]["warnings"] = [{"key": "auth_disabled"}]
    unexpected_warning = subprocess.run(
        [sys.executable, str(validator), "--allow-human-auth-pending"],
        input=json.dumps(readiness),
        capture_output=True,
        text=True,
        check=False,
    )
    assert unexpected_warning.returncode != 0

    readiness["deployment"]["readiness"] = {
        "status": "blocked",
        "blockingIssues": [{"key": "platform_database"}],
        "warnings": [{"key": "human_auth_pending_https"}],
    }
    blocked = subprocess.run(
        [sys.executable, str(validator), "--allow-human-auth-pending"],
        input=json.dumps(readiness),
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode != 0


def test_protected_environment_mutators_do_not_require_python_312_f_strings():
    for path in (
        "ops/scripts/upgrade-primary-env.py",
        "ops/scripts/rotate-break-glass-token.py",
    ):
        script = read_text(path)

        assert r"={'\''" not in script
        assert "rendered_value =" in script


def test_primary_environment_generator_preserves_operator_supplied_tianditu_key():
    generator = read_text("ops/scripts/generate-primary-env.sh")

    assert 'tianditu_tk="${REMOTE_SENSING_TIANDITU_TK:-}"' in generator
    assert 'REMOTE_SENSING_TIANDITU_TK=${tianditu_tk}' in generator
    assert "REMOTE_SENSING_TIANDITU_TK=" not in generator.replace(
        "REMOTE_SENSING_TIANDITU_TK=${tianditu_tk}",
        "",
    )


def test_primary_compose_schedules_project_basemap_prewarm_without_blocking_startup():
    environment = compose_app_environment("ops/compose.primary.yml")

    assert environment["REMOTE_SENSING_TIANDITU_PREWARM_BOUNDS"]
    assert environment["REMOTE_SENSING_TIANDITU_PREWARM_LAYERS"] == "img_w,cia_w"
    assert environment["REMOTE_SENSING_TIANDITU_PREWARM_MIN_ZOOM"] == "8"
    assert environment["REMOTE_SENSING_TIANDITU_PREWARM_MAX_ZOOM"] == "13"
    assert environment["REMOTE_SENSING_TIANDITU_DETAIL_PREWARM_BOUNDS"] == "117.675,27.495,117.75,27.59"
    assert environment["REMOTE_SENSING_TIANDITU_DETAIL_PREWARM_MIN_ZOOM"] == "14"
    assert environment["REMOTE_SENSING_TIANDITU_DETAIL_PREWARM_MAX_ZOOM"] == "16"
    assert environment["REMOTE_SENSING_TIANDITU_PREWARM_MAX_TILES"] == "10000"
    assert "/api/health/live" in read_text("ops/compose.primary.yml")


def test_standby_failover_inherits_project_basemap_prewarm_settings():
    environment = compose_app_environment("ops/compose.standby.yml")

    assert environment["REMOTE_SENSING_TIANDITU_PREWARM_BOUNDS"]
    assert environment["REMOTE_SENSING_TIANDITU_PREWARM_LAYERS"] == "img_w,cia_w"
    assert environment["REMOTE_SENSING_TIANDITU_PREWARM_MIN_ZOOM"] == "8"
    assert environment["REMOTE_SENSING_TIANDITU_PREWARM_MAX_ZOOM"] == "13"
    assert environment["REMOTE_SENSING_TIANDITU_DETAIL_PREWARM_BOUNDS"] == "117.675,27.495,117.75,27.59"
    assert environment["REMOTE_SENSING_TIANDITU_DETAIL_PREWARM_MIN_ZOOM"] == "14"
    assert environment["REMOTE_SENSING_TIANDITU_DETAIL_PREWARM_MAX_ZOOM"] == "16"
    assert environment["REMOTE_SENSING_TIANDITU_PREWARM_MAX_TILES"] == "10000"
    assert "/api/health/live" in read_text("ops/compose.standby.yml")


def test_v2_map_defaults_to_2d_and_keeps_cesium_lazy_loaded():
    map_page = read_text("apps/web-operations/src/pages/MapPage.tsx")
    map_canvas = read_text("apps/web-operations/src/components/MapCanvas.tsx")

    assert 'getItem(MAP_MODE_STORAGE_KEY) === "3d" ? "3d" : "2d"' in map_page
    assert 'const CesiumGlobe = lazy(async () =>' in map_canvas
    assert 'await import("./CesiumGlobe")' in map_canvas


def test_v2_map_defers_noncritical_queries_and_secure_entry_uses_http2():
    map_page = read_text("apps/web-operations/src/pages/MapPage.tsx")
    secure_nginx = read_text("ops/nginx/smart-bamboo-v2-secure.conf")

    assert 'enabled: filtersOpen' in map_page
    assert 'enabled: resultsOpen' in map_page
    assert 'http2 on;' in secure_nginx


def test_tianditu_key_configurator_updates_only_key_without_logging_it(tmp_path):
    env_file = tmp_path / "primary.env"
    env_file.write_text(
        "MYSQL_PASSWORD=keep-this-secret\n"
        "REMOTE_SENSING_TIANDITU_TK=\n"
        "SMART_BAMBOO_RELEASE_TAG=keep-this-release\n",
        encoding="utf-8",
    )
    key = "0123456789abcdef0123456789abcdef"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "ops/scripts/configure-tianditu-key.py"),
            "--env-file",
            str(env_file),
            "--key-stdin",
        ],
        input=key + "\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    content = env_file.read_text(encoding="utf-8")
    assert "MYSQL_PASSWORD=keep-this-secret" in content
    assert "SMART_BAMBOO_RELEASE_TAG=keep-this-release" in content
    assert f"REMOTE_SENSING_TIANDITU_TK={key}" in content
    assert key not in result.stdout
    assert key not in result.stderr
    assert not list(tmp_path.glob(".primary.env.*"))


def test_tianditu_cache_activation_recreates_only_app_and_verifies_real_cache_hit():
    activation = read_text("ops/scripts/activate-tianditu-cache.sh")

    assert "set -Eeuo pipefail" in activation
    assert "set -x" not in activation
    assert "configure-tianditu-key.py" in activation
    assert '"${compose[@]}" up -d --no-deps --no-build --force-recreate app' in activation
    assert "/api/health" in activation
