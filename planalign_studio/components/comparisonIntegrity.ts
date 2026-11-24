import type {
  ComparisonIntegrityResponse,
  ConfigDelta,
  IntegrityReason,
  RunChange,
  RunChangesResponse,
  ScenarioIntegrity,
  UnevaluatedCheck,
} from '../services/api';
import { describeMinimumWage, minimumWageFromConfig } from './config/minimumWage';
import { acquisitionsFromConfig, listAcquisitions } from './config/acquisitions';

/** Plain-words copy for the like-for-like verdict (#1179, #1180). */

export type IntegrityTone = 'ok' | 'warning' | 'unknown';

export interface IntegrityLine {
  scenarioId: string;
  tone: IntegrityTone;
  headline: string;
  details: string[];
  notes: string[];
}

export interface IntegritySummary {
  lines: IntegrityLine[];
  /** Notes about the anchor itself, shown once rather than on every line. */
  anchorNotes: string[];
  /** Set only when every result ran on the same known engine version. */
  versionNote: string | null;
}

const MAX_SETTING_DETAILS = 4;

const SETTING_LABELS: Record<string, string> = {
  'simulation.target_growth_rate': 'Headcount growth',
  'workforce.total_termination_rate': 'Turnover',
  'workforce.new_hire_termination_rate': 'New-hire turnover',
  'workforce.part_time_new_hire_pct': 'Part-time share of new hires',
  'workforce.acquisitions': 'Acquisitions',
  'compensation.target_compensation_growth_percent': 'Pay growth target',
  'compensation.merit_budget_percent': 'Merit budget',
  'compensation.cola_rate_percent': 'Cost-of-living raise',
  'compensation.minimum_wage': 'Minimum wage',
  'compensation.promotion_budget_percent': 'Promotion budget',
  'compensation.raise_budget_percent': 'Raise budget',
  'new_hire.salary_growth_rate': 'New-hire pay growth',
  'new_hire.target_percentile': 'New-hire pay percentile',
  'dc_plan.opt_out_rate_target': 'Auto-enrollment opt-out rate',
  'dc_plan.voluntary_enrollment_rate': 'Voluntary enrollment rate',
  'dc_plan.match_magnet_probability': 'Share who defer to the match maximum',
  // Studio's DC plan form, in the form's own words (#1236).
  'dc_plan.eligibility_months': 'Eligibility waiting period',
  'dc_plan.auto_enroll': 'Automatic enrollment',
  'dc_plan.auto_enroll_scope': 'Enrollment scope',
  'dc_plan.auto_enroll_hire_date_cutoff': 'Auto-enrollment hire date cutoff',
  'dc_plan.default_deferral_percent': 'Default deferral rate',
  'dc_plan.new_hire_opt_out_rate': 'New-hire opt-out rate',
  'dc_plan.deferral_spread_max_lift': 'Max upward spread',
  'dc_plan.match_enabled': 'Employer match',
  'dc_plan.match_status': 'Match calculation mode',
  'dc_plan.match_template': 'Match template',
  'dc_plan.auto_escalation': 'Automatic contribution increases',
  'dc_plan.escalation_mode': 'Who gets automatic increases',
  'dc_plan.escalation_rate_percent': 'Annual automatic increase',
  'dc_plan.escalation_hire_date_cutoff': 'Automatic increase hire date cutoff',
  'dc_plan.easy_enroll_enabled': 'Easy Enroll',
  // Also labels Studio's dc_plan.deferral_match_response.* copy (MIRRORS).
  'deferral_match_response.enabled': 'First-year match response',
  'deferral_match_response.upward_participation_rate': 'Increase deferral response',
  'deferral_match_response.downward_enabled': 'Allow deferral decreases',
  'deferral_match_response.downward_participation_rate': 'Decrease deferral response',
  // Also labels Studio's dc_plan.core_* copies (CORE_COPIES).
  'employer_core_contribution.enabled': 'Employer core contribution',
  'employer_core_contribution.status': 'Core contribution type',
  'employer_core_contribution.contribution_rate': 'Core rate',
  'employer_core_contribution.graded_schedule': 'Core rates by service',
  'employer_core_contribution.points_schedule': 'Core rates by points',
  'employer_core_contribution.age_schedule': 'Core rates by age',
  'employer_core_contribution.eligibility.minimum_tenure_years': 'Core service requirement',
  'employer_core_contribution.eligibility.minimum_hours_annual': 'Core hours requirement',
  'employer_core_contribution.eligibility.require_active_at_year_end': 'Core requires year-end employment',
  'employer_core_contribution.eligibility.allow_new_hires': 'Core for new hires',
  'employer_core_contribution.eligibility.allow_terminated_new_hires': 'Core for new hires who leave',
  'employer_core_contribution.eligibility.allow_experienced_terminations': 'Core for other leavers',
  'employer_core_contribution.integration.enabled': 'Social Security integration',
  'employer_core_contribution.integration.level_mode': 'Integration level',
  'employer_core_contribution.integration.level_value': 'Integration level amount',
  'employer_core_contribution.integration.disparity_rate': 'Integration disparity rate',
  // Engine sections.
  'employer_match.active_formula': 'Employer match formula',
  'enrollment.auto_enrollment.enabled': 'Automatic enrollment',
  'plan_eligibility.minimum_age': 'Minimum eligibility age',
  'plan_eligibility.minimum_tenure_years': 'Eligibility service requirement',
};

