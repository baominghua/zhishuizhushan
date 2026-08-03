const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = `${fs.readFileSync(path.join(process.cwd(), "admin-common.js"), "utf8")}\nglobalThis.__AdminCommon = AdminCommon;`;
const dashboardSource = fs.readFileSync(path.join(process.cwd(), "admin-dashboard.js"), "utf8").replace(
  /\n  initialize\(\);\n\}\)\(\);\s*$/,
  "\n  globalThis.__AdminDashboard = { fetchDeploymentHealth };\n})();",
);

class ClassList {
  constructor() { this.values = new Set(); }
  add(...values) { values.forEach((value) => this.values.add(value)); }
  remove(...values) { values.forEach((value) => this.values.delete(value)); }
  toggle(value, force) {
    const enabled = force === undefined ? !this.values.has(value) : Boolean(force);
    if (enabled) this.add(value); else this.remove(value);
    return enabled;
  }
  contains(value) { return this.values.has(value); }
}

class Element {
  constructor(id = "", documentRef = null) {
    this.id = id;
    this.documentRef = documentRef;
    this.attributes = {};
    this.classList = new ClassList();
    this.dataset = {};
    this.hidden = false;
    this.listeners = new Map();
    this.textContent = "";
    this.value = "";
    this.children = [];
    this.open = false;
  }
  addEventListener(event, listener) { this.listeners.set(event, listener); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || null; }
  removeAttribute(name) { delete this.attributes[name]; }
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.append(child); return child; }
  prepend(child) { this.children.unshift(child); }
  insertBefore(child) { this.append(child); }
  focus() { this.focused = true; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  set innerHTML(value) {
    this._innerHTML = value;
    for (const match of String(value).matchAll(/id="([^"]+)"/g)) {
      const child = new Element(match[1], this.documentRef);
      this.documentRef.elements.set(`#${child.id}`, child);
      this.children.push(child);
    }
  }
  get innerHTML() { return this._innerHTML || ""; }
}

function jsonResponse(status, payload = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "status",
    headers: { get: () => "application/json" },
    json: async () => payload,
    text: async () => JSON.stringify(payload),
    clone() { return jsonResponse(status, payload); },
  };
}

function deferred() {
  let resolve;
  return { promise: new Promise((done) => { resolve = done; }), resolve };
}

function storage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) { return values.get(key) || null; },
    setItem(key, value) { values.set(key, String(value)); },
    removeItem(key) { values.delete(key); },
    has(key) { return values.has(key); },
  };
}

function createHarness({ responses, href = "https://zhushan.example/admin-users.html?role=operator#ledger", script = source, session = {}, local = {}, cookie = "" }) {
  const elements = new Map();
  const documentRef = {
    elements,
    body: new Element("body"),
    createElement() { return new Element("", documentRef); },
    querySelector(selector) { return elements.get(selector) || null; },
    querySelectorAll(selector) {
      if (selector === "[data-permission], [data-permission-all], [data-permission-any]") {
        return [documentRef.body];
      }
      return [];
    },
  };
  documentRef.body.dataset = { adminModule: "users", permission: "system.users.view" };
  documentRef.cookie = cookie;
  for (const id of ["apiBase", "statusBadge", "statusText"]) {
    const element = new Element(id, documentRef);
    elements.set(`#${id}`, element);
  }
  const calls = [];
  const queue = [...responses];
  const sessionStorage = storage({ smartBambooCsrfToken: "csrf-secret", smartBambooAuthProfile: "old profile", ...session });
  const localStorage = storage(local);
  const location = {
    href,
    origin: new URL(href).origin,
    protocol: new URL(href).protocol,
    pathname: new URL(href).pathname,
    search: new URL(href).search,
    hash: new URL(href).hash,
    replace(value) { this.replacedWith = value; },
  };
  const context = {
    Headers,
    FormData,
    URL,
    URLSearchParams,
    document: documentRef,
    sessionStorage,
    localStorage,
    window: { location, setTimeout(callback) { callback(); } },
    fetch(url, options = {}) {
      calls.push({ url, options });
      const response = queue.shift();
      if (!response) throw new Error(`Unexpected fetch: ${url}`);
      return response;
    },
  };
  vm.runInNewContext(script, context, { filename: "admin-common.js" });
  return { calls, context, documentRef, elements, location, localStorage, sessionStorage };
}

async function settle() {
  for (let index = 0; index < 10; index += 1) await Promise.resolve();
}

