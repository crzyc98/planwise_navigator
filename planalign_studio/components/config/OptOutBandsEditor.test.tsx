import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { OptOutBandsEditor } from './OptOutBandsEditor';
import { DEFAULT_FORM_DATA } from './constants';
import { buildConfigPayload } from './buildConfigPayload';
import { applyResolvedFormData } from './resolvedFormData';
import { applyConfigToFormData } from './ConfigContext';

describe('opt-out bands', () => {
  it('exports the default target and band contracts without legacy segment rates', () => {
    const plan = buildConfigPayload(DEFAULT_FORM_DATA, null, null).dc_plan;
    expect(plan.opt_out_rate_target).toBe(0.09);
    expect(plan.opt_out_multipliers_age).toEqual([{ min: 0, multiplier: 1.8 }, { min: 30, multiplier: 1.1 }, { min: 45, multiplier: 0.7 }, { min: 60, multiplier: 0.4 }]);
    expect(plan.opt_out_multipliers_income.map(row => row.min)).toEqual([0, 50000, 100000, 200000]);
    expect(plan).not.toHaveProperty('opt_out_rate_young');
  });
  it('loads saved and inherited custom bands and ignores legacy segment rates', () => {
    const bands = [{ min: 0, multiplier: 0 }, { min: 40, multiplier: 2 }];
    const loaded = applyConfigToFormData({ dc_plan: { opt_out_rate_target: 0.12, opt_out_multipliers_age: bands, opt_out_rate_young: 0.9 } }, DEFAULT_FORM_DATA);
    expect(loaded.dcOptOutRateTarget).toBe(12);
    expect(loaded.dcOptOutMultipliersAge).toEqual(bands);
    expect(applyResolvedFormData({ opt_out_rate_target: 0.15, opt_out_multipliers_income: bands }, loaded)).toMatchObject({ dcOptOutRateTarget: 15, dcOptOutMultipliersIncome: bands });
  });
  it('renders collapsed editable age and income bands and accurate expected-rate copy', () => {
    const html = renderToStaticMarkup(<OptOutBandsEditor form={DEFAULT_FORM_DATA} onChange={() => {}} />);
    expect(html).toContain('Advanced: opt-out by age and income');
    expect(html).not.toContain('<details open');
    expect(html).toContain('Minimum age (years)');
    expect(html).toContain('Minimum income ($)');
    expect(html).toContain('Add age band');
    expect(html).toContain('Add income band');
    expect(html).toContain('can lower the expected rate');
  });
});
