# 管理员密码认证上线运行手册

本手册覆盖智慧竹山管理员密码认证的生产上线和容灾切换。所有命令均在云主机 `/opt/smart-bamboo` 执行。密钥、证书、临时密码和 token 只能在受控服务器控制台输入或保存至 `/srv/smart-bamboo*/config/`，不得放入 Git、工单正文、截图或 shell 历史。

## 0. 固定拓扑与不变量

- 主节点：`36.140.138.117`，运行目录 `/opt/smart-bamboo`，数据/环境目录 `/srv/smart-bamboo`，环境文件 `/srv/smart-bamboo/config/primary.env`，Compose 文件 `ops/compose.primary.yml`。
- 热备节点：`36.137.23.53`，运行目录 `/opt/smart-bamboo`，数据/环境目录 `/srv/smart-bamboo-dr`，环境文件 `/srv/smart-bamboo-dr/config/standby.env`，Compose 文件 `ops/compose.standby.yml`。
- `SMART_BAMBOO_HUMAN_AUTH_ENABLED=0` 是准备阶段唯一允许的认证状态；此时健康检查只能有 `human_auth_pending_https` 这一项预期 warning，不能使用要求 `ready` 的验证命令。
- 正式启用必须同时满足 `SMART_BAMBOO_AUTH_REQUIRE_HTTPS=1`、`SMART_BAMBOO_TRUST_PROXY_HEADERS=1`、`SMART_BAMBOO_SESSION_COOKIE_SECURE=1`、`SMART_BAMBOO_TLS_ENABLED=1`。
- `REMOTE_SENSING_API_TOKENS` 至少保留只读 dashboard token 和服务器控制台保管的 `break_glass` 管理员 token。人类认证、旧管理员 token 或浏览器会话均不能是唯一管理入口。

主节点 Compose 数组：

```bash
cd /opt/smart-bamboo
PRIMARY=(docker compose --project-directory /opt/smart-bamboo \
  --env-file /srv/smart-bamboo/config/primary.env \
  -f ops/compose.primary.yml)
```

## 0.1 既有环境的幂等升级

已存在的 `primary.env` 不可重新执行 `generate-primary-env.sh`，除非经过独立审批的完整秘密轮换。先使用升级工具补齐 immutable release、TLS 字段和缺失的 break-glass profile；它不会轮换已有 MySQL 或服务 token。若需要新 break-glass token，必须在交互式受控控制台提供一个不存在的 0600 输出文件，读取后离线保存并立即删除该文件；不要从 systemd、CI 或重定向日志执行。

```bash
install -d -m 700 /root/smart-bamboo-token-handoff
handoff=/root/smart-bamboo-token-handoff/break-glass.token
test ! -e "${handoff}"
python3 ops/scripts/upgrade-primary-env.py \
  --env-file /srv/smart-bamboo/config/primary.env \
  --token-output-file "${handoff}"
# The handoff file exists only if the upgrade had to repair/create break-glass.
if test -f "${handoff}"; then chmod 600 "${handoff}"; fi
```

## 0.2 固定审批提交和备份

发布负责人必须提供已审批的不可变 full commit SHA（或经审计的 immutable tag 解析出的 full SHA）。不要 checkout 移动分支后直接部署。主、备均执行：

```bash
cd /opt/smart-bamboo
read -r -p 'Approved immutable release commit: ' RELEASE_COMMIT; echo
git fetch origin "$RELEASE_COMMIT"
git checkout --detach "$RELEASE_COMMIT"
test "$(git rev-parse HEAD)" = "$RELEASE_COMMIT"
git status --short
```

主节点将实际检出的 commit 写入受保护环境文件，避免镜像 tag 和部署源码漂移；不要重新运行 `generate-primary-env.sh`，它会轮换所有秘密。

```bash
RELEASE_TAG="release-${RELEASE_COMMIT:0:12}"
sed -i "s/^SMART_BAMBOO_RELEASE_COMMIT=.*/SMART_BAMBOO_RELEASE_COMMIT=${RELEASE_COMMIT}/" \
  /srv/smart-bamboo/config/primary.env
sed -i "s/^SMART_BAMBOO_RELEASE_TAG=.*/SMART_BAMBOO_RELEASE_TAG=${RELEASE_TAG}/" \
  /srv/smart-bamboo/config/primary.env
grep -E '^SMART_BAMBOO_RELEASE_(COMMIT|TAG)=' /srv/smart-bamboo/config/primary.env
```

创建云硬盘发布前快照，然后生成可校验 MySQL 备份：

```bash
cd /opt/smart-bamboo
bash ops/scripts/backup-mysql.sh
ls -lh /srv/smart-bamboo/backups/smart-bamboo-*.sql.gz*
```

## 2. 认证关闭的构建、schema 和迁移 gate

