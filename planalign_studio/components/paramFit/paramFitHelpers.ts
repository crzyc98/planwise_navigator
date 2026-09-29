/**
 * Pure helpers for the Fit & Backtest page (#588): defaults that mirror the
 * CLI, moved-setting detection, progress labels, and defensive readers for the
 * loosely-typed result payloads (summary, diagnostics, scorecard).
 */
import type {
  FitHistorySet,
  FitSplitOption,
  ParamFitOptions,
  ParamFitProgress,
  ParamFitStatus,
  ParamFitThresholds,
  ParamPackAcknowledgement,
} from '../../services/api';

export type FitMode = 'fit' | 'backtest';
export type Tone = 'success' | 'warning' | 'danger' | 'neutral';

/** planalign_fit smoothing/promotion defaults — identical to `planalign fit`. */
export const DEFAULT_FIT_OPTIONS: Required<ParamFitOptions> = {
  credibility_k: 200,
  min_exposure: 50,
  level_coverage_threshold: 0.95,
  separation_exposure_gate: 0.5,
};

/** planalign_backtest MetricThresholds defaults — identical to `planalign backtest`. */
export const DEFAULT_THRESHOLDS: Required<ParamFitThresholds> = {
  headcount: { warn: 0.02, fail: 0.04 },
  compensation: { warn: 0.03, fail: 0.06 },
  flows: { warn: 0.1, fail: 0.2 },
  plan: { warn: 0.05, fail: 0.1 },
};

export const DEFAULT_SEEDS = [42, 43, 44];

export const FIT_OPTION_LABELS: Record<keyof ParamFitOptions, string> = {
  credibility_k: 'Credibility constant (k)',
  min_exposure: 'Thin-cell exposure floor',
  level_coverage_threshold: 'Job-level coverage threshold',
  separation_exposure_gate: 'Promotion separation gate',
};

export const ACKNOWLEDGEMENT_LABELS: Record<ParamPackAcknowledgement, string> = {
  thin_cells: 'Some fitted cells are thin and lean on the prior instead of the data.',
  unfittable: 'Some parameter groups could not be fitted and keep their current defaults.',
  no_backtest: 'This pack has no current backtest — its predictions have not been checked against held-out history.',
  backtest_warn: 'The backtest verdict is WARN: some metrics missed their warning threshold.',
  backtest_fail: 'The backtest verdict is FAIL: some metrics missed their failure threshold.',
};

const STAGE_LABELS: Record<string, string> = {
  queued: 'Queued',
  loading_history: 'Loading history',
  fitting: 'Fitting parameters',
  simulating: 'Simulating held-out years',
  scoring: 'Scoring against actuals',
  writing_pack: 'Writing parameter pack',
};

export interface MovedSetting {
  key: string;
  label: string;
  value: string;
  defaultValue: string;
}

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;
const pair = (value: { warn: number; fail: number }) => `${pct(value.warn)} / ${pct(value.fail)}`;

export function movedSettings(
  options: ParamFitOptions,
  thresholds: ParamFitThresholds,
  mode: FitMode
): MovedSetting[] {
  const moved: MovedSetting[] = [];
  for (const key of Object.keys(DEFAULT_FIT_OPTIONS) as (keyof ParamFitOptions)[]) {
    const value = options[key] ?? DEFAULT_FIT_OPTIONS[key];
    if (value !== DEFAULT_FIT_OPTIONS[key]) {
      moved.push({ key, label: FIT_OPTION_LABELS[key], value: String(value), defaultValue: String(DEFAULT_FIT_OPTIONS[key]) });
    }
  }
  if (mode !== 'backtest') return moved;
  for (const family of Object.keys(DEFAULT_THRESHOLDS) as (keyof ParamFitThresholds)[]) {
    const current = thresholds[family] ?? DEFAULT_THRESHOLDS[family];
    const baseline = DEFAULT_THRESHOLDS[family];
    if (current.warn !== baseline.warn || current.fail !== baseline.fail) {
      moved.push({
        key: `thresholds.${family}`,
        label: `${family} threshold (warn / fail)`,
        value: pair(current),
        defaultValue: pair(baseline),
      });
    }
  }
  return moved;
}