const CHECK_WORDS: Record<UnevaluatedCheck['check'], string> = {
  census: 'census',
  seed: 'random seed',
  years: 'simulated years',
  engine_version: 'engine version',
  seed_files: 'model seed tables',
  config: 'settings',
};

/**
/** Pay settings the engine reads as compensation.<name> (decimal) and Studio saves as <name>_percent. */
export const COMPENSATION_PERCENT_FIELDS = [
  'cola_rate',
  'merit_budget',
  'raise_budget',
  'raise_coverage',
  'promotion_increase',
  'promotion_budget',
  'promotion_distribution_range',
] as const;

/**
 * Studio's dc_plan.core_* settings and the employer_core_contribution keys a
 * run's saved config derives from them (#1321): [Studio key, engine path, scale].
 * Keep in step with planalign_api/services/setting_mirrors.py.
 */
const CORE_COPIES: ReadonlyArray<readonly [string, string, number?]> = [
  ['core_enabled', 'enabled'],
  ['core_status', 'status'],
  ['core_contribution_rate_percent', 'contribution_rate', 0.01],
  ['core_graded_schedule', 'graded_schedule'],
  ['core_points_schedule', 'points_schedule'],
  ['core_age_schedule', 'age_schedule'],
  ['core_min_tenure_years', 'eligibility.minimum_tenure_years'],
  ['core_min_hours_annual', 'eligibility.minimum_hours_annual'],
  ['core_require_year_end_active', 'eligibility.require_active_at_year_end'],
  ['core_allow_new_hires', 'eligibility.allow_new_hires'],
  ['core_allow_terminated_new_hires', 'eligibility.allow_terminated_new_hires'],
  ['core_allow_experienced_terminations', 'eligibility.allow_experienced_terminations'],
  ['core_integration_enabled', 'integration.enabled'],
  ['core_integration_level_mode', 'integration.level_mode'],
  ['core_integration_level_value', 'integration.level_value'],
  ['core_integration_disparity_rate', 'integration.disparity_rate'],
  ['core_integration_disparity_rate_percent', 'integration.disparity_rate', 0.01],
];

/**
 * Settings recorded twice under different paths (#1178). Each maps to one
 * canonical path so both copies render identical text and collapse into one
 * line. `scale` converts the value to the canonical path's units.
 * Keep in step with planalign_api/services/setting_mirrors.py.
 */
const MIRRORS: ReadonlyArray<{ pattern: RegExp; replace: string; scale?: number }> = [
  // The engine reads compensation.<name>; Studio writes <name>_percent.
  {
    pattern: new RegExp(`^compensation\\.(${COMPENSATION_PERCENT_FIELDS.join('|')})$`),
    replace: 'compensation.$1_percent',
    scale: 100,
  },
  // Studio's DC plan form copy of the engine section.
  { pattern: /^dc_plan\.deferral_match_response\./, replace: 'deferral_match_response.' },
  ...CORE_COPIES.map(([studioKey, enginePath, scale]) => ({
    pattern: new RegExp(`^dc_plan\\.${studioKey}$`),
    replace: `employer_core_contribution.${enginePath}`,
    scale,
  })),
];