test("shared API uses cookies, limits CSRF to human writes, and redirects 401s locally", async () => {
  const harness = createHarness({ responses: [jsonResponse(200, { ok: true }), jsonResponse(401, { detail: "expired" })] });
  const common = harness.context.__AdminCommon;
  await common.api("/api/records", { method: "POST", body: "{}" });

  assert.equal(harness.calls[0].options.credentials, "include");
  assert.equal(harness.calls[0].options.headers.get("X-CSRF-Token"), "csrf-secret");
  assert.equal(common.buildHeaders({}, "POST").get("X-CSRF-Token"), "csrf-secret");
  await assert.rejects(common.api("/api/records"), /401 expired/);
  assert.equal(harness.calls[1].options.credentials, "include");
  assert.equal(harness.calls[1].options.headers.has("X-CSRF-Token"), false);
  assert.equal(harness.location.replacedWith, "admin-login.html?returnTo=admin-users.html%3Frole%3Doperator%23ledger");
});

test("shared API reuses the current-tab service token without copying it to local storage", async () => {
  const harness = createHarness({
    session: {
      smartBambooServiceToken: "deployment-token",
      smartBambooAuthProfile: JSON.stringify({
        authenticated: true,
        authType: "service-token",
        user: "deployment",
      }),
    },
    responses: [jsonResponse(200, { ok: true })],
  });

  await harness.context.__AdminCommon.api("/api/forest-blocks");

  assert.equal(
    harness.calls[0].options.headers.get("Authorization"),
    "Bearer deployment-token",
  );
  assert.equal(harness.localStorage.has("smartBambooServiceToken"), false);
});

test("session refresh renders effective permissions and blocks then releases forced password change", async () => {
  const harness = createHarness({
    responses: [
      jsonResponse(200, { authenticated: true, authType: "session", user: "operator", roles: ["operator"], permissions: ["system.users.view"], menuModules: [], visibleMenuModules: [], mustChangePassword: true }),
      jsonResponse(200, { ok: true }),
      jsonResponse(200, { authenticated: true, authType: "session", user: "operator", roles: ["operator"], permissions: ["system.users.view"], menuModules: [], visibleMenuModules: [], mustChangePassword: false }),
    ],
  });
  const common = harness.context.__AdminCommon;
  await common.refreshSession();
  assert.equal(harness.calls[0].url, "https://zhushan.example/api/auth/me");
  assert.equal(harness.documentRef.body.classList.contains("password-change-required"), true);

  const form = harness.elements.get("#forcedPasswordChangeForm");
  harness.elements.get("#currentPassword").value = "old-password";
  harness.elements.get("#newPassword").value = "New-password-1";
  harness.elements.get("#confirmPassword").value = "New-password-1";
  await form.listeners.get("submit")({ preventDefault() {} });
  await settle();

  assert.equal(harness.calls[1].url, "https://zhushan.example/api/auth/change-password");
  assert.equal(harness.calls[1].options.headers.get("X-CSRF-Token"), "csrf-secret");
  assert.equal(harness.documentRef.body.classList.contains("password-change-required"), false);
  assert.equal(harness.elements.get("#currentPassword").value, "");
  assert.equal(harness.elements.get("#newPassword").value, "");
  assert.equal(harness.elements.get("#confirmPassword").value, "");
});

test("a new tab recovers a CSRF token from the shared browser cookie before enabling writes", async () => {
  const profile = {
    authenticated: true,
    authType: "session",
    user: "operator",
    roles: ["operator"],
    permissions: ["system.users.view"],
    menuModules: [],
    visibleMenuModules: [],
    mustChangePassword: false,
  };
  const harness = createHarness({
    session: { smartBambooCsrfToken: "" },
    cookie: "smart_bamboo_session_csrf=recovered-csrf",
    responses: [
      jsonResponse(200, profile),
      jsonResponse(200, { ...profile, csrfToken: "recovered-csrf" }),
      jsonResponse(200, { ok: true }),
    ],
  });

  await harness.context.__AdminCommon.refreshSession();
  const completed = await harness.context.__AdminCommon.logout();

  assert.equal(completed, true);
  assert.deepEqual(
    harness.calls.map((call) => call.url),
    [
      "https://zhushan.example/api/auth/me",
      "https://zhushan.example/api/auth/session",
      "https://zhushan.example/api/auth/logout",
    ],
  );
  assert.equal(
    harness.calls[2].options.headers.get("X-CSRF-Token"),
    "recovered-csrf",
  );
});

