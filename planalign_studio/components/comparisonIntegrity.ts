import type {
  ComparisonIntegrityResponse,
  ConfigDelta,
  IntegrityReason,
  ScenarioIntegrity,
  UnevaluatedCheck,
} from '../services/api';

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
}

const MAX_SETTING_DETAILS = 4;

const SETTING_LABELS: Record<string, string> = {
  'simulation.target_growth_rate': 'Headcount growth',
  'workforce.total_termination_rate': 'Turnover',
  'workforce.new_hire_termination_rate': 'New-hire turnover',
  'workforce.part_time_new_hire_pct': 'Part-time share of new hires',
  'compensation.target_compensation_growth_percent': 'Pay growth target',
  'compensation.merit_budget_percent': 'Merit budget',
  'compensation.cola_rate_percent': 'Cost-of-living raise',
  'compensation.promotion_budget_percent': 'Promotion budget',
  'compensation.raise_budget_percent': 'Raise budget',
  'new_hire.salary_growth_rate': 'New-hire pay growth',
  'new_hire.target_percentile': 'New-hire pay percentile',
  'dc_plan.opt_out_rate_target': 'Auto-enrollment opt-out rate',
  'dc_plan.voluntary_enrollment_rate': 'Voluntary enrollment rate',
  'dc_plan.match_magnet_probability': 'Share who defer to the match maximum',
};

const CHECK_WORDS: Record<UnevaluatedCheck['check'], string> = {
  census: 'census',
  seed: 'random seed',
  years: 'simulated years',
  engine_version: 'engine version',
  config: 'settings',
};

const FALLBACK_AREA = 'other plan settings';
const PLAN_AREAS: ReadonlyArray<readonly [RegExp, string]> = [
  [/^(dc_plan\.(match(?!_magnet)|tenure_match|points_match|tenure_graded)|employer_match)/, 'the employer match'],
  [/^(dc_plan\.core|employer_core_contribution)/, 'the employer core contribution'],
  [/^(dc_plan\.(auto_enroll|default_deferral|reenrollment_sweep)|enrollment\.auto_enrollment)/, 'auto-enrollment'],
  [/^(dc_plan\.(auto_escalation|escalation)|deferral_auto_escalation)/, 'auto-escalation'],
  [/^(dc_plan\.easy_enroll|easy_enroll)/, 'Easy Enroll'],
  [/(eligibility|plan_year)/, 'eligibility'],
];

export function settingLabel(path: string): string {
  if (SETTING_LABELS[path]) return SETTING_LABELS[path];
  const key = path.split('.').at(-1) ?? path;
  return key.replaceAll('_', ' ').replace(/^./, letter => letter.toUpperCase());
}

function trimNumber(value: number): string {
  return String(Number(value.toFixed(2)));
}

/** A config value in plain words, or null when it can't be shown inline. */
export function formatSetting(path: string, value: unknown): string | null {
  if (value === null || value === undefined) return 'not set';
  if (typeof value === 'boolean') return value ? 'on' : 'off';
  if (typeof value === 'string') return value;
  if (typeof value !== 'number') return null;
  const key = path.split('.').at(-1) ?? path;
  if (key.endsWith('_percent')) return `${trimNumber(value)}%`;
  if (/(_rate|_pct|_probability)$/.test(key) && Math.abs(value) <= 1) {
    return `${trimNumber(value * 100)}%`;
  }
  return trimNumber(value);
}

function plain(value: unknown): string {
  return value === null || value === undefined ? 'not recorded' : String(value);
}

export function describeReason(reason: IntegrityReason): string {
  const pair = `${plain(reason.anchor_value)} vs ${plain(reason.scenario_value)}`;
  switch (reason.code) {
    case 'census_differs':
      return reason.anchor_value && reason.scenario_value && reason.anchor_value !== reason.scenario_value
        ? `Census: ${pair}`
        : 'Census: same file name, different data';
    case 'seed_differs':
      return `Random seed: ${pair}`;
    case 'years_differ':
      return `Simulated years: ${pair}`;
    case 'engine_version_differs':
      return `Engine version: ${pair}`;
    default:
      return describeSetting(reason);
  }
}

function describeSetting(reason: IntegrityReason): string {
  const path = reason.path ?? '';
  const label = settingLabel(path);
  const a = formatSetting(path, reason.anchor_value);
  const b = formatSetting(path, reason.scenario_value);
  return a === null || b === null ? `${label} differs` : `${label}: ${a} vs ${b}`;
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
  return reason.code === 'edited_since_run'
    ? `${who} was edited after its result ran. This compares the settings it ran with.`
    : `${who}'s result mixes rows from runs with different settings or seeds.`;
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

function breakingDetails(reasons: IntegrityReason[]): string[] {
  const breaking = reasons.filter(reason => reason.effect === 'breaks');
  const facts = breaking.filter(reason => reason.code !== 'config_differs').map(describeReason);
  const settings = breaking.filter(reason => reason.code === 'config_differs').map(describeReason);
  const shown = settings.slice(0, MAX_SETTING_DETAILS);
  const hidden = settings.length - shown.length;
  return [...facts, ...shown, ...(hidden > 0 ? [`and ${hidden} more ${hidden === 1 ? 'setting' : 'settings'}`] : [])];
}

const TONES: Record<ScenarioIntegrity['verdict'], IntegrityTone> = {
  like_for_like: 'ok',
  not_like_for_like: 'warning',
  unknown: 'unknown',
};

export function summarizeIntegrity(result: ComparisonIntegrityResponse): IntegritySummary {
  const names: Record<string, string> = { [result.anchor_scenario_id]: result.anchor_scenario_name };
  result.scenarios.forEach(item => { names[item.scenario_id] = item.scenario_name; });
  const notesAbout = (scenarioId: string) => (item: ScenarioIntegrity) => item.reasons
    .filter(reason => reason.effect === 'note' && reason.scenario_id === scenarioId)
    .map(reason => describeNote(reason, names));
  const anchorNotes = result.scenarios.length > 0 ? notesAbout(result.anchor_scenario_id)(result.scenarios[0]) : [];
  return {
    anchorNotes,
    lines: result.scenarios.map(item => ({
      scenarioId: item.scenario_id,
      tone: TONES[item.verdict],
      headline: headline(item, result.anchor_scenario_name, names),
      details: breakingDetails(item.reasons),
      notes: notesAbout(item.scenario_id)(item),
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

/** The check a page asks for, or null when there is nothing to compare. */
export function integrityRequest(
  workspaceId: string | undefined,
  scenarioIds: string[],
  anchorId: string | undefined,
): IntegrityRequest | null {
  if (!workspaceId || !anchorId) return null;
  const ids = [...new Set([anchorId, ...scenarioIds.filter(Boolean)])];
  if (ids.length < 2) return null;
  return { workspaceId, anchorId, scenarioIds: ids, key: `${workspaceId}|${anchorId}|${ids.join(',')}` };
}