/** Last path segments too vague to label a setting on their own. */
const GENERIC_KEYS = new Set(['enabled', 'rate', 'mode', 'value', 'status', 'type', 'amount', 'scope']);
/** Top-level sections whose keys name the setting on their own (dc_plan.core_enabled). */
const SELF_NAMED_SECTIONS = new Set(['simulation', 'setup', 'workforce', 'compensation', 'new_hire', 'dc_plan', 'advanced']);
/** Unit suffixes the formatted value already shows. */
const UNIT_SUFFIX = /_(percent|pct)$/;

const MAX_SEED_FILES = 3;

interface CanonicalSetting { path: string; value: unknown }

/** One path (and units) for settings recorded under two paths. */
export function canonicalSetting(path: string, value: unknown): CanonicalSetting {
  const mirror = MIRRORS.find(({ pattern }) => pattern.test(path));
  if (!mirror) return { path, value };
  const scaled = mirror.scale && typeof value === 'number' ? value * mirror.scale : value;
  return { path: path.replace(mirror.pattern, mirror.replace), value: scaled };
}

function words(segment: string): string {
  return segment.replaceAll('_', ' ');
}

function unique(items: string[]): string[] {
  return [...new Set(items)];
}

function withMore(shown: string[], total: number, noun: string): string[] {
  const hidden = total - shown.length;
  return hidden > 0 ? [...shown, `and ${hidden} more ${hidden === 1 ? noun : `${noun}s`}`] : shown;
}

const FALLBACK_AREA = 'other plan settings';
const PLAN_AREAS: ReadonlyArray<readonly [RegExp, string]> = [
  [/^(dc_plan\.(match(?!_magnet)|tenure_match|points_match|tenure_graded)|employer_match)/, 'the employer match'],
  [/^(dc_plan\.core|employer_core_contribution)/, 'the employer core contribution'],
  [/^(dc_plan\.(auto_enroll|default_deferral|reenrollment_sweep)|enrollment\.auto_enrollment)/, 'auto-enrollment'],
  [/^(dc_plan\.(auto_escalation|escalation)|deferral_auto_escalation)/, 'auto-escalation'],
  [/^(dc_plan\.easy_enroll|easy_enroll)/, 'Easy Enroll'],
  [/(eligibility|plan_year)/, 'eligibility'],
];

export function settingLabel(rawPath: string): string {
  const { path } = canonicalSetting(rawPath, null);
  if (SETTING_LABELS[path]) return SETTING_LABELS[path];
  const segments = path.split('.');
  const key = segments.at(-1) ?? path;
  const parent = segments.at(-2);
  const name = words(key.replace(UNIT_SUFFIX, ''));
  // A key inside a nested or engine section reads with its parent ("Integration
  // disparity rate", not "Disparity rate"); so does a vague one anywhere.
  const withParent = parent !== undefined && (GENERIC_KEYS.has(key) || !SELF_NAMED_SECTIONS.has(parent));
  const label = withParent ? joinParent(words(parent), name) : name;
  return label.replace(/^./, letter => letter.toUpperCase());
}

/** "Employer core contribution rate", not "... contribution contribution rate". */
function joinParent(parent: string, name: string): string {
  const overlap = `${parent.split(' ').at(-1)} `;
  return `${parent} ${name.startsWith(overlap) ? name.slice(overlap.length) : name}`;
}

function trimNumber(value: number, digits = 2): string {
  return String(Number(value.toFixed(digits)));
}

/** `_percent` keys Studio saves as decimals (0.75 = 75%), not whole percents. */
const DECIMAL_PERCENT_KEYS = new Set(['max_voluntary_deferral_percent', 'match_cap_percent']);
/**
 * Rate keys saved as whole percents (2 = 2%): the points-based core rate before
 * the service minimum, in Studio's dc_plan copy and the engine section. dbt
 * divides both by 100.
 */
const WHOLE_PERCENT_KEYS = new Set(['core_points_pre_service_rate', 'points_pre_service_rate']);
/** Settings where no value means none to the engine. */
export const NONE_WHEN_UNSET = new Set(['compensation.minimum_wage', 'workforce.acquisitions']);

