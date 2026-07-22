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
  const location = {
    href,
    origin: new URL(href).origin,
    replace(value) {
      this.replacedWith = value;
    },
  };
  const queue = [...responses];
  const context = {
    URL,
    URLSearchParams,
    document: {
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
    window: { location },
  };
  vm.runInNewContext(source, context, { filename: "admin-login.js" });
  return { calls, elements, location, storage };
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

test("only displays the non-persistent service-token fallback when human login is disabled", async () => {
  const harness = createHarness({ responses: [response(200, { humanLoginEnabled: false, httpsRequired: false })] });
  await settle();
  const { elements, storage } = harness;

  assert.equal(elements.get("#loginForm").hidden, true);
  assert.equal(elements.get("#serviceTokenFallback").hidden, false);
  assert.equal(elements.get("#serviceTokenFallback").children.length, 1);
  assert.equal(storage.size, 0);
});
