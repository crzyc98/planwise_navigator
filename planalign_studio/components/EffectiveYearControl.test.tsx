import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import EffectiveYearControl from './EffectiveYearControl';

const WARNING = 'Auto enroll differs from Baseline in auto-enrollment.';

function render(overrides: Partial<React.ComponentProps<typeof EffectiveYearControl>> = {}): string {
  return renderToStaticMarkup(
    <EffectiveYearControl
      value={null}
      firstYear={2025}
      options={[2025, 2026, 2027]}
      anchorName="Baseline"
      blockedReason={null}
      warnings={[]}
      applied={false}
      onChange={() => undefined}
      {...overrides}
    />,
  );
}

describe('EffectiveYearControl', () => {
  it('defaults to the first simulation year, applied immediately', () => {
    const html = render();

    expect(html).toContain('Effective year');
    expect(html).toMatch(/<option value="2025" selected="">2025 \(immediately\)<\/option>/);
    expect(html).toContain('<option value="2027">2027</option>');
    expect(html).toContain("Each scenario&#x27;s design applies from the first simulation year.");
    expect(html).not.toContain('disabled=""');
  });

  it('describes a later year in terms of the anchor', () => {
    const html = render({ value: 2027 });

    expect(html).toMatch(/<option value="2027" selected="">2027<\/option>/);
    expect(html).toContain('Before 2027, scenarios other than Baseline show Baseline&#x27;s figures; from 2027 on, their own.');
  });

  it('is disabled with the reason when another view option blocks it', () => {
    const html = render({ blockedReason: 'Turn off grandfathering to set one.' });

    expect(html).toMatch(/<select[^>]*disabled=""/);
    expect(html).toContain('Turn off grandfathering to set one.');
  });

  it('shows the accuracy warning only while a later year is applied', () => {
    expect(render({ value: 2026, warnings: [WARNING], applied: true })).toContain(WARNING);
    expect(render({ value: 2026, warnings: [], applied: true })).not.toContain('role="alert"');
    expect(render({ value: null, warnings: [WARNING], applied: false })).not.toContain(WARNING);
  });
});
