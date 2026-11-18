import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CensusEstimate, CensusNotice, MinimumWageSection } from './MinimumWageSection';
import { useConfigContext, type ConfigContextType } from './ConfigContext';
import { DEFAULT_FORM_DATA } from './constants';
import { minimumWageFromConfig } from './minimumWage';

vi.mock('./ConfigContext', () => ({ useConfigContext: vi.fn() }));
vi.mock('../../services/api', () => ({ analyzeMinimumWage: vi.fn() }));

function renderWith(changes: Partial<typeof DEFAULT_FORM_DATA>) {
  const context = { formData: { ...DEFAULT_FORM_DATA, startYear: 2025, endYear: 2027, ...changes }, setFormData: vi.fn(), activeWorkspace: { id: 'w' } };
  vi.mocked(useConfigContext).mockReturnValue(context as unknown as ConfigContextType);
  return renderToStaticMarkup(<MinimumWageSection />);
}

describe('Minimum wage block', () => {
  beforeEach(() => vi.clearAllMocks());

  it('is collapsed and reads "none" when the scenario has no minimum wage', () => {
    const html = renderWith({ censusDataPath: 'data/census.parquet' });
    expect(html).toContain('<details');
    expect(html).not.toContain('<details open');
    expect(html).toContain('Raises census staff below a new hourly minimum on a date: none.');
    expect(html).toContain('Add a minimum wage');
  });

  it('is disabled until a census is chosen', () => {
    const html = renderWith({ censusDataPath: '' });
    expect(html).toContain('Choose a census in Data Sources first.');
    expect(html).toMatch(/<button[^>]*disabled[^>]*>Add a minimum wage/);
  });

  it('shows saved steps, offers another, and flags a date outside the simulated years', () => {
    const minimumWage = minimumWageFromConfig([
      { hourly_rate: 20, effective_date: '2026-07-01' },
      { hourly_rate: 22, effective_date: '2030-01-01' },
    ]);
    const html = renderWith({ censusDataPath: 'data/census.parquet', minimumWage });
    expect(html).toContain('2 steps: $20.00 from Jul 1, 2026; $22.00 from Jan 1, 2030.');
    expect(html).toContain('Add another step');
    expect(html).toContain('outside the simulated years 2025–2027');
  });
});

describe('Census without hourly rates', () => {
  const render = (columnsPresent: string[]) => renderToStaticMarkup(
    <CensusNotice status={{ kind: 'no_rates', columnsPresent, minimumRate: 7.25, maximumRate: 500 }} />,
  );

  it('names the columns the sponsor needs to send', () => {
    const html = render([]);
    expect(html).toContain('This census has no hourly rates');
    expect(html).toContain('hourly_rate</span>: the base hourly rate (preferred)');
    expect(html).toContain('hours_worked</span>: all paid hours in the census year');
    expect(html).toContain('scheduled_hours_per_week</span>: scheduled weekly hours');
  });

  it('says when the columns are there but no rate is usable', () => {
    expect(render(['hours_worked'])).toContain('This census has hours_worked but no usable hourly rate: every row is blank or outside $7.25–$500.00 an hour.');
  });
});

describe('Census estimate', () => {
  const preview = {
    headcount: 149, columns_needed: ['hourly_rate', 'hours_worked', 'scheduled_hours_per_week'],
    hourly_rate_summary: {
      columns_present: ['hourly_rate'], with_rate: 100, blank: 49, out_of_bounds: 0, multiple_columns: 0,
      minimum_rate: 7.25, maximum_rate: 500, by_source: { hourly_rate: 100 },
    },
    steps: [{ hourly_rate: 20, effective_date: '2026-07-01', people_below: 29, added_annual_pay: 720379.4 }],
  };

  it('gives people below, people without a rate and the added pay, as a census-date estimate', () => {
    const html = renderToStaticMarkup(<CensusEstimate preview={preview} pending={false} />);
    expect(html).toContain('$20.00 from Jul 1, 2026: 29 people below it, adding $720,379 a year in pay.');
    expect(html).toContain('49 of 149 active employees on the census have no hourly rate');
    expect(html).toContain('This is an estimate from the census as of its date.');
    expect(html).toContain('Simulated hires have no hourly rate and aren&#x27;t covered, so the effect fades as census staff leave.');
  });

  it('counts people with a rate before any step is entered', () => {
    expect(renderToStaticMarkup(<CensusNotice status={{ kind: 'ready', headcount: 149, withRate: 100 }} />))
      .toContain('100 of 149 active employees on the census have an hourly rate.');
  });
});