export function isTerminal(status: ParamFitStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled';
}

export function progressLabel(
  progress: Pick<ParamFitProgress, 'stage'> & Partial<ParamFitProgress>,
  status: ParamFitStatus
): string {
  if (isTerminal(status)) return status.charAt(0).toUpperCase() + status.slice(1);
  if (progress.stage === 'simulating' && progress.index && progress.total) {
    return `Simulating seed ${progress.seed ?? '?'} (${progress.index} of ${progress.total})`;
  }
  return STAGE_LABELS[progress.stage ?? 'queued'] ?? 'Working';
}

export function verdictTone(verdict: string | null | undefined): Tone {
  if (verdict === 'pass') return 'success';
  if (verdict === 'warn') return 'warning';
  if (verdict === 'fail') return 'danger';
  return 'neutral';
}

export const TONE_CLASSES: Record<Tone, string> = {
  success: 'border-success-border bg-success-surface text-success-ink',
  warning: 'border-warning-border bg-warning-surface text-warning-ink',
  danger: 'border-danger-border bg-danger-surface text-danger-ink',
  neutral: 'border-border bg-surface-subtle text-ink-muted',
};

export function shortHash(hash: string, length = 12): string {
  return hash.length > length ? `${hash.slice(0, length)}…` : hash;
}

// ---------------------------------------------------------------------------
// Result readers — the API types these payloads as open records.
// ---------------------------------------------------------------------------

type Loose = Record<string, unknown>;

const num = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null);
const str = (value: unknown): string | null => (typeof value === 'string' ? value : null);
const nums = (value: unknown): number[] => (Array.isArray(value) ? value.filter((v): v is number => typeof v === 'number') : []);
const strs = (value: unknown): string[] => (Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []);

export interface SummaryView {
  snapshotYears: number[];
  linkedEmployees: number | null;
  fittedCount: number | null;
  thinCount: number | null;
  promotionBasisLabel: string | null;
  verdict: string | null;
}

export function summaryView(summary: Loose): SummaryView {
  return {
    snapshotYears: nums(summary.snapshot_years),
    linkedEmployees: num(summary.linked_employees),
    fittedCount: num(summary.fitted_count),
    thinCount: num(summary.thin_count),
    promotionBasisLabel: str(summary.promotion_basis_label),
    verdict: str(summary.verdict),
  };
}

export interface DiagnosticRow {
  group: string;
  name: string;
  value: number | null;
  prior: number | null;
  exposure: number | null;
  events: number | null;
  credibility: number | null;
  basis: string;
  note: string;
  thin: boolean;
  movedPct: number | null;
}

/** The report's order: hazards first, then merit, deferral, and config values. */
const GROUP_ORDER = ['termination', 'promotion', 'merit', 'deferral', 'config'];
const groupRank = (group: string) => {
  const rank = GROUP_ORDER.indexOf(group);
  return rank === -1 ? GROUP_ORDER.length : rank;
};

export function diagnosticRows(groups: Record<string, Loose[]>): DiagnosticRow[] {
  const ordered = Object.entries(groups).sort(([a], [b]) => groupRank(a) - groupRank(b));
  return ordered.flatMap(([group, rows]) =>
    rows.map((row) => ({
      group,
      name: str(row.name) ?? '',
      value: num(row.value),
      prior: num(row.prior),
      exposure: num(row.exposure),
      events: num(row.events),
      credibility: num(row.credibility),
      basis: str(row.basis) ?? '',
      note: str(row.note) ?? '',
      thin: row.thin === true,
      movedPct: num(row.moved_pct),
    }))
  );
}

