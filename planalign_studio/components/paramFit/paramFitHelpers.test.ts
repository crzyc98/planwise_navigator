import { describe, expect, it } from 'vitest';

import {
  ACKNOWLEDGEMENT_LABELS,
  DEFAULT_FIT_OPTIONS,
  DEFAULT_THRESHOLDS,
  diagnosticRows,
  isTerminal,
  movedSettings,
  preRunSummary,
  progressLabel,
  scorecardView,
  shortHash,
  splitFor,
  summaryView,
  verdictTone,
} from './paramFitHelpers';

describe('moved settings', () => {
  it('reports nothing when every dial is at its default', () => {
    expect(movedSettings(DEFAULT_FIT_OPTIONS, DEFAULT_THRESHOLDS, 'backtest')).toEqual([]);
  });

  it('names each fit option and threshold moved off its default', () => {
    const moved = movedSettings(
      { ...DEFAULT_FIT_OPTIONS, credibility_k: 25 },
      { ...DEFAULT_THRESHOLDS, flows: { warn: 0.15, fail: 0.2 } },
      'backtest'
    );
    expect(moved.map((item) => item.key)).toEqual(['credibility_k', 'thresholds.flows']);
    expect(moved[1].value).toBe('15.0% / 20.0%');
  });

  it('ignores thresholds for fit-only jobs, which never score', () => {
    const moved = movedSettings(DEFAULT_FIT_OPTIONS, { ...DEFAULT_THRESHOLDS, plan: { warn: 0.01, fail: 0.02 } }, 'fit');
    expect(moved).toEqual([]);
  });
});

describe('job status', () => {
  it('knows which statuses are final', () => {
    expect(isTerminal('completed')).toBe(true);
    expect(isTerminal('failed')).toBe(true);
    expect(isTerminal('cancelled')).toBe(true);
    expect(isTerminal('running')).toBe(false);
    expect(isTerminal('queued')).toBe(false);
  });

  it('labels progress in plain language', () => {
    expect(progressLabel({ stage: 'fitting' }, 'running')).toBe('Fitting parameters');
    expect(progressLabel({ stage: 'simulating', seed: 43, index: 2, total: 3 }, 'running')).toBe(
      'Simulating seed 43 (2 of 3)'
    );
    expect(progressLabel({ stage: 'queued' }, 'queued')).toBe('Queued');
    expect(progressLabel({ stage: 'scoring' }, 'completed')).toBe('Completed');
  });
});

describe('results', () => {
  const result = {
    summary: { snapshot_years: [2022, 2023, 2024], linked_employees: 900, fitted_count: 3, thin_count: 1, promotion_basis_label: 'measured', verdict: null },
    diagnostics: {
      termination: [
        { name: 'termination.base_rate', value: 0.12, prior: 0.1, exposure: 400, events: 48, observed: 0.12, credibility: 0.8, basis: 'observed', note: '', thin: false, moved_pct: 0.2 },
        { name: 'termination.age.<25', value: 0.1, prior: 0.1, exposure: 3, events: 0, observed: 0, credibility: 0.05, basis: 'pooled', note: 'thin', thin: true, moved_pct: 0 },
      ],
      config: [{ name: 'workforce.total_termination_rate', value: 0.13, prior: 0.12, exposure: 800, events: 104, observed: 0.13, credibility: 0.9, basis: 'observed', note: '', thin: false, moved_pct: null }],
    },
  };

  it('flattens diagnostics with their group and thin flag', () => {
    const rows = diagnosticRows(result.diagnostics);
    expect(rows).toHaveLength(3);
    expect(rows.filter((row) => row.thin).map((row) => row.name)).toEqual(['termination.age.<25']);
    expect(rows[2].group).toBe('config');
    expect(rows[2].movedPct).toBeNull();
  });

  it('orders groups hazards-first regardless of payload order', () => {
    const rows = diagnosticRows({ config: result.diagnostics.config, termination: result.diagnostics.termination });
    expect(rows.map((row) => row.group)).toEqual(['termination', 'termination', 'config']);
  });

  it('reads the summary defensively', () => {
    const summary = summaryView(result.summary);
    expect(summary.snapshotYears).toEqual([2022, 2023, 2024]);
    expect(summary.thinCount).toBe(1);
    expect(summaryView({}).fittedCount).toBeNull();
  });

  it('reads a scorecard into comparison rows', () => {
    const view = scorecardView({
      verdict: 'warn',
      verdict_summary: '3 pass, 1 warn',
      seeds: [42, 43],
      overridden_thresholds: ['flows'],
      split: { fit_years: [2022, 2023], holdout_years: [2024] },
      comparisons: [
        { metric: 'headcount.total', period: 2024, family: 'headcount', observable: true, predicted: 101, actual: 100, percent_error: 0.01, status: 'pass', spread: { seed_count: 2, minimum: 99, maximum: 103, values: [99, 103], actual_within_spread: true, distance_outside: null } },
        { metric: 'plan.participation', period: 'cumulative', family: 'plan', observable: false, status: 'not_observable', unobservable_reason: 'no column' },
      ],
    });
    expect(view?.verdict).toBe('warn');
    expect(view?.comparisons[0]).toMatchObject({ metric: 'headcount.total', period: '2024', percentError: 0.01 });
    expect(view?.comparisons[1].status).toBe('not_observable');
    expect(view?.comparisons[0].spread).toEqual({ minimum: 99, maximum: 103, actualWithin: true });
    expect(view?.comparisons[1].spread).toBeNull();
    expect(view?.holdoutYears).toEqual([2024]);
    expect(view?.overriddenThresholds).toEqual(['flows']);
    expect(scorecardView(null)).toBeNull();
  });

  it('colors verdicts by severity', () => {
    expect(verdictTone('pass')).toBe('success');
    expect(verdictTone('warn')).toBe('warning');
    expect(verdictTone('fail')).toBe('danger');
    expect(verdictTone(null)).toBe('neutral');
  });
});

