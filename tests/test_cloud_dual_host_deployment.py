from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


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
