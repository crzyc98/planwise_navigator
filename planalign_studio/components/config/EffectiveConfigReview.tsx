import { useEffect, useRef, useState } from 'react';
import { previewConfiguration, type ConfigPreview } from '../../services/api';
import { ELIGIBILITY_DEFAULTS, MATCH_TEMPLATES } from './constants';

type Config = Record<string, unknown>;
const asConfig = (value: unknown): Config => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Config : {};
export interface ConfigurationReviewDraft {
  draft: Config;
  saved: Config;
  workspaceId: string;
  scenarioId?: string;
  targetName: string;
  runAfterSave: boolean;
}

const sensitiveKey = /path|file|token|password|secret|credential|census|employee_id|employee_name|employee_rows|^employees$|first_name|last_name|ssn|email|date_of_birth/i;
/** Review contains configuration only; redact paths and possible identity fields. */
export function redactReviewValue(value: unknown, key = ''): unknown {
  if (sensitiveKey.test(key)) return '[hidden]';
  if (Array.isArray(value)) return value.map(item => redactReviewValue(item));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([name, child]) => [name, redactReviewValue(child, name)]));
  if (typeof value === 'string' && (/^(\/|[A-Z]:\\)/i.test(value) || /\.(csv|parquet|duckdb)$/i.test(value))) return '[hidden]';
  return value;
}

function flatten(config: Config, prefix = ''): Config {
  return Object.fromEntries(Object.entries(config).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return value && typeof value === 'object' && !Array.isArray(value)
      ? Object.entries(flatten(asConfig(value), path)) : [[path, value]];
  }));
}

export function reviewChanges(saved: Config, draft: Config) {
  const before = flatten(saved);
  const after = flatten(draft);
  return [...new Set([...Object.keys(before), ...Object.keys(after)])].sort()
    .filter(key => JSON.stringify(before[key]) !== JSON.stringify(after[key]))
    .map(key => ({ key, before: redactReviewValue(before[key], key), after: redactReviewValue(after[key], key) }));
}

const showValue = (value: unknown) => value === undefined ? 'Inherited / default' : JSON.stringify(value);
const matchEligibilityFields: Record<string, [string, string]> = {
  match_min_tenure_years: ['minimum_tenure_years', 'Match minimum service'],
  match_min_hours_annual: ['minimum_hours_annual', 'Match minimum annual hours'],
  match_require_year_end_active: ['require_active_at_year_end', 'Match year-end employment requirement'],
  match_allow_terminated_new_hires: ['allow_terminated_new_hires', 'Match eligibility for terminated hire-year employees'],
  match_allow_experienced_terminations: ['allow_experienced_terminations', 'Match eligibility for terminated experienced employees'],
};
// Studio has no waiver control; the engine derives it from service, so only engine reviews compare it.
const engineMatchEligibilityFields: [string, string][] = [...Object.values(matchEligibilityFields),
  ['allow_new_hires', 'New-hire exemption from match service requirement']];
function eligibilityField(key: string): [string, string] | undefined {
  return key.startsWith('dc_plan.') ? matchEligibilityFields[key.slice(8)]
    : key.startsWith('employer_match.eligibility.')
      ? engineMatchEligibilityFields.find(([field]) => key.endsWith(`.${field}`)) : undefined;
}

function effectiveMatchRules(match: Config): Config {
  const rules = match.apply_eligibility === false ? {} : asConfig(match.eligibility);
  return { ...ELIGIBILITY_DEFAULTS.Match, ...rules,
    allow_new_hires: rules.allow_new_hires ?? (rules.minimum_tenure_years ?? ELIGIBILITY_DEFAULTS.Match.minimum_tenure_years) === 0 };
}

/** Compare effective rules, leaving storage/compatibility details in the full config. */
export function eligibilityReviewChanges(
  saved: Config, draft: Config, before: Config, after: Config, engine = false,
) {
  const changes = reviewChanges(saved, draft);
  if (!before.employer_match || !after.employer_match) return changes;
  const oldRules = effectiveMatchRules(asConfig(before.employer_match));
  const newRules = effectiveMatchRules(asConfig(after.employer_match));
  const otherChanges = changes.filter(change => engine
    ? change.key !== 'employer_match.apply_eligibility' && !eligibilityField(change.key)
    : !eligibilityField(change.key));
  const fields: [string, string][] = engine
    ? engineMatchEligibilityFields.map(([field]) => [`employer_match.eligibility.${field}`, field])
    : Object.entries(matchEligibilityFields).map(([alias, [field]]) => [`dc_plan.${alias}`, field]);
  const rules = fields.flatMap(([key, field]) =>
    (!engine && !changes.some(change => change.key === key)) || oldRules[field] === newRules[field]
      ? [] : [{ key, before: oldRules[field], after: newRules[field] }]);
  return [...otherChanges, ...rules];
}

