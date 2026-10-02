import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { DCPlanAnalytics } from '../services/api';
import { buildCostBreakdownRows, componentKey, componentShare, restoreCostBreakdown, splitUnavailableReason } from './costBreakdown';
import CostBreakdownTooltip from './CostBreakdownTooltip';

vi.mock('../hooks/useChartTheme', () => ({
  useChartTheme: () => ({ tooltip: { contentStyle: { color: '#fff', backgroundColor: '#111' } } }),
}));

function analytics(id: string, amounts: Array<[number, number, number]>): DCPlanAnalytics {
  return {
    scenario_id: id,
    contribution_by_year: amounts.map(([year, match, core]) => ({
      year, total_employer_match: match, total_employer_core: core,
      total_employer_cost: match + core,
    })),
  } as DCPlanAnalytics;
}

describe('gross cost breakdown', () => {
  const data = [analytics('a', [[2025, 80, 20], [2026, 100, 50]]),
    analytics('b', [[2025, 0, 40], [2026, 60, 0]])];

  it.each([false, true])('reconciles every scenario/year with totals (cumulative=%s)', cumulative => {
    const rows = cumulative
      ? [{ year: 2025, a: 100, b: 40 }, { year: 2026, a: 250, b: 100 }]
      : [{ year: 2025, a: 100, b: 40 }, { year: 2026, a: 150, b: 60 }];
    const split = buildCostBreakdownRows(rows, data, ['b', 'a'], cumulative);
    split.forEach(row => ['a', 'b'].forEach(id => {
      expect(row[componentKey(id, 'match')]! + row[componentKey(id, 'core')]!).toBe(row[id]);
    }));
    expect(split[1][componentKey('a', 'match')]).toBe(cumulative ? 180 : 100);
    expect(rows[0]).not.toHaveProperty(componentKey('a', 'match'));
  });

  it('uses the supplied cohort values, preserving empty cohorts and real zero components', () => {
    const filtered = [analytics('a', [[2026, 0, 12]])];
    const rows = buildCostBreakdownRows([{ year: 2025, a: 0 }, { year: 2026, a: 12 }], filtered, ['a'], false);
    expect(rows[0][componentKey('a', 'core')]).toBe(0);
    expect(rows[1][componentKey('a', 'match')]).toBe(0);
    expect(rows[1][componentKey('a', 'core')]).toBe(12);
  });

  it('preserves unavailable values and cumulative gaps', () => {
    const rows = [{ year: 2025, a: null }, { year: 2026, a: 150 }];
    expect(buildCostBreakdownRows(rows, data, ['a'], false)[0][componentKey('a', 'core')]).toBeNull();
    expect(buildCostBreakdownRows(rows, data, ['a'], true)[1][componentKey('a', 'match')]).toBeNull();
  });

  it('restores only valid preferences and gates split on requested modes, including before net data loads', () => {
    expect(restoreCostBreakdown('split')).toBe('split');
    for (const value of [undefined, null, 'invalid', {}, 'total']) expect(restoreCostBreakdown(value)).toBe('total');
    expect(splitUnavailableReason('gross', false)).toBeNull();
    expect(splitUnavailableReason('net', false)).toContain('Forfeiture');
    expect(splitUnavailableReason('gross', true)).toContain('grandfathered');
    expect(splitUnavailableReason('net', true)).not.toBeNull();
  });

  it('renders ordered scenarios, component amounts, shares, and totals using theme colors', () => {
    const row = buildCostBreakdownRows([{ year: 2025, a: 100, b: 40 }], data, ['a', 'b'], false)[0];
    const html = renderToStaticMarkup(<CostBreakdownTooltip active label={2025} payload={[{ payload: row }]}
      scenarioIds={['b', 'a']} names={{ a: 'Baseline', b: 'Alternative' }} colors={{ a: '#008800', b: '#000088' }} />);
    expect(html.indexOf('Alternative')).toBeLessThan(html.indexOf('Baseline'));
    for (const text of ['Employer match:', 'Non-elective core:', '$80.00', '80.0%', '20.0%', 'Total:', '$100.00']) {
      expect(html).toContain(text);
    }
    expect(html).toContain('background-color:#111');
  });

  it('handles zero-cost shares and inactive tooltips', () => {
    expect(componentShare(0, 0)).toBe('—');
    expect(componentShare(0, 10)).toBe('0.0%');
    expect(renderToStaticMarkup(<CostBreakdownTooltip scenarioIds={[]} names={{}} colors={{}} />)).toBe('');
  });
});
