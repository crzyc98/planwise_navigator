import { describe, expect, it } from 'vitest';
import {
  CensusGuide,
  CensusGuideField,
  buildColumnListText,
  buildTemplateCsv,
  groupOptionalFields,
} from './censusGuide';

function field(overrides: Partial<CensusGuideField> & { field_name: string }): CensusGuideField {
  return {
    label: overrides.field_name,
    required: false,
    data_type: 'string',
    description: 'desc',
    aliases: [],
    group: 'other',
    example: 'x',
    when_missing: '',
    ...overrides,
  };
}

const FIELDS: CensusGuideField[] = [
  field({ field_name: 'employee_id', required: true, example: 'SAMPLE-0001' }),
  field({ field_name: 'employee_ssn', group: 'status', example: 'SSN-00000001' }),
  field({ field_name: 'active', required: true, data_type: 'boolean', example: 'true' }),
  field({ field_name: 'employee_termination_date', group: 'status', data_type: 'date', example: '' }),
  field({ field_name: 'notes', description: 'Has "quotes", and a comma', example: 'a,b' }),
];

const GUIDE: CensusGuide = {
  fields: FIELDS,
  groups: [{ key: 'status', label: 'Identity and status' }, { key: 'hours', label: 'Hours' }, { key: 'other', label: 'Other columns' }],
  file_rules: {
    import_file_types: ['csv', 'xlsx'], import_max_mb: 500, parquet_max_mb: 50,
    date_formats: ['YYYY-MM-DD'], true_values: ['yes'], false_values: ['no'],
  },
};

describe('buildTemplateCsv', () => {
  it('has exactly the schema columns, in order, and one example row', () => {
    const lines = buildTemplateCsv(FIELDS).trimEnd().split('\n');
    expect(lines).toHaveLength(2);
    expect(lines[0].split(',')).toEqual(FIELDS.map((f) => f.field_name));
    expect(lines[1]).toBe('SAMPLE-0001,SSN-00000001,true,,"a,b"');
  });
});

describe('buildColumnListText', () => {
  it('lists every required column before any optional one', () => {
    const text = buildColumnListText(FIELDS);
    const at = (name: string) => text.indexOf(`- ${name} `);
    for (const f of FIELDS) expect(at(f.field_name)).toBeGreaterThan(-1);
    const lastRequired = Math.max(at('employee_id'), at('active'));
    const firstOptional = Math.min(at('employee_ssn'), at('employee_termination_date'), at('notes'));
    expect(text.indexOf('Required columns:')).toBeLessThan(lastRequired);
    expect(lastRequired).toBeLessThan(text.indexOf('Optional columns'));
    expect(text.indexOf('Optional columns')).toBeLessThan(firstOptional);
    expect(text).toContain('- active (yes / no, e.g. true):');
    expect(text).toContain('- employee_termination_date (date):');
  });
});

describe('groupOptionalFields', () => {
  it('groups optional fields in API order, drops empty groups and files unknown groups under other', () => {
    const withUnknown: CensusGuide = { ...GUIDE, fields: [...FIELDS, field({ field_name: 'hours_worked', group: 'nope' })] };
    const groups = groupOptionalFields(withUnknown);
    expect(groups.map((g) => g.group.key)).toEqual(['status', 'other']);
    expect(groups[1].fields.map((f) => f.field_name)).toEqual(['notes', 'hours_worked']);
  });
});