首先确认主环境保持准备状态。此阶段的 `verify-cluster` 明确只允许单个 `human_auth_pending_https` warning；任意 database、schema、目录或 token warning/error 都会失败。

```bash
grep -E '^SMART_BAMBOO_(HUMAN_AUTH_ENABLED|TLS_ENABLED|AUTH_REQUIRE_HTTPS|TRUST_PROXY_HEADERS|SESSION_COOKIE_SECURE)=' \
  /srv/smart-bamboo/config/primary.env
# Required: 0, 0, 1, 1, 1 respectively.
"${PRIMARY[@]}" config --quiet
"${PRIMARY[@]}" up -d --build
bash ops/scripts/verify-cluster.sh primary --allow-human-auth-pending
```

应用启动会创建 MySQL schema。若有旧 JSON 私有数据，先只读盘点，再执行迁移；盘点或命令任一退出码非零即停止。

```bash
"${PRIMARY[@]}" exec -T app python server/scripts/migrate_json_to_mysql.py --dry-run
"${PRIMARY[@]}" exec -T app python server/scripts/migrate_json_to_mysql.py
bash ops/scripts/verify-cluster.sh primary --allow-human-auth-pending
```

确认 bootstrap 已写入 `admin_user_credentials`、`admin_sessions`、`admin_users` 和 `admin_roles` 所需 schema 后，仅在主节点运行一次。自动生成的临时密码只会输出一次，操作员须立即离线保存并清屏；不可重跑以获取同一密码。

```bash
"${PRIMARY[@]}" exec -T app python ops/scripts/bootstrap-admin-password.py \
  --username bootstrap_admin --display-name 'Bootstrap Administrator'
```

## 3. 真实 TLS 终止前置步骤

仓库基础 `ops/nginx/smart-bamboo.conf` 仅提供 HTTP，且其 `X-Forwarded-Proto` 是 `$scheme`；它不具备密码认证上线条件。正式 TLS 使用 `ops/compose.tls.yml` 覆盖 Nginx，并挂载运维人员从真实证书颁发方取得的证书和私钥。该仓库不提供域名、证书或私钥。

将真实证书文件放在主节点受限目录，并以实际路径写入环境。`PUBLIC_FQDN` 必须是已经在 DNS 和证书 SAN 中批准的名称，不要以 IP 或示例域名替代。

```bash
install -d -m 750 /srv/smart-bamboo/tls
install -m 640 -o root -g root <real-fullchain.pem> /srv/smart-bamboo/tls/fullchain.pem
install -m 640 -o root -g root <real-privkey.pem> /srv/smart-bamboo/tls/privkey.pem
editor /srv/smart-bamboo/config/primary.env
# Set SMART_BAMBOO_TLS_ENABLED=1
# Set SMART_BAMBOO_TLS_CERT_PATH=/srv/smart-bamboo/tls/fullchain.pem
# Set SMART_BAMBOO_TLS_KEY_PATH=/srv/smart-bamboo/tls/privkey.pem
# Set REMOTE_SENSING_CORS_ORIGINS=https://<approved-public-fqdn>
cd /opt/smart-bamboo
bash ops/scripts/enable-tls.sh primary
read -r -p 'Approved public DNS name: ' PUBLIC_FQDN; echo
openssl s_client -connect "${PUBLIC_FQDN}:443" -servername "${PUBLIC_FQDN}" -verify_return_error </dev/null
curl --fail --show-error --silent "https://${PUBLIC_FQDN}/api/auth/config"
```

`enable-tls.sh` 是 primary only：它检查证书存在、证书与私钥公钥匹配、剩余有效期至少 30 天并运行 `docker compose ... config --quiet`；TLS Nginx 把 HTTP 308 重定向至 HTTPS，并固定上游 `X-Forwarded-Proto https`。外部 DNS、证书链和 HTTPS health 未通过时，保持 `SMART_BAMBOO_HUMAN_AUTH_ENABLED=0`。应用 `/api/health` 只报告应用配置和数据就绪，does not prove TLS；外部 `openssl s_client` 与 HTTPS `curl` 是独立且必经的 TLS gate。

## 4. 启用认证、正式 ready 与登录

只有上一步 TLS 外部验收完成后，才启用人类认证。顺序不可倒置：先 HTTPS，后开关，后健康 `ready`，最后才进行密码登录和强制改密。

```bash
sed -i 's/^SMART_BAMBOO_HUMAN_AUTH_ENABLED=.*/SMART_BAMBOO_HUMAN_AUTH_ENABLED=1/' \
  /srv/smart-bamboo/config/primary.env
grep -E '^SMART_BAMBOO_(HUMAN_AUTH_ENABLED|TLS_ENABLED|AUTH_REQUIRE_HTTPS|TRUST_PROXY_HEADERS|SESSION_COOKIE_SECURE)=' \
  /srv/smart-bamboo/config/primary.env
docker compose --project-directory /opt/smart-bamboo \
  --env-file /srv/smart-bamboo/config/primary.env \
  -f ops/compose.primary.yml -f ops/compose.tls.yml up -d --no-deps app nginx
bash ops/scripts/verify-cluster.sh primary
```

