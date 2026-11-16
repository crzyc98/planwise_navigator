/**
 * The one derivation of the Cost Comparison tables.
 *
 * The Multi-Year Cost and Compensation matrices render these figures, the
 * copy-to-clipboard text is built from them, and the summary workbook is the
 * same object posted to the API (`toSummaryExportRequest`). The server adds
 * names and run provenance but derives nothing, so a figure in the workbook is
 * the figure on the page by construction.
 *
 * A null figure is unavailable, never zero; `notes[field]` says why.
 */
import type {
  CostSummaryExportRequest,
  CostSummaryFiguresPayload,
  CostSummaryView,
  ContributionYearSummary,
  DCPlanAnalytics,
  DCPlanCohort,
  EmployerCostOffsetRow,
  GrandfatheredCostComparisonResponse,
} from '../services/api';

export type SummaryField = Exclude<keyof CostSummaryFiguresPayload, 'notes'>;
export type SummaryNotes = Partial<Record<SummaryField, string>>;
export type SummaryFigures = Record<SummaryField, number | null> & { notes: SummaryNotes };

export interface SummaryYear extends SummaryFigures {
  year: number;
  /** False when the selected cohort has no employees this year. */
  has_data: boolean;
}

export interface ScenarioSummary {
  scenario_id: string;
  is_anchor: boolean;
  years: SummaryYear[];
  totals: SummaryFigures;
}

export interface GrandfatherInput {
  data: GrandfatheredCostComparisonResponse | null;
  loading: boolean;
  error: string | null;
}

export interface NetInput {
  offsets: Map<string, Map<number, EmployerCostOffsetRow>>;
  policyReducesCost: boolean;
}

export interface CostSummaryInputs {
  analytics: DCPlanAnalytics[];
  /** Display order: anchor first. */
  scenarioIds: string[];
  anchorId: string;
  years: number[];
  cohort: DCPlanCohort;
  /** Null unless existing employees are grandfathered. */
  grandfather: GrandfatherInput | null;
  /** Null in the gross view, and until forfeiture offsets have loaded. */
  net: NetInput | null;
  /** Match/core split is shown. */
  split: boolean;
}

export const ANCHOR_NOTE = 'This is the anchor scenario.';
export const NO_OFFSET_NOTE = 'No forfeiture projection for this year';
const NO_ANCHOR_NOTE = 'The anchor has no figure to compare with.';

const FIELDS: SummaryField[] = [
  'employer_cost', 'employer_cost_vs_anchor', 'cost_pct_of_capped_pay', 'cost_pct_vs_anchor_pp',
  'employer_match', 'employer_core', 'forfeiture_offset', 'reallocated_to_participants',
  'net_employer_cost', 'net_employer_cost_vs_anchor', 'total_compensation',
  'total_compensation_vs_anchor',
];

// ---------------------------------------------------------------------------
// Shared arithmetic
// ---------------------------------------------------------------------------

export function differenceFromAnchor(value: number | null, anchor: number | null): number | null {
  return value === null || anchor === null ? null : value - anchor;
}

/** Cost as a percent of capped pay; zero pay reads as 0%, as the page always has. */
export function costPctOfCappedPay(cost: number | null, cappedPay: number): number | null {
  if (cost === null) return null;
  return cappedPay > 0 ? cost / cappedPay * 100 : 0;
}

function emptyFigures(): SummaryFigures {
  const figures = { notes: {} } as SummaryFigures;
  FIELDS.forEach(field => { figures[field] = null; });
  return figures;
}

