import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { DataQualityNotice } from './PreviewStep';
import { DataQualityResult } from '../../services/importService';

vi.mock('../../services/importService', () => ({}));

const clean: DataQualityResult = {
  duplicate_employee_id_count: 0,
  null_required_field_counts: {},
  plausibility: [],
};

const render = (dataQuality: DataQualityResult) =>
  renderToStaticMarkup(<DataQualityNotice workspaceId="ws" importId="imp" dataQuality={dataQuality} />);

describe('Import data-quality notice', () => {
  it('shows nothing for a clean file', () => {
    expect(render(clean)).toBe('');
  });

  it('separates impossible values from warnings and offers the download', () => {
    const html = render({
      ...clean,
      duplicate_employee_id_count: 2,
      plausibility: [
        {
          rule_id: 'birth_on_or_after_hire', field: 'employee_birth_date', severity: 'error', count: 3,
          message: '3 row(s) have a birth date on or after the hire date.',
        },
        {
          rule_id: 'age_over_100', field: 'employee_birth_date', severity: 'warning', count: 1,
          message: '1 row(s) are over age 100 at the end of the census year.',
        },
      ],
    });
    const [errorBox, warningBox] = html.split('Data quality notice');
    expect(errorBox).toContain('bg-danger-surface');
    expect(errorBox).toContain('3 row(s) have a birth date on or after the hire date.');
    expect(warningBox).toContain('1 row(s) are over age 100');
    expect(warningBox).toContain('2 duplicate employee ID row(s)');
    expect(html).toContain('Download flagged rows (CSV)');
  });

  it('has no download when only duplicates are flagged', () => {
    const html = render({ ...clean, duplicate_employee_id_count: 1 });
    expect(html).toContain('1 duplicate employee ID row(s)');
    expect(html).not.toContain('Download flagged rows');
  });
});
