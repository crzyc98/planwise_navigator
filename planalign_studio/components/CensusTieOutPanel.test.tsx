import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import {
  CensusTieOutView,
  censusTieOutPath,
  formatTieOutDifference,
  formatTieOutValue,
  loadTieOutState,
  TieOutState,
} from './CensusTieOutPanel';
import { CensusTieOut, CensusTieOutRow } from '../services/api';

vi.mock('../services/api', () => ({}));

const row = (overrides: Partial<CensusTieOutRow>): CensusTieOutRow => ({
  metric: 'active_headcount', label: 'Active headcount', unit: 'count',
  definition: 'Employees active at year end.', census_value: 100, simulated_value: 103,
  expected_value: 103, difference: 3, relative_difference: 0.03, tolerance: 4.6,
  status: 'ties', message: 'Active headcount ties to the census within the expected range.',
  ...overrides,
});

const tieOut: CensusTieOut = {
  scenario_id: 's', scenario_name: 'Baseline', available: true, unavailable_reason: null,
  run_id: 'run', census_file: 'census_2024.parquet', census_year: 2024,
  census_as_of_date: '2024-12-31', first_simulated_year: 2025, growth_rate: 0.03, raise_rate: 0.05,
  source_note: 'Compares census_2024.parquet (census year 2024) with 2025, the first simulated year, allowing for one year of the configured growth and raises. Meaningful only for a scenario that models the current plan.',
  rows: [
    row({}),
    row({
      metric: 'employer_match', label: 'Employer match', unit: 'dollars', census_value: 90000,
      simulated_value: 120000, expected_value: 97335, difference: 30000, relative_difference: 0.333,
      status: 'gap',
      message: 'Employer match is 33% above the census, where about +8% was expected from growth and raises. Check the match formula and match eligibility.',
    }),
    row({
      metric: 'employer_core', label: 'Employer core', unit: 'dollars', census_value: null,
      simulated_value: 52000, expected_value: null, difference: null, relative_difference: null,
      tolerance: null, status: 'not_in_census',
      message: "The census has no employer core column, so core can't be compared.",
    }),
  ],
};

const render = (props: Partial<React.ComponentProps<typeof CensusTieOutView>>) =>
  renderToStaticMarkup(<CensusTieOutView tieOut={tieOut} loading={false} failed={false} {...props} />);

describe('Census tie-out panel', () => {
  it('prints the server sentence naming the census file and years', () => {
    const html = render({});
    expect(html).toContain('id="census-tie-out"');
    expect(html).toContain(tieOut.source_note);
    expect(html).toContain('Census 2024');
    expect(html).toContain('Simulated 2025');
    expect(html).toContain('Meaningful only for a scenario that models the current plan');
  });

  it('describes gaps with the server message and warning styling, never as errors', () => {
    const html = render({});
    expect(html).toContain('Check the match formula and match eligibility.');
    expect(html).toContain('1 gap');
    expect(html).toContain('bg-warning-surface');
    expect(html).not.toMatch(/danger|error|fail/i);
  });

  it('keeps ties quiet and shows rows without census data as not in census', () => {
    const html = render({});
    expect(html).not.toContain('ties to the census within the expected range');
    expect(html).toContain('Not in census');
    expect(html).toContain('<td class="px-4 py-2 text-sm text-ink text-right align-top whitespace-nowrap">—</td>');
  });

  it('shows no gap count when every row ties', () => {
    const html = render({ tieOut: { ...tieOut, rows: [row({})] } });
    expect(html).not.toMatch(/>\d+ gaps?</);
  });

  it('shows the reason quietly when there is nothing to compare', () => {
    const reason = 'This scenario has no completed Studio run, so there is no archived census to compare.';
    const html = render({ tieOut: { ...tieOut, available: false, unavailable_reason: reason, rows: [] } });
    expect(html).toContain(reason);
    expect(html).not.toContain('<table');
    expect(html).not.toMatch(/danger|warning/);
  });

  it('has loading and failure states', () => {
    expect(render({ tieOut: null, loading: true })).toContain('Loading census tie-out...');
    expect(render({ tieOut: null, failed: true })).toContain('Census tie-out is not available right now.');
  });

  it('formats values and differences in the row unit', () => {
    expect(formatTieOutValue('count', 1234.4)).toBe('1,234');
    expect(formatTieOutValue('rate', 0.625)).toBe('62.5%');
    expect(formatTieOutValue('dollars', 1234567.8)).toBe('$1,234,568');
    expect(formatTieOutValue('dollars', null)).toBe('—');
    expect(formatTieOutDifference('count', 3)).toBe('+3');
    expect(formatTieOutDifference('rate', -0.012)).toBe('-1.2 pts');
    expect(formatTieOutDifference('dollars', -30000)).toBe('-$30,000');
  });

  it('never shows a negative sign on a difference that rounds to zero', () => {
    expect(formatTieOutDifference('count', -0.4)).toBe('+0');
    expect(formatTieOutDifference('dollars', -0.5)).toBe('+$0');
    expect(formatTieOutDifference('rate', -0.0004)).toBe('+0.0 pts');
    expect(formatTieOutDifference('dollars', -0.6)).toBe('-$1');
    expect(formatTieOutDifference('rate', -0.0006)).toBe('-0.1 pts');
  });

  it('clears the previous scenario when a load starts and when it fails', async () => {
    const states: TieOutState[] = [];
    await loadTieOutState(() => Promise.reject(new Error('offline')), state => states.push(state), () => false);
    expect(states).toEqual([
      { tieOut: null, loading: true, failed: false },
      { tieOut: null, loading: false, failed: true },
    ]);
    for (const state of states) expect(render(state)).not.toMatch(/>\d+ gaps?</);
  });

  it('ignores a response that arrives after the scenario changed', async () => {
    const states: TieOutState[] = [];
    await loadTieOutState(() => Promise.resolve(tieOut), state => states.push(state), () => true);
    expect(states).toEqual([{ tieOut: null, loading: true, failed: false }]);
  });

  it('links to the panel on Overview', () => {
    expect(censusTieOutPath('s 1')).toBe('/analytics?scenario=s%201&focus=census-tie-out');
  });
});