export interface ComparisonRow {
  metric: string;
  period: string;
  family: string;
  observable: boolean;
  predicted: number | null;
  actual: number | null;
  percentError: number | null;
  status: string;
  note: string | null;
}

export interface ScorecardView {
  verdict: string | null;
  verdictSummary: string;
  seeds: number[];
  fitYears: number[];
  holdoutYears: number[];
  overriddenThresholds: string[];
  comparisons: ComparisonRow[];
}

export function scorecardView(scorecard: Loose | null | undefined): ScorecardView | null {
  if (!scorecard) return null;
  const split = (scorecard.split ?? {}) as Loose;
  const comparisons = Array.isArray(scorecard.comparisons) ? (scorecard.comparisons as Loose[]) : [];
  return {
    verdict: str(scorecard.verdict),
    verdictSummary: str(scorecard.verdict_summary) ?? '',
    seeds: nums(scorecard.seeds),
    fitYears: nums(split.fit_years),
    holdoutYears: nums(split.holdout_years),
    overriddenThresholds: strs(scorecard.overridden_thresholds),
    comparisons: comparisons.map((row) => ({
      metric: str(row.metric) ?? '',
      period: String(row.period ?? ''),
      family: str(row.family) ?? '',
      observable: row.observable === true,
      predicted: num(row.predicted),
      actual: num(row.actual),
      percentError: num(row.percent_error),
      status: str(row.status) ?? 'undefined',
      note: str(row.unobservable_reason),
    })),
  };
}

// ---------------------------------------------------------------------------
// Pre-run review
// ---------------------------------------------------------------------------

export function splitFor(history: FitHistorySet, holdoutYears: number): FitSplitOption {
  return (
    history.splits.find((option) => option.holdout_years === holdoutYears) ?? {
      holdout_years: holdoutYears,
      split: null,
      error: 'No split preview for this holdout.',
    }
  );
}

export interface SummaryRow {
  label: string;
  value: string;
  emphasis?: boolean;
}

export function preRunSummary(input: {
  history: FitHistorySet;
  scenarioName: string;
  mode: FitMode;
  holdoutYears: number;
  seeds: number[];
  moved: MovedSetting[];
}): SummaryRow[] {
  const { history, scenarioName, mode, holdoutYears, seeds, moved } = input;
  const years = history.snapshots.map((snapshot) => snapshot.year);
  const option = mode === 'backtest' ? splitFor(history, holdoutYears) : null;
  const split = option?.split ?? null;
  const rows: SummaryRow[] = [
    { label: 'Mode', value: mode === 'backtest' ? `Fit + backtest (${holdoutYears}-year holdout)` : 'Fit only' },
    { label: 'Base scenario (priors)', value: scenarioName },
    { label: 'Source digest', value: shortHash(history.source_digest, 16) },
  ];
  if (split) {
    rows.push(
      { label: 'Fit years', value: split.fit_years.join(', ') },
      { label: 'Held-out years', value: split.holdout_years.join(', ') },
      { label: 'Boundary year', value: String(split.boundary_year) },
      { label: 'Simulation starts from', value: split.simulation_effective_date },
      { label: 'Seeds', value: seeds.join(', ') }
    );
  } else if (option) {
    rows.push({ label: 'Backtest split', value: option.error ?? 'Not available', emphasis: true });
  } else {
    rows.push({ label: 'Fit years', value: years.join(', ') });
  }
  rows.push({
    label: 'Settings moved off defaults',
    value: moved.length ? moved.map((item) => `${item.label}: ${item.value}`).join('; ') : 'None',
    emphasis: moved.length > 0,
  });
  return rows;
}

export function formatNumber(value: number | null, digits = 4): string {
  return value === null ? '—' : value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function formatPercent(value: number | null, signed = false): string {
  if (value === null) return '—';
  const text = `${(value * 100).toFixed(2)}%`;
  return signed && value > 0 ? `+${text}` : text;
}