test("session refresh replaces a stale tab CSRF token after another tab logs in", async () => {
  const profile = {
    authenticated: true,
    authType: "session",
    user: "operator",
    roles: ["operator"],
    permissions: ["system.users.view"],
    menuModules: [],
    visibleMenuModules: [],
    mustChangePassword: false,
  };
  const harness = createHarness({
    session: { smartBambooCsrfToken: "stale-csrf" },
    cookie: "smart_bamboo_session_csrf=current-csrf",
    responses: [
      jsonResponse(200, profile),
      jsonResponse(200, { ...profile, csrfToken: "current-csrf" }),
    ],
  });

  await harness.context.__AdminCommon.refreshSession();

  assert.equal(
    harness.sessionStorage.getItem("smartBambooCsrfToken"),
    "current-csrf",
  );
  assert.deepEqual(
    harness.calls.map((call) => call.url),
    [
      "https://zhushan.example/api/auth/me",
      "https://zhushan.example/api/auth/session",
    ],
  );
});

test("service-token startup does not require a human session CSRF endpoint", async () => {
  const profile = {
    authenticated: true,
    authType: "service-token",
    user: "automation",
    roles: ["admin"],
    permissions: ["system.users.view"],
    menuModules: [],
    visibleMenuModules: [],
    mustChangePassword: false,
  };
  const harness = createHarness({
    session: { smartBambooCsrfToken: "" },
    responses: [jsonResponse(200, profile)],
  });

  await harness.context.__AdminCommon.refreshSession();

  assert.deepEqual(
    harness.calls.map((call) => call.url),
    ["https://zhushan.example/api/auth/me"],
  );
  assert.equal(harness.location.replacedWith, undefined);
});

test("a stale CSRF write recovers the current token and retries once", async () => {
  const profile = {
    authenticated: true,
    authType: "session",
    user: "operator",
    roles: ["operator"],
    permissions: ["system.users.update"],
    menuModules: [],
    visibleMenuModules: [],
    mustChangePassword: false,
  };
  const harness = createHarness({
    session: { smartBambooCsrfToken: "stale-csrf" },
    cookie: "smart_bamboo_session_csrf=current-csrf",
    responses: [
      jsonResponse(200, profile),
      jsonResponse(200, { ...profile, csrfToken: "current-csrf" }),
      jsonResponse(403, { detail: "CSRF validation failed" }),
      jsonResponse(200, { ...profile, csrfToken: "new-csrf" }),
      jsonResponse(200, { ok: true }),
    ],
  });
  const common = harness.context.__AdminCommon;
  await common.refreshSession();

  const result = await common.api("/api/admin/users/user-1", {
    method: "PATCH",
    body: JSON.stringify({ displayName: "Updated" }),
  });

  assert.equal(result.ok, true);
  assert.deepEqual(
    harness.calls.map((call) => call.url),
    [
      "https://zhushan.example/api/auth/me",
      "https://zhushan.example/api/auth/session",
      "https://zhushan.example/api/admin/users/user-1",
      "https://zhushan.example/api/auth/session",
      "https://zhushan.example/api/admin/users/user-1",
    ],
  );
  assert.equal(
    harness.calls[4].options.headers.get("X-CSRF-Token"),
    "new-csrf",
  );
});

test("page permission denial does not disable the forced password change dialog", async () => {
  const harness = createHarness({
    href: "https://zhushan.example/admin.html",
    responses: [
      jsonResponse(200, {
        authenticated: true,
        authType: "session",
        user: "viewer",
        roles: ["viewer"],
        permissions: ["forest.blocks.view"],
        menuModules: [],
        visibleMenuModules: [],
        mustChangePassword: true,
      }),
    ],
  });
  harness.documentRef.body.dataset = { adminModule: "overview", permission: "admin.overview.view" };

  await harness.context.__AdminCommon.refreshSession();

  assert.equal(harness.documentRef.body.classList.contains("permission-page-denied"), true);
  assert.equal(harness.documentRef.body.classList.contains("password-change-required"), true);
  assert.equal(harness.documentRef.body.classList.contains("permission-disabled"), false);
  assert.equal(harness.documentRef.body.getAttribute("aria-disabled"), null);
  const dialog = harness.documentRef.body.children.find((element) => element.id === "forcedPasswordChangeDialog");
  assert.equal(dialog.getAttribute("aria-hidden"), "false");
  assert.equal(harness.elements.get("#currentPassword").disabled, undefined);
});

