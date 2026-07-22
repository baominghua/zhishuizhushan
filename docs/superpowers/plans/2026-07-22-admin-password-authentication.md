# Admin Password Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add secure username/password authentication tied to existing admin users, roles, permissions, and data scopes while preserving bearer tokens for dashboard and integration clients.

**Architecture:** Keep `admin_users` as the public account ledger and store secrets in dedicated credential and session stores. Resolve either an HttpOnly-cookie human session or the existing bearer service token into the current `AuthContext`, so all existing authorization code remains reusable. Enable human password login only over HTTPS in production, with an explicit loopback development override.

**Tech Stack:** FastAPI 0.139+, Pydantic 2, MySQL 8.4, JSON development storage, Argon2id via `argon2-cffi`, vanilla JavaScript, Nginx, pytest.

## Global Constraints

- Human passwords are accepted only over HTTPS in production; the current public HTTP `:18080` endpoint remains an acceptance environment.
- Password hashes and session-token hashes never appear in user serializers, API responses, logs, or audit snapshots.
- Five consecutive failed logins lock the account for 15 minutes.
- First login and administrator password reset require a password change.
- Browser sessions use an opaque `HttpOnly`, `SameSite=Lax` cookie plus `X-CSRF-Token` on mutating requests.
- Service/dashboard bearer tokens remain backward compatible and are not accepted by the normal human login form.
- Existing `{module}.manage` permission implications remain unchanged.
- Every production-code change follows RED, GREEN, REFACTOR and is committed independently.

## File Structure

- Create `server/modules/passwords.py`: Argon2id hashing and password-policy validation only.
- Create `server/modules/auth_store.py`: credential/session persistence for MySQL and JSON development mode.
- Create `server/modules/human_auth.py`: login, logout, session, password-change service and routes.
- Modify `server/modules/auth.py`: resolve human sessions before service-token fallback and expose mixed auth configuration.
- Modify `server/modules/admin_users.py`: password reset and session-revocation administration endpoints.
- Modify `server/modules/database.py`: secret JSON paths for development storage.
- Modify `server/modules/mysql_schema.py`: credentials/sessions tables and indexes.
- Modify `server/modules/settings.py`: human-auth, HTTPS, proxy, cookie, and session settings.
- Modify `server/app.py`: include the human-auth router.
- Modify `server/requirements.txt`: add `argon2-cffi`.
- Modify `admin-login.html`, `admin-login.js`, `admin-common.js`, `admin-users.html`, `admin-users.js`, and `admin.css`: formal human login and account-security controls.
- Create `ops/scripts/bootstrap-admin-password.py`: one-time administrator password bootstrap.
- Modify `ops/compose.primary.yml`, `ops/scripts/generate-primary-env.sh`, and `ops/nginx/smart-bamboo.conf`: production switches and trusted proxy headers.
- Create `tests/test_passwords.py`, `tests/test_human_auth.py`, and `tests/test_admin_login_ui.py`; extend existing auth, roles, schema, and deployment tests.

---

### Task 1: Password Policy and Argon2id Primitives

**Files:**
- Create: `server/modules/passwords.py`
- Modify: `server/requirements.txt`
- Create: `tests/test_passwords.py`

**Interfaces:**
- Produces: `password_errors(password: str) -> list[str]`
- Produces: `hash_password(password: str) -> str`
- Produces: `verify_password(password_hash: str, password: str) -> bool`
- Produces: `needs_rehash(password_hash: str) -> bool`

- [ ] **Step 1: Write the failing password-policy and hashing tests**

```python
from server.modules.passwords import hash_password, needs_rehash, password_errors, verify_password


def test_password_policy_requires_length_and_three_character_groups():
    assert "password_too_short" in password_errors("Abc123!")
    assert "password_not_complex_enough" in password_errors("abcdefghij")
    assert password_errors("Bamboo-2026!") == []


def test_argon2_hash_round_trip_never_contains_plaintext():
    encoded = hash_password("Bamboo-2026!")
    assert encoded.startswith("$argon2id$")
    assert "Bamboo-2026!" not in encoded
    assert verify_password(encoded, "Bamboo-2026!") is True
    assert verify_password(encoded, "wrong-password") is False
    assert needs_rehash(encoded) is False
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_passwords.py -q`  
Expected: collection fails with `ModuleNotFoundError: server.modules.passwords`.

