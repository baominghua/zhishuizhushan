const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const rawSource = fs.readFileSync(path.join(process.cwd(), "admin-users.js"), "utf8");
const source = rawSource.replace(
  /\n  initialize\(\);\n\}\)\(\);\s*$/,
  "\n  globalThis.__AdminUsersSecurity = { openTemporaryPasswordDialog, revokeUserSessions, submitTemporaryPassword, payloadFromForm };\n})();",
);

class Element {
  constructor(id = "") { this.id = id; this.value = ""; this.listeners = new Map(); this.dataset = {}; this.hidden = false; this.classList = { add() {}, remove() {} }; }
  addEventListener(event, listener) { this.listeners.set(event, listener); }
  setAttribute() {}
  focus() {}
}

function createHarness() {
  const elements = new Map();
  for (const id of ["temporaryPasswordDialog", "temporaryPasswordForm", "temporaryPassword", "temporaryPasswordStatus", "temporaryPasswordTitle"]) elements.set(`#${id}`, new Element(id));
  const calls = [];
  const context = {
    document: { querySelector: (selector) => elements.get(selector) || null },
    window: { location: { search: "" }, setTimeout },
    URLSearchParams,
    AdminCommon: {
      $: (selector) => elements.get(selector) || null,
      api: async (url, options) => { calls.push({ url, options }); return { ok: true, revoked: 3 }; },
      apiBase: () => "",
      applyActionPermissions() {},
      createLedgerPager() { return {}; },
      escapeHtml: (value) => String(value),
      formatDateTime: (value) => String(value || ""),
      initShell() {},
      parseJson: () => ({}),
      query: () => "",
      refreshRoleMenu: async () => {},
      rowActionButtons: () => "",
      setStatus() {},
      splitValues: () => [],
      stringifyPretty: () => "{}",
    },
  };
  vm.runInNewContext(source, context, { filename: "admin-users.js" });
  return { calls, context, elements };
}

test("temporary-password action uses its own payload, clears the field, and revokes sessions separately", async () => {
  const harness = createHarness();
  const security = harness.context.__AdminUsersSecurity;
  security.openTemporaryPasswordDialog({ id: "u-1", username: "operator" });
  harness.elements.get("#temporaryPassword").value = "Temporary-1";
  await security.submitTemporaryPassword({ preventDefault() {} });

  assert.deepEqual(JSON.parse(harness.calls[0].options.body), { temporaryPassword: "Temporary-1" });
  assert.equal(harness.calls[0].url, "/api/admin/users/u-1/set-password");
  assert.equal(harness.elements.get("#temporaryPassword").value, "");
  await security.revokeUserSessions({ id: "u-1", username: "operator" });
  assert.equal(harness.calls[1].url, "/api/admin/users/u-1/revoke-sessions");
  assert.equal(harness.calls[1].options.method, "POST");
});
