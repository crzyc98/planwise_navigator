import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, expect, it, vi } from 'vitest';
import { WorkforceParametersSection } from './WorkforceParametersSection';
import { SimulationSection } from './SimulationSection';
import { DEFAULT_FORM_DATA } from './constants';

const state = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('./ConfigContext', () => ({ useConfigContext: () => state.value }));
vi.mock('./PromotionHazardEditor', () => ({ PromotionHazardEditor: () => <p>Promotion hazard editor</p> }));
vi.mock('./SegmentationSection', () => ({ SegmentationSection: () => <p>Band editor</p> }));

beforeEach(() => {
  const formData = { ...structuredClone(DEFAULT_FORM_DATA), startYear: 2025, endYear: 2027 };
  state.value = { formData, activeWorkspace: { id: 'w' }, scenarioId: 'a', scenarioLoading: false,
    setFormData: vi.fn(), inputProps: (name: keyof typeof formData) => ({ name, value: formData[name], onChange: vi.fn() }),
    promotionHazardConfig: null, bandConfig: null,
  };
});

it('orders setup tasks and keeps detailed assumptions collapsed with current values', () => {
  const html = renderToStaticMarkup(<WorkforceParametersSection />);
  const headings = ['Projection period', 'Headcount and turnover', 'Compensation growth', 'New-hire assumptions', 'Advanced workforce assumptions'];
  const positions = headings.map(heading => html.indexOf(heading));
  expect(positions.every(position => position >= 0)).toBe(true);
  expect(positions).toEqual([...positions].sort((a, b) => a - b));
  expect(html.match(/<details/g)).toHaveLength(2);
  expect(html).not.toContain('<details open');
  expect(html).toContain('Part-time:');
  expect(html).toContain('Pay ranges (5 levels)');
  expect(html).toContain('Seed 42');
  expect(html).toContain('85% of average compensation');
  expect(html).toContain('prior-year surviving hires');
  expect(html).toContain('Promotion hazard editor');
  expect(html).toContain('Band editor');
});

it('shows consequential custom values in collapsed summaries', () => {
  state.value.formData = { ...DEFAULT_FORM_DATA, partTimeNewHirePct: 23, marketScenario: 'aggressive', seed: 129,
    promoRateMultiplier: 1.8, newHireAgeDistribution: [{ age: 44, weight: 1, description: 'custom' }],
    jobLevelCompensation: [{ level: 1, name: 'Custom level', minComp: 70000, maxComp: 90000 }],
    levelDistributionMode: 'fixed', newHireLevelDistribution: [{ level: 1, name: 'Custom level', percentage: 100 }],
    levelMarketAdjustments: [{ level: 1, adjustment: 8 }],
  };
  state.value.promotionHazardConfig = { base: { base_rate: 0.17, level_dampener_factor: 0.12 },
    age_multipliers: [{ age_band: 'young', multiplier: 1.8 }], tenure_multipliers: [{ tenure_band: 'new', multiplier: 0.7 }],
  };
  const html = renderToStaticMarkup(<WorkforceParametersSection />);
  expect(html).toContain('44: 100%');
  expect(html).toContain('Part-time: 23%');
  expect(html).toContain('Custom level: $70,000–$90,000');
  expect(html).toContain('Seed 129');
  expect(html).toContain('multiplier 1.8×');
  expect(html).toContain('base promotion rate 17.0%');
  expect(html).toContain('age multipliers: young 1.8×');
  expect(html).toContain('tenure multipliers: new 0.7×');
  expect(html).toContain('Custom level 100%');
  expect(html).toContain('L1 8%');
  expect(html).toContain('unsupported');
});

it('shows the inclusive year count without an unconditional warning', () => {
  const html = renderToStaticMarkup(<SimulationSection variant="essentials" />);
  expect(html).toContain('3 projection years');
  expect(html).not.toContain('role="alert"');
  expect(html).not.toContain('warning-surface');
});

it('places actionable validation next to invalid projection years', () => {
  state.value.formData = { ...DEFAULT_FORM_DATA, startYear: 2027, endYear: 2025 };
  const html = renderToStaticMarkup(<SimulationSection variant="essentials" />);
  expect(html).toContain('role="alert"');
  expect(html).toContain('Last projection year must be at least the first');
});