- [ ] **Step 3: Add the dependency and minimal password module**

Add `argon2-cffi>=23.1,<26` to `server/requirements.txt` and create:

```python
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)


def password_errors(password: str) -> list[str]:
    errors: list[str] = []
    if len(password) < 10:
        errors.append("password_too_short")
    groups = sum(
        (
            any(char.isupper() for char in password),
            any(char.islower() for char in password),
            any(char.isdigit() for char in password),
            any(not char.isalnum() for char in password),
        )
    )
    if groups < 3:
        errors.append("password_not_complex_enough")
    return errors


def hash_password(password: str) -> str:
    errors = password_errors(password)
    if errors:
        raise ValueError(",".join(errors))
    return _HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _HASHER.verify(password_hash, password)
    except (InvalidHashError, VerifyMismatchError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
```

- [ ] **Step 4: Install the dependency and verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pip install "argon2-cffi>=23.1,<26"`  
Run: `.\.venv\Scripts\python.exe -m pytest tests/test_passwords.py -q`  
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add server/requirements.txt server/modules/passwords.py tests/test_passwords.py
git commit -m "Add password hashing primitives"
```

---

### Task 2: Credential and Session Persistence

**Files:**
- Modify: `server/modules/mysql_schema.py`
- Modify: `server/modules/database.py`
- Create: `server/modules/auth_store.py`
- Create: `tests/test_auth_store.py`
- Modify: `tests/test_mysql_schema.py`

**Interfaces:**
- Produces: `CredentialRecord` and `SessionRecord` typed dictionaries.
- Produces: `credential_for_user(user_id: str) -> CredentialRecord | None`
- Produces: `save_credential(record: CredentialRecord) -> None`
- Produces: `record_failed_login(user_id: str, now: datetime) -> CredentialRecord`
- Produces: `reset_failed_login(user_id: str) -> CredentialRecord`
- Produces: `create_session(user_id: str, credential_version: int, request: Request) -> tuple[str, str, SessionRecord]`
- Produces: `session_for_token(raw_token: str, now: datetime) -> SessionRecord | None`
- Produces: `revoke_session(raw_token: str) -> None` and `revoke_user_sessions(user_id: str, except_session_id: str | None = None) -> int`

- [ ] **Step 1: Write failing JSON-store behavior tests**

```python
from datetime import UTC, datetime, timedelta

from server.modules.auth_store import (
    credential_for_user,
    new_credential,
    record_failed_login,
    save_credential,
    session_for_token,
    store_session,
)


def test_fifth_failure_locks_for_fifteen_minutes(isolated_env):
    now = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    save_credential(new_credential("user-1", "$argon2id$test"))
    for _ in range(5):
        credential = record_failed_login("user-1", now)
    assert credential["failedLoginCount"] == 5
    assert credential["lockedUntil"] == (now + timedelta(minutes=15)).isoformat()


def test_session_lookup_uses_hash_and_rejects_expired_token(isolated_env):
    now = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    raw_token, record = store_session("user-1", 1, "csrf-hash", now, "127.0.0.1", "pytest")
    assert raw_token not in str(record)
    assert session_for_token(raw_token, now)["userId"] == "user-1"
    assert session_for_token(raw_token, now + timedelta(hours=25)) is None
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_auth_store.py -q`  
Expected: import fails because `auth_store` does not exist.

- [ ] **Step 3: Add schema tests for the secret tables**

```python
def test_mysql_schema_contains_auth_secret_tables():
    sql = "\n".join(mysql_platform_schema_statements())
    assert "CREATE TABLE IF NOT EXISTS admin_user_credentials" in sql
    assert "CREATE TABLE IF NOT EXISTS admin_sessions" in sql
    assert "UNIQUE KEY uq_admin_user_credentials_user" in sql
    assert "UNIQUE KEY uq_admin_sessions_token_hash" in sql
    assert "KEY idx_admin_sessions_expiry" in sql
```