describe('pre-run review', () => {
  const history = {
    history_id: 'hist_1',
    created_at: '2026-09-28T00:00:00Z',
    source_digest: 'a'.repeat(64),
    snapshots: [],
    splits: [
      { holdout_years: 1, split: { fit_years: [2022, 2023], holdout_years: [2024], boundary_year: 2023, simulation_effective_date: '2024-12-31' }, error: null },
      { holdout_years: 2, split: null, error: 'leaves 1 year to fit' },
    ],
  };

  it('finds the split for the chosen holdout', () => {
    expect(splitFor(history, 1).split?.boundary_year).toBe(2023);
    expect(splitFor(history, 2).error).toBe('leaves 1 year to fit');
  });

  it('lists every input the analyst is about to run', () => {
    const rows = preRunSummary({
      history,
      scenarioName: 'Baseline',
      mode: 'backtest',
      holdoutYears: 1,
      seeds: [42, 43],
      moved: [],
    });
    const labels = rows.map((row) => row.label);
    expect(labels).toEqual([
      'Mode',
      'Base scenario (priors)',
      'Source digest',
      'Fit years',
      'Held-out years',
      'Boundary year',
      'Simulation starts from',
      'Seeds',
      'Settings moved off defaults',
    ]);
    expect(rows.find((row) => row.label === 'Fit years')?.value).toBe('2022, 2023');
    expect(rows.find((row) => row.label === 'Settings moved off defaults')?.value).toBe('None');
  });

  it('shows why an impossible backtest split cannot run', () => {
    const rows = preRunSummary({ history, scenarioName: 'Baseline', mode: 'backtest', holdoutYears: 2, seeds: [42], moved: [] });
    const split = rows.find((row) => row.label === 'Backtest split');
    expect(split).toMatchObject({ value: 'leaves 1 year to fit', emphasis: true });
    expect(rows.map((row) => row.label)).not.toContain('Fit years');
  });

  it('omits backtest-only rows for a fit', () => {
    const rows = preRunSummary({ history, scenarioName: 'Baseline', mode: 'fit', holdoutYears: 1, seeds: [42], moved: [] });
    expect(rows.map((row) => row.label)).not.toContain('Seeds');
  });

  it('shortens hashes for display', () => {
    expect(shortHash('abcdef0123456789abcdef')).toBe('abcdef012345…');
  });

  it('labels every acknowledgement', () => {
    expect(Object.keys(ACKNOWLEDGEMENT_LABELS).sort()).toEqual(
      ['backtest_fail', 'backtest_warn', 'no_backtest', 'thin_cells', 'unfittable'].sort()
    );
  });
});

describe('defaults stay in step with the API', () => {
  it('matches the fit-option defaults the backend publishes', async () => {
    const { readFileSync } = await import('node:fs');
    const schema = JSON.parse(
      readFileSync(new URL('../../../tests/api/snapshots/openapi_schema.json', import.meta.url), 'utf-8')
    ) as { components: { schemas: Record<string, { properties: Record<string, { default?: unknown }> }> } };
    const properties = schema.components.schemas['FitOptionsModel-Input'].properties;
    for (const [key, value] of Object.entries(DEFAULT_FIT_OPTIONS)) {
      expect(properties[key].default).toBe(value);
    }
  });
});
