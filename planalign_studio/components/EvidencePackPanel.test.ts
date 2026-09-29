import { describe, expect, it } from 'vitest';

import { formatFigure } from './EvidencePackPanel';

const figure = (value: string, unit: 'count' | 'currency' | 'rate' | 'percent_of_change') => ({
  value,
  unit,
  status: 'defined' as const,
});

describe('evidence figure formatting', () => {
  it('never renders a value that rounds to zero with a minus sign', () => {
    expect(formatFigure(figure('-0.002618', 'percent_of_change'))).toBe('0.00%');
    expect(formatFigure(figure('-0.001', 'currency'))).toBe('$0.00');
    expect(formatFigure(figure('-0.00001', 'rate'))).toBe('0.00%');
  });

  it('keeps the sign on values that are visibly non-zero', () => {
    expect(formatFigure(figure('-45.1', 'percent_of_change'))).toBe('-45.10%');
    expect(formatFigure(figure('-23999169.6', 'currency'))).toBe('-$23,999,169.60');
  });
});