- [ ] **Step 4: Run the schema test and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_mysql_schema.py -q`  
Expected: assertion fails because both tables are absent.

- [ ] **Step 5: Add the MySQL tables and secret JSON paths**

Add `admin_credentials_json_path()` and `admin_sessions_json_path()` under the existing admin data directory. Add MySQL tables with these exact security fields:

```sql
CREATE TABLE IF NOT EXISTS admin_user_credentials (
    id CHAR(36) PRIMARY KEY,
    admin_user_id CHAR(36) NOT NULL,
    password_hash VARCHAR(512) NOT NULL,
    password_changed_at DATETIME(6),
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
    failed_login_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    locked_until DATETIME(6),
    credential_version INT UNSIGNED NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    UNIQUE KEY uq_admin_user_credentials_user (admin_user_id),
    CONSTRAINT fk_admin_user_credentials_user FOREIGN KEY (admin_user_id) REFERENCES admin_users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    id CHAR(36) PRIMARY KEY,
    admin_user_id CHAR(36) NOT NULL,
    token_hash CHAR(64) NOT NULL,
    csrf_token_hash CHAR(64) NOT NULL,
    credential_version INT UNSIGNED NOT NULL,
    ip_address VARCHAR(64),
    user_agent VARCHAR(512),
    issued_at DATETIME(6) NOT NULL,
    last_seen_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    revoked_at DATETIME(6),
    UNIQUE KEY uq_admin_sessions_token_hash (token_hash),
    KEY idx_admin_sessions_user (admin_user_id),
    KEY idx_admin_sessions_expiry (expires_at, revoked_at),
    CONSTRAINT fk_admin_sessions_user FOREIGN KEY (admin_user_id) REFERENCES admin_users(id) ON DELETE CASCADE
);
```

- [ ] **Step 6: Implement the persistence module**

Use `secrets.token_urlsafe(48)` for raw session tokens, `secrets.token_urlsafe(32)` for CSRF tokens, and store only `hashlib.sha256(value.encode()).hexdigest()`. JSON files store the same normalized dictionaries as MySQL. All timestamp comparisons use timezone-aware UTC datetimes in Python and UTC-naive values only at the MySQL adapter boundary.

- [ ] **Step 7: Verify persistence tests GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_auth_store.py tests/test_mysql_schema.py -q`  
Expected: all selected tests pass.

- [ ] **Step 8: Commit**

```bash
git add server/modules/mysql_schema.py server/modules/database.py server/modules/auth_store.py tests/test_auth_store.py tests/test_mysql_schema.py
git commit -m "Add credential and session storage"
```

---

### Task 3: Login, Logout, Session, and Password Change APIs

**Files:**
- Create: `server/modules/human_auth.py`
- Modify: `server/modules/settings.py`
- Modify: `server/app.py`
- Create: `tests/test_human_auth.py`

**Interfaces:**
- Produces routes `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/session`, and `POST /api/auth/change-password`.
- Produces `human_session_context(request: Request) -> AuthContext | None` for Task 4.
- Consumes user lookup from `admin_users.user_by_username()` and persistence from Task 2.

- [ ] **Step 1: Write failing login success and cookie tests**

```python
def test_login_returns_profile_and_sets_http_only_cookie(password_user_client):
    client, _user = password_user_client
    response = client.post(
        "/api/auth/login",
        json={"username": "field_worker", "password": "Bamboo-2026!"},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert response.status_code == 200
    assert response.json()["user"] == "field_worker"
    assert response.json()["mustChangePassword"] is True
    assert response.json()["csrfToken"]
    cookie = response.headers["set-cookie"]
    assert "smart_bamboo_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
```

- [ ] **Step 2: Write failing rejection and lockout tests**

```python
def test_login_rejects_http_in_production(password_user_client, monkeypatch):
    client, _user = password_user_client
    monkeypatch.setenv("SMART_BAMBOO_DEPLOYMENT_MODE", "production")
    response = client.post("/api/auth/login", json={"username": "field_worker", "password": "Bamboo-2026!"})
    assert response.status_code == 426
    assert response.json()["detail"] == "HTTPS is required for password login"


def test_five_bad_passwords_lock_account(password_user_client):
    client, _user = password_user_client
    headers = {"X-Forwarded-Proto": "https"}
    for _ in range(5):
        response = client.post("/api/auth/login", json={"username": "field_worker", "password": "wrong-password"}, headers=headers)
    assert response.status_code == 423
    assert response.json()["detail"] == "Account temporarily locked"
```