此时 `/api/health` 必须为 `ready` 且无 warnings，具体包括 proxy/secure cookie、`admin_user_credentials`、`admin_sessions`、活跃管理员 credential 和 MySQL schema；它不验证实际 TLS 握手。只有第 3 节的外部 TLS gate 和本节的应用 ready 都通过后，才从 HTTPS 的 `/admin-login.html` 以 bootstrap 管理员登录，完成强制改密并确认可以访问 `/admin.html`。

## 5. 权限、审计与 token 观察期

在 HTTPS 浏览器中记录操作者、时间、结果和审计事件编号：

1. 以 bootstrap 管理员登录并强制改密；确认改密前所有非认证后台操作被阻止。
2. 使用具有 `system.users.setPassword` 的管理员为测试用户设置临时密码；该用户首次登录必须强制改密。使用 `system.users.revokeSessions` 撤销该用户会话，确认旧 cookie 立即失效。
3. 在 `/admin-roles.html` 验证菜单、动作权限以及 projects/areas data scope 的允许和拒绝路径。
4. 验证 `SMART_BAMBOO_DASHBOARD_TOKEN` 对应 viewer 服务 token 只能读取 dashboard；不在浏览器或截图中暴露 token。
5. 在审计列表检查 `bootstrap_password`、`login_success`、`login_failure`、`login_locked`、`password_change`、`logout`、临时密码和会话撤销事件；审计中不得出现密码、cookie、CSRF 或 bearer token。

旧管理员 service token 必须先进入稳定观察期，期间至少验证一次人类认证、dashboard token 和 break-glass token。观察期完成并经变更负责人批准后，才从主节点 `/srv/smart-bamboo/config/primary.env` 的 `REMOTE_SENSING_API_TOKENS` 删除旧 token，**保留** `break_glass` 和 dashboard 条目；重建 app 后用旧 token 验证拒绝。

```bash
editor /srv/smart-bamboo/config/primary.env
"${PRIMARY[@]}" up -d --no-deps app
bash ops/scripts/verify-cluster.sh primary
```

删除旧 token 后必须立即同步主环境到热备，避免故障切换把已撤销 token 复活。先在主节点加密传输 primary 环境文件，在热备生成 standby 环境；命令会检查认证、TLS、break-glass 和 token 字段存在。

```bash
# On primary, after every authentication or token change.
openssl enc -aes-256-cbc -pbkdf2 -salt \
  -in /srv/smart-bamboo/config/primary.env -out /root/primary.env.enc
scp /root/primary.env.enc root@192.168.0.104:/root/
rm -f /root/primary.env.enc

# On standby console.
openssl enc -d -aes-256-cbc -pbkdf2 -in /root/primary.env.enc -out /root/primary.env
cd /opt/smart-bamboo
bash ops/scripts/make-standby-env.sh /root/primary.env /srv/smart-bamboo-dr/config/standby.env
rm -f /root/primary.env /root/primary.env.enc
```

TLS 已启用时，证书和私钥也必须在同一变更窗口安全同步到热备。热备 env 由 `make-standby-env.sh` 改写为 `/srv/smart-bamboo-dr/tls` 路径；不要把私钥写入 Git、对象存储普通 bucket 或终端输出。

```bash
# On primary, after the encrypted env transfer, use the private network only.
scp /srv/smart-bamboo/tls/fullchain.pem /srv/smart-bamboo/tls/privkey.pem \
  root@192.168.0.104:/root/

# On standby console.
install -d -m 750 /srv/smart-bamboo-dr/tls
install -m 640 -o root -g root /root/fullchain.pem /srv/smart-bamboo-dr/tls/fullchain.pem
install -m 640 -o root -g root /root/privkey.pem /srv/smart-bamboo-dr/tls/privkey.pem
rm -f /root/fullchain.pem /root/privkey.pem
```

## 6. 热备提升和 break-glass 恢复

热备提升前，先在热备核对同一 immutable commit 和同步后的环境值。脚本在停止复制或解除只读前读取 `SHOW REPLICA STATUS`，要求 SQL 线程运行、`Last_SQL_Error` 为空，并先停止 IO 线程以冻结 `Retrieved_Gtid_Set`，等待并验证该集合全部包含于 `@@GLOBAL.gtid_executed`。超时或状态缺失即拒绝提升；脚本不执行 `RESET REPLICA ALL`，保留复制元数据供取证和重建。该检查只能保证已经接收的 GTID 全部应用，源端在 IO 线程冻结前尚未传输的事务仍须由值班负责人结合源端证据确认 source-side RPO。若 `SMART_BAMBOO_HUMAN_AUTH_ENABLED=1`，提升命令要求显式确认；仅当 `SMART_BAMBOO_TLS_ENABLED=1` 时才加入 TLS Compose 覆盖并检查证书、私钥、公钥匹配和有效期。