function formatEligibilityValue(key: string, value: unknown): string | undefined {
  const field = eligibilityField(key)?.[0];
  if (!field || value === undefined) return undefined;
  if (field === 'minimum_tenure_years') return `${value} ${value === 1 ? 'year' : 'years'}`;
  if (field === 'minimum_hours_annual') return `${value} hours`;
  if (typeof value !== 'boolean') return undefined;
  if (field === 'require_active_at_year_end') return value ? 'Required' : 'Not required';
  if (field === 'allow_new_hires') return value ? 'Exempt from service requirement' : 'Must meet service requirement';
  return value ? 'Allowed' : 'Excluded';
}
const behaviorLabels: Record<string, string> = {
  reenrollment_sweep_enabled: 'Periodic re-enrollment sweep',
  reenrollment_sweep_interval_years: 'Sweep interval (years)',
  reenrollment_sweep_first_year: 'First sweep year',
  reenrollment_sweep_method: 'Sweep method',
  reenrollment_sweep_include_non_contributors: 'Not contributing (0%)',
  reenrollment_sweep_include_below_default: 'Contributing below the default rate',
  reenrollment_sweep_include_below_aip_cap: 'Contributing below the automatic-increase cap',
  reenrollment_sweep_decline_probability: 'Share of contributors who decline',
  escalation_mode: 'Enrollment in automatic contribution increases',
  deferral_escalation_mode: 'Enrollment in automatic contribution increases',
  escalation_participant_elected_signup_probability: 'Employees who sign up for automatic increases',
  deferral_escalation_participant_elected_signup_probability: 'Employees who sign up for automatic increases',
  match_magnet_downward_enabled: 'Pull starting rates down to the full-match rate',
  enrollment_match_magnet_downward_enabled: 'Pull starting rates down to the full-match rate',
  below_default_share_tiers: 'Choosing a rate below the auto-enrollment default',
  below_default_steps: 'How far below the default',
  easy_enroll_enabled: 'Offer Easy Enroll packages',
  easy_enroll_channel_share_with_auto_enrollment: 'Easy Enroll share — plans with auto-enrollment',
  easy_enroll_channel_share_without_auto_enrollment: 'Easy Enroll share — plans without auto-enrollment',
  easy_enroll_packages: 'Easy Enroll packages',
  easy_enroll_escalation_cap: 'Automatic increases for Easy Enroll members stop at',
};
const labelFor = (key: string) => behaviorLabels[key.replace(/^dc_plan\./, '')] ?? ({ 'dc_plan.match_template': 'Employer match template', 'dc_plan.match_tiers': 'Employer match formula', match_tiers: 'Employer match formula', 'compensation.promotion_compensation.base_increase_pct': 'Promotion pay increase', 'compensation.promotion_compensation.distribution_range': 'Promotion increase spread', promotion_base_increase_pct: 'Promotion pay increase', deferral_escalation_cap: 'Annual auto-escalation cap', target_growth_rate: 'Annual headcount growth', simulation_start_year: 'First projection year', end_year: 'Last projection year' }[key] ?? key.replaceAll('_', ' ').replaceAll('.', ' → '));

