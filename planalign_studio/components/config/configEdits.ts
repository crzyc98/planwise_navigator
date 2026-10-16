type ConfigObject = Record<string, unknown>;

function isObject(value: unknown): value is ConfigObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

const equal = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right);

function editRows(original: unknown, before: unknown[], after: unknown[]): unknown[] {
  const originalRows = Array.isArray(original) ? original : [];
  const available = new Set(before.map((_, index) => index));
  const matches = after.map(row => {
    const index = [...available].find(candidate => equal(before[candidate], row));
    if (index !== undefined) available.delete(index);
    return index;
  });
  const unmatched = matches.filter(index => index === undefined).length;
  // When rows are edited as well as inserted/deleted, row ownership is ambiguous.
  // Refuse to silently move custom fields to a different schedule row.
  if (unmatched && available.size && unmatched !== available.size &&
      [...available].some(index => !equal(originalRows[index] ?? before[index], before[index]))) {
    throw new Error('This schedule contains custom row settings. Save row edits separately from adding or removing rows so those settings remain attached to the correct row.');
  }
  const remaining = [...available];
  const pairEdits = unmatched === remaining.length;
  return after.map((row, index) => {
    const previousIndex = matches[index] ?? (pairEdits ? remaining.shift() : undefined);
    if (previousIndex === undefined) return structuredClone(row);
    return applyConfigEdits(originalRows[previousIndex] ?? before[previousIndex], before[previousIndex], row);
  });
}

/** Apply only edited form values to the original configuration, preserving extras. */
export function applyConfigEdits(original: unknown, before: unknown, after: unknown): unknown {
  if (equal(before, after)) return structuredClone(original);
  if (Array.isArray(before) && Array.isArray(after)) {
    return editRows(original, before, after);
  }
  if (!isObject(after)) return structuredClone(after);
  const result: ConfigObject = isObject(original) ? structuredClone(original) : {};
  const previous = isObject(before) ? before : {};
  for (const key of new Set([...Object.keys(previous), ...Object.keys(after)])) {
    if (equal(previous[key], after[key])) continue;
    if (!(key in after)) {
      if (isObject(previous[key])) {
        const retained = applyConfigEdits(result[key], previous[key], {}) as ConfigObject;
        if (Object.keys(retained).length) result[key] = retained;
        else delete result[key];
      } else delete result[key];
    } else result[key] = applyConfigEdits(result[key], previous[key], after[key]);
  }
  return result;
}

/** Canonical decimal fields take precedence over Studio percentage aliases. */
export function synchronizeCompensationAliases(
  config: ConfigObject, before: ConfigObject, after: ConfigObject,
): ConfigObject {
  const result = structuredClone(config);
  const oldComp = isObject(before.compensation) ? before.compensation : {};
  const newComp = isObject(after.compensation) ? after.compensation : {};
  const comp = isObject(result.compensation) ? result.compensation : {};
  for (const key of ['cola_rate', 'merit_budget', 'promotion_increase', 'promotion_budget', 'promotion_distribution_range']) {
    const alias = `${key}_percent`;
    if (!equal(oldComp[alias], newComp[alias])) comp[key] = Number(newComp[alias]) / 100;
  }
  if (isObject(result.compensation)) result.compensation = comp;
  return result;
}
