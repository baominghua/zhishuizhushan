const AdminSmartFields = (() => {
  const DEFAULT_LIMIT = 20;

  function defaultApi(path) {
    if (!window.AdminCommon?.api) {
      return Promise.reject(new Error("后台 API 尚未初始化"));
    }
    return window.AdminCommon.api(path);
  }

  function option(value, label, { historic = false } = {}) {
    const element = document.createElement("option");
    element.value = String(value ?? "");
    element.textContent = String(label ?? value ?? "");
    if (historic) element.dataset.historic = "true";
    return element;
  }

  function selectedLabel(select) {
    const selected = Array.from(select.children || [])
      .find((candidate) => String(candidate.value) === String(select.value));
    return selected?.textContent || "";
  }

  function normalizeItems(payload) {
    return Array.isArray(payload?.items) ? payload.items : [];
  }

  function replaceOptions(select, items, {
    valueKey = "itemCode",
    labelKey = "itemLabel",
    blankLabel = "请选择",
    value = select.value,
  } = {}) {
    const normalizedValue = String(value || "");
    const options = [option("", blankLabel)];
    items.forEach((item) => {
      const itemValue = String(item?.[valueKey] ?? "");
      if (!itemValue) return;
      options.push(option(itemValue, item?.[labelKey] || itemValue));
    });
    if (normalizedValue && !items.some((item) => String(item?.[valueKey] ?? "") === normalizedValue)) {
      options.push(option(normalizedValue, `历史值：${normalizedValue}`, { historic: true }));
    }
    select.replaceChildren(...options);
    select.value = normalizedValue;
    select.disabled = false;
  }

  function errorOption(select, message, value = select.value) {
    const normalizedValue = String(value || "");
    const options = [option("", message)];
    if (normalizedValue) {
      options.push(option(normalizedValue, `历史值：${normalizedValue}`, { historic: true }));
    }
    select.replaceChildren(...options);
    select.value = normalizedValue;
    select.disabled = false;
  }

  function bindDictionarySelect({
    element,
    typeCode,
    api = defaultApi,
    blankLabel = "请选择",
    query = {},
  }) {
    if (!element || !typeCode) throw new Error("字典控件缺少目标元素或字典编码");
    const initialValue = element.value;
    element.disabled = true;
    element.replaceChildren(option("", "正在加载..."));
    const params = new URLSearchParams({ limit: "500", ...query });
    const ready = api(`/api/dictionary-options/${encodeURIComponent(typeCode)}?${params}`)
      .then((payload) => {
        replaceOptions(element, normalizeItems(payload), {
          valueKey: "value",
          labelKey: "label",
          blankLabel,
          value: initialValue,
        });
        return element;
      })
      .catch((error) => {
        errorOption(element, "字典加载失败", initialValue);
        element.dataset.loadError = error?.message || "字典加载失败";
        return element;
      });
    return {
      element,
      ready,
      setValue(value) {
        const normalizedValue = String(value || "");
        if (
          normalizedValue
          && !Array.from(element.children || []).some((candidate) => String(candidate.value) === normalizedValue)
        ) {
          element.append(option(normalizedValue, `历史值：${normalizedValue}`, { historic: true }));
        }
        element.value = normalizedValue;
      },
      getValue() { return element.value; },
    };
  }

  function divisionOptionsUrl({ level, parentCode = "" }) {
    const params = new URLSearchParams({ level, limit: "500" });
    if (parentCode) params.set("parentCode", parentCode);
    return `/api/dictionary-options/administrative-divisions?${params}`;
  }

  function bindAdministrativeDivision({
    county,
    town,
    village,
    api = defaultApi,
  }) {
    const levels = [
      { ...county, level: "county" },
      { ...town, level: "town" },
      { ...village, level: "village" },
    ];
    if (levels.some((entry) => !entry.code || !entry.name)) {
      throw new Error("行政区划控件需要县、乡镇、村的编码与名称字段");
    }

    async function loadLevel(index, parentCode = "", selectedValue = "") {
      const entry = levels[index];
      entry.code.disabled = true;
      entry.code.replaceChildren(option("", "正在加载..."));
      try {
        const payload = await api(divisionOptionsUrl({ level: entry.level, parentCode }));
        replaceOptions(entry.code, normalizeItems(payload), {
          valueKey: "value",
          labelKey: "label",
          blankLabel: `请选择${entry.level === "county" ? "区县" : entry.level === "town" ? "乡镇" : "村"}`,
          value: selectedValue,
        });
      } catch (error) {
        errorOption(entry.code, "区划加载失败", selectedValue);
        entry.code.dataset.loadError = error?.message || "区划加载失败";
      }
      entry.name.value = selectedLabel(entry.code).replace(/^历史值：/, "");
    }

    function clearLevel(index) {
      const entry = levels[index];
      entry.code.replaceChildren(option("", `请先选择${index === 1 ? "区县" : "乡镇"}`));
      entry.code.value = "";
      entry.code.disabled = true;
      entry.name.value = "";
    }

    function applyProvidedName(index, name) {
      const normalizedName = String(name || "").trim();
      if (!normalizedName) return;
      const entry = levels[index];
      entry.name.value = normalizedName;
      const selected = Array.from(entry.code.children || [])
        .find((candidate) => String(candidate.value) === String(entry.code.value));
      if (selected?.dataset?.historic === "true") selected.textContent = normalizedName;
    }

    levels[0].code.addEventListener("change", async () => {
      levels[0].name.value = selectedLabel(levels[0].code).replace(/^历史值：/, "");
      clearLevel(1);
      clearLevel(2);
      if (levels[0].code.value) await loadLevel(1, levels[0].code.value);
    });
    levels[1].code.addEventListener("change", async () => {
      levels[1].name.value = selectedLabel(levels[1].code).replace(/^历史值：/, "");
      clearLevel(2);
      if (levels[1].code.value) await loadLevel(2, levels[1].code.value);
    });
    levels[2].code.addEventListener("change", () => {
      levels[2].name.value = selectedLabel(levels[2].code).replace(/^历史值：/, "");
    });

    const initial = levels.map((entry) => ({
      code: String(entry.code.value || ""),
      name: String(entry.name.value || ""),
    }));
    const ready = (async () => {
      await loadLevel(0, "", initial[0].code);
      if (initial[0].code) await loadLevel(1, initial[0].code, initial[1].code);
      else clearLevel(1);
      if (initial[1].code) await loadLevel(2, initial[1].code, initial[2].code);
      else clearLevel(2);
      initial.forEach((entry, index) => applyProvidedName(index, entry.name));
    })();

    return {
      ready,
      async setValue(value = {}) {
        const next = [
          { code: value.countyCode, name: value.countyName },
          { code: value.townCode, name: value.townName },
          { code: value.villageCode, name: value.villageName },
        ];
        await loadLevel(0, "", next[0].code || "");
        if (next[0].code) await loadLevel(1, next[0].code, next[1].code || "");
        else clearLevel(1);
        if (next[1].code) await loadLevel(2, next[1].code, next[2].code || "");
        else clearLevel(2);
        next.forEach((entry, index) => applyProvidedName(index, entry.name));
      },
      getValue() {
        return {
          countyCode: levels[0].code.value,
          countyName: levels[0].name.value,
          townCode: levels[1].code.value,
          townName: levels[1].name.value,
          villageCode: levels[2].code.value,
          villageName: levels[2].name.value,
        };
      },
    };
  }

  function splitValues(value) {
    return String(value || "")
      .split(/[,，\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function bindReferencePicker({
    input,
    endpoint,
    valueKey,
    labelKey,
    api = defaultApi,
    placeholder = "输入编号或名称搜索",
    limit = DEFAULT_LIMIT,
    multiple = true,
  }) {
    if (!input || !endpoint || !valueKey) throw new Error("关联选择控件配置不完整");
    const selected = new Map(splitValues(input.value).map((value) => [value, { value, label: value, historic: true }]));
    const container = document.createElement("div");
    container.className = "smart-reference-picker";
    const searchInput = document.createElement("input");
    searchInput.type = "search";
    searchInput.className = "smart-reference-search";
    searchInput.placeholder = placeholder;
    searchInput.setAttribute("autocomplete", "off");
    searchInput.setAttribute("role", "combobox");
    searchInput.setAttribute("aria-expanded", "false");
    const results = document.createElement("div");
    results.className = "smart-reference-results hidden";
    results.setAttribute("role", "listbox");
    const chips = document.createElement("div");
    chips.className = "smart-reference-chips";
    container.append(searchInput, results, chips);
    input.type = "hidden";
    input.insertAdjacentElement("afterend", container);

    function syncInput() {
      input.value = Array.from(selected.keys()).join(", ");
    }

    function renderChips() {
      const chipElements = Array.from(selected.values()).map((item) => {
        const chip = document.createElement("span");
        chip.className = "smart-reference-chip";
        const label = document.createElement("span");
        label.textContent = item.label || item.value;
        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.className = "smart-reference-remove";
        removeButton.textContent = "×";
        removeButton.title = `移除 ${item.label || item.value}`;
        removeButton.setAttribute("aria-label", removeButton.title);
        removeButton.addEventListener("click", () => remove(item.value));
        chip.append(label, removeButton);
        return chip;
      });
      chips.replaceChildren(...chipElements);
      syncInput();
    }

    function add(item) {
      const value = String(item?.[valueKey] ?? item?.value ?? "");
      if (!value) return;
      if (!multiple) selected.clear();
      selected.set(value, {
        value,
        label: String(item?.[labelKey] ?? item?.label ?? value),
        historic: false,
      });
      renderChips();
      searchInput.value = "";
      results.classList.add("hidden");
      searchInput.setAttribute("aria-expanded", "false");
    }

    function remove(value) {
      selected.delete(String(value));
      renderChips();
    }

    async function search(term) {
      const normalized = String(term || "").trim();
      if (!normalized) {
        results.replaceChildren();
        results.classList.add("hidden");
        searchInput.setAttribute("aria-expanded", "false");
        return [];
      }
      results.classList.remove("hidden");
      results.replaceChildren();
      const loading = document.createElement("p");
      loading.className = "smart-reference-state";
      loading.textContent = "正在搜索...";
      results.append(loading);
      try {
        const params = new URLSearchParams({ q: normalized, limit: String(limit), offset: "0" });
        const separator = endpoint.includes("?") ? "&" : "?";
        const items = normalizeItems(await api(`${endpoint}${separator}${params}`));
        const buttons = items.map((item) => {
          const value = String(item?.[valueKey] ?? "");
          const button = document.createElement("button");
          button.type = "button";
          button.className = "smart-reference-result";
          button.setAttribute("role", "option");
          button.disabled = selected.has(value);
          button.textContent = `${item?.[labelKey] || value} · ${value}`;
          button.addEventListener("click", () => add(item));
          return button;
        });
        if (!buttons.length) {
          const empty = document.createElement("p");
          empty.className = "smart-reference-state";
          empty.textContent = "没有匹配记录";
          results.replaceChildren(empty);
        } else {
          results.replaceChildren(...buttons);
        }
        searchInput.setAttribute("aria-expanded", "true");
        return items;
      } catch (error) {
        const failure = document.createElement("p");
        failure.className = "smart-reference-state";
        failure.textContent = "搜索失败，请稍后重试";
        results.replaceChildren(failure);
        results.dataset.loadError = error?.message || "搜索失败";
        return [];
      }
    }

    let searchTimer = null;
    searchInput.addEventListener("input", () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => search(searchInput.value), 240);
    });
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        results.classList.add("hidden");
        searchInput.setAttribute("aria-expanded", "false");
      }
    });

    renderChips();
    return {
      container,
      searchInput,
      results,
      chips,
      search,
      add,
      remove,
      setValues(values = []) {
        selected.clear();
        values.slice(0, multiple ? values.length : 1).forEach((item) => {
          if (typeof item === "string") {
            selected.set(item, { value: item, label: item, historic: true });
          } else {
            const value = String(item?.[valueKey] ?? item?.value ?? "");
            if (value) {
              selected.set(value, {
                value,
                label: String(item?.[labelKey] ?? item?.label ?? value),
                historic: Boolean(item?.historic),
              });
            }
          }
        });
        renderChips();
      },
      getValues() { return Array.from(selected.keys()); },
      setDisabled(disabled) {
        searchInput.disabled = Boolean(disabled);
        container.classList.toggle("is-disabled", Boolean(disabled));
      },
    };
  }

  return {
    bindAdministrativeDivision,
    bindDictionarySelect,
    bindReferencePicker,
    replaceOptions,
    splitValues,
  };
})();

window.AdminSmartFields = AdminSmartFields;