type NumberUnit = 'whole_percent' | 'decimal_percent' | 'number';

/** One unit for every value given, so two sides of a difference never mix units. */
function numberUnit(path: string, values: number[]): NumberUnit {
  const key = path.split('.').at(-1) ?? path;
  if (DECIMAL_PERCENT_KEYS.has(key)) return 'decimal_percent';
  if (WHOLE_PERCENT_KEYS.has(key) || key.endsWith('_percent')) return 'whole_percent';
  // A rate is a decimal fraction only if every value could be one.
  const fractions = values.every(value => Math.abs(value) <= 1);
  return /(_rate|_pct|_probability)$/.test(key) && fractions ? 'decimal_percent' : 'number';
}

function formatNumber(value: number, unit: NumberUnit, digits = 2): string {
  if (unit === 'decimal_percent') return `${trimNumber(value * 100, digits)}%`;
  if (unit === 'whole_percent') return `${trimNumber(value, digits)}%`;
  return trimNumber(value, digits);
}

/** A config value in plain words, or null when it can't be shown inline. */
export function formatSetting(path: string, value: unknown): string | null {
  // One side without a minimum wage reads "none", never "not set".
  if (path === 'compensation.minimum_wage') return describeMinimumWage(minimumWageFromConfig(value) ?? []);
  // One side without acquisitions reads "none", never "not set".
  if (path === 'workforce.acquisitions') return listAcquisitions(acquisitionsFromConfig(value) ?? []);
  if (value === null || value === undefined) return 'not set';
  if (typeof value === 'boolean') return value ? 'on' : 'off';
  if (typeof value === 'string') return value;
  if (typeof value !== 'number') return null;
  return formatNumber(value, numberUnit(path, [value]));
}

const MAX_DIGITS = 12;

/**
 * Two numbers for one setting in a shared unit, with enough decimals that
 * different values never read the same and a nonzero value never reads 0.
 */
export function formatNumberPair(path: string, a: number, b: number): [string, string] {
  const unit = numberUnit(path, [a, b]);
  const unclear = (digits: number, texts: [string, string]) => digits < MAX_DIGITS && (
    (a !== b && texts[0] === texts[1]) || [a, b].some((value, index) => value !== 0 && Number.parseFloat(texts[index]) === 0)
  );
  let digits = 2;
  let texts: [string, string] = [formatNumber(a, unit, digits), formatNumber(b, unit, digits)];
  while (unclear(digits, texts)) {
    digits += 1;
    texts = [formatNumber(a, unit, digits), formatNumber(b, unit, digits)];
  }
  return texts;
}

function plain(value: unknown): string {
  return value === null || value === undefined ? 'not recorded' : String(value);
}

/** `joiner` separates the two values: " vs " across scenarios, " → " across runs. */
export function describeReason(reason: IntegrityReason, joiner = ' vs '): string {
  const pair = `${plain(reason.anchor_value)}${joiner}${plain(reason.scenario_value)}`;
  switch (reason.code) {
    case 'census_differs':
      return describeCensus(reason, pair);
    case 'seed_files_differ':
      return describeSeedFiles(reason.files);
    case 'engine_build_differs':
      return reason.anchor_value && reason.scenario_value ? `Engine build differs: ${pair}` : 'Engine build differs';
    case 'seed_differs':
      return `Random seed: ${pair}`;
    case 'years_differ':
      return `Simulated years: ${pair}`;
    case 'engine_version_differs':
      return `Engine version: ${pair}`;
    default:
      return describeSetting(reason, joiner);
  }
}

function describeCensus(reason: IntegrityReason, pair: string): string {
  if (!reason.anchor_value || !reason.scenario_value) return 'Census data differs';
  return reason.anchor_value === reason.scenario_value ? 'Census: same file name, different data' : `Census: ${pair}`;
}

function describeSeedFiles(files: string[]): string {
  if (files.length === 0) return 'Model seed tables differ';
  const shown = files.slice(0, MAX_SEED_FILES);
  const hidden = files.length - shown.length;
  return `Model seed tables differ: ${shown.join(', ')}${hidden > 0 ? ` and ${hidden} more` : ''}`;
}

