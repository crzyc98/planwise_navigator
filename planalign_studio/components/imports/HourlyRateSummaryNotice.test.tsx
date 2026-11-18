import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import HourlyRateSummaryNotice from './HourlyRateSummaryNotice';
import { CensusHourlyRateSummary } from '../../services/api';

vi.mock('../../services/api', () => ({}));

const summary: CensusHourlyRateSummary = {
  columns_present: ['hourly_rate', 'hours_worked'],
  with_rate: 1200,
  blank: 300,
  out_of_bounds: 4,
  multiple_columns: 0,
  minimum_rate: 7.25,
  maximum_rate: 500,
  by_source: { hourly_rate: 1000, hours_worked: 200 },
};

const render = (value: CensusHourlyRateSummary | null) =>
  renderToStaticMarkup(<HourlyRateSummaryNotice summary={value} />);

describe('Hourly rate summary', () => {
  it('reports rates, blanks and implausible rates', () => {
    const html = render(summary);
    expect(html).toContain('1,200 people have an hourly rate');
    expect(html).toContain('1,000 from hourly_rate, 200 from hours_worked');
    expect(html).toContain('300 people have none');
    expect(html).toContain('below $7.25 or');
    expect(html).toContain('hourly_rate is preferred');
  });

  it('says which column wins when a row has several', () => {
    expect(render({ ...summary, multiple_columns: 1 })).toContain(
      'from hourly_rate first, then hours_worked, then scheduled_hours_per_week',
    );
  });

  it('shows nothing for a census without hourly columns', () => {
    expect(render(null)).toBe('');
  });
});