function formatBehaviorSetting(key: string, value: unknown): string | undefined {
  key = key.replace(/^dc_plan\./, '');
  if (!(key in behaviorLabels) || value == null) return undefined;
  if (key.endsWith('escalation_mode')) return value === 'automatic' ? 'Automatic (everyone unless they opt out)'
    : value === 'participant_elected' ? 'Participant-elected (employees sign up)' : showValue(value);
  if (key.endsWith('signup_probability') && typeof value === 'number') return `${Number((value * 100).toFixed(3))}%`;
  if (key.startsWith('easy_enroll_') && typeof value === 'number') return `${Number((value * 100).toFixed(3))}%`;
  if (key === 'easy_enroll_enabled' && typeof value === 'boolean') return value ? 'On' : 'Off';
  if (!Array.isArray(value)) return undefined;
  const pct = (rate: unknown) => typeof rate === 'number' ? `${Number((rate * 100).toFixed(3))}%` : showValue(rate);
  if (key === 'easy_enroll_packages') return value.map((row: unknown) => {
    const pkg = asConfig(row);
    return `${pct(pkg.rate)} contribution, chosen by ${pct(pkg.share)}`;
  }).join('; ');
  if (key === 'below_default_share_tiers') return value.map((row: unknown) => {
    const tier = asConfig(row);
    const ceiling = tier.max_auto_enroll_default_rate;
    return `${ceiling === null ? 'Higher auto-enrollment defaults' : `Auto-enrollment default up to ${pct(ceiling)}`}: ${pct(tier.share)} choose below`;
  }).join('; ');
  if (key === 'below_default_steps') return value.map((row: unknown) => {
    const step = asConfig(row);
    return `${step.pp} percentage ${step.pp === 1 ? 'point' : 'points'} below (${pct(step.weight)})`;
  }).join('; ');
  return undefined;
}
const percentVariables = new Set(['reenrollment_sweep_decline_probability', 'target_growth_rate', 'total_termination_rate', 'new_hire_termination_rate', 'cola_rate', 'merit_budget', 'promotion_base_increase_pct', 'promotion_distribution_range', 'auto_enrollment_default_deferral_rate', 'voluntary_enrollment_rate', 'new_hire_opt_out_rate', 'deferral_escalation_increment', 'deferral_escalation_cap', 'match_cap_percent', 'employer_match_max_deferral_rate', 'employer_core_contribution_rate', 'new_hire_ineligible_pct']);
const summaryVariables = ['reenrollment_sweep_method', 'reenrollment_sweep_include_non_contributors', 'reenrollment_sweep_include_below_default', 'reenrollment_sweep_include_below_aip_cap', 'reenrollment_sweep_decline_probability', 'reenrollment_sweep_enabled', 'reenrollment_sweep_interval_years', 'reenrollment_sweep_first_year', 'simulation_start_year', 'end_year', 'random_seed', 'target_growth_rate', 'total_termination_rate', 'new_hire_termination_rate', 'cola_rate', 'merit_budget', 'promotion_base_increase_pct', 'promotion_distribution_range', 'promotion_rate_multiplier', 'auto_enrollment_enabled', 'auto_enrollment_scope', 'auto_enrollment_hire_date_cutoff', 'auto_enrollment_window_days', 'auto_enrollment_default_deferral_rate', 'voluntary_enrollment_rate', 'new_hire_opt_out_rate', 'deferral_escalation_enabled', 'deferral_escalation_increment', 'deferral_escalation_cap',
  'deferral_escalation_mode', 'deferral_escalation_participant_elected_signup_probability', 'enrollment_match_magnet_downward_enabled', 'below_default_share_tiers', 'below_default_steps',
  'easy_enroll_enabled', 'easy_enroll_channel_share_with_auto_enrollment', 'easy_enroll_channel_share_without_auto_enrollment', 'easy_enroll_packages', 'easy_enroll_escalation_cap'];
