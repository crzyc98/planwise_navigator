import { describe, expect, it } from 'vitest';

import { citationLabel, differencesSummary } from './CrossScenarioEvidencePanel';

const citation = (query_id: 'QA' | 'QB', result_column: string) => ({
  query_id,
  result_column,
  query: 'SELECT 1',
  result_store: 'runs/r/simulation.duckdb',
});

describe('cross-scenario evidence labels', () => {
  it('cites each scenario store a figure is derived from', () => {
    expect(citationLabel({ citations: [citation('QA', 'value')] })).toBe('QA.value');
    expect(citationLabel({ citations: [citation('QA', 'value'), citation('QB', 'value')] })).toBe('QA.value, QB.value');
  });

  it('states when no configuration differences were cited', () => {
    expect(differencesSummary(0)).toBe('No configuration differences cited');
    expect(differencesSummary(1)).toBe('1 configuration difference cited');
    expect(differencesSummary(3)).toBe('3 configuration differences cited');
  });
});
