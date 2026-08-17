from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_login_page_uses_username_and_password_fields():
    root = project_root()
    html = (root / "admin-login.html").read_text(encoding="utf-8")
    script = (root / "admin-login.js").read_text(encoding="utf-8")

    assert 'id="username"' in html
    assert 'id="password"' in html
    assert 'id="accessToken"' not in html
    assert 'autocomplete="username"' in html
    assert 'autocomplete="current-password"' in html
    assert 'credentials: "include"' in script
    assert "sessionStorage.setItem(CSRF_TOKEN_KEY" in script
    assert "smartBambooAdminTokenPersistent" not in script


def test_login_page_keeps_sensitive_deployment_controls_out_of_human_form():
    html = (project_root() / "admin-login.html").read_text(encoding="utf-8")

    assert 'id="apiBase"' not in html
    assert 'id="rememberToken"' not in html
    assert 'id="togglePassword"' in html
    assert 'aria-label=' in html
    assert 'aria-live="polite"' in html


def test_password_label_is_explicit_and_toggle_is_outside_the_label():
    html = (project_root() / "admin-login.html").read_text(encoding="utf-8")

    assert '<label for="password">' in html
    assert html.index('<label for="password">') < html.index('<span class="admin-login-password-control">')


def test_login_script_uses_relative_session_auth_endpoints_and_clears_password():
    script = (project_root() / "admin-login.js").read_text(encoding="utf-8")

    assert 'fetch("/api/auth/config"' in script
    assert 'fetch("/api/auth/login"' in script
    assert 'fetch("/api/auth/me"' in script
    assert '$("#password").value = ""' in script
    assert 'window.location.origin' in script
    assert '18080' not in script


def test_login_page_allows_safe_return_to_v2_deep_links():
    script = (project_root() / "admin-login.js").read_text(encoding="utf-8")
    shell = (
        project_root() / "apps" / "web-operations" / "src" / "components" / "AppShell.tsx"
    ).read_text(encoding="utf-8")

    assert 'target.pathname === "/v2" || target.pathname.startsWith("/v2/")' in script
    assert 'return `${target.pathname}${target.search}${target.hash}`' in script
    assert "returnTo=${encodeURIComponent(returnTo)}" in shell
    assert "returnUrl=" not in shell


def test_https_requirement_keeps_the_password_submit_control_disabled():
    script = (project_root() / "admin-login.js").read_text(encoding="utf-8")

    assert 'button.disabled = passwordLoginBlocked;' in script


def test_admin_common_uses_cookie_sessions_and_csrf_for_human_mutations():
    script = (project_root() / "admin-common.js").read_text(encoding="utf-8")

    assert 'credentials: "include"' in script
    assert 'headers.set("X-CSRF-Token", csrfToken())' in script
    assert 'api("/api/auth/logout", { method: "POST" })' in script
    assert "const LEGACY_TOKEN_KEYS" in script
    assert "localStorage.removeItem(key)" in script


def test_user_page_has_separate_password_security_actions():
    html = (project_root() / "admin-users.html").read_text(encoding="utf-8")

    assert 'id="setTemporaryPassword"' in html
    assert 'data-permission="system.users.setPassword"' in html
    assert 'id="revokeUserSessions"' in html
    assert 'data-permission="system.users.revokeSessions"' in html


def test_every_admin_fetch_explicitly_includes_cookie_credentials():
    root = project_root()

    for script_path in root.glob("admin-*.js"):
        script = script_path.read_text(encoding="utf-8")
        assert script.count('credentials: "include"') >= script.count("fetch("), script_path.name


def test_user_ledger_security_actions_have_stable_space_and_await_revoke_failures():
    root = project_root()
    html = (root / "admin-users.html").read_text(encoding="utf-8")
    script = (root / "admin-users.js").read_text(encoding="utf-8")
    css = (root / "admin.css").read_text(encoding="utf-8")

    assert 'class="user-ledger-table"' in html
    assert "user-row-actions" in script
    assert "await revokeUserSessions(user)" in script
    assert ".user-ledger-table th:last-child" in css
    assert ".user-row-actions" in css
    mobile_css = css.split("@media (max-width: 860px)", 1)[1]
    assert ".user-ledger-table th:last-child" in mobile_css
    assert "min-width: 260px;" in mobile_css