const formatVariable = (key: string, value: unknown) => {
  if (key.replace(/^dc_plan\./, '') === 'reenrollment_sweep_method') return value === 'into_aip' ? 'Sweep into automatic increases' : 'Enroll at the default rate';
  if (key.replace(/^dc_plan\./, '') === 'reenrollment_sweep_first_year' && value === null) return 'Start year + sweep interval';
  const behavior = formatBehaviorSetting(key, value);
  if (behavior !== undefined) return behavior;
  const eligibility = formatEligibilityValue(key, value);
  if (eligibility !== undefined) return eligibility;
  if (key === 'match_tiers') return formatMatchTiers(value);
  if (typeof value === 'boolean') return value ? 'On' : 'Off';
  if (typeof value === 'number' && (percentVariables.has(key) || /^deferral_match_response_.*(rate|factor)$/.test(key))) return `${Number((value * 100).toFixed(3))}%`;
  if (value === 'new_hires_only') return 'New hires only';
  if (value === 'all_eligible_employees' || value === 'all_eligible') return 'All eligible employees';
  return showValue(redactReviewValue(value, key));
};
const percentagePointPaths = new Set([
  ...['target_compensation_growth', 'merit_budget', 'cola_rate', 'promotion_increase', 'promotion_distribution_range', 'promotion_budget'].map(key => `compensation.${key}_percent`),
  'new_hire.compensation_variance_percent', 'dc_plan.default_deferral_percent', 'dc_plan.core_contribution_rate_percent',
  'dc_plan.escalation_rate_percent', 'dc_plan.escalation_cap_percent',
]);
const decimalRatePaths = new Set([
  'dc_plan.reenrollment_sweep_decline_probability',
  'simulation.target_growth_rate', 'workforce.total_termination_rate', 'workforce.new_hire_termination_rate', 'workforce.part_time_new_hire_pct',
  ...['cola_rate', 'merit_budget', 'promotion_increase', 'promotion_distribution_range', 'promotion_budget'].map(key => `compensation.${key}`),
  'compensation.promotion_compensation.base_increase_pct', 'compensation.promotion_compensation.distribution_range',
  ...['match_cap_percent', 'max_voluntary_deferral_percent', 'voluntary_enrollment_rate', 'new_hire_opt_out_rate', 'opt_out_rate_target',
    'match_magnet_probability', 'core_integration_disparity_rate', 'opt_out_rate_young', 'opt_out_rate_mid', 'opt_out_rate_mature', 'opt_out_rate_senior',
    'opt_out_rate_low_income', 'opt_out_rate_moderate', 'opt_out_rate_high', 'opt_out_rate_executive'].map(key => `dc_plan.${key}`),
  'dc_plan.deferral_match_response.upward_participation_rate', 'dc_plan.deferral_match_response.downward_participation_rate',
]);
export function formatDraftValue(key: string, value: unknown) {
  if (key.replace(/^dc_plan\./, '') === 'reenrollment_sweep_method') return value === 'into_aip' ? 'Sweep into automatic increases' : 'Enroll at the default rate';
  if (key.replace(/^dc_plan\./, '') === 'reenrollment_sweep_first_year' && value === null) return 'Start year + sweep interval';
  const behavior = formatBehaviorSetting(key, value);
  if (behavior !== undefined) return behavior;
  const eligibility = formatEligibilityValue(key, value);
  if (eligibility !== undefined) return eligibility;
  if (key === 'dc_plan.match_tiers') return formatMatchTiers(value);
  if (key === 'dc_plan.match_template' && typeof value === 'string' && Object.prototype.hasOwnProperty.call(MATCH_TEMPLATES, value)) {
    return MATCH_TEMPLATES[value as keyof typeof MATCH_TEMPLATES].name;
  }
  if (typeof value !== 'number') return showValue(value);
  if (percentagePointPaths.has(key)) return `${Number(value.toFixed(3))}%`;
  if (decimalRatePaths.has(key) || key.startsWith('dc_plan.voluntary_deferral_base_rates.')) return `${Number((value * 100).toFixed(3))}%`;
  return showValue(value);
}

function formatMatchTiers(value: unknown): string {
  if (!Array.isArray(value)) return showValue(value);
  if (!value.length) return 'No explicit match tiers';
  const fields = ['employee_min', 'employee_max', 'match_rate'];
  if (value.some(row => !row || !fields.every(key => typeof row[key] === 'number' && Number.isFinite(row[key])) || row.employee_min < 0 || row.employee_max <= row.employee_min || row.match_rate < 0)) {
    return showValue(value);
  }
  const pct = (rate: number) => `${Number((rate * 100).toFixed(3))}%`;
  return value.map((row, index) => {
    const interval = row.employee_min === 0 ? `the first ${pct(row.employee_max)}`
      : index > 0 && value[index - 1].employee_max === row.employee_min
        ? `the next ${pct(row.employee_max - row.employee_min)}`
        : `employee contributions from ${pct(row.employee_min)} to ${pct(row.employee_max)}`;
    const extras = Object.fromEntries(Object.entries(row).filter(([key]) => !fields.includes(key)));
    const details = Object.keys(extras).length ? ` (additional row settings: ${showValue(redactReviewValue(extras))})` : '';
    return `${pct(row.match_rate)} on ${interval}${details}`;
  }).join('; then ');
}
function inactiveVariable(key: string, variables: Config): string | null {
  if (key.startsWith('easy_enroll_') && key !== 'easy_enroll_enabled') {
    if (variables.easy_enroll_enabled === false) return 'Inactive while Easy Enroll is off; saved value retained.';
    const applicable = variables.auto_enrollment_enabled === true ? 'with' : 'without';
    if (key.includes('channel_share_') && key !== `easy_enroll_channel_share_${applicable}_auto_enrollment`) {
      return 'Inactive for this plan; saved value retained.';
    }
  }
  if (variables.deferral_escalation_enabled === false && ['deferral_escalation_mode', 'deferral_escalation_participant_elected_signup_probability'].includes(key)) {
    return 'Inactive while automatic contribution increases are off; saved value retained.';
  }
  if (key === 'deferral_escalation_participant_elected_signup_probability' && variables.deferral_escalation_mode !== 'participant_elected') {
    return 'Inactive when employees join automatic contribution increases automatically; saved value retained.';
  }
  if (key === 'enrollment_match_magnet_downward_enabled' && variables.enrollment_match_magnet_enabled === false) {
    return 'Inactive while new-enrollee match seeking is off; uses the same probability as the upward pull.';
  }
  if (key.startsWith('reenrollment_sweep_') && (variables.auto_enrollment_enabled === false || (key !== 'reenrollment_sweep_enabled' && variables.reenrollment_sweep_enabled !== true))) {
    return 'Sweep settings inactive; saved values retained.';
  }
  return variables.auto_enrollment_enabled === false && ['auto_enrollment_default_deferral_rate', 'new_hire_opt_out_rate', 'below_default_share_tiers', 'below_default_steps', 'enrollment_match_magnet_downward_enabled'].includes(key)
    ? 'Inactive while automatic enrollment is off; saved value retained.' : null;
}

