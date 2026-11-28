// Two plan designs in one simulation, split by a hire-date cutoff (#646). Emits the
// engine's `plan_design_assignment` and `plan_design_parameters` (docs/plan_design_assignment.md).
import { designParameters, formulaFromDesign, pickFormula, sameSettings, sharedParameters } from './designParameters';
import { CORE_FORMULA_KEYS, MATCH_FORMULA_KEYS } from './types';
import type { DesignFormula, FormData, GrandfatheredDesignForm } from './types';

type Json = Record<string, unknown>;
const isObject = (value: unknown): value is Json =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
const asJson = (value: unknown): Json => (isObject(value) ? value : {});

export const DEFAULT_EXISTING_DESIGN_ID = 'existing_employees';
export const DEFAULT_NEW_HIRE_DESIGN_ID = 'new_hires';

/** A first-time setup: new hires start from a copy of the current formulas. */
export function newGrandfatheredDesign(form: FormData): GrandfatheredDesignForm {
  return {
    enabled: true,
    cutoff: `${Number(form.startYear)}-01-01`,
    existingDesignId: DEFAULT_EXISTING_DESIGN_ID,
    newHireDesignId: DEFAULT_NEW_HIRE_DESIGN_ID,
    changeMatch: true,
    changeCore: false,
    newHireFormula: pickFormula(form),
    savedActive: false,
  };
}

const pick = (formula: DesignFormula, keys: readonly (keyof DesignFormula)[]): Partial<DesignFormula> =>
  Object.fromEntries(keys.map(key => [key, formula[key]]));

/** The new-hire formula: plan-wide formulas with only the chosen parts replaced. */
export function newHireFormula(form: FormData, design: GrandfatheredDesignForm): DesignFormula {
  return {
    ...pickFormula(form),
    ...(design.changeMatch ? pick(design.newHireFormula, MATCH_FORMULA_KEYS) : {}),
    ...(design.changeCore ? pick(design.newHireFormula, CORE_FORMULA_KEYS) : {}),
  };
}

/**
 * Top-level payload keys. Nothing when the feature was never used, so the
 * single-design payload is unchanged. Turning off a saved setup writes nulls,
 * which also clears a setup inherited from the workspace.
 */
export function grandfatheredDesignPayload(form: FormData): Json {
  const design = form.dcGrandfather;
  if (!design) return {};
  if (!design.enabled) return design.savedActive ? { plan_design_assignment: null, plan_design_parameters: null } : {};
  return {
    plan_design_assignment: {
      default_plan_design_id: design.existingDesignId,
      rules: [{ type: 'hire_date_cutoff', cutoff: design.cutoff, plan_design_id: design.newHireDesignId }],
    },
    plan_design_parameters: {
      [design.existingDesignId]: designParameters(form),
      [design.newHireDesignId]: designParameters(form, newHireFormula(form, design)),
    },
  };
}

/** The saved plan-design keys as a run sees them: scenario overrides deep-merged onto the workspace. */
export function mergedDesignConfig(base: Json, overrides: Json | undefined): Json {
  const merge = (left: unknown, right: unknown): unknown => {
    if (right === undefined) return left;
    if (!isObject(left) || !isObject(right)) return right;
    const result = { ...left };
    for (const [key, value] of Object.entries(asJson(right))) result[key] = merge(result[key], value);
    return result;
  };
  return Object.fromEntries(['plan_design_assignment', 'plan_design_parameters']
    .map(key => [key, merge(base[key], overrides?.[key])]));
}

/** Whether a configuration defines plan designs (active, not cleared with null). */
export function hasSavedDesigns(config: Json): boolean {
  return Object.keys(asJson(config.plan_design_assignment)).length > 0
    || Object.keys(asJson(config.plan_design_parameters)).length > 0;
}

interface SavedSplit { cutoff: string; existingId: string; newHireId: string }

function savedSplit(config: Json): SavedSplit | null {
  const assignment = asJson(config.plan_design_assignment);
  const rules = Array.isArray(assignment.rules) ? assignment.rules : [];
  const rule = asJson(rules[0]);
  const ids = Object.keys(asJson(config.plan_design_parameters));
  const split = { cutoff: rule.cutoff, existingId: assignment.default_plan_design_id, newHireId: rule.plan_design_id };
  if (rules.length !== 1 || (rule.type ?? 'hire_date_cutoff') !== 'hire_date_cutoff') return null;
  if (typeof split.cutoff !== 'string' || typeof split.existingId !== 'string' || typeof split.newHireId !== 'string') return null;
  if (split.existingId === split.newHireId || ids.length !== 2 || !ids.includes(split.existingId) || !ids.includes(split.newHireId)) return null;
  return split as SavedSplit;
}

/**
 * Load a saved setup into the editor. Returns null, leaving the saved designs
 * untouched on save, unless the existing-employee design is exactly what the
 * DC Plan page shows and the designs differ only in match or core.
 */
export function grandfatheredDesignFromConfig(config: Json, form: FormData): GrandfatheredDesignForm | null {
  const split = savedSplit(config);
  if (!split) return null;
  const parameters = asJson(config.plan_design_parameters);
  const existing = asJson(parameters[split.existingId]);
  const newHire = asJson(parameters[split.newHireId]);
  const formula = formulaFromDesign(newHire, form);
  if (!formula || !sameSettings(existing, designParameters(form))) return null;
  const shared = sharedParameters(form);
  if (Object.keys(shared).some(key => !sameSettings(newHire[key], shared[key]))) return null;
  return {
    enabled: true,
    cutoff: split.cutoff,
    existingDesignId: split.existingId,
    newHireDesignId: split.newHireId,
    changeMatch: !sameSettings(newHire.match, existing.match),
    changeCore: !sameSettings(newHire.employer_core, existing.employer_core),
    newHireFormula: formula,
    savedActive: true,
  };
}
