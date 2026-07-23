# 智慧竹山双云主机部署手册

本手册对应以下固定拓扑：

| 角色 | 公网 IP | 内网 IP | 系统盘 | 数据盘 |
| --- | --- | --- | --- | --- |
| 高配生产主节点 | `36.140.138.117` | `192.168.0.32` | `/dev/sda1` 500GB | `/dev/sdb` 4TB |
| 低配热备节点 | `36.137.23.53` | `192.168.0.104` | `/dev/sda1` 300GB | `/dev/sdb` 1TB |

> **操作纪律：未经检查不得继续下一检查点。** 两台机器均通过移动云“远程登录”操作，不在聊天、GitHub 或截图中传递密码、Token、对象存储密钥。

## 检查点 0：安全组与云服务

在移动云控制台完成：

1. 高配机入方向开放 TCP 80、443；TCP 3306 仅允许 `192.168.0.104/32`；TCP 22 如需主从初始化文件传输，也仅允许 `192.168.0.104/32`。
2. 低配机首期不开放 TCP 80、443；确认公网没有 3306、8010、8080 规则。
3. 两台机器出方向允许访问 GitHub、Docker Registry 和移动云对象存储。
4. 创建私有对象存储桶，开启版本控制；数据库备份保留 90 天，原始影像按项目归档。
5. 设置云硬盘快照：数据库数据盘每日、系统盘每周；每次正式发布前手工快照。

回传：两台安全组入方向规则截图，以及对象存储桶名称和区域（不要回传访问密钥）。

## 检查点 1：磁盘与 Docker

两台机器先安装 Git 并克隆固定部署分支：

```bash
dnf install -y git
git clone --depth 1 --branch codex/production-deploy https://github.com/baominghua/zhishuizhushan.git /opt/smart-bamboo
cd /opt/smart-bamboo
bash ops/scripts/install-docker-bclinux.sh
```

高配机再次检查空盘后执行：

```bash
lsblk -f
wipefs -n /dev/sdb
CONFIRM_FORMAT_EMPTY_DISK=YES bash ops/scripts/prepare-data-disk.sh primary
```

低配机再次检查空盘后执行：

```bash
lsblk -f
wipefs -n /dev/sdb
CONFIRM_FORMAT_EMPTY_DISK=YES bash ops/scripts/prepare-data-disk.sh standby
```

两台机器统一验证并重启一次：

```bash
mount -a
docker version
docker compose version
df -hT /srv/smart-bamboo* 2>/dev/null || true
cat /etc/fstab
reboot
```

重启后重新登录，执行 `lsblk -f && df -hT && docker version`。回传完整输出，确认 XFS、UUID、挂载容量和 Docker 正常。

## 检查点 2：高配主节点

在高配机生成一次性生产秘密并检查 Compose：

```bash
cd /opt/smart-bamboo
bash ops/scripts/generate-primary-env.sh
docker compose --project-directory /opt/smart-bamboo \
  --env-file /srv/smart-bamboo/config/primary.env \
  -f ops/compose.primary.yml config --quiet
```

如已有天地图服务端密钥，先用编辑器填写 `primary.env` 中空白的 `REMOTE_SENSING_TIANDITU_TK`；不要把密钥发到聊天或 GitHub。随后启动正式服务并建立复制账号：

```bash
docker compose --project-directory /opt/smart-bamboo \
  --env-file /srv/smart-bamboo/config/primary.env \
  -f ops/compose.primary.yml up -d --build
bash ops/scripts/configure-primary-replication.sh
bash ops/scripts/verify-cluster.sh primary --allow-human-auth-pending
curl -fsS http://127.0.0.1:8010/api/health
```

生成初始化从库的一致性备份：

```bash
bash ops/scripts/backup-mysql.sh
ls -lh /srv/smart-bamboo/backups
```

回传：`docker compose ps`、`verify-cluster.sh primary`、健康接口和备份文件列表；不要回传 `.env` 或管理员 Token。

## 检查点 3：低配热备节点

将高配机 `primary.env` 通过 OpenSSL 加密后走内网传到低配机。先在高配机执行，口令只在控制台人工输入：

