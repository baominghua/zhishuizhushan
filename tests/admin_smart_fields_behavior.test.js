const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = `${fs.readFileSync(path.join(process.cwd(), "admin-smart-fields.js"), "utf8")}
globalThis.__AdminSmartFields = AdminSmartFields;`;

class ClassList {
  constructor() { this.values = new Set(); }
  add(...values) { values.forEach((value) => this.values.add(value)); }
  remove(...values) { values.forEach((value) => this.values.delete(value)); }
  contains(value) { return this.values.has(value); }
  toggle(value, force) {
    const enabled = force === undefined ? !this.values.has(value) : Boolean(force);
    if (enabled) this.add(value); else this.remove(value);
    return enabled;
  }
}

class Element {
  constructor(tagName = "div", documentRef = null) {
    this.tagName = tagName.toUpperCase();
    this.documentRef = documentRef;
    this.children = [];
    this.listeners = new Map();
    this.attributes = {};
    this.classList = new ClassList();
    this.dataset = {};
    this.disabled = false;
    this.hidden = false;
    this.parentElement = null;
    this.textContent = "";
    this.value = "";
    this.type = "";
  }
  append(...children) {
    children.forEach((child) => {
      child.parentElement = this;
      this.children.push(child);
    });
  }
  appendChild(child) { this.append(child); return child; }
  replaceChildren(...children) {
    this.children = [];
    this.append(...children);
  }
  insertAdjacentElement(_position, child) {
    if (!this.parentElement) return null;
    const index = this.parentElement.children.indexOf(this);
    child.parentElement = this.parentElement;
    this.parentElement.children.splice(index + 1, 0, child);
    return child;
  }
  addEventListener(event, listener) {
    const listeners = this.listeners.get(event) || [];
    listeners.push(listener);
    this.listeners.set(event, listeners);
  }
  async dispatch(event, detail = {}) {
    for (const listener of this.listeners.get(event) || []) {
      await listener({ target: this, preventDefault() {}, stopPropagation() {}, ...detail });
    }
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || null; }
  remove() {
    if (!this.parentElement) return;
    this.parentElement.children = this.parentElement.children.filter((child) => child !== this);
  }
  focus() { this.focused = true; }
}

function createHarness() {
  const documentRef = {
    createElement(tagName) { return new Element(tagName, documentRef); },
  };
  const context = {
    AbortController,
    URLSearchParams,
    document: documentRef,
    window: {
      clearTimeout,
      setTimeout(callback) { callback(); return 1; },
    },
  };
  vm.runInNewContext(source, context, { filename: "admin-smart-fields.js" });
  return { documentRef, smart: context.__AdminSmartFields };
}

function select(documentRef, value = "") {
  const element = documentRef.createElement("select");
  element.value = value;
  return element;
}

test("dictionary select loads stable codes and preserves an unknown historic value", async () => {
  const { documentRef, smart } = createHarness();
  const element = select(documentRef, "legacy-grade");
  const controller = smart.bindDictionarySelect({
    element,
    typeCode: "quality-grades",
    api: async () => ({
      items: [
        { value: "excellent", label: "优质" },
        { value: "standard", label: "标准" },
      ],
    }),
  });

  await controller.ready;

  assert.deepEqual(
    Array.from(element.children, (option) => [option.value, option.textContent]),
    [["", "请选择"], ["excellent", "优质"], ["standard", "标准"], ["legacy-grade", "历史值：legacy-grade"]],
  );
  assert.equal(element.value, "legacy-grade");
});

test("administrative division cascade derives labels and reloads child options", async () => {
  const { documentRef, smart } = createHarness();
  const county = select(documentRef);
  const town = select(documentRef);
  const village = select(documentRef);
  const countyName = documentRef.createElement("input");
  const townName = documentRef.createElement("input");
  const villageName = documentRef.createElement("input");
  const calls = [];
  const api = async (url) => {
    calls.push(url);
    if (url.includes("level=county")) return { items: [{ value: "350703", label: "建阳区" }] };
    if (url.includes("parentCode=350703101")) return { items: [{ value: "350703101201", label: "黄坑村" }] };
    if (url.includes("parentCode=350703")) return { items: [{ value: "350703101", label: "麻沙镇" }] };
    return { items: [] };
  };

  const controller = smart.bindAdministrativeDivision({
    api,
    county: { code: county, name: countyName },
    town: { code: town, name: townName },
    village: { code: village, name: villageName },
  });
  await controller.ready;

  county.value = "350703";
  await county.dispatch("change");
  town.value = "350703101";
  await town.dispatch("change");
  village.value = "350703101201";
  await village.dispatch("change");

  assert.equal(countyName.value, "建阳区");
  assert.equal(townName.value, "麻沙镇");
  assert.equal(villageName.value, "黄坑村");
  assert.equal(calls.some((url) => url.includes("parentCode=350703")), true);
  assert.equal(calls.some((url) => url.includes("parentCode=350703101")), true);
});

