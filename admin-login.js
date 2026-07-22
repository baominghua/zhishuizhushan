(() => {
  const CSRF_TOKEN_KEY = "smartBambooCsrfToken";
  const PROFILE_KEY = "smartBambooAuthProfile";
  let authConfig = null;
  let passwordLoginBlocked = false;

  const $ = (selector) => document.querySelector(selector);

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

  function setStatus(message, kind = "") {
    const status = $("#loginStatus");
    status.textContent = message;
    status.dataset.kind = kind;
  }

  function profileFrom(payload) {
    const { csrfToken, ...profile } = payload && typeof payload === "object" ? payload : {};
    return profile;
  }

  function storeProfile(payload) {
    sessionStorage.setItem(PROFILE_KEY, JSON.stringify(profileFrom(payload)));
  }

  function storeCsrfToken(payload) {
    if (payload && payload.csrfToken) {
      sessionStorage.setItem(CSRF_TOKEN_KEY, payload.csrfToken);
    }
  }

  async function readPayload(response) {
    return response.json().catch(() => ({}));
  }

  function setPasswordLoginBlocked(blocked) {
    passwordLoginBlocked = blocked;
    $("#username").disabled = blocked;
    $("#password").disabled = blocked;
    $("#togglePassword").disabled = blocked;
    $("#loginButton").disabled = blocked;
  }

  function passwordChangeMessage() {
    return "该账户需要先修改初始密码，请联系管理员完成密码更新。";
  }

  function completeLogin(profile) {
    storeProfile(profile);
    if (profile.mustChangePassword) {
      setStatus(passwordChangeMessage(), "warning");
      return;
    }
    setStatus(`登录成功：${profile.user || "后台用户"}`, "success");
    const returnTo = safeReturnPath(new URLSearchParams(window.location.search).get("returnTo"));
    window.location.replace(returnTo);
  }

  async function fetchCurrentProfile() {
    const response = await fetch("/api/auth/me", { credentials: "include" });
    const payload = await readPayload(response);
    if (!response.ok) {
      const error = new Error(payload.detail || `身份验证失败（${response.status}）`);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function showServiceTokenFallback() {
    const fallback = $("#serviceTokenFallback");
    $("#loginForm").hidden = true;
    fallback.hidden = false;
    fallback.replaceChildren();

    const form = document.createElement("form");
    form.id = "serviceTokenForm";
    const label = document.createElement("label");
    const caption = document.createElement("span");
    caption.textContent = "部署服务令牌";
    const token = document.createElement("input");
    token.id = "serviceToken";
    token.type = "password";
    token.autocomplete = "off";
    token.required = true;
    label.append(caption, token);
    const button = document.createElement("button");
    button.type = "submit";
    button.textContent = "验证服务令牌";
    form.append(label, button);
    fallback.append(form);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      button.disabled = true;
      setStatus("正在验证部署服务令牌...", "busy");
      try {
        const response = await fetch("/api/auth/me", {
          credentials: "include",
          headers: { Authorization: `Bearer ${token.value.trim()}` },
        });
        const payload = await readPayload(response);
        if (!response.ok) throw new Error(payload.detail || "服务令牌验证失败。");
        storeProfile(payload);
        setStatus("服务令牌验证通过，请由部署系统继续访问后台。", "success");
      } catch (error) {
        setStatus(error.message || "服务令牌验证失败。", "error");
      } finally {
        token.value = "";
        button.disabled = false;
      }
    });
  }

  function applyAuthConfig(config) {
    authConfig = config || {};
    if (authConfig.humanLoginEnabled === false) {
      showServiceTokenFallback();
      return;
    }
    $("#serviceTokenFallback").replaceChildren();
    $("#serviceTokenFallback").hidden = true;
    const requiresHttps = authConfig.httpsRequired && window.location.protocol !== "https:";
    if (requiresHttps) {
      setPasswordLoginBlocked(true);
      setStatus("当前部署要求使用 HTTPS，请先通过 HTTPS 安全地址访问后台。", "error");
    }
  }

  async function submitLogin(event) {
    event.preventDefault();
    const button = $("#loginButton");
    const username = $("#username").value.trim();
    const password = $("#password").value;
    if (passwordLoginBlocked) {
      setStatus("当前部署要求使用 HTTPS，请先通过 HTTPS 安全地址访问后台。", "error");
      return;
    }
    if (!username || !password) return;

    button.disabled = true;
    setStatus("正在登录...", "busy");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const payload = await readPayload(response);
      if (!response.ok) {
        if (response.status === 401) throw new Error("用户名或密码不正确，请重试。");
        if (response.status === 423) throw new Error("账户已临时锁定，请稍后再试或联系管理员。");
        if (response.status === 426) {
          setPasswordLoginBlocked(true);
          throw new Error("当前部署要求使用 HTTPS，请先通过 HTTPS 安全地址访问后台。");
        }
        throw new Error(payload.detail || `登录失败（${response.status}）`);
      }
      storeCsrfToken(payload);
      const profile = await fetchCurrentProfile();
      completeLogin({ ...profile, mustChangePassword: Boolean(payload.mustChangePassword || profile.mustChangePassword) });
    } catch (error) {
      setStatus(error.message || "身份验证失败。", "error");
    } finally {
      $("#password").value = "";
      button.disabled = passwordLoginBlocked;
    }
  }

  async function initialize() {
    $("#togglePassword").addEventListener("click", () => {
      const password = $("#password");
      const visible = password.type === "password";
      password.type = visible ? "text" : "password";
      $("#togglePassword").setAttribute("aria-pressed", String(visible));
      $("#togglePassword").setAttribute("aria-label", visible ? "隐藏密码" : "显示密码");
      $("#togglePassword").setAttribute("title", visible ? "隐藏密码" : "显示密码");
    });
    $("#loginForm").addEventListener("submit", submitLogin);
    try {
      const response = await fetch("/api/auth/config", { credentials: "include" });
      const config = await readPayload(response);
      if (!response.ok) throw new Error(config.detail || "无法获取登录配置。");
      applyAuthConfig(config);
      if (authConfig.humanLoginEnabled !== false) {
        try {
          const profile = await fetchCurrentProfile();
          completeLogin(profile);
        } catch (error) {
          if (error.status !== 401) throw error;
        }
      }
    } catch (error) {
      setStatus(error.message || "登录服务暂不可用，请稍后重试。", "error");
    }
  }

  initialize();
})();