test("startup and successful logout remove legacy token keys after the server confirms logout", async () => {
  const harness = createHarness({
    responses: [jsonResponse(200, { ok: true })],
    session: { smartBambooAdminToken: "legacy-human" },
    local: { smartBambooAdminTokenPersistent: "legacy-service" },
  });
  await harness.context.__AdminCommon.logout();

  assert.equal(harness.calls[0].url, "https://zhushan.example/api/auth/logout");
  assert.equal(harness.calls[0].options.method, "POST");
  assert.equal(harness.calls[0].options.headers.get("X-CSRF-Token"), "csrf-secret");
  assert.equal(harness.sessionStorage.has("smartBambooCsrfToken"), false);
  assert.equal(harness.sessionStorage.has("smartBambooAuthProfile"), false);
  assert.equal(harness.sessionStorage.has("smartBambooAdminToken"), false);
  assert.equal(harness.localStorage.has("smartBambooAdminTokenPersistent"), false);
  assert.equal(harness.location.replacedWith, "admin-login.html?returnTo=admin-users.html%3Frole%3Doperator%23ledger");
});

test("startup clears migrated token keys before the session profile is loaded", async () => {
  const harness = createHarness({
    responses: [jsonResponse(200, { authenticated: false, authType: "development-header", permissions: [], menuModules: [], visibleMenuModules: [], mustChangePassword: false })],
    session: { smartBambooAdminToken: "legacy-human" },
    local: { smartBambooAdminTokenPersistent: "legacy-service" },
  });
  harness.context.__AdminCommon.initShell();

  assert.equal(harness.sessionStorage.has("smartBambooAdminToken"), false);
  assert.equal(harness.localStorage.has("smartBambooAdminTokenPersistent"), false);
});

test("remote admin startup discards a stale loopback API base", async () => {
  const harness = createHarness({
    href: "http://36.140.138.117:18080/admin-blocks.html",
    local: { smartBambooApiBase: "http://127.0.0.1:8010" },
    responses: [jsonResponse(401, { detail: "Authentication required" })],
  });

  harness.context.__AdminCommon.initShell();
  await settle();

  assert.equal(harness.elements.get("#apiBase").value, "http://36.140.138.117:18080");
  assert.equal(harness.localStorage.has("smartBambooApiBase"), false);
  assert.equal(harness.calls[0].url, "http://36.140.138.117:18080/api/auth/me");
});

test("failed session startup releases queued business requests instead of hanging", async () => {
  const harness = createHarness({
    responses: [
      jsonResponse(401, { detail: "Authentication required" }),
      jsonResponse(401, { detail: "Authentication required" }),
    ],
  });
  const common = harness.context.__AdminCommon;

  common.initShell();
  await settle();

  await assert.rejects(common.api("/api/forest-blocks"), /401 Authentication required/);
  assert.equal(harness.calls.length, 2);
  assert.equal(harness.location.replacedWith, "admin-login.html?returnTo=admin-users.html%3Frole%3Doperator%23ledger");
});

test("failed logout keeps the browser session and lets the user retry", async () => {
  const harness = createHarness({ responses: [jsonResponse(500, { detail: "server unavailable" })] });
  const completed = await harness.context.__AdminCommon.logout();

  assert.equal(completed, false);
  assert.equal(harness.sessionStorage.has("smartBambooCsrfToken"), true);
  assert.equal(harness.sessionStorage.has("smartBambooAuthProfile"), true);
  assert.equal(harness.location.replacedWith, undefined);
  assert.match(harness.elements.get("#statusText").textContent, /退出登录失败/);
});

test("raw admin downloads and uploads use the same session-aware fetch gate", async () => {
  const harness = createHarness({ responses: [jsonResponse(200, { ok: true })] });
  const response = await harness.context.__AdminCommon.fetchWithSession("/api/report.json", { method: "POST" });

  assert.equal(response.ok, true);
  assert.equal(harness.calls[0].options.credentials, "include");
  assert.equal(harness.calls[0].options.headers.get("X-CSRF-Token"), "csrf-secret");
});