test("administrative division keeps imported labels for codes not yet in the dictionary", async () => {
  const { documentRef, smart } = createHarness();
  const county = select(documentRef);
  const town = select(documentRef);
  const village = select(documentRef);
  const countyName = documentRef.createElement("input");
  const townName = documentRef.createElement("input");
  const villageName = documentRef.createElement("input");
  const controller = smart.bindAdministrativeDivision({
    api: async () => ({ items: [] }),
    county: { code: county, name: countyName },
    town: { code: town, name: townName },
    village: { code: village, name: villageName },
  });
  await controller.ready;
  await controller.setValue({
    countyCode: "350799",
    countyName: "历史区县",
    townCode: "350799100",
    townName: "历史乡镇",
    villageCode: "350799100001",
    villageName: "历史村",
  });

  assert.equal(controller.getValue().countyName, "历史区县");
  assert.equal(controller.getValue().townName, "历史乡镇");
  assert.equal(controller.getValue().villageName, "历史村");
});

test("reference picker searches remotely and serializes selected stable codes", async () => {
  const { documentRef, smart } = createHarness();
  const wrapper = documentRef.createElement("label");
  const input = documentRef.createElement("input");
  wrapper.append(input);
  const controller = smart.bindReferencePicker({
    input,
    endpoint: "/api/forest-blocks",
    valueKey: "blockCode",
    labelKey: "name",
    api: async (url) => {
      assert.match(url, /q=%E9%BA%BB%E6%B2%99/);
      return { items: [{ blockCode: "350703101-001", name: "麻沙一号林班" }] };
    },
  });

  const results = await controller.search("麻沙");
  controller.add(results[0]);
  assert.equal(input.value, "350703101-001");
  assert.deepEqual(Array.from(controller.getValues()), ["350703101-001"]);

  controller.remove("350703101-001");
  assert.equal(input.value, "");
  assert.deepEqual(Array.from(controller.getValues()), []);
});

test("reference picker appends search parameters to endpoints that already have filters", async () => {
  const { documentRef, smart } = createHarness();
  const wrapper = documentRef.createElement("label");
  const input = documentRef.createElement("input");
  wrapper.append(input);
  let requestedUrl = "";
  const controller = smart.bindReferencePicker({
    input,
    endpoint: "/api/dictionary-options/administrative-divisions?level=town",
    valueKey: "label",
    labelKey: "fullName",
    multiple: false,
    api: async (url) => {
      requestedUrl = url;
      return { items: [] };
    },
  });

  await controller.search("麻沙");

  assert.match(requestedUrl, /\?level=town&q=/);
  assert.equal((requestedUrl.match(/\?/g) || []).length, 1);
  assert.match(requestedUrl, /&limit=20&offset=0$/);
});

test("reference picker retains historic codes that are absent from the current search result", () => {
  const { documentRef, smart } = createHarness();
  const wrapper = documentRef.createElement("label");
  const input = documentRef.createElement("input");
  input.value = "ARCHIVE-OLD-01, ARCHIVE-OLD-02";
  wrapper.append(input);

  const controller = smart.bindReferencePicker({
    input,
    endpoint: "/api/forest-rights",
    valueKey: "archiveCode",
    labelKey: "name",
    api: async () => ({ items: [] }),
  });

  assert.deepEqual(Array.from(controller.getValues()), ["ARCHIVE-OLD-01", "ARCHIVE-OLD-02"]);
  assert.equal(input.value, "ARCHIVE-OLD-01, ARCHIVE-OLD-02");
});