function describeSetting(reason: IntegrityReason, joiner: string): string {
  const anchor = canonicalSetting(reason.path ?? '', reason.anchor_value);
  const scenario = canonicalSetting(reason.path ?? '', reason.scenario_value);
  const path = anchor.path;
  const label = settingLabel(path);
  const a = formatSetting(path, anchor.value);
  const b = formatSetting(path, scenario.value);
  if (a === null || b === null) return joiner === ' vs ' ? `${label} differs` : `${label} changed`;
  return `${label}: ${a}${joiner}${b}`;
}

function joinWords(words: string[]): string {
  if (words.length <= 1) return words.join('');
  return `${words.slice(0, -1).join(', ')} and ${words.at(-1)}`;
}

export function planDesignSummary(differences: ConfigDelta[]): string {
  if (differences.length === 0) return 'No settings differ.';
  const areas = [...new Set(differences.map(delta =>
    PLAN_AREAS.find(([pattern]) => pattern.test(delta.path))?.[1] ?? FALLBACK_AREA
  ))];
  if (areas.length === 1 && areas[0] === FALLBACK_AREA) return 'Only plan design settings differ.';
  const verb = areas.length === 1 ? 'differs' : 'differ';
  return `Only ${joinWords(areas)} ${verb}.`;
}

function unknownCause(checks: UnevaluatedCheck[], names: Record<string, string>): string {
  const byScenario = new Map<string, UnevaluatedCheck[]>();
  checks.forEach(check => byScenario.set(check.scenario_id, [...(byScenario.get(check.scenario_id) ?? []), check]));
  return [...byScenario.entries()].map(([scenarioId, missing]) => {
    const who = names[scenarioId] ?? 'One scenario';
    if (missing.some(check => check.cause === 'no_run_record')) {
      return `${who}'s result has no run record`;
    }
    return `${who}'s run did not record its ${joinWords(missing.map(check => CHECK_WORDS[check.check]))}`;
  }).join('; ');
}

function describeNote(reason: IntegrityReason, names: Record<string, string>): string {
  const who = names[reason.scenario_id ?? ''] ?? 'A scenario';
  switch (reason.code) {
    case 'edited_since_run':
      return `${who} was edited after its result ran. This compares the settings it ran with.`;
    case 'changed_since_previous_run':
      return `${who}'s assumptions or inputs changed since its previous run.`;
    default:
      return `${who}'s result mixes rows from runs with different settings or seeds.`;
  }
}

function headline(item: ScenarioIntegrity, anchorName: string, names: Record<string, string>): string {
  if (item.verdict === 'like_for_like') {
    return `${item.scenario_name} is like-for-like with ${anchorName}. ${planDesignSummary(item.plan_design_differences)}`;
  }
  if (item.verdict === 'not_like_for_like') {
    return `${item.scenario_name} is not like-for-like with ${anchorName}: part of the difference is not the plan design.`;
  }
  return `Can't tell whether ${item.scenario_name} is like-for-like with ${anchorName}: ${unknownCause(item.unevaluated, names)}.`;
}

function breakingDetails(reasons: IntegrityReason[], names: Record<string, string>): string[] {
  const breaking = reasons.filter(reason => reason.effect === 'breaks');
  const facts = breaking
    .filter(reason => reason.code !== 'config_differs')
    .map(reason => (reason.code === 'mixed_generation' ? describeNote(reason, names) : describeReason(reason)));
  // Mirrored settings describe identically; count each line once.
  const settings = unique(breaking.filter(reason => reason.code === 'config_differs').map(reason => describeReason(reason)));
  const shown = settings.slice(0, MAX_SETTING_DETAILS);
  return unique([...facts, ...withMore(shown, settings.length, 'setting')]);
}

/** What couldn't be checked, when a found difference already settles the verdict. */
function uncheckedNote(item: ScenarioIntegrity, names: Record<string, string>): string[] {
  if (item.verdict !== 'not_like_for_like' || item.unevaluated.length === 0) return [];
  return [`Not everything could be checked: ${unknownCause(item.unevaluated, names)}.`];
}