test("dashboard health waits for a forced password change before its business fetch starts", async () => {
  const harness = createHarness({
    script: `${source}\n${dashboardSource}`,
    responses: [
      jsonResponse(200, { authenticated: true, authType: "session", user: "operator", roles: ["operator"], permissions: ["system.users.view"], menuModules: [], visibleMenuModules: [], mustChangePassword: true }),
      jsonResponse(200, { ok: true }),
      jsonResponse(200, { authenticated: true, authType: "session", user: "operator", roles: ["operator"], permissions: ["system.users.view"], menuModules: [], visibleMenuModules: [], mustChangePassword: false }),
      jsonResponse(200, { ok: true }),
    ],
  });
  const common = harness.context.__AdminCommon;
  common.initShell();
  await settle();
  const healthPromise = harness.context.__AdminDashboard.fetchDeploymentHealth();
  await settle();
  assert.equal(harness.calls.length, 1);

  harness.elements.get("#currentPassword").value = "old-password";
  harness.elements.get("#newPassword").value = "New-password-1";
  harness.elements.get("#confirmPassword").value = "New-password-1";
  await harness.elements.get("#forcedPasswordChangeForm").listeners.get("submit")({ preventDefault() {} });
  const health = await healthPromise;

  assert.deepEqual(harness.calls.map((call) => call.url), [
    "https://zhushan.example/api/auth/me",
    "https://zhushan.example/api/auth/change-password",
    "https://zhushan.example/api/auth/me",
    "https://zhushan.example/api/health",
  ]);
  assert.equal(health.ok, true);
  assert.equal(health.httpStatus, 200);
});

test("a runtime password-change 403 atomically reopens the gate for later business requests", async () => {
  const normalProfile = { authenticated: true, authType: "session", user: "operator", roles: ["operator"], permissions: ["system.users.view"], menuModules: [], visibleMenuModules: [], mustChangePassword: false };
  const harness = createHarness({
    responses: [
      jsonResponse(200, normalProfile),
      jsonResponse(403, { detail: "Password change required" }),
      jsonResponse(200, { ok: true }),
      jsonResponse(200, normalProfile),
      jsonResponse(200, { ok: true }),
    ],
  });
  const common = harness.context.__AdminCommon;
  common.initShell();
  await settle();

  await assert.rejects(common.api("/api/business/first"), /403 Password change required/);
  const laterRequest = common.fetchWithSession("/api/business/second");
  await settle();
  assert.equal(harness.calls.length, 2);

  harness.elements.get("#currentPassword").value = "old-password";
  harness.elements.get("#newPassword").value = "New-password-1";
  harness.elements.get("#confirmPassword").value = "New-password-1";
  await harness.elements.get("#forcedPasswordChangeForm").listeners.get("submit")({ preventDefault() {} });

  const laterResponse = await laterRequest;
  assert.equal(laterResponse.ok, true);
  assert.deepEqual(harness.calls.map((call) => call.url), [
    "https://zhushan.example/api/auth/me",
    "https://zhushan.example/api/business/first",
    "https://zhushan.example/api/auth/change-password",
    "https://zhushan.example/api/auth/me",
    "https://zhushan.example/api/business/second",
  ]);
});

test("a stale forced 403 arriving after password change cannot reopen the released gate", async () => {
  const normalProfile = { authenticated: true, authType: "session", user: "operator", roles: ["operator"], permissions: ["system.users.view"], menuModules: [], visibleMenuModules: [], mustChangePassword: false };
  const lateBusinessResponse = deferred();
  const harness = createHarness({
    responses: [
      jsonResponse(200, normalProfile),
      jsonResponse(403, { detail: "Password change required" }),
      lateBusinessResponse.promise,
      jsonResponse(200, { ok: true }),
      jsonResponse(200, normalProfile),
      jsonResponse(200, { ok: true, record: "C" }),
    ],
  });
  const common = harness.context.__AdminCommon;
  common.initShell();
  await settle();

  const requestA = common.api("/api/business/A");
  const requestB = common.fetchWithSession("/api/business/B");
  await assert.rejects(requestA, /403 Password change required/);

  harness.elements.get("#currentPassword").value = "old-password";
  harness.elements.get("#newPassword").value = "New-password-1";
  harness.elements.get("#confirmPassword").value = "New-password-1";
  await harness.elements.get("#forcedPasswordChangeForm").listeners.get("submit")({ preventDefault() {} });
  assert.equal(harness.documentRef.body.classList.contains("password-change-required"), false);

  lateBusinessResponse.resolve(jsonResponse(403, { detail: "Password change required" }));
  const staleResponse = await requestB;
  assert.equal(staleResponse.status, 403);
  assert.equal(harness.documentRef.body.classList.contains("password-change-required"), false);

  const requestC = common.api("/api/business/C");
  await settle();
  assert.equal(harness.calls.length, 6);
  assert.deepEqual(await requestC, { ok: true, record: "C" });
});
