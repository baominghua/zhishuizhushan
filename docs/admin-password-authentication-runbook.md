# 管理员密码认证上线运行手册

本文仅覆盖智慧竹山管理员密码认证的分阶段上线。双云主机既有基础设施流程见 `ops/README.md`。所有命令在服务器的 `/opt/smart-bamboo` 执行；秘密只能在服务器控制台输入或保存在 `/srv/smart-bamboo*/config/*.env`，不得贴入聊天、终端历史或 Git。

## 0. 固定文件、目录与发布原则

- 主节点（`36.140.138.117`）：数据目录 `/srv/smart-bamboo`，环境文件 `/srv/smart-bamboo/config/primary.env`，Compose 文件 `ops/compose.primary.yml`。
- 热备节点（`36.137.23.53`）：数据目录 `/srv/smart-bamboo-dr`，环境文件 `/srv/smart-bamboo-dr/config/standby.env`，Compose 文件 `ops/compose.standby.yml`。
- 两套 Compose 都要求 `SMART_BAMBOO_AUTH_REQUIRE_HTTPS=1`、`SMART_BAMBOO_TRUST_PROXY_HEADERS=1`、`SMART_BAMBOO_SESSION_COOKIE_SECURE=1`。认证开关初始必须保持 `SMART_BAMBOO_HUMAN_AUTH_ENABLED=0`。
- 密码认证只在主节点启用；热备继续复制数据库并保持 failover profile 停止，直到既有容灾流程提升它。

设置可复用的主节点 Compose 命令：

```bash
cd /opt/smart-bamboo
PRIMARY=(docker compose --project-directory /opt/smart-bamboo \
  --env-file /srv/smart-bamboo/config/primary.env \
  -f ops/compose.primary.yml)
```

## 1. 备份和发布前 gate

先在移动云创建发布前磁盘快照，再生成可校验的 MySQL 备份。备份脚本使用 `db-primary`、`/srv/smart-bamboo/config/primary.env` 和 `/srv/smart-bamboo/backups`，会输出 SQL gzip 文件和同名 SHA-256 文件。

```bash
cd /opt/smart-bamboo
bash ops/scripts/backup-mysql.sh
ls -lh /srv/smart-bamboo/backups/smart-bamboo-*.sql.gz*
```

在两台云主机执行 Compose 渲染，确认端口和挂载没有漂移。主节点的 `app`/`geoserver` 仅绑定 `127.0.0.1`，Nginx 才公开 `0.0.0.0:80`；热备在没有 `--profile failover` 时不能启动应用面。

```bash
cd /opt/smart-bamboo
docker compose --project-directory /opt/smart-bamboo \
  --env-file /srv/smart-bamboo/config/primary.env \
  -f ops/compose.primary.yml config >/tmp/primary-compose.txt
grep -nE '0\.0\.0\.0:80|127\.0\.0\.1:8010|192\.168\.0\.32:3306' /tmp/primary-compose.txt

docker compose --project-directory /opt/smart-bamboo \
  --env-file /srv/smart-bamboo-dr/config/standby.env \
  -f ops/compose.standby.yml config >/tmp/standby-compose.txt
grep -nE '0\.0\.0\.0:80|127\.0\.0\.1:8010|/srv/smart-bamboo-dr' /tmp/standby-compose.txt
```

`docker compose config` 是云主机发布 gate。本地没有 Docker CLI 时，不得将本地验证写为通过。

## 2. 拉取、构建和 schema 检查（保持人类认证关闭）

先检查主节点环境文件仍处于分阶段模式。不要在这一阶段把认证开关改为 `1`。

```bash
cd /opt/smart-bamboo
git fetch origin
git checkout codex/production-deploy
git pull --ff-only origin codex/production-deploy
grep -E '^SMART_BAMBOO_(HUMAN_AUTH_ENABLED|AUTH_REQUIRE_HTTPS|TRUST_PROXY_HEADERS|SESSION_COOKIE_SECURE)=' \
  /srv/smart-bamboo/config/primary.env
# Required: 0, 1, 1, 1 respectively.
"${PRIMARY[@]}" up -d --build
"${PRIMARY[@]}" ps
curl -fsS http://127.0.0.1:8010/api/health
bash ops/scripts/verify-cluster.sh primary
```

应用启动会初始化 MySQL schema。只有健康响应显示 `deployment.database.platform.schemaReady=true`、`deployment.database.remoteSensingCatalog.schemaReady=true` 和 `deployment.readiness.status=ready` 才能继续。若仍有旧 JSON 私有数据，先只读盘点，再执行幂等迁移；任何 `verification.verified` 非真、`missingRecords` 非零或退出码非零均停止发布。

```bash
"${PRIMARY[@]}" exec -T app python server/scripts/migrate_json_to_mysql.py --dry-run
"${PRIMARY[@]}" exec -T app python server/scripts/migrate_json_to_mysql.py
curl -fsS http://127.0.0.1:8010/api/health
```

从库通过既有流程接收同一份主节点备份、构建但不启动 failover 应用，并验证复制。不要在未提升的热备节点执行密码 bootstrap。

```bash
cd /opt/smart-bamboo
docker compose --project-directory /opt/smart-bamboo \
  --env-file /srv/smart-bamboo-dr/config/standby.env \
  -f ops/compose.standby.yml --profile failover pull
docker compose --project-directory /opt/smart-bamboo \
  --env-file /srv/smart-bamboo-dr/config/standby.env \
  -f ops/compose.standby.yml --profile failover build app
bash ops/scripts/verify-cluster.sh standby
```

## 3. 初始化第一个管理员