```bash
openssl enc -aes-256-cbc -pbkdf2 -salt \
  -in /srv/smart-bamboo/config/primary.env \
  -out /root/primary.env.enc
scp /root/primary.env.enc root@192.168.0.104:/root/
rm -f /root/primary.env.enc
```

再在低配机解密并生成 `standby.env`：

```bash
cd /opt/smart-bamboo
openssl enc -d -aes-256-cbc -pbkdf2 \
  -in /root/primary.env.enc \
  -out /root/primary.env
bash ops/scripts/make-standby-env.sh /root/primary.env /srv/smart-bamboo-dr/config/standby.env
rm -f /root/primary.env /root/primary.env.enc
```

在高配机将检查点 2 生成的 `.sql.gz` 和 `.sha256` 通过内网 SCP 复制到低配机 `/srv/smart-bamboo-dr/backups/`。文件名以实际备份为准：

```bash
scp /srv/smart-bamboo/backups/smart-bamboo-*.sql.gz* \
  root@192.168.0.104:/srv/smart-bamboo-dr/backups/
```

再在低配机提前拉取固定镜像、构建备用应用但不启动，最后初始化从库：

```bash
cd /opt/smart-bamboo
docker compose --project-directory /opt/smart-bamboo \
  --env-file /srv/smart-bamboo-dr/config/standby.env \
  -f ops/compose.standby.yml --profile failover pull
docker compose --project-directory /opt/smart-bamboo \
  --env-file /srv/smart-bamboo-dr/config/standby.env \
  -f ops/compose.standby.yml --profile failover build app
docker image inspect \
  "smart-bamboo-app:$(sed -n 's/^SMART_BAMBOO_RELEASE_TAG=//p' /srv/smart-bamboo-dr/config/standby.env)" \
  docker.osgeo.org/geoserver:2.25.7 \
  nginx:1.30.4-alpine
bash ops/scripts/initialize-replica.sh /srv/smart-bamboo-dr/backups/<备份文件>.sql.gz
bash ops/scripts/verify-cluster.sh standby
```

备用应用此时保持停止状态，以下命令不应显示 `app/nginx/geoserver` 正在运行：

```bash
docker compose --project-directory /opt/smart-bamboo \
  --env-file /srv/smart-bamboo-dr/config/standby.env \
  -f ops/compose.standby.yml ps
```

回传：复制状态中的 `Replica_IO_Running`、`Replica_SQL_Running`、`Seconds_Behind_Source` 和 `super_read_only`；不要回传复制密码。

## 检查点 4：私有数据迁移

本机 `data/` 不进入公开 GitHub。在 Windows 项目目录执行下面命令；程序会无回显地询问口令，并自动排除瓦片缓存、日志和 Python 缓存：

```powershell
.\.venv\Scripts\python.exe -m ops.tools.private_bundle create data private-data.sbbundle
Get-FileHash .\private-data.sbbundle -Algorithm SHA256
```

将 `private-data.sbbundle` 和 `private-data.sbbundle.sha256` 上传移动云私有对象存储，再通过短期授权地址下载到高配机 `/srv/smart-bamboo/incoming/`。口令不得上传、截图或写入命令历史。先只校验文件，确认无误后再解密迁移：

```bash
cd /opt/smart-bamboo
sha256sum -c /srv/smart-bamboo/incoming/private-data.sbbundle.sha256
bash ops/scripts/migrate-private-data.sh /srv/smart-bamboo/incoming/private-data.sbbundle || test $? -eq 2
CONFIRM_MIGRATE_PRIVATE_DATA=YES \
  bash ops/scripts/migrate-private-data.sh /srv/smart-bamboo/incoming/private-data.sbbundle
bash ops/scripts/verify-cluster.sh primary --allow-human-auth-pending
```

迁移后在后台核对林班、林权、图层、成果批次、影像和经营主体数量。任一核心数据集不一致即停止发布。

## 检查点 5：备份与容灾演练

先在高配机配置对象存储。下面命令进入 rclone 的交互配置，访问密钥只输入远程控制台，不要回传：