- [ ] **Step 3: Run login tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_human_auth.py -q`  
Expected: route responses are `404`.

- [ ] **Step 4: Add explicit settings**

Extend `PlatformSettings` with `human_auth_enabled`, `auth_require_https`, `trust_proxy_headers`, `session_idle_seconds`, `session_absolute_seconds`, and `session_cookie_name`. Defaults are enabled, HTTPS required in production, proxy trust disabled, idle eight hours, absolute 24 hours, and cookie name `smart_bamboo_session`.

- [ ] **Step 5: Implement the router and auth service**

Use request models with `extra="forbid"`. Login normalizes the username, rejects missing/deleted/non-active users with the same generic `401 Invalid username or password`, checks lock state, verifies Argon2id, records failures, resets counters on success, creates a session, and returns the effective profile plus CSRF token. Logout and password change require the CSRF header. Password change validates the current password and new policy, increments `credential_version`, revokes other sessions, and clears `must_change_password`.

- [ ] **Step 6: Verify API tests GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_human_auth.py -q`  
Expected: login, HTTP rejection, lockout, logout, expiry, CSRF, and password-change tests all pass.

- [ ] **Step 7: Commit**

```bash
git add server/modules/human_auth.py server/modules/settings.py server/app.py tests/test_human_auth.py
git commit -m "Add human authentication APIs"
```

---

### Task 4: Unified Request Context and Service-token Compatibility

**Files:**
- Modify: `server/modules/auth.py`
- Modify: `tests/test_auth.py`
- Modify: `tests/test_human_auth.py`

**Interfaces:**
- Consumes: `human_session_context(request)` from Task 3.
- Preserves: `request_context(request) -> AuthContext` for all existing routers.
- Changes: `/api/auth/config` reports session and bearer capabilities.

- [ ] **Step 1: Write failing compatibility tests**

```python
def test_request_context_accepts_human_session(password_user_client):
    client, _user = password_user_client
    login = client.post(
        "/api/auth/login",
        json={"username": "field_worker", "password": "Bamboo-2026!"},
        headers={"X-Forwarded-Proto": "https"},
    )
    response = client.get("/api/auth/me")
    assert login.status_code == 200
    assert response.status_code == 200
    assert response.json()["authType"] == "session"


def test_service_bearer_token_remains_supported(app_client, configured_service_token):
    response = app_client.get("/api/auth/me", headers={"Authorization": "Bearer secure-test-token"})
    assert response.status_code == 200
    assert response.json()["authType"] == "service-token"
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_auth.py tests/test_human_auth.py -q`  
Expected: session request receives `401` or lacks `authType`.

- [ ] **Step 3: Resolve session first, then service token**

Change `request_context()` to return a valid human context when the cookie resolves. If no human session exists, preserve the current bearer-token path exactly. Header-based development identity remains available only when authentication is not required.

Return this configuration shape:

```python
{
    "required": settings.auth_required,
    "scheme": "session-or-bearer",
    "humanLoginEnabled": settings.human_auth_enabled,
    "httpsRequired": settings.auth_require_https,
    "serviceTokenEnabled": bool(token_profiles()),
}
```

Add `authType`, `mustChangePassword`, and `sessionExpiresAt` to `/api/auth/me` without changing roles, permissions, menus, or data scopes.

- [ ] **Step 4: Run auth and authorization regression tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_auth.py tests/test_admin_roles.py -q`  
Expected: all selected tests pass, including the existing service-token test.

- [ ] **Step 5: Commit**

```bash
git add server/modules/auth.py tests/test_auth.py tests/test_human_auth.py
git commit -m "Unify session and service authentication"
```

---

### Task 5: Account Password Administration and Bootstrap

**Files:**
- Modify: `server/modules/admin_users.py`
- Modify: `server/modules/admin_roles.py`
- Create: `ops/scripts/bootstrap-admin-password.py`
- Modify: `tests/test_admin_roles.py`
- Create: `tests/test_bootstrap_admin_password.py`

**Interfaces:**
- Produces: `POST /api/admin/users/{user_id}/set-password`
- Produces: `POST /api/admin/users/{user_id}/revoke-sessions`
- Produces permissions `system.users.setPassword` and `system.users.revokeSessions`.

- [ ] **Step 1: Write failing permission and reset tests**

```python
def test_password_reset_requires_independent_permission(app_client, seeded_user):
    denied = app_client.post(
        f"/api/admin/users/{seeded_user['id']}/set-password",
        json={"temporaryPassword": "Bamboo-2026!"},
        headers={"X-RS-Roles": "system.users.update"},
    )
    assert denied.status_code == 403
    allowed = app_client.post(
        f"/api/admin/users/{seeded_user['id']}/set-password",
        json={"temporaryPassword": "Bamboo-2026!"},
        headers={"X-RS-Roles": "system.users.setPassword"},
    )
    assert allowed.status_code == 200
    assert allowed.json() == {"ok": True, "mustChangePassword": True}
