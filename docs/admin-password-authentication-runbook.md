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

首次启用新版复制健康检查前，先把既有热备的只读覆盖文件改为自动恢复复制。该文件仍保持 `read_only=ON` 与 `super_read_only=ON`；只有提升脚本在 provider fencing 和 RPO gate 全部通过后才会把它替换为可写角色。修改后重建副本容器，并确认容器健康检查要求 IO/SQL 两个线程都为 `Yes`：

```bash
cd /opt/smart-bamboo
printf '[mysqld]\nread_only=ON\nsuper_read_only=ON\nskip_replica_start=OFF\n' |
  python3 ops/scripts/durable-atomic-write.py \
    /srv/smart-bamboo-dr/config/role-override.cnf 0644
docker compose --project-directory /opt/smart-bamboo \
  --env-file /srv/smart-bamboo-dr/config/standby.env \
  -f ops/compose.standby.yml up -d --force-recreate db-replica
docker compose --project-directory /opt/smart-bamboo \
  --env-file /srv/smart-bamboo-dr/config/standby.env \
  -f ops/compose.standby.yml ps db-replica
```

热备提升前，必须先在移动云控制台关停主云主机，或使用云平台能力把主机、数据盘或网络写入路径隔离。**HTTP 健康探测失败、SSH 不通、人工口头确认都不是 fencing 证明。** 提升脚本强制调用 provider-backed fence adapter，并要求 adapter 在执行云平台关停或隔离后重新查询 provider 状态，再返回含 `fenced=true`、provider、主机 instance ID、状态、一次性 nonce 和 proof ID 的 JSON。adapter 必须使用规范化绝对路径；文件及其到 `/` 的每一级父目录都必须由 root 所有、不可被组或其他用户写入、不得有额外 ACL。脚本验证后复制一份 root-only 快照再执行，目标实例、nonce 或 provider proof 任一不符都会拒绝提升。仓库不伪造也不内置移动云 adapter，真实 adapter 和云平台凭据接入是云上发布 gate。

provider 已完成 fencing 后，复制 IO 线程可能为 `Yes`、`Connecting` 或 `No`，`Last_IO_Error` 也可能记录主节点失联；这不应与数据损坏混为一谈。脚本仍强制要求 `Replica_SQL_Running=Yes`、`Last_SQL_Error` 为空且 `Auto_Position=1`，随后停止 IO 线程、冻结 `Retrieved_Gtid_Set`，等待并验证该集合全部包含于 `@@GLOBAL.gtid_executed`。它不执行 `RESET REPLICA ALL`，会保留复制元数据供取证和重建。

提升改为两阶段。第一阶段先取得并持久化本次提升的最终 provider fencing proof，再生成 `/srv/smart-bamboo-dr/config/rpo-evidence`，其中绑定最终 Retrieved/Executed GTID、主实例、发布 commit 和该 fencing proof 摘要；状态停在 `rpo-review`，数据库继续只读，备用应用不会启动。值班负责人核对源端可能未传输事务并明确接受 source-side RPO 后，第二阶段必须同时提供 `CONFIRM_SOURCE_RPO_ACCEPTED=YES` 和第一阶段输出的 `CONFIRM_SOURCE_RPO_EVIDENCE_SHA256`。第二阶段不会重新调用 adapter 或覆盖 proof，而是通过 `verify-rpo-acceptance.py` 验证 promotion state、RPO evidence、最终 proof 哈希及当前 GTID 完全一致，才写入 `commit-intent`、解除只读并启动服务。任何一份文件被替换或 GTID 发生变化都会拒绝提升。

脚本还会把热备环境中的令牌、break-glass、密码认证、Cookie/代理和 TLS 启用状态计算为摘要，与主库复制过来的 `platform_runtime_config` 记录及发布 commit 比较。旧环境文件、撤销前令牌或认证开关不一致时一律禁止提升。主热备证书路径本来不同，不参与字面摘要；证书、私钥、公钥匹配和有效期由提升脚本单独校验。若 `SMART_BAMBOO_HUMAN_AUTH_ENABLED=1`，还必须显式设置 `CONFIRM_HUMAN_AUTH_ENABLED=1`，且 TLS 未启用时拒绝提升。