function describeSettings(value: unknown): string {
  if (Array.isArray(value)) return `${value.length} rows: ${value.map(row => describeSettings(row)).join('; ')}`;
  if (value && typeof value === 'object') return Object.entries(value).map(([key, child]) => `${labelFor(key)}: ${describeSettings(child)}`).join(', ');
  return value === undefined ? 'Inherited / default' : String(value);
}

export function matchEligibilityReview(value: Config): string {
  const legacy = value.apply_eligibility === false;
  const rules: Config = { ...ELIGIBILITY_DEFAULTS.Match, ...(legacy ? {} : asConfig(value.eligibility)) };
  return `Minimum service: ${rules.minimum_tenure_years} years; minimum annual hours: ${rules.minimum_hours_annual}; ` +
    `active employment at year-end: ${rules.require_active_at_year_end ? 'required' : 'not required'}; ` +
    `terminated hire-year employees: ${rules.allow_terminated_new_hires ? 'allowed' : 'excluded'}; ` +
    `terminated experienced employees: ${rules.allow_experienced_terminations ? 'allowed' : 'excluded'}. ` +
    (legacy ? 'No new-hire service waiver is needed with zero minimum service.'
      : `New-hire service waiver: ${(rules.allow_new_hires ?? rules.minimum_tenure_years === 0) ? 'allowed' : 'not allowed'}.`);
}

function formatActiveSetting(key: string, value: unknown): string {
  if (key === 'employer_match' && value && typeof value === 'object') return matchEligibilityReview(value as Config);
  if (key === 'match_tiers') return formatMatchTiers(value);
  return value && typeof value === 'object' ? describeSettings(redactReviewValue(value, key)) : formatVariable(key, value);
}

export function matchRuleSummary(variables: Config): string | null {
  if (variables.employer_match_enabled === false) return 'Employer match is off; the saved formula and schedules are retained.';
  if (typeof variables.employer_match_status === 'string' && variables.employer_match_status !== 'deferral_based') return `Match varies by ${labelFor(variables.employer_match_status)}. Review the resolved schedule below.`;
  if (Object.keys(asConfig(variables.plan_design_parameters)).length) return 'Match rules vary by assigned plan design. Review the resolved plan-design parameters below.';
  const tiers = variables.match_tiers;
  if (!Array.isArray(tiers) || !tiers.length) return 'No explicit matching tiers were exported. The match calculation uses its engine default tier schedule; a legacy formula label alone does not verify the applied schedule. Mapping unverified.';
  if (tiers.some(tier => !['employee_min', 'employee_max', 'match_rate'].every(key => Number.isFinite(tier[key])))) return 'The exported matching tiers could not be summarized. Inspect the complete engine variables. Mapping unverified.';
  const positiveTiers = tiers.filter(tier => tier.match_rate > 0);
  const threshold = Math.max(0, ...positiveTiers.map(tier => tier.employee_max));
  const total = tiers.reduce((sum, tier) => sum + Math.max(0, tier.employee_max - tier.employee_min) * tier.match_rate, 0);
  const maximum = Math.min(total, typeof variables.match_cap_percent === 'number' && Number.isFinite(variables.match_cap_percent)
    ? variables.match_cap_percent : 0.04);
  const pct = (value: number) => `${Number((value * 100).toFixed(3))}%`;
  return `${tiers.map(tier => `${pct(tier.match_rate)} match on employee contributions from ${pct(tier.employee_min)} to ${pct(tier.employee_max)}`).join('; ')}. Employee contribution at the top matching tier: ${pct(threshold)} of compensation. Maximum formula match: ${pct(maximum)} of compensation, before eligibility and IRS limits.`;
}