```

- [ ] **Step 2: Run and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_admin_roles.py::test_password_reset_requires_independent_permission -q`  
Expected: reset route returns `404`.

- [ ] **Step 3: Add permissions and endpoints**

Add both permissions to the user-management catalog and to the `system.users.manage` implication list. The reset endpoint validates policy, hashes the temporary password, increments credential version, sets `mustChangePassword`, clears lock state, revokes sessions, and writes an audit event containing only changed field names. Session revocation returns `{ "ok": true, "revoked": <count> }`.

- [ ] **Step 4: Add a safe bootstrap command**

The script accepts `--username`, `--display-name`, and optional `--password-stdin`. Without password input it generates a 20-character temporary password with `secrets`, creates/updates an active admin user, assigns the admin role, writes the credential, prints the temporary password exactly once, and never writes it to a file. It exits non-zero unless the configured backend is MySQL or an explicit `--allow-json-development` flag is supplied.

- [ ] **Step 5: Verify endpoint and bootstrap tests GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_admin_roles.py tests/test_bootstrap_admin_password.py -q`  
Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add server/modules/admin_users.py server/modules/admin_roles.py ops/scripts/bootstrap-admin-password.py tests/test_admin_roles.py tests/test_bootstrap_admin_password.py
git commit -m "Add account password administration"
```

---

### Task 6: Username and Password Login Interface

**Files:**
- Modify: `admin-login.html`
- Modify: `admin-login.js`
- Modify: `admin.css`
- Create: `tests/test_admin_login_ui.py`

**Interfaces:**
- Consumes: `/api/auth/config`, `/api/auth/login`, and `/api/auth/me`.
- Stores: CSRF token and non-secret profile in `sessionStorage`; stores no password or human session token.

- [ ] **Step 1: Write failing DOM contract tests**

```python
def test_login_page_uses_username_and_password_fields(project_root):
    html = (project_root / "admin-login.html").read_text(encoding="utf-8")
    script = (project_root / "admin-login.js").read_text(encoding="utf-8")
    assert 'id="username"' in html
    assert 'id="password"' in html
    assert 'id="accessToken"' not in html
    assert 'autocomplete="username"' in html
    assert 'autocomplete="current-password"' in html
    assert 'credentials: "include"' in script
    assert 'sessionStorage.setItem(CSRF_TOKEN_KEY' in script
    assert "smartBambooAdminTokenPersistent" not in script
```

- [ ] **Step 2: Run and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_admin_login_ui.py -q`  
Expected: assertions fail because the token form is still present.

- [ ] **Step 3: Replace the token form**

Render username, password, show-password toggle, submit button, and an accessible live status. Remove API URL and remember-token fields from normal login. Fetch `/api/auth/config` on load. If production human login is blocked by HTTPS, show a clear “请先配置 HTTPS” state and do not submit credentials. A deployment-only service-token form may be shown only when the server reports `humanLoginEnabled=false`; it is removed once human login is enabled.

- [ ] **Step 4: Implement session login**

POST JSON `{username, password}` with `credentials: "include"`. Store only `csrfToken` and the returned non-secret profile in `sessionStorage`, clear the password input in `finally`, and redirect through the existing safe `returnTo` validation. Handle `401`, `423`, `426`, and `mustChangePassword` with distinct Chinese messages.

- [ ] **Step 5: Verify login UI tests and JavaScript syntax**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_admin_login_ui.py -q`  
Run: `node --check admin-login.js`  
Expected: tests pass and Node exits `0`.

- [ ] **Step 6: Commit**

```bash
git add admin-login.html admin-login.js admin.css tests/test_admin_login_ui.py
git commit -m "Replace admin token login with account login"
```

---

### Task 7: Session-aware Admin Shell and Forced Password Change