提升状态保存在受保护的 `/srv/smart-bamboo-dr/config/promotion-state`，阶段依次为 `preflight`、`draining`、`rpo-review`、`commit-intent`、`database-promoted` 与 `services-started`。`promotion-state`、`rpo-evidence` 与 `role-override.cnf` 均按临时文件写入、flush/fsync、原子 rename、fsync 父目录的顺序持久化。`draining` 失败时脚本 best-effort 恢复 IO；若失败则标记 `recovery-failed`。`commit-intent` 之后只允许 fail-forward：重跑必须继续使用 promotion state 已绑定且经过 RPO 接受的最终 provider proof，并核对数据库角色；不会生成新 proof，任何证明摘要变化或混合读写状态都拒绝执行。

```bash
cd /opt/smart-bamboo
test "$(git rev-parse HEAD)" = "$(sed -n 's/^SMART_BAMBOO_RELEASE_COMMIT=//p' /srv/smart-bamboo-dr/config/standby.env)"
grep -E '^SMART_BAMBOO_(HUMAN_AUTH_ENABLED|TLS_ENABLED|RELEASE_COMMIT)=' \
  /srv/smart-bamboo-dr/config/standby.env
# 第一阶段：只冻结复制并生成最终 RPO 证据。退出码 12 是预期的人工审核停点。
set +e
stage1_output="$(
  SMART_BAMBOO_FENCE_ADAPTER=/root/smart-bamboo-mobile-cloud-fence \
  SMART_BAMBOO_PRIMARY_INSTANCE_ID=ECS-98299861 \
  CONFIRM_PRIMARY_UNAVAILABLE=YES \
  CONFIRM_HUMAN_AUTH_ENABLED=1 \
    bash ops/scripts/promote-standby.sh 2>&1
)"
stage1_rc=$?
set -e
printf '%s\n' "${stage1_output}"
test "${stage1_rc}" -eq 12
rpo_sha="$(
  printf '%s\n' "${stage1_output}" |
    sed -n 's/^RPO_EVIDENCE_READY_SHA256=//p'
)"
test "${#rpo_sha}" -eq 64
cat /srv/smart-bamboo-dr/config/rpo-evidence

# 人工核对证据后才执行第二阶段；摘要必须原样使用第一阶段输出。
SMART_BAMBOO_FENCE_ADAPTER=/root/smart-bamboo-mobile-cloud-fence \
SMART_BAMBOO_PRIMARY_INSTANCE_ID=ECS-98299861 \
CONFIRM_PRIMARY_UNAVAILABLE=YES \
CONFIRM_SOURCE_RPO_ACCEPTED=YES \
CONFIRM_SOURCE_RPO_EVIDENCE_SHA256="${rpo_sha}" \
CONFIRM_HUMAN_AUTH_ENABLED=1 \
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

中断恢复只能在热备控制台执行。先检查阶段、RPO 证据和数据库状态；`rpo-review` 阶段必须使用证据文件当前的 SHA-256，其他阶段按脚本提示 fail-forward。不要手工删除状态文件、执行 `RESET REPLICA ALL` 或自行切换只读开关：

```bash
cat /srv/smart-bamboo-dr/config/promotion-state
sha256sum /srv/smart-bamboo-dr/config/rpo-evidence
SMART_BAMBOO_FENCE_ADAPTER=/root/smart-bamboo-mobile-cloud-fence \
SMART_BAMBOO_PRIMARY_INSTANCE_ID=ECS-98299861 \
CONFIRM_PRIMARY_UNAVAILABLE=YES \
CONFIRM_SOURCE_RPO_ACCEPTED=YES \
CONFIRM_SOURCE_RPO_EVIDENCE_SHA256="<上一步输出的64位摘要>" \
CONFIRM_HUMAN_AUTH_ENABLED=1 \
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
