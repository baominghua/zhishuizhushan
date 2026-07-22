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


def test_login_script_uses_relative_session_auth_endpoints_and_clears_password():
    script = (project_root() / "admin-login.js").read_text(encoding="utf-8")

    assert 'fetch("/api/auth/config"' in script
    assert 'fetch("/api/auth/login"' in script
    assert 'fetch("/api/auth/me"' in script
    assert '$("#password").value = ""' in script
    assert 'window.location.origin' in script
    assert '18080' not in script


def test_https_requirement_keeps_the_password_submit_control_disabled():
    script = (project_root() / "admin-login.js").read_text(encoding="utf-8")

    assert 'button.disabled = passwordLoginBlocked;' in script