**Files:**
- Modify: `admin-common.js`
- Modify: `admin-users.html`
- Modify: `admin-users.js`
- Modify: `admin.css`
- Modify: `tests/test_admin_login_ui.py`
- Modify: `tests/test_admin_separation.py`

**Interfaces:**
- Consumes: the cookie session and CSRF token created by Task 6.
- Produces: `AdminCommon.refreshSession()` and `AdminCommon.logout()`.

- [ ] **Step 1: Write failing shell-security tests**

```python
def test_admin_common_uses_cookie_and_csrf(project_root):
    script = (project_root / "admin-common.js").read_text(encoding="utf-8")
    assert 'credentials: "include"' in script
    assert 'headers.set("X-CSRF-Token", csrfToken())' in script
    assert 'api("/api/auth/logout", { method: "POST" })' in script
    assert "smartBambooAdminTokenPersistent" not in script


def test_user_page_has_password_security_actions(project_root):
    html = (project_root / "admin-users.html").read_text(encoding="utf-8")
    assert 'id="setTemporaryPassword"' in html
    assert 'data-permission="system.users.setPassword"' in html
    assert 'id="revokeUserSessions"' in html
    assert 'data-permission="system.users.revokeSessions"' in html
```

- [ ] **Step 2: Run and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_admin_login_ui.py tests/test_admin_separation.py -q`  
Expected: assertions fail for cookie, CSRF, and account-security actions.

- [ ] **Step 3: Convert the shared API client**

Every fetch uses `credentials: "include"`. Mutating methods set `X-CSRF-Token` from session storage. Remove persistent human-token storage. On startup, call `/api/auth/me`, cache the profile, render menus from effective permissions even when no debug role field exists, and redirect on `401`. Logout calls the server before clearing local non-secret state.

- [ ] **Step 4: Add forced-change and account-security UI**

When `mustChangePassword=true`, block normal admin content with a focused change-password dialog. In the user ledger, add separate “设置临时密码” and “撤销会话” actions with their own permissions. Temporary password inputs never reuse the general user payload and are cleared after submission.

- [ ] **Step 5: Verify UI tests and all admin JavaScript syntax**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_admin_login_ui.py tests/test_admin_separation.py -q`  
Run: `Get-ChildItem -Filter *.js | ForEach-Object { node --check $_.FullName }`  
Expected: tests pass and every syntax check exits `0`.

- [ ] **Step 6: Commit**

```bash
git add admin-common.js admin-users.html admin-users.js admin.css tests/test_admin_login_ui.py tests/test_admin_separation.py
git commit -m "Make admin shell session aware"
```

---

### Task 8: Production Configuration, HTTPS Gate, and Migration Safety

**Files:**
- Modify: `ops/compose.primary.yml`
- Modify: `ops/scripts/generate-primary-env.sh`
- Modify: `ops/nginx/smart-bamboo.conf`
- Modify: `tests/test_cloud_dual_host_deployment.py`
- Modify: `tests/test_deployment_config.py`
- Modify: `server/modules/settings.py`

**Interfaces:**
- Produces environment variables `SMART_BAMBOO_HUMAN_AUTH_ENABLED`, `SMART_BAMBOO_AUTH_REQUIRE_HTTPS`, `SMART_BAMBOO_TRUST_PROXY_HEADERS`, and `SMART_BAMBOO_SESSION_COOKIE_SECURE`.

- [ ] **Step 1: Write failing deployment configuration tests**

```python
def test_primary_compose_enforces_secure_human_auth(project_root):
    compose = (project_root / "ops/compose.primary.yml").read_text(encoding="utf-8")
    assert 'SMART_BAMBOO_HUMAN_AUTH_ENABLED: "${SMART_BAMBOO_HUMAN_AUTH_ENABLED:-0}"' in compose
    assert 'SMART_BAMBOO_AUTH_REQUIRE_HTTPS: "1"' in compose
    assert 'SMART_BAMBOO_TRUST_PROXY_HEADERS: "1"' in compose
    assert 'SMART_BAMBOO_SESSION_COOKIE_SECURE: "1"' in compose


def test_nginx_forwards_transport_and_client_context(project_root):
    nginx = (project_root / "ops/nginx/smart-bamboo.conf").read_text(encoding="utf-8")
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in nginx
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in nginx
```