function ActiveSettings({ variables, configuration }: { variables: Config; configuration: Config }) {
  const groups = [
    { title: 'Match formula, schedules and eligibility', keys: ['employer_match_enabled', 'active_match_formula', 'match_cap_percent', 'employer_match_max_deferral_rate', 'match_tiers', 'tenure_match_tiers', 'tenure_graded_bands', 'employer_match_graded_schedule', 'points_match_tiers', 'employer_match'] },
    { title: 'Core formula, schedules and eligibility', keys: Object.keys(variables).filter(key => /^(employer_core|core_(minimum|require|allow))/.test(key)) },
    { title: 'Enrollment, response parameters and caps', keys: Object.keys(variables).filter(key => /deferral_match_response|deferral_escalation|enrollment.*(cutoff|window)|^(eligibility_waiting_period_days|minimum_age|new_hire_ineligible_pct)$/.test(key)) },
  ];
  return <div className="space-y-3">
    {matchRuleSummary(variables) && <p className="text-sm border border-info-border bg-info-surface p-3 rounded">{matchRuleSummary(variables)}</p>}
    {groups.map(group => <div key={group.title} className="border border-border rounded p-3"><h4 className="font-medium text-sm">{group.title}</h4><dl className="space-y-1 mt-2 text-sm">{group.keys.filter(key => key in variables).map(key => <div key={key}><dt className="inline text-ink-muted capitalize">{key === 'employer_match' ? 'Match eligibility' : labelFor(key)}: </dt><dd className="inline break-words">{formatActiveSetting(key, variables[key])}</dd></div>)}</dl></div>)}
    {['promotion_hazard', 'promotion_hazards', 'bands', 'plan_designs', 'plan_design_assignment'].filter(key => key in configuration).map(key => <div key={key} className="border border-border rounded p-3 text-sm"><h4 className="font-medium capitalize">{labelFor(key)}</h4><p className="mt-2 break-words">{describeSettings(redactReviewValue(configuration[key], key))}</p></div>)}
  </div>;
}

function ChangesTable({ changes, engine = false }: { changes: ReturnType<typeof reviewChanges>; engine?: boolean }) {
  return changes.length ? <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left"><th className="p-2">Setting</th><th className="p-2">Saved</th><th className="p-2">Draft</th></tr></thead>
    <tbody>{changes.map(change => <tr key={change.key} className="border-t border-border align-top"><th className="p-2 text-left font-normal break-words">{eligibilityField(change.key)?.[1] ?? labelFor(change.key)} <span className="text-xs text-info-ink">Changed</span></th><td className="p-2 break-words">{engine ? formatVariable(change.key, change.before) : formatDraftValue(change.key, change.before)}</td><td className="p-2 break-words">{engine ? formatVariable(change.key, change.after) : formatDraftValue(change.key, change.after)}</td></tr>)}</tbody>
  </table></div> : <p className="text-sm text-ink-muted">No changes to saved values.</p>;
}

export function formatPreviewError(cause: unknown): string {
  if (cause && typeof cause === 'object' && 'status' in cause && cause.status === 422 && 'detail' in cause && typeof cause.detail === 'string') {
    try {
      const detail: unknown = JSON.parse(cause.detail);
      if (detail && typeof detail === 'object' && 'errors' in detail && Array.isArray(detail.errors)) {
        const fields = detail.errors.map((error: unknown) => {
          if (!error || typeof error !== 'object' || !('field' in error) || !('message' in error)) return null;
          return `${String(error.field)}: ${String(error.message)}`;
        }).filter(Boolean);
        if (fields.length) return fields.join('\n');
      }
    } catch { /* Other API errors retain their original message. */ }
  }
  return cause instanceof Error ? cause.message : 'Unable to resolve configuration';
}

