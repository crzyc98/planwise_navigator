/**
 * Census guide: the census columns Studio accepts, served from the API's
 * census schema. The page, the template CSV and the copied column list are
 * all built from this one response.
 */

import type { components } from './api.generated';
import { fetchWithAuth } from './api';

const API_BASE = import.meta.env.VITE_API_URL ?? '';

type Schemas = components['schemas'];
export type CensusGuide = Schemas['CensusGuideResponse'];
export type CensusGuideField = Schemas['CensusGuideField'];
export type CensusGuideGroup = Schemas['CensusGuideGroup'];
export type CensusFileRules = Schemas['CensusFileRules'];

export const TEMPLATE_FILENAME = 'census_template.csv';

export async function getCensusGuide(): Promise<CensusGuide> {
  const response = await fetchWithAuth(`${API_BASE}/api/census/schema`);
  if (!response.ok) throw new Error(`Could not load the census guide (${response.status})`);
  return response.json() as Promise<CensusGuide>;
}

export const FORMAT_LABELS: Record<string, string> = {
  string: 'Text',
  date: 'Date',
  decimal: 'Number',
  boolean: 'Yes / no',
};

export function formatLabel(dataType: string): string {
  return FORMAT_LABELS[dataType] ?? 'Text';
}

/** Optional fields by group, in the API's group order; empty groups are dropped. */
export function groupOptionalFields(
  guide: CensusGuide,
): { group: CensusGuideGroup; fields: CensusGuideField[] }[] {
  const optional = guide.fields.filter((f) => !f.required);
  const known = new Set(guide.groups.map((g) => g.key));
  return guide.groups
    .map((group) => ({
      group,
      fields: optional.filter((f) => (known.has(f.group) ? f.group : 'other') === group.key),
    }))
    .filter((entry) => entry.fields.length > 0);
}

function csvCell(value: string): string {
  return /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/** Every census column as a header, plus one made-up example row. */
export function buildTemplateCsv(fields: CensusGuideField[]): string {
  const header = fields.map((f) => csvCell(f.field_name)).join(',');
  const example = fields.map((f) => csvCell(f.example)).join(',');
  return `${header}\n${example}\n`;
}

function describeLine(f: CensusGuideField): string {
  const example = f.example ? `, e.g. ${f.example}` : '';
  return `- ${f.field_name} (${formatLabel(f.data_type).toLowerCase()}${example}): ${f.description}`;
}

/** Plain-text column list to paste into an email to a plan sponsor. */
export function buildColumnListText(fields: CensusGuideField[]): string {
  const required = fields.filter((f) => f.required);
  const optional = fields.filter((f) => !f.required);
  return [
    'Census file: one row per employee, with one header row. CSV or Excel.',
    '',
    'Required columns:',
    ...required.map(describeLine),
    '',
    'Optional columns (send what you have):',
    ...optional.map(describeLine),
    '',
    'Please do not include real Social Security numbers.',
    '',
  ].join('\n');
}
