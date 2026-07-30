const AdminBusinessComputations = (() => {
  function hasValue(value) {
    return value !== null && value !== undefined && String(value).trim() !== "";
  }

  function numericValue(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : 0;
  }

  function computeFieldValue(definition = {}, values = {}) {
    const fields = Array.isArray(definition.fields) ? definition.fields : [];
    const operation = String(definition.operation || "");
    if (!fields.length) return "";

    if (operation === "subtract") {
      if (!fields.some((field) => hasValue(values[field]))) return "";
      const result = numericValue(values[fields[0]]) - numericValue(values[fields[1]]);
      const precision = Number.isInteger(definition.precision) ? definition.precision : 2;
      return Number(result.toFixed(precision));
    }

    if (operation === "stock-status") {
      if (!hasValue(values[fields[0]])) return "";
      const stock = numericValue(values[fields[0]]);
      const warningThreshold = numericValue(values[fields[1]]);
      if (stock <= 0) return "out";
      if (warningThreshold > 0 && stock <= warningThreshold) return "warning";
      return "normal";
    }

    return "";
  }

  function relationTargets(field, links) {
    return (Array.isArray(links) ? links : [])
      .filter((link) => (
        String(link?.relationType || "") === String(field?.relationType || "")
        && String(link?.targetModuleKey || "") === String(field?.targetModuleKey || "")
        && hasValue(link?.targetRecordId)
      ))
      .map((link) => String(link.targetRecordId));
  }

  function validateRelationRequirements(fieldSchema = [], links = []) {
    const relationFields = (Array.isArray(fieldSchema) ? fieldSchema : [])
      .filter((field) => field?.inputType === "business-relation");
    const valuesByField = new Map(
      relationFields.map((field) => [field.key, relationTargets(field, links)]),
    );

    const missingRequired = relationFields.find(
      (field) => field.required && !(valuesByField.get(field.key) || []).length,
    );
    if (missingRequired) {
      return {
        valid: false,
        fieldKey: missingRequired.key,
        message: `请选择${missingRequired.label || missingRequired.key}`,
      };
    }

    const groups = new Map();
    relationFields.forEach((field) => {
      const relationGroup = String(field.relationGroup || "").trim();
      if (!relationGroup) return;
      if (!groups.has(relationGroup)) {
        groups.set(relationGroup, {
          fields: [],
          targets: new Set(),
          minimum: 0,
        });
      }
      const group = groups.get(relationGroup);
      group.fields.push(field);
      (valuesByField.get(field.key) || []).forEach((value) => group.targets.add(value));
      group.minimum = Math.max(group.minimum, Number(field.minGroupTargets || 0));
    });

    for (const [relationGroup, group] of groups.entries()) {
      if (group.targets.size >= group.minimum) continue;
      const labels = group.fields.map((field) => field.label || field.key).join("、");
      return {
        valid: false,
        fieldKey: group.fields[0]?.key || "",
        relationGroup,
        message: `请在${labels}中至少选择${group.minimum}项`,
      };
    }
    return { valid: true };
  }

  return { computeFieldValue, validateRelationRequirements };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = AdminBusinessComputations;
}
if (typeof window !== "undefined") {
  window.AdminBusinessComputations = AdminBusinessComputations;
}
