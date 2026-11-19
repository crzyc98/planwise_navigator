import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { CensusGuideContent } from './CensusGuide';
import type { CensusGuide } from '../services/censusGuide';

const GUIDE: CensusGuide = {
  fields: [
    {
      field_name: 'employee_id', label: 'Employee ID', required: true, data_type: 'string',
      description: 'A unique ID for each employee.', aliases: ['empid', 'staff_id'], group: 'other',
      example: 'SAMPLE-0001', when_missing: '',
    },
    {
      field_name: 'employee_deferral_rate', label: 'Deferral rate', required: false, data_type: 'decimal',
      description: 'Share of pay saved.', aliases: [], group: 'participation', example: '0.06',
      when_missing: 'Without it, everyone starts at 0% and not enrolled.',
    },
    // A field added without guide metadata: API defaults only.
    {
      field_name: 'hours_worked', label: 'Hours worked', required: false, data_type: 'decimal',
      description: 'Hours worked in the plan year', aliases: [], group: 'other', example: '0', when_missing: '',
    },
  ],
  groups: [
    { key: 'participation', label: 'Plan participation and contributions' },
    { key: 'hours', label: 'Hours' },
    { key: 'other', label: 'Other columns' },
  ],
  file_rules: {
    import_file_types: ['csv', 'xlsx'], import_max_mb: 500, parquet_max_mb: 50,
    date_formats: ['YYYY-MM-DD', 'MM/DD/YYYY'], true_values: ['true', 'yes'], false_values: ['false', 'no'],
  },
};

function render(): string {
  return renderToStaticMarkup(
    <MemoryRouter>
      <CensusGuideContent guide={GUIDE} />
    </MemoryRouter>,
  );
}

describe('CensusGuideContent', () => {
  it('shows required and grouped optional sections with each field and its when-missing sentence', () => {
    const html = render();
    expect(html).toContain('Required columns');
    expect(html).toContain('Employee ID');
    expect(html).toContain('Plan participation and contributions');
    expect(html).toContain('Without it, everyone starts at 0% and not enrolled.');
    expect(html).toContain('Number · e.g. <code class="font-mono text-ink-muted">0.06</code>');
    expect(html).toContain('Other header names Studio recognises (2)');
    expect(html).toContain('empid, staff_id');
  });

  it('renders a field with no extra metadata under Other columns, without an empty group', () => {
    const html = render();
    expect(html).toContain('Other columns');
    expect(html).toContain('Hours worked');
    expect(html).toContain('hours_worked');
    expect(html).not.toContain('>Hours<');
    expect(html.match(/border-l-2 border-brand-green/g)).toHaveLength(1);
  });

  it('shows file rules, the actions and the privacy line', () => {
    const html = render();
    expect(html).toContain('.csv or Excel (.xlsx), up to 500 MB');
    expect(html).toContain('YYYY-MM-DD, MM/DD/YYYY');
    expect(html).toContain('Download template');
    expect(html).toContain('Copy column list');
    expect(html).toContain('No real Social Security numbers are needed');
  });
});