提升状态保存在受保护的 `/srv/smart-bamboo-dr/config/promotion-state`，阶段依次为 `preflight`、`draining`、`commit-intent`、`database-promoted` 与 `services-started`。在 `draining` 失败时，脚本 best-effort 重启 IO 线程并明确打印恢复结果；若恢复失败，状态记为 `recovery-failed`，必须先处理复制故障。`commit-intent` 已写入后不得回滚到副本模式：在同一确认门和主节点不可用检查仍通过时重跑命令，脚本会查询数据库只读状态并明确 fail-forward 到 `database-promoted` 和服务启动，避免可写状态不明。

```bash
cd /opt/smart-bamboo
test "$(git rev-parse HEAD)" = "$(sed -n 's/^SMART_BAMBOO_RELEASE_COMMIT=//p' /srv/smart-bamboo-dr/config/standby.env)"
grep -E '^SMART_BAMBOO_(HUMAN_AUTH_ENABLED|TLS_ENABLED|RELEASE_COMMIT)=' \
  /srv/smart-bamboo-dr/config/standby.env
CONFIRM_PRIMARY_UNAVAILABLE=YES CONFIRM_HUMAN_AUTH_ENABLED=1 \
  bash ops/scripts/promote-standby.sh
if grep -qx 'SMART_BAMBOO_TLS_ENABLED=1' /srv/smart-bamboo-dr/config/standby.env; then
  docker compose --project-directory /opt/smart-bamboo \
    --env-file /srv/smart-bamboo-dr/config/standby.env \
    -f ops/compose.standby.yml -f ops/compose.tls.yml --profile failover ps
else
  docker compose --project-directory /opt/smart-bamboo \
    --env-file /srv/smart-bamboo-dr/config/standby.env \
    -f ops/compose.standby.yml --profile failover ps
fi
```

中断恢复只能在热备控制台执行，先检查阶段和数据库状态，再使用同一命令重跑；不要手工删除状态文件、执行 `RESET REPLICA ALL` 或自行切换只读开关：

```bash
cat /srv/smart-bamboo-dr/config/promotion-state
CONFIRM_PRIMARY_UNAVAILABLE=YES CONFIRM_HUMAN_AUTH_ENABLED=1 \
  bash ops/scripts/promote-standby.sh
```

认证故障回滚时仅将主节点 `SMART_BAMBOO_HUMAN_AUTH_ENABLED=0` 并重建 app；此时使用已保留的 break-glass 服务 token 进入管理面。不得删除或清空 `admin_user_credentials`、`admin_sessions`、`admin_users`、`admin_roles` 或审计记录。

```bash
sed -i 's/^SMART_BAMBOO_HUMAN_AUTH_ENABLED=.*/SMART_BAMBOO_HUMAN_AUTH_ENABLED=0/' \
  /srv/smart-bamboo/config/primary.env
"${PRIMARY[@]}" up -d --no-deps app
bash ops/scripts/verify-cluster.sh primary --allow-human-auth-pending
```

若误删了旧管理员 token，也不得恢复它；在服务器控制台使用仍保留的 break-glass token。若 break-glass token 本身不可用，经双人复核后只在交互式主节点控制台执行下列命令。生产环境一律使用不存在的 `--token-output-file` 新建 0600 文件；工具拒绝 stdout 输出任何 secret。工具先安全创建交接文件，再原子更新环境；若环境更新失败会删除本次交接文件。它会删除当前 `SMART_BAMBOO_BREAK_GLASS_TOKEN` 指向的 token 与所有 `user=break_glass` profiles，再生成一个新 token；随后重建 app 并立刻按第 5 节同步至热备。任何 token 恢复都不能从聊天记录、浏览器存储或旧工单回收。

```bash
cd /opt/smart-bamboo
install -d -m 700 /root/smart-bamboo-token-handoff
test ! -e /root/smart-bamboo-token-handoff/break-glass.token
python3 ops/scripts/rotate-break-glass-token.py --env-file /srv/smart-bamboo/config/primary.env \
  --token-output-file /root/smart-bamboo-token-handoff/break-glass.token
chmod 600 /root/smart-bamboo-token-handoff/break-glass.token
"${PRIMARY[@]}" up -d --no-deps app
bash ops/scripts/verify-cluster.sh primary --allow-human-auth-pending
```
