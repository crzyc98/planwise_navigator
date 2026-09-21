import { describe, expect, it } from 'vitest';

import { formatProbability, formatValue, metricLabel } from './EnsembleAnalysisPanel';

describe('ensemble metric formatting', () => {
  it('formats rates, currency, and counts with metric-aware semantics', () => {
    expect(formatValue('participation_rate', 0.8123)).toBe('81.2%');
    expect(formatValue('total_employer_plan_cost', 1234.4)).toBe('$1,234');
    expect(formatValue('active_headcount', 1234.45)).toBe('1,234.5');
  });

  it('does not turn missing or invalid values into plausible numbers', () => {
    expect(formatValue('active_headcount', null)).toBe('Unavailable');
    expect(formatValue('active_headcount', Number.NaN)).toBe('Unavailable');
    expect(formatProbability(null)).toBe('Unavailable');
  });

  it('uses canonical labels and readable fallbacks', () => {
    expect(metricLabel('active_headcount')).toBe('Active headcount');
    expect(metricLabel('custom_metric_name')).toBe('Custom Metric Name');
  });
});