确认主库 schema 已就绪、`SMART_BAMBOO_HUMAN_AUTH_ENABLED=0` 仍生效后，在主节点运行一次 bootstrap。脚本在 MySQL 事务中创建/恢复 `admin` 角色、管理员用户、credential，并撤销该用户既有会话；自动生成的临时密码只打印这一次。控制台操作员必须立即离线保存该行，然后清屏，不得重跑命令来“查看”密码。

```bash
cd /opt/smart-bamboo
"${PRIMARY[@]}" exec -T app python ops/scripts/bootstrap-admin-password.py \
  --username bootstrap_admin --display-name 'Bootstrap Administrator'
```

若组织已通过安全通道准备合规临时密码，可使用标准输入避免脚本输出密码。密码不应出现在 shell 历史或日志中：

```bash
cd /opt/smart-bamboo
read -rs -p 'Temporary bootstrap password: ' BOOTSTRAP_PASSWORD; echo
printf '%s\n' "$BOOTSTRAP_PASSWORD" | "${PRIMARY[@]}" exec -T app \
  python ops/scripts/bootstrap-admin-password.py \
  --username bootstrap_admin --display-name 'Bootstrap Administrator' --password-stdin
unset BOOTSTRAP_PASSWORD
```

## 4. HTTPS 验收后启用人类认证

在 Nginx 已配置真实 HTTPS 终止且外部浏览器访问使用 `https://` 后，确认代理会转发 `X-Forwarded-Proto` 和 `X-Forwarded-For`。先用 HTTPS 登录页完成一次临时管理员登录；HTTP 密码登录应返回 426，而不是绕过 HTTPS。

```bash
curl -fsSI https://<production-domain>/admin-login.html
curl -fsS https://<production-domain>/api/auth/config
```

确认后只修改主节点环境文件中的这一行，再重新创建 app。不要改变另外三个 HTTPS/cookie/proxy 安全变量，也不要在热备节点手工改为 `1`。

```bash
sed -i 's/^SMART_BAMBOO_HUMAN_AUTH_ENABLED=.*/SMART_BAMBOO_HUMAN_AUTH_ENABLED=1/' \
  /srv/smart-bamboo/config/primary.env
grep -E '^SMART_BAMBOO_(HUMAN_AUTH_ENABLED|AUTH_REQUIRE_HTTPS|TRUST_PROXY_HEADERS|SESSION_COOKIE_SECURE)=' \
  /srv/smart-bamboo/config/primary.env
"${PRIMARY[@]}" up -d --no-deps app
"${PRIMARY[@]}" ps
curl -fsS http://127.0.0.1:8010/api/health
bash ops/scripts/verify-cluster.sh primary
```

健康响应必须同时确认 HTTPS/proxy/secure-cookie、MySQL credential/session 表和 active admin credential 均通过；`deployment.readiness.status` 必须为 `ready`。任何失败均保持认证开关为 `0` 并修复根因。

## 5. 登录、授权、审计和服务 token 验收

在 HTTPS 浏览器中完成以下人工检查，并将操作者、时间、结果和关联审计事件编号记录在变更单中：

1. 以 bootstrap 管理员登录 `/admin-login.html`，确认强制改密界面阻止其他后台操作；改为组织正式密码后，确认可访问 `/admin.html`。
2. 在 `/admin-users.html` 用有 `system.users.set_password` 权限的管理员为测试用户设置临时密码，确认该用户首次登录仍被强制改密；用 `system.users.revoke_sessions` 撤销该用户会话，确认旧 cookie 随即失效。
3. 在 `/admin-roles.html` 为非管理员角色配置菜单、动作权限和 projects/areas data scope；分别验证允许范围内的读取/写入与范围外的拒绝。
4. 访问大屏和移动端，确认 `SMART_BAMBOO_DASHBOARD_TOKEN` 对应 viewer 只读服务 token 仍可读取 dashboard，且不会获得管理员写权限。不要在浏览器、截图或工单正文暴露该 token。
5. 在用户与角色审计列表核对 `bootstrap_password`、`login_success`、`login_failure`、`login_locked`、`password_change`、`logout`、设置临时密码和会话撤销事件；审计内容不得出现密码、cookie、CSRF 或 bearer token。

旧的管理员 service token 必须在确认上述人类会话路径和只读 dashboard token 都正常后撤销：编辑 `/srv/smart-bamboo/config/primary.env` 的 `REMOTE_SENSING_API_TOKENS`，删除旧管理员 token 条目，只保留或轮换最小权限服务身份；随后重建 app 并以旧 token 验证 401/403。

```bash
cd /opt/smart-bamboo
editor /srv/smart-bamboo/config/primary.env
"${PRIMARY[@]}" up -d --no-deps app
curl -fsS http://127.0.0.1:8010/api/health
```

## 6. 回滚

认证路径故障时，只关闭人类认证开关并重新创建 app：

```bash
sed -i 's/^SMART_BAMBOO_HUMAN_AUTH_ENABLED=.*/SMART_BAMBOO_HUMAN_AUTH_ENABLED=0/' \
  /srv/smart-bamboo/config/primary.env
"${PRIMARY[@]}" up -d --no-deps app
curl -fsS http://127.0.0.1:8010/api/health
bash ops/scripts/verify-cluster.sh primary
```

回滚**不得**删除或清空 `admin_credentials`、`admin_sessions`、`admin_users`、`admin_roles` 或审计记录；这些表保留用于修复后重新启用认证。服务 token 的轮换与撤销按独立变更处理，避免在回滚时恢复已撤销的管理员 token。
