import { COMPENSATION_PERCENT_FIELDS } from './comparisonIntegrity';

/**
 * Copy one setting from a scenario diff row into another scenario's saved
 * overrides. The diff shows paths from each run's saved config (workspace base
 * merged with scenario overrides), so writing the value at the same override
 * path reproduces it on the next run -- except for the cases handled here.
 */

type Overrides = Record<string, unknown>;

/** Run-config paths a scenario override can't set, or that another setting overrides. */
const NOT_APPLICABLE: ReadonlyArray<RegExp> = [
  /^setup\./, // census path is resolved per run
  /^param_pack(\.|$)/, // provenance stamped at run time
  /^(promotion_hazard|age_bands|tenure_bands)(\.|$)/, // whole seed tables, validated as a unit
  // Engine DC sections: Studio's dc_plan.* settings override these when the
  // run exports, so copying them changes nothing. The dc_plan.* row carries it.
  /^(enrollment|employer_match|employer_core_contribution|deferral_auto_escalation|eligibility|plan_eligibility|easy_enroll|deferral_rate_changes)(\.|$)/,
];

const PAY_FIELD = new RegExp(`^compensation\\.(${COMPENSATION_PERCENT_FIELDS.join('|')})(_percent)?$`);

export interface OverrideWrite {
  path: string;
  value: unknown;
}

export function canApplyDelta(path: string): boolean {
  return !NOT_APPLICABLE.some(pattern => pattern.test(path));
}

function scaled(value: unknown, factor: number): unknown {
  return typeof value === 'number' ? Number((value * factor).toPrecision(12)) : value;
}

/**
 * Override paths (and units) to write for a diff row. Pay settings are written
 * as both the engine decimal and Studio's percent, like the Studio form keeps
 * them: the engine prefers the decimal, so the percent alone would be ignored.
 */
export function overrideWritesFor(path: string, value: unknown): OverrideWrite[] | null {
  if (!canApplyDelta(path)) return null;
  const pay = PAY_FIELD.exec(path);
  if (pay) {
    const isPercent = pay[2] !== undefined;
    return [
      { path: `compensation.${pay[1]}`, value: isPercent ? scaled(value, 0.01) : value },
      { path: `compensation.${pay[1]}_percent`, value: isPercent ? value : scaled(value, 100) },
    ];
  }
  // Studio's DC plan copy wins over the engine section when configs merge.
  if (path.startsWith('deferral_match_response.')) {
    return [{ path: `dc_plan.${path}`, value }];
  }
  return [{ path, value }];
}

function isRecord(value: unknown): value is Overrides {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function setPath(root: Overrides, path: string, value: unknown): void {
  const keys = path.split('.');
  let node = root;
  for (const key of keys.slice(0, -1)) {
    const child = node[key];
    node[key] = isRecord(child) ? { ...child } : {};
    node = node[key] as Overrides;
  }
  node[keys[keys.length - 1]] = value;
}

/** New overrides with the diff row's value written; null if it can't be applied. */
export function applyDeltaToOverrides<T extends object>(overrides: T, path: string, value: unknown): T | null {
  const writes = overrideWritesFor(path, value);
  if (!writes) return null;
  const next = structuredClone(overrides) as T & Overrides;
  for (const write of writes) setPath(next, write.path, structuredClone(write.value));
  return next;
}
