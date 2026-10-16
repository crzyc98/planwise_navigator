type ConfigObject = Record<string, unknown>;

function isObject(value: unknown): value is ConfigObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

// YAML/API serialization can reorder object keys without changing a setting.
// Schedule row order, however, remains significant.
function equal(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((value, index) => equal(value, right[index]));
  }
  if (!isObject(left) || !isObject(right)) return false;
  const keys = Object.keys(left);
  return keys.length === Object.keys(right).length && keys.every(key =>
    Object.prototype.hasOwnProperty.call(right, key) && equal(left[key], right[key]),
  );
}

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

/** Editing a legacy match rule saves the full displayed policy. */
export function preserveDisplayedMatchEligibility(
  config: ConfigObject, before: ConfigObject, after: ConfigObject, variables: ConfigObject,
): ConfigObject {
  const match = isObject(variables.employer_match) ? variables.employer_match : {};
  if (match.apply_eligibility !== false) return config;
  const oldPlan = isObject(before.dc_plan) ? before.dc_plan : {};
  const newPlan = isObject(after.dc_plan) ? after.dc_plan : {};
  const fields = ['match_min_tenure_years', 'match_min_hours_annual', 'match_require_year_end_active',
    'match_allow_terminated_new_hires', 'match_allow_experienced_terminations'];
  if (!fields.some(key => !equal(oldPlan[key], newPlan[key]))) return config;
  // Enabling detailed matching must not resurrect dormant rules absent from
  // the displayed policy. Keep the legacy source intact for auditability.
  return { ...config, dc_plan: {
    ...(isObject(config.dc_plan) ? config.dc_plan : {}),
    ...Object.fromEntries(fields.map(key => [key, newPlan[key]])),
    match_allow_new_hires: newPlan.match_min_tenure_years === 0,
  } };
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