- [ ] **Step 2: Run and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cloud_dual_host_deployment.py tests/test_deployment_config.py -q`  
Expected: compose assertions fail because human-auth settings are absent.

- [ ] **Step 3: Add secure production defaults**

Generate `SMART_BAMBOO_HUMAN_AUTH_ENABLED=0` until TLS is installed, with HTTPS, trusted proxy, and secure cookie requirements already enabled. The formal rollout changes only `HUMAN_AUTH_ENABLED` to `1` after HTTPS verification. Keep the dashboard token in `satellite-config.local.js`; remove generation of a human-facing `admin-token.txt` after the bootstrap administrator is confirmed.

- [ ] **Step 4: Extend production readiness checks**

Production readiness reports blocking issues for human auth enabled without HTTPS enforcement, secure cookies, trusted proxy headers, credentials table, sessions table, or at least one active administrator credential. Service-token-only acceptance mode remains ready but reports `human_auth_pending_https` as a non-blocking warning.

- [ ] **Step 5: Run deployment tests GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cloud_dual_host_deployment.py tests/test_deployment_config.py -q`  
Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add ops/compose.primary.yml ops/scripts/generate-primary-env.sh ops/nginx/smart-bamboo.conf server/modules/settings.py tests/test_cloud_dual_host_deployment.py tests/test_deployment_config.py
git commit -m "Secure production human authentication"
```

---

### Task 9: Full Verification and Deployment Runbook

**Files:**
- Create: `docs/admin-password-authentication-runbook.md`
- Modify: `docs/smart-bamboo-production-checklist.md`

**Interfaces:**
- Documents exact bootstrap, HTTPS activation, verification, rollback, and service-token compatibility commands.

- [ ] **Step 1: Run focused backend suites**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_passwords.py tests/test_auth_store.py tests/test_human_auth.py tests/test_auth.py tests/test_admin_roles.py -q`  
Expected: all selected tests pass with no warnings introduced by this work.

- [ ] **Step 2: Run full regression suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`  
Expected: all tests pass.

- [ ] **Step 3: Run frontend syntax verification**

Run: `Get-ChildItem -Filter *.js | ForEach-Object { node --check $_.FullName }`  
Expected: every JavaScript file exits `0`.

- [ ] **Step 4: Write the operations runbook**

Document these exact gates in order: database backup, schema migration, bootstrap administrator, verify temporary login on HTTPS, force password change, verify role/data scope, verify service dashboard token, revoke old admin token, inspect login audit, and roll back by setting `SMART_BAMBOO_HUMAN_AUTH_ENABLED=0` without deleting credential/session tables.

- [ ] **Step 5: Perform local browser acceptance**

Verify login success, bad password, fifth-attempt lock, forced change, logout, expired session redirect, disabled account, permission-controlled password reset, session revocation, and the existing dashboard service token. Capture desktop and mobile screenshots and verify no text overlap or exposed token fields.

- [ ] **Step 6: Commit verification documentation**

```bash
git add docs/admin-password-authentication-runbook.md docs/smart-bamboo-production-checklist.md
git commit -m "Document password authentication rollout"
```

- [ ] **Step 7: Push only after all gates pass**

Run: `git status --short --branch`  
Expected: only pre-existing unrelated untracked files remain.  
Run: `git push origin codex/production-deploy`  
Expected: the remote branch advances to the verified authentication release.

## Follow-up Plans

After this plan is green, create and execute these independent plans against the approved design specification:

1. `2026-07-22-metadata-forms-and-core-relations.md`: shared form schema, reference selector, normalized relationship validation, and core registries.
2. `2026-07-22-operations-and-decision-modules.md`: operations, maintenance, forecast, harvest, income, performance, and carbon modules.
3. `2026-07-22-industry-platform-modules.md`: trade, logistics, QR, finance, prices, mobile channels, migration report, and final cross-module acceptance.

## Self-review Result

- Spec coverage: human/service identity separation, Argon2id, lockout, forced change, sessions, CSRF, permissions, bootstrap, HTTPS gate, compatibility, audit, testing, and rollout are each mapped to a task.
- Placeholder scan: every implementation and verification step contains a concrete action, interface, command, and expected result.
- Type consistency: `AuthContext`, credential/session function names, cookie name, CSRF header, permission codes, endpoint paths, and environment variables are consistent across tasks.
