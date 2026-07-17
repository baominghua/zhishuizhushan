(() => {
  const SESSION_TOKEN_KEY = "smartBambooAdminToken";
  const PERSISTENT_TOKEN_KEY = "smartBambooAdminTokenPersistent";
  const PROFILE_KEY = "smartBambooAuthProfile";
  const DEFAULT_API_BASE = /^https?:$/.test(window.location.protocol)
    ? window.location.origin
    : "http://127.0.0.1:8010";

  const $ = (selector) => document.querySelector(selector);

  function normalizeApiBase(value) {
    return String(value || DEFAULT_API_BASE).trim().replace(/\/+$/, "");
  }

  function safeReturnPath(value) {
    try {
      const target = new URL(value || "admin.html", window.location.origin);
      const fileName = target.pathname.split("/").pop() || "";
      const isAdminPage = /^admin(?:-[a-z0-9-]+)?\.html$/i.test(fileName);
      if (target.origin !== window.location.origin || !isAdminPage || fileName === "admin-login.html") {
        return "admin.html";
      }
      return `${fileName}${target.search}${target.hash}`;
    } catch (error) {
      return "admin.html";
    }
  }

  function savedToken() {
    return sessionStorage.getItem(SESSION_TOKEN_KEY) || localStorage.getItem(PERSISTENT_TOKEN_KEY) || "";
  }

  function setStatus(message, kind = "") {
    const status = $("#loginStatus");
    status.textContent = message;
    status.dataset.kind = kind;
  }

  async function submitLogin(event) {
    event.preventDefault();
    const button = $("#loginButton");
    const apiBase = normalizeApiBase($("#apiBase").value);
    const token = $("#accessToken").value.trim() || savedToken();
    if (!token) {
      setStatus("请输入访问令牌。", "error");
      return;
    }

    button.disabled = true;
    setStatus("正在验证身份...", "busy");
    try {
      const response = await fetch(`${apiBase}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || `登录失败（${response.status}）`);

      sessionStorage.removeItem(SESSION_TOKEN_KEY);
      localStorage.removeItem(PERSISTENT_TOKEN_KEY);
      const storage = $("#rememberToken").checked ? localStorage : sessionStorage;
      const key = $("#rememberToken").checked ? PERSISTENT_TOKEN_KEY : SESSION_TOKEN_KEY;
      storage.setItem(key, token);
      sessionStorage.setItem(PROFILE_KEY, JSON.stringify(payload));
      localStorage.setItem("smartBambooApiBase", apiBase);
      setStatus(`身份验证通过：${payload.user || "后台用户"}`, "success");
      const returnTo = safeReturnPath(new URLSearchParams(window.location.search).get("returnTo"));
      window.location.replace(returnTo);
    } catch (error) {
      setStatus(error.message || "身份验证失败。", "error");
    } finally {
      button.disabled = false;
    }
  }

  function initialize() {
    $("#apiBase").value = normalizeApiBase(localStorage.getItem("smartBambooApiBase") || DEFAULT_API_BASE);
    if (savedToken()) setStatus("检测到已有会话，可直接重新验证。", "info");
    $("#loginForm").addEventListener("submit", submitLogin);
  }

  initialize();
})();