export function EffectiveConfigReview({ review, stale, saving, onClose, onSave, onEdit }: {
  review: ConfigurationReviewDraft; stale: boolean; saving: boolean;
  onClose: () => void; onSave: () => Promise<boolean>; onEdit: (section: string) => void;
}) {
  const [resolved, setResolved] = useState<{ before: ConfigPreview | null; after: ConfigPreview } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState(false);
  const [savingLocally, setSavingLocally] = useState(false);
  const savePending = useRef(false);
  const panel = useRef<HTMLDivElement>(null);
  const busy = saving || savingLocally;
  useEffect(() => {
    let current = true;
    const target = review.scenarioId ? 'scenario' : 'workspace';
    Promise.allSettled([
      previewConfiguration(review.workspaceId, review.saved, target),
      previewConfiguration(review.workspaceId, review.draft, target),
    ]).then(([before, after]) => {
      if (after.status === 'rejected') throw after.reason;
      if (current) setResolved({ before: before.status === 'fulfilled' ? before.value : null, after: after.value });
    })
      .catch(cause => { if (current) setError(formatPreviewError(cause)); });
    return () => { current = false; };
  }, [review]);
  useEffect(() => {
    panel.current?.focus();
  }, []);

  const save = async () => {
    if (!resolved || error || stale || busy || savePending.current) return;
    savePending.current = true; setSavingLocally(true); setSaveError(false);
    try { if (!await onSave()) setSaveError(true); }
    finally { savePending.current = false; setSavingLocally(false); }
  };
  const variables = resolved?.after.engine_variables ?? {};
  const effectiveNewHire = asConfig(resolved?.after.configuration.new_hire ?? review.draft.new_hire);
  const inactive = ['strategy', 'target_percentile', 'compensation_variance_percent', 'level_distribution_mode', 'level_distribution', 'level_market_adjustments']
    .filter(key => key in effectiveNewHire);
  const engineChanges = resolved?.before ? eligibilityReviewChanges(resolved.before.engine_variables, variables, resolved.before.engine_variables, variables, true) : [];
  const draftChanges = resolved?.before ? eligibilityReviewChanges(review.saved, review.draft, resolved.before.engine_variables, variables) : reviewChanges(review.saved, review.draft);

  return <div className="fixed inset-0 z-50 bg-black/40 flex justify-end" onKeyDown={event => {
    if (event.key === 'Escape' && !busy) { event.preventDefault(); onClose(); }
    if (event.key !== 'Tab') return;
    const focusable = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), summary, [tabindex="0"]') ?? [])
      .filter(element => element.getClientRects().length > 0);
    if (!focusable?.length) return;
    const first = focusable[0]; const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || document.activeElement === panel.current)) { event.preventDefault(); first.focus(); }
  }}>
    <div ref={panel} role="dialog" aria-modal="true" aria-labelledby="configuration-review-title" tabIndex={-1} className="w-full max-w-3xl h-full bg-surface-raised text-ink flex flex-col shadow-xl focus:outline-none">
      <div className="p-5 border-b border-border"><h2 id="configuration-review-title" className="text-xl font-bold">Review configuration</h2><p className="text-sm text-ink-muted mt-1">Saving to {review.scenarioId ? 'scenario' : 'workspace'}: <strong>{review.targetName}</strong></p></div>
      <div className="flex-1 overflow-y-auto p-5 space-y-6">
        {stale && <p role="alert" className="text-danger-ink">The draft or target changed. Return to editing and review the current configuration.</p>}
        {error && <div role="alert" className="rounded border border-danger-border bg-danger-surface p-3 text-danger-ink"><h3 className="font-semibold">Configuration could not be resolved</h3><p className="text-sm whitespace-pre-wrap">{error}</p><p className="text-sm">Return to editing to correct the inputs. Nothing has been saved.</p></div>}
        {!resolved && !error && <p role="status" className="text-sm text-ink-muted">Resolving saved and draft engine settings…</p>}
        <section><h3 className="font-semibold mb-2">Changes</h3><ChangesTable changes={draftChanges} /></section>
        {resolved && <>
          <section><h3 className="font-semibold mb-2">Indirect effects in engine settings</h3><p className="text-xs text-ink-muted mb-2">Canonical engine variables after production configuration normalization. Rates are displayed as percentages.</p>{resolved.before ? <ChangesTable changes={engineChanges} engine /> : <p role="status" className="text-sm text-warning-ink">The saved configuration could not be resolved, so an engine comparison is unavailable. The corrected draft has been validated and can be saved. Saved-to-draft changes remain visible above.</p>}</section>
          <section><h3 className="font-semibold mb-2">Effective assumptions</h3><p className="text-xs text-ink-muted mb-3">Resolved by the same configuration loader and variable export used for simulation. {resolved.after.scope}</p>
            {variables.easy_enroll_enabled === true && <p className="mb-3 text-xs text-ink-muted">Easy Enroll members get automatic increases even when plan-wide automatic increases are off.</p>}
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">{summaryVariables.filter(key => key in variables).map(key => <div key={key} className="border border-border rounded p-2"><dt className="text-ink-muted capitalize">{labelFor(key)}</dt><dd className="font-medium break-all">{formatVariable(key, variables[key])}{inactiveVariable(key, variables) && <span className="block mt-1 text-xs font-normal text-ink-muted">{inactiveVariable(key, variables)}</span>}</dd></div>)}</dl>
            <p className="text-sm mt-3">Voluntary enrollment: {'voluntary_enrollment_rate' in variables ? formatVariable('voluntary_enrollment_rate', variables.voluntary_enrollment_rate) : 'Demographic model'}. New-hire opt-out: {'new_hire_opt_out_rate' in variables ? formatVariable('new_hire_opt_out_rate', variables.new_hire_opt_out_rate) : 'Demographic model'}{variables.auto_enrollment_enabled === false ? ' (inactive while automatic enrollment is off)' : ''}.</p>
          </section>
          <section><h3 className="font-semibold mb-2">Other active custom settings</h3><p className="text-sm text-ink-muted">Expand the complete resolved settings to inspect unchanged seed, promotion hazards, age and tenure bands, plan designs, eligibility exceptions, enrollment cutoffs, response parameters and caps. Presence in resolved configuration alone does not verify that an engine model consumes a setting.</p>
            <div className="mt-3"><ActiveSettings variables={variables} configuration={resolved.after.configuration} /></div>
            <details className="mt-2 border border-border rounded p-3"><summary className="cursor-pointer font-medium">Complete resolved configuration and engine variables</summary>
              <p className="text-xs text-ink-muted my-2">{review.scenarioId ? 'Scenario override: keys explicitly stored in this draft. Inherited: remaining workspace or engine defaults.' : 'Workspace configuration with engine defaults.'} Paths and sensitive values are hidden.</p>
              <div className="space-y-2">{Object.entries(resolved.after.configuration).map(([key, value]) => <details key={key} className="border-t border-border pt-2"><summary className="cursor-pointer capitalize">{labelFor(key)} <span className="text-xs text-ink-muted">{review.scenarioId ? (key in review.draft ? 'Scenario override / inherited nested values' : 'Inherited') : 'Workspace / engine default'}</span></summary><pre className="text-xs whitespace-pre-wrap break-all mt-2">{JSON.stringify(redactReviewValue(value, key), null, 2)}</pre></details>)}</div>
              <details className="mt-3 border-t border-border pt-2"><summary className="cursor-pointer font-medium">All exported engine variables</summary><pre className="text-xs whitespace-pre-wrap break-all mt-2">{JSON.stringify(redactReviewValue(variables), null, 2)}</pre></details>
            </details>
          </section>
        </>}
        <section><h3 className="font-semibold mb-2">Inactive saved settings</h3>
          {inactive.length ? <><p className="text-sm text-ink-muted">These retained new-hire settings, including inherited values, have no active engine mapping or consumer:</p><ul className="list-disc pl-5 text-sm">{inactive.map(key => <li key={key}>{labelFor(key)}: {showValue(redactReviewValue(effectiveNewHire[key], key))} <span className="text-xs">Inactive</span></li>)}</ul><button type="button" disabled={busy} onClick={() => onEdit('newhire')} className="text-sm text-info-ink underline mt-2">Review new-hire assumptions</button></> : <p className="text-sm text-ink-muted">No retained unsupported new-hire settings in this draft.</p>}
          {asConfig(review.draft.compensation).promotion_budget !== undefined || asConfig(review.draft.compensation).promotion_budget_percent !== undefined ? <p className="mt-2 text-sm text-ink-muted">Promotion budget is saved for reference and is not enforced by the engine.</p> : null}
        </section>
        <details className="border border-border rounded p-3"><summary className="cursor-pointer font-medium">Additional configured settings — mapping unverified</summary><p className="text-xs text-ink-muted my-2">All preserved draft settings, including legacy and unknown keys. Unsupported and unmapped settings do not imply an effect on outputs. Paths and sensitive fields are hidden.</p><pre className="text-xs whitespace-pre-wrap break-all">{JSON.stringify(redactReviewValue(review.draft), null, 2)}</pre></details>
        <section><h3 className="font-semibold mb-2">Items requiring attention</h3><p className="text-sm text-ink-muted">Suggestions require explicit application in their editor. Review does not calculate or apply suggestions. A changed-input suggestion must be recalculated before applying.</p>
          <button type="button" disabled={busy} onClick={() => onEdit('compensation')} className="text-sm text-info-ink underline mt-2">Review compensation inputs and nested override limitations</button>
        </section>
        {saveError && <p role="alert" className="text-danger-ink text-sm">Save failed or the reviewed draft changed. Your edits are preserved. Return to editing for details.</p>}
      </div>
      <div className="p-5 border-t border-border flex flex-wrap justify-end gap-3">
        <button type="button" onClick={onClose} disabled={busy} className="px-4 py-2 border border-border rounded-lg text-sm disabled:opacity-50">Back to editing</button>
        <button type="button" onClick={save} disabled={!resolved || !!error || stale || busy} className="px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg text-sm disabled:opacity-50">{busy ? 'Saving…' : review.runAfterSave ? 'Save configuration & Run' : 'Save configuration'}</button>
      </div>
    </div>
  </div>;
}
