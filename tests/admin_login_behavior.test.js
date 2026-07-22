const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(process.cwd(), "admin-login.js"), "utf8");

class Element {
  constructor(id = "") {
    this.id = id;
    this.attributes = {};
    this.children = [];
    this.dataset = {};
    this.disabled = false;
    this.hidden = false;
    this.listeners = new Map();
    this.textContent = "";
    this.type = "";
    this.value = "";
  }

  addEventListener(event, listener) {
    this.listeners.set(event, listener);
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  async submit() {
    await this.listeners.get("submit")({ preventDefault() {} });
  }
}

function response(status, payload = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

function deferred() {
  let resolve;
  return { promise: new Promise((done) => { resolve = done; }), resolve };
}

function createHarness({ responses, href = "https://zhushan.example/admin-login.html" }) {
  const elements = new Map();
  for (const id of ["username", "password", "togglePassword", "loginButton", "loginForm", "loginStatus", "serviceTokenFallback"]) {
    elements.set(`#${id}`, new Element(id));
  }
  const calls = [];
  const storage = new Map();
  const localStorage = new Map();
  const cookieWrites = [];
  const location = {
    href,
    origin: new URL(href).origin,
    search: new URL(href).search,
    replace(value) {
      this.replacedWith = value;
    },
  };
  const queue = [...responses];
  const context = {
    URL,
    URLSearchParams,
    document: {
      get cookie() {
        return cookieWrites.join("; ");
      },
      set cookie(value) {
        cookieWrites.push(value);
      },
      querySelector(selector) {
        return elements.get(selector) || null;
      },
      createElement() {
        return new Element();
      },
    },
    fetch(url, options = {}) {
      calls.push({ url, options });
      const next = queue.shift();
      if (!next) throw new Error(`Unexpected fetch: ${url}`);
      return next;
    },
    sessionStorage: {
      setItem(key, value) {
        storage.set(key, value);
      },
    },
    localStorage: {
      setItem(key, value) {
        localStorage.set(key, value);
      },
    },
    window: { location },
  };
  vm.runInNewContext(source, context, { filename: "admin-login.js" });
  return { calls, cookieWrites, elements, localStorage, location, storage };
}

async function settle() {
  for (let index = 0; index < 8; index += 1) await Promise.resolve();
}

test("keeps the human form fail-closed while auth config is pending", async () => {
  const config = deferred();
  const harness = createHarness({ responses: [config.promise] });
  const { elements, calls } = harness;

  assert.equal(elements.get("#username").disabled, true);
  assert.equal(elements.get("#password").disabled, true);
  assert.equal(elements.get("#loginButton").disabled, true);
  elements.get("#username").value = "operator";
  elements.get("#password").value = "secret";
  await elements.get("#loginForm").submit();

  assert.equal(calls.filter((call) => call.url === "/api/auth/login").length, 0);
  assert.equal(elements.get("#password").value, "");
  config.resolve(response(200, { humanLoginEnabled: true, httpsRequired: false }));
});

test("keeps controls disabled and clears the password after HTTPS login rejection", async () => {
  const harness = createHarness({
    responses: [
      response(200, { humanLoginEnabled: true, httpsRequired: false }),
      response(401),
      response(426, { detail: "HTTPS is required for password login" }),
    ],
  });
  await settle();
  const { elements } = harness;
  elements.get("#username").value = "operator";
  elements.get("#password").value = "secret";
  await elements.get("#loginForm").submit();

  assert.equal(elements.get("#loginButton").disabled, true);
  assert.equal(elements.get("#password").value, "");
  assert.match(elements.get("#loginStatus").textContent, /HTTPS/);
});

test("shows a Chinese first-password-change status when config is blocked by an existing session", async () => {
  const harness = createHarness({ responses: [response(403, { detail: "Password change required" })] });
  await settle();

  assert.match(harness.elements.get("#loginStatus").textContent, /首次.*改密/);
  assert.doesNotMatch(harness.elements.get("#loginStatus").textContent, /Password change required/);
  assert.equal(harness.elements.get("#loginButton").disabled, true);
  assert.equal(harness.calls.filter((call) => call.url === "/api/auth/login").length, 0);
});

test("keeps the form closed and shows a Chinese HTTPS status when config returns 426", async () => {
  const harness = createHarness({ responses: [response(426, { detail: "HTTPS is required" })] });
  await settle();
  const { elements, calls } = harness;
  elements.get("#username").value = "operator";
  elements.get("#password").value = "secret";
  await elements.get("#loginForm").submit();

  assert.equal(elements.get("#loginButton").disabled, true);
  assert.equal(elements.get("#password").value, "");
  assert.match(elements.get("#loginStatus").textContent, /请先通过 HTTPS/);
  assert.equal(calls.filter((call) => call.url === "/api/auth/login").length, 0);
});

test("stores only CSRF and a non-secret profile after successful login", async () => {
  const harness = createHarness({
    href: "https://zhushan.example/admin-login.html?returnTo=https%3A%2F%2Fevil.example%2Fadmin.html",
    responses: [
      response(200, { humanLoginEnabled: true, httpsRequired: false }),
      response(401),
      response(200, { csrfToken: "csrf-secret", user: "operator", mustChangePassword: false }),
      response(200, { authenticated: true, user: "operator", roles: ["admin"], csrfToken: "must-not-persist" }),
    ],
  });
  await settle();
  const { elements, location, storage } = harness;
  elements.get("#username").value = "operator";
  elements.get("#password").value = "secret";
  await elements.get("#loginForm").submit();

  assert.deepEqual([...storage.keys()].sort(), ["smartBambooAuthProfile", "smartBambooCsrfToken"]);
  assert.equal(storage.get("smartBambooCsrfToken"), "csrf-secret");
  assert.deepEqual(JSON.parse(storage.get("smartBambooAuthProfile")), {
    authenticated: true,
    user: "operator",
    roles: ["admin"],
    mustChangePassword: false,
  });
  assert.equal(location.replacedWith, "admin.html");
});

test("hands a successful forced-password-change session to the safe shell while keeping the form locked", async () => {
  const harness = createHarness({
    href: "https://zhushan.example/admin-login.html?returnTo=admin-users.html",
    responses: [
      response(200, { humanLoginEnabled: true, httpsRequired: false }),
      response(401),
      response(200, { csrfToken: "csrf-secret", user: "operator", mustChangePassword: true }),
      response(200, { authenticated: true, user: "operator", roles: ["admin"], mustChangePassword: true }),
    ],
  });
  await settle();
  const { elements, location, storage } = harness;
  elements.get("#username").value = "operator";
  elements.get("#password").value = "secret";
  await elements.get("#loginForm").submit();

  assert.equal(storage.get("smartBambooCsrfToken"), "csrf-secret");
  assert.equal(JSON.parse(storage.get("smartBambooAuthProfile")).mustChangePassword, true);
  assert.equal(elements.get("#password").value, "");
  assert.equal(elements.get("#loginButton").disabled, true);
  assert.equal(location.replacedWith, "admin-users.html");
});

test("routes a login Password change required response to the shell without retrying login", async () => {
  const harness = createHarness({
    responses: [
      response(200, { humanLoginEnabled: true, httpsRequired: false }),
      response(401),
      response(403, { detail: "Password change required" }),
    ],
  });
  await settle();
  const { calls, elements, location } = harness;
  elements.get("#username").value = "operator";
  elements.get("#password").value = "secret";
  await elements.get("#loginForm").submit();
  await elements.get("#loginForm").submit();

  assert.match(elements.get("#loginStatus").textContent, /首次.*改密/);
  assert.doesNotMatch(elements.get("#loginStatus").textContent, /Password change required/);
  assert.equal(elements.get("#password").value, "");
  assert.equal(elements.get("#loginButton").disabled, true);
  assert.equal(calls.filter((call) => call.url === "/api/auth/login").length, 1);
  assert.equal(location.replacedWith, "admin.html");
});

test("keeps the service-token fallback absent when human login is enabled", async () => {
  const harness = createHarness({
    responses: [response(200, { humanLoginEnabled: true, httpsRequired: false }), response(401)],
  });
  await settle();

  assert.equal(harness.elements.get("#loginForm").hidden, false);
  assert.equal(harness.elements.get("#serviceTokenFallback").hidden, true);
  assert.equal(harness.elements.get("#serviceTokenFallback").children.length, 0);
});

test("only displays the non-persistent service-token fallback when human login is disabled", async () => {
  const harness = createHarness({ responses: [response(200, { humanLoginEnabled: false, httpsRequired: false })] });
  await settle();
  const { elements, storage } = harness;

  assert.equal(elements.get("#loginForm").hidden, true);
  assert.equal(elements.get("#serviceTokenFallback").hidden, false);
  assert.equal(elements.get("#serviceTokenFallback").children.length, 1);
  assert.equal(storage.size, 0);
});

test("uses a fallback bearer only for its diagnostic request without persisting or navigating it", async () => {
  const harness = createHarness({
    responses: [
      response(200, { humanLoginEnabled: false, httpsRequired: false }),
      response(200, { authenticated: true, user: "deployment" }),
    ],
  });
  await settle();
  const { calls, cookieWrites, elements, localStorage, location, storage } = harness;
  const fallbackForm = elements.get("#serviceTokenFallback").children[0];
  const token = fallbackForm.children[0].children[1];
  token.value = "deployment-token";
  await fallbackForm.submit();

  assert.equal(calls.length, 2);
  assert.equal(calls[0].options.headers, undefined);
  assert.deepEqual(Object.keys(calls[1].options.headers), ["Authorization"]);
  assert.equal(calls[1].options.headers.Authorization, "Bearer deployment-token");
  assert.equal(token.value, "");
  assert.equal(localStorage.size, 0);
  assert.equal(cookieWrites.length, 0);
  assert.equal([...storage.values()].some((value) => String(value).includes("deployment-token")), false);
  assert.equal(location.replacedWith, undefined);
  assert.doesNotMatch(location.href, /deployment-token/);
});