```bash
install -m 600 /dev/null /srv/smart-bamboo/config/rclone.conf
docker run --rm -it \
  --mount type=bind,src=/srv/smart-bamboo/config/rclone.conf,dst=/config/rclone/rclone.conf \
  rclone/rclone:1.74.3 config
cat >/srv/smart-bamboo/config/backup-upload.env <<'EOF'
RCLONE_BACKUP_REMOTE=mobile-cloud-private:smart-bamboo/database
EOF
chmod 600 /srv/smart-bamboo/config/backup-upload.env /srv/smart-bamboo/config/rclone.conf
cd /opt/smart-bamboo
bash ops/scripts/install-systemd-units.sh primary
systemctl start smart-bamboo-backup.service
systemctl status smart-bamboo-backup.service --no-pager
systemctl list-timers --all 'smart-bamboo-*'
```

其中 `mobile-cloud-private` 和存储桶路径要替换为 rclone 配置中的实际远端名称和目录。低配机安装每分钟一次的主节点健康巡检：

```bash
cd /opt/smart-bamboo
bash ops/scripts/install-systemd-units.sh standby
systemctl start smart-bamboo-health.service
tail -n 20 /srv/smart-bamboo-dr/monitoring/primary-health.log
systemctl list-timers --all 'smart-bamboo-*'
```

完成一次数据库备份上传和临时库恢复测试后，再进行人工容灾演练。

低配提升必须同时满足：主节点已确认不可写、负责人批准、安全组尚未开放低配 80。执行：

```bash
cd /opt/smart-bamboo
CONFIRM_PRIMARY_UNAVAILABLE=YES CONFIRM_HUMAN_AUTH_ENABLED=1 \
  bash ops/scripts/promote-standby.sh
curl -fsS http://127.0.0.1:8010/api/health
```

只有健康检查为 `ready` 后，才在移动云安全组开放低配公网 TCP 80、443。若同步环境中的 `SMART_BAMBOO_HUMAN_AUTH_ENABLED=1`，提升命令必须带 `CONFIRM_HUMAN_AUTH_ENABLED=1`；若 auth0（`SMART_BAMBOO_HUMAN_AUTH_ENABLED=0`），该确认变量不需要。脚本以非执行式 dotenv 解析读取受保护环境，不会 `source` 其中的值；它会在 `STOP REPLICA` 前核对 commit、目录、app/nginx/geoserver 镜像、TLS 证书/私钥公钥匹配、证书有效期和 Compose 合约，再验证已接收 GTID 的 SQL 应用完成。提升阶段写入 `/srv/smart-bamboo-dr/config/promotion-state`；中断后保留同样确认门重跑，不要手工删状态文件或改只读开关。若高配健康接口仍可访问，脚本默认阻止提升，避免双主写入。

最终验收：公网仅 80、443 可达；3306、8010、8080 均不可达；林班地图、分层筛选、后台权限、成果导入和影像管理通过。

## 管理员密码认证和 TLS 切换

本手册的初始 Compose 是 HTTP 准备模式，`SMART_BAMBOO_HUMAN_AUTH_ENABLED=0` 时 `verify-cluster.sh primary --allow-human-auth-pending` 只允许 `human_auth_pending_https` 这一预期 warning。不得在这个阶段使用要求 `ready` 的验证命令。

密码认证上线前，必须把真实、已批准域名的证书和私钥放入 `/srv/smart-bamboo/tls/`，在受保护的 `primary.env` 设置 `SMART_BAMBOO_TLS_ENABLED=1`、`SMART_BAMBOO_TLS_CERT_PATH` 和 `SMART_BAMBOO_TLS_KEY_PATH`，然后执行：

```bash
cd /opt/smart-bamboo
bash ops/scripts/enable-tls.sh primary
```

该命令使用 `ops/compose.tls.yml` 和 TLS Nginx 覆盖，将 HTTP 重定向到 HTTPS，并向 app 传递 `X-Forwarded-Proto=https`。仅在外部 DNS、证书链与 HTTPS 验收通过后，才将 `SMART_BAMBOO_HUMAN_AUTH_ENABLED=1` 并执行不带 `--allow-human-auth-pending` 的 `bash ops/scripts/verify-cluster.sh primary`。具体 token 观察期、热备同步、提升确认和 break-glass 恢复见 `docs/admin-password-authentication-runbook.md`。