const TONES: Record<ScenarioIntegrity['verdict'], IntegrityTone> = {
  like_for_like: 'ok',
  not_like_for_like: 'warning',
  unknown: 'unknown',
};

/** "All results ran on engine version X." only when that is known for every result. */
export function sharedVersionNote(result: ComparisonIntegrityResponse): string | null {
  const version = result.anchor_engine_version;
  if (!version || result.scenarios.length === 0) return null;
  const same = result.scenarios.every(item => item.engine_version === version);
  return same ? `All results ran on engine version ${version}.` : null;
}

export function summarizeIntegrity(result: ComparisonIntegrityResponse): IntegritySummary {
  const names: Record<string, string> = { [result.anchor_scenario_id]: result.anchor_scenario_name };
  result.scenarios.forEach(item => { names[item.scenario_id] = item.scenario_name; });
  const notesAbout = (scenarioId: string) => (item: ScenarioIntegrity) => unique(item.reasons
    .filter(reason => reason.effect === 'note' && reason.scenario_id === scenarioId)
    .map(reason => describeNote(reason, names)));
  const anchorNotes = result.scenarios.length > 0 ? notesAbout(result.anchor_scenario_id)(result.scenarios[0]) : [];
  return {
    anchorNotes,
    versionNote: sharedVersionNote(result),
    lines: result.scenarios.map(item => ({
      scenarioId: item.scenario_id,
      tone: TONES[item.verdict],
      headline: headline(item, result.anchor_scenario_name, names),
      details: breakingDetails(item.reasons, names),
      notes: [...notesAbout(item.scenario_id)(item), ...uncheckedNote(item, names)],
    })),
  };
}

export interface IntegrityRequest {
  workspaceId: string;
  anchorId: string;
  /** Anchor first, then the others in page order, without repeats. */
  scenarioIds: string[];
  /** Changes whenever the selection or anchor does, so the banner refetches. */
  key: string;
}

/** The check a page asks for, or null when there is nothing to compare or the anchor is not selected. */
export function integrityRequest(
  workspaceId: string | undefined,
  scenarioIds: string[],
  anchorId: string | undefined,
): IntegrityRequest | null {
  if (!workspaceId || !anchorId || !scenarioIds.includes(anchorId)) return null;
  const ids = [...new Set([anchorId, ...scenarioIds.filter(Boolean)])];
  if (ids.length < 2) return null;
  return { workspaceId, anchorId, scenarioIds: ids, key: `${workspaceId}|${anchorId}|${ids.join(',')}` };
}

export interface RunChangesSummary {
  /** One sentence; the change list follows it when there is one. */
  headline: string;
  changes: string[];
  /** What one of the runs didn't record, so "no change" can't be claimed for it. */
  missing: string | null;
}

const MAX_RUN_CHANGES = 8;

/** A change since the previous run in plain words, previous value first. */
export function describeRunChange(change: RunChange): string {
  return describeReason({
    code: change.code,
    effect: 'breaks',
    anchor_value: change.previous_value,
    scenario_value: change.current_value,
    path: change.path,
    group: change.group,
    files: change.files,
    scenario_id: null,
  }, ' → ');
}

/** "Since the previous run" copy for Overview (#1186). */
export function summarizeRunChanges(result: RunChangesResponse): RunChangesSummary {
  if (!result.has_previous_run) return { headline: 'No previous run to compare.', changes: [], missing: null };
  const when = result.previous_run_at ? new Date(result.previous_run_at).toLocaleDateString() : null;
  const missing = result.unevaluated.length > 0
    ? `Couldn't compare the ${joinWords(result.unevaluated.map(check => CHECK_WORDS[check]))}: one of the runs didn't record it.`
    : null;
  if (result.changes.length === 0) {
    const headline = missing ? 'No recorded settings changed since the previous run' : 'Same settings as the previous run';
    return { headline: when ? `${headline} (${when}).` : `${headline}.`, changes: [], missing };
  }
  // Mirrored settings describe identically; count each line once.
  const described = unique(result.changes.map(describeRunChange));
  return {
    headline: when ? `Since the previous run (${when}):` : 'Since the previous run:',
    changes: withMore(described.slice(0, MAX_RUN_CHANGES), described.length, 'setting'),
    missing,
  };
}