function set(figures: SummaryFigures, field: SummaryField, value: number | null, note: string): void {
  figures[field] = value;
  if (value === null) figures.notes[field] = note;
  else delete figures.notes[field];
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

// ---------------------------------------------------------------------------
// Per-year figures
// ---------------------------------------------------------------------------

/** The cost the page shows: gross, or the grandfathered splice when selected. */
export function displayedCost(
  scenarioId: string, yearData: ContributionYearSummary, grandfather: GrandfatherInput | null,
): { value: number | null; note: string } {
  if (!grandfather) return { value: yearData.total_employer_cost, note: '' };
  const row = grandfather.data?.scenarios.find(series => series.scenario_id === scenarioId)
    ?.years.find(item => item.year === yearData.year);
  if (row?.available) return { value: row.total_employer_cost ?? null, note: '' };
  if (grandfather.loading) return { value: null, note: 'Loading grandfathered employer cost.' };
  if (grandfather.error) {
    return { value: null, note: `Grandfathered employer cost request failed: ${grandfather.error}` };
  }
  return {
    value: null,
    note: row?.unavailable_reason ?? 'Grandfathered employer cost has not been loaded.',
  };
}

function setNetYear(figures: SummaryYear, scenarioId: string, net: NetInput): void {
  const row = net.offsets.get(scenarioId)?.get(figures.year) ?? null;
  const reason = row?.unavailable_reason ?? NO_OFFSET_NOTE;
  const applied = row?.basis_available ? (row.offset_amount ?? 0) : null;
  set(figures, 'forfeiture_offset', applied, reason);
  if (!net.policyReducesCost) {
    set(figures, 'reallocated_to_participants',
      row?.basis_available ? (row.participant_allocation ?? 0) : null, reason);
  }
  const cost = figures.employer_cost;
  const netCost = cost === null || applied === null ? null : cost - applied;
  const costNote = figures.has_data ? 'Employer cost is unavailable.' : 'No cost data for this year';
  set(figures, 'net_employer_cost', netCost, `Gross only — ${cost === null ? costNote : reason}`);
}

function yearFigures(
  analytics: DCPlanAnalytics, year: number, inputs: CostSummaryInputs,
): SummaryYear {
  const yearData = analytics.contribution_by_year.find(item => item.year === year);
  const figures: SummaryYear = { ...emptyFigures(), year, has_data: yearData !== undefined };
  if (!yearData) {
    const note = inputs.cohort !== 'all' ? 'No employees in cohort' : 'No cost data for this year';
    FIELDS.forEach(field => { figures.notes[field] = note; });
  } else {
    const cost = displayedCost(analytics.scenario_id, yearData, inputs.grandfather);
    set(figures, 'employer_cost', cost.value, cost.note);
    set(figures, 'cost_pct_of_capped_pay',
      costPctOfCappedPay(cost.value, yearData.total_capped_compensation), cost.note);
    figures.total_compensation = yearData.total_compensation;
    if (inputs.split) {
      figures.employer_match = yearData.total_employer_match;
      figures.employer_core = yearData.total_employer_core;
    }
  }
  if (inputs.net) setNetYear(figures, analytics.scenario_id, inputs.net);
  return figures;
}

// ---------------------------------------------------------------------------
// Horizon totals
// ---------------------------------------------------------------------------

function costTotal(years: SummaryYear[], grandfather: GrandfatherInput | null): SummaryFigures {
  const totals = emptyFigures();
  const present = years.filter(year => year.has_data);
  const costs = present.map(year => year.employer_cost);
  const total = costs.some(cost => cost === null) ? null : sum(costs as number[]);
  const note = grandfather?.loading
    ? 'Loading grandfathered employer cost.'
    : 'Employer cost is unavailable for at least one year.';
  set(totals, 'employer_cost', total, note);
  totals.total_compensation = sum(present.map(year => year.total_compensation ?? 0));
  return totals;
}

function setNetTotals(totals: SummaryFigures, years: SummaryYear[], net: NetInput): void {
  const measurable = years.filter(year => year.forfeiture_offset !== null);
  const none = 'No year has a measurable forfeiture basis.';
  const offset = measurable.length ? sum(measurable.map(year => year.forfeiture_offset ?? 0)) : null;
  set(totals, 'forfeiture_offset', offset, none);
  if (!net.policyReducesCost) {
    set(totals, 'reallocated_to_participants', measurable.length
      ? sum(measurable.map(year => year.reallocated_to_participants ?? 0)) : null, none);
  }
  // Years without a measurable offset contribute gross unchanged.
  const gross = totals.employer_cost;
  set(totals, 'net_employer_cost', gross === null ? null : gross - (offset ?? 0),
    totals.notes.employer_cost ?? '');
}

function scenarioTotals(
  analytics: DCPlanAnalytics, years: SummaryYear[], inputs: CostSummaryInputs,
): SummaryFigures {
  const totals = costTotal(years, inputs.grandfather);
  const cappedPay = sum(analytics.contribution_by_year.map(year => year.total_capped_compensation));
  set(totals, 'cost_pct_of_capped_pay', costPctOfCappedPay(totals.employer_cost, cappedPay),
    totals.notes.employer_cost ?? '');
  if (inputs.split) {
    totals.employer_match = sum(analytics.contribution_by_year.map(year => year.total_employer_match));
    totals.employer_core = sum(analytics.contribution_by_year.map(year => year.total_employer_core));
  }
  if (inputs.net) setNetTotals(totals, years, inputs.net);
  return totals;
}

// ---------------------------------------------------------------------------
// Differences from the anchor
// ---------------------------------------------------------------------------

const YEAR_DIFFERENCES: Array<[SummaryField, SummaryField]> = [
  ['employer_cost_vs_anchor', 'employer_cost'],
];

const TOTAL_DIFFERENCES: Array<[SummaryField, SummaryField]> = [
  ['employer_cost_vs_anchor', 'employer_cost'],
  ['cost_pct_vs_anchor_pp', 'cost_pct_of_capped_pay'],
  ['net_employer_cost_vs_anchor', 'net_employer_cost'],
  ['total_compensation_vs_anchor', 'total_compensation'],
];

function setDifferences(
  figures: SummaryFigures,
  anchor: SummaryFigures | undefined,
  pairs: Array<[SummaryField, SummaryField]>,
  isAnchor: boolean,
): void {
  pairs.forEach(([target, source]) => {
    if (isAnchor) {
      set(figures, target, null, ANCHOR_NOTE);
      return;
    }
    const value = differenceFromAnchor(figures[source], anchor?.[source] ?? null);
    const note = figures[source] === null
      ? (figures.notes[source] ?? 'No figure for this scenario.')
      : NO_ANCHOR_NOTE;
    set(figures, target, value, note);
  });
}

function withAnchorDifferences(
  scenario: ScenarioSummary, anchor: ScenarioSummary | undefined, net: boolean,
): ScenarioSummary {
  const totalPairs = TOTAL_DIFFERENCES.filter(([target]) =>
    net || target !== 'net_employer_cost_vs_anchor');
  setDifferences(scenario.totals, anchor?.totals, totalPairs, scenario.is_anchor);
  scenario.years.forEach(year => setDifferences(year,
    anchor?.years.find(item => item.year === year.year), YEAR_DIFFERENCES, scenario.is_anchor));
  return scenario;
}

/** Every figure the Cost Comparison tables show, for every selected scenario. */
export function buildCostSummary(inputs: CostSummaryInputs): ScenarioSummary[] {
  const byId = new Map(inputs.analytics.map(item => [item.scenario_id, item]));
  const scenarios = inputs.scenarioIds.flatMap(id => {
    const analytics = byId.get(id);
    if (!analytics) return [];
    const years = inputs.years.map(year => yearFigures(analytics, year, inputs));
    return [{
      scenario_id: id,
      is_anchor: id === inputs.anchorId,
      years,
      totals: scenarioTotals(analytics, years, inputs),
    }];
  });
  const anchor = scenarios.find(item => item.is_anchor);
  return scenarios.map(item => withAnchorDifferences(item, anchor, inputs.net !== null));
}

/** The run each scenario's figures were read from (carried by the analytics response itself). */
export function runIdsFromAnalytics(
  analytics: DCPlanAnalytics[],
): Record<string, string | null> {
  return Object.fromEntries(analytics.map(item => [item.scenario_id, item.run_id ?? null]));
}

/** The workbook request: the same figures, plus the view and the runs they came from. */
export function toSummaryExportRequest(
  summary: ScenarioSummary[],
  view: CostSummaryView,
  runIds: Record<string, string | null | undefined>,
): CostSummaryExportRequest {
  return {
    view,
    scenarios: summary.map(({ scenario_id, years, totals }) => ({
      scenario_id,
      run_id: runIds[scenario_id] ?? null,
      years,
      totals,
    })),
  };
}

// ---------------------------------------------------------------------------
// Display formatting shared by the page's tables and clipboard text
// ---------------------------------------------------------------------------

export const formatCurrency = (value: number): string => {
  if (value >= 1000000) return `$${(value / 1000000).toFixed(2)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
};

export const formatPercent = (value: number, decimals: number = 1): string =>
  `${value.toFixed(decimals)}%`;

export const formatSigned = (value: number): string =>
  `${value >= 0 ? '+' : ''}${formatCurrency(value)}`;

// ---------------------------------------------------------------------------
// Clipboard text for the two matrices
// ---------------------------------------------------------------------------

function cellText(year: SummaryYear, value: number | null, format: (value: number) => string): string {
  if (!year.has_data) return '-';
  return value === null ? 'unavailable' : format(value);
}

function pointsText(value: number | null): string {
  return value === null ? '--' : `${value >= 0 ? '+' : ''}${value.toFixed(2)} pp`;
}

function netLines(scenario: ScenarioSummary, name: string): string[] {
  const offset = (value: number | null) => value === null ? 'no measurable basis' : `-${formatCurrency(value)}`;
  const { totals } = scenario;
  return [
    [`${name} — forfeiture offset`, ...scenario.years.map(year => offset(year.forfeiture_offset)),
      offset(totals.forfeiture_offset), '--'].join('\t'),
    [`${name} — net employer cost`,
      ...scenario.years.map(year => year.net_employer_cost === null ? 'gross only' : formatCurrency(year.net_employer_cost)),
      totals.net_employer_cost === null ? 'unavailable' : formatCurrency(totals.net_employer_cost),
      totals.net_employer_cost_vs_anchor === null ? '--' : formatSigned(totals.net_employer_cost_vs_anchor)].join('\t'),
  ];
}

export function costMatrixTSV(
  summary: ScenarioSummary[], years: number[], names: Record<string, string>,
  preamble: string[], net: boolean,
): string {
  const lines = [...preamble, ['Scenario', ...years.map(String), 'Total', 'Variance'].join('\t')];
  summary.forEach(scenario => {
    const name = names[scenario.scenario_id] ?? scenario.scenario_id;
    const { totals } = scenario;
    lines.push([name, ...scenario.years.map(year => cellText(year, year.employer_cost, formatCurrency)),
      totals.employer_cost === null ? 'unavailable' : formatCurrency(totals.employer_cost),
      totals.employer_cost_vs_anchor === null ? '--' : formatSigned(totals.employer_cost_vs_anchor),
    ].join('\t'));
    const pct = (value: number) => formatPercent(value, 2);
    lines.push([`${name} — cost % of capped compensation`,
      ...scenario.years.map(year => cellText(year, year.cost_pct_of_capped_pay, pct)),
      totals.cost_pct_of_capped_pay === null ? 'unavailable' : pct(totals.cost_pct_of_capped_pay),
      pointsText(totals.cost_pct_vs_anchor_pp),
    ].join('\t'));
    if (net) lines.push(...netLines(scenario, name));
  });
  return lines.join('\n');
}

export function compensationMatrixTSV(
  summary: ScenarioSummary[], years: number[], names: Record<string, string>, preamble: string[],
): string {
  const lines = [...preamble, ['Scenario', ...years.map(String), 'Total', 'Variance'].join('\t')];
  summary.forEach(scenario => {
    const { totals } = scenario;
    lines.push([names[scenario.scenario_id] ?? scenario.scenario_id,
      ...scenario.years.map(year => cellText(year, year.total_compensation, formatCurrency)),
      formatCurrency(totals.total_compensation ?? 0),
      totals.total_compensation_vs_anchor === null ? '--' : formatSigned(totals.total_compensation_vs_anchor),
    ].join('\t'));
  });
  return lines.join('\n');
}
