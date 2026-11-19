import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Check, Copy, Download, Loader2, ShieldCheck } from 'lucide-react';
import { saveBrowserDownload } from '../services/api';
import {
  CensusFileRules,
  CensusGuide as CensusGuideData,
  CensusGuideField,
  TEMPLATE_FILENAME,
  buildColumnListText,
  buildTemplateCsv,
  formatLabel,
  getCensusGuide,
  groupOptionalFields,
} from '../services/censusGuide';
import { useCopyToClipboard } from '../hooks/useCopyToClipboard';
import { useWorkspacePath } from '../hooks/useWorkspaceNavigation';

function FieldRow({ field }: Readonly<{ field: CensusGuideField }>) {
  return (
    <li className="py-4 first:pt-0 last:pb-0 space-y-1.5">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <h3 className="text-sm font-semibold text-ink">{field.label}</h3>
        <code className="text-xs font-mono text-ink-muted break-all">{field.field_name}</code>
      </div>
      <p className="text-sm text-ink-muted">{field.description}</p>
      <p className="text-xs text-ink-subtle">
        {formatLabel(field.data_type)}
        {field.example && (
          <>
            {' · e.g. '}
            <code className="font-mono text-ink-muted">{field.example}</code>
          </>
        )}
      </p>
      {field.when_missing && (
        <p className="text-sm text-ink border-l-2 border-brand-green pl-3">{field.when_missing}</p>
      )}
      {field.aliases.length > 0 && (
        <details className="text-xs text-ink-subtle">
          <summary className="cursor-pointer hover:text-ink-muted">
            Other header names Studio recognises ({field.aliases.length})
          </summary>
          <p className="mt-1 font-mono break-words">{field.aliases.join(', ')}</p>
        </details>
      )}
    </li>
  );
}

function Section({ title, intro, children }: Readonly<{ title: string; intro?: string; children: React.ReactNode }>) {
  return (
    <section className="border border-border rounded-xl p-4 sm:p-6 bg-surface-raised shadow-sm space-y-4">
      <div>
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        {intro && <p className="text-sm text-ink-muted mt-0.5">{intro}</p>}
      </div>
      {children}
    </section>
  );
}

function FieldList({ fields }: Readonly<{ fields: CensusGuideField[] }>) {
  return (
    <ul className="divide-y divide-border">
      {fields.map((f) => <FieldRow key={f.field_name} field={f} />)}
    </ul>
  );
}

function Chips({ fields, tone }: Readonly<{ fields: CensusGuideField[]; tone: 'required' | 'optional' }>) {
  const style = tone === 'required'
    ? 'bg-success-surface text-success-ink'
    : 'bg-surface-subtle text-ink-muted';
  return (
    <div className="flex flex-wrap gap-1.5">
      {fields.map((f) => (
        <span key={f.field_name} className={`text-xs font-medium px-2 py-0.5 rounded-full ${style}`}>
          {f.label}
        </span>
      ))}
    </div>
  );
}

function FileRules({ rules }: Readonly<{ rules: CensusFileRules }>) {
  const types = rules.import_file_types.map((t) => (t === 'xlsx' ? 'Excel (.xlsx)' : `.${t}`)).join(' or ');
  const items: { title: string; body: string }[] = [
    {
      title: 'File type',
      body: `${types}, up to ${rules.import_max_mb} MB. If an Excel file has several sheets, Studio asks which one to use. A Parquet file up to ${rules.parquet_max_mb} MB can also be uploaded as is.`,
    },
    {
      title: 'Layout',
      body: 'One header row, then one row per employee. No merged cells or extra title rows. Extra columns are fine; Studio does not use columns it does not recognise.',
    },
    {
      title: 'Dates',
      body: `Any of ${rules.date_formats.join(', ')}. Use one format per column. If a column could be month-first or day-first, Studio asks you to choose. A date Studio cannot read stops the import and names the column.`,
    },
    {
      title: 'Yes / no',
      body: `Yes: ${rules.true_values.join(', ')}. No: ${rules.false_values.join(', ')}. Capitals do not matter. A blank cell means unknown.`,
    },
    {
      title: 'Numbers',
      body: 'Plain numbers. Currency signs ($, €, £), thousands commas and brackets for negatives are fine. Do not use a % sign: write rates as decimals (0.06 for 6%).',
    },
    {
      title: 'Duplicates',
      body: 'If an employee ID appears more than once, Studio keeps the row with the latest hire date (then the higher pay) and drops the rest. Repeated header names get a number added, such as salary_1.',
    },
    {
      title: 'Text encoding',
      body: 'Save CSV files as UTF-8. Files that are not UTF-8 are read as Latin-1, with a warning if characters may look wrong.',
    },
  ];
  return (
    <dl className="space-y-3">
      {items.map((item) => (
        <div key={item.title} className="sm:grid sm:grid-cols-[8rem_1fr] sm:gap-4">
          <dt className="text-sm font-semibold text-ink">{item.title}</dt>
          <dd className="text-sm text-ink-muted">{item.body}</dd>
        </div>
      ))}
    </dl>
  );
}

export function CensusGuideContent({ guide }: Readonly<{ guide: CensusGuideData }>) {
  const importPath = useWorkspacePath('/import');
  const { copy, copied, error: copyError } = useCopyToClipboard();
  const required = guide.fields.filter((f) => f.required);
  const optional = guide.fields.filter((f) => !f.required);
  const groups = groupOptionalFields(guide);

  const downloadTemplate = () => {
    saveBrowserDownload(new Blob([buildTemplateCsv(guide.fields)], { type: 'text/csv' }), TEMPLATE_FILENAME);
  };

  return (
    <div className="p-4 sm:p-6 max-w-4xl mx-auto space-y-6">
      <Link to={importPath} className="inline-flex items-center gap-1 text-sm text-brand-ink hover:underline">
        <ArrowLeft size={14} /> Back to Import Data
      </Link>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink">What should the census include?</h1>
          <p className="text-sm text-ink-muted mt-0.5">
            One row per employee. {required.length} columns are required; everything else is optional and adds detail.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          <button
            type="button"
            onClick={downloadTemplate}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-brand-green text-ink-inverse text-sm font-medium rounded-lg hover:bg-brand-dark transition-colors"
          >
            <Download size={14} /> Download template
          </button>
          <button
            type="button"
            onClick={() => void copy(buildColumnListText(guide.fields))}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm border border-border rounded-lg text-ink-muted hover:bg-surface-subtle"
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? 'Copied' : 'Copy column list'}
          </button>
        </div>
      </div>
      {copyError && <p className="text-sm text-danger-ink">Could not copy: {copyError}</p>}

      <Section title="At a glance">
        <div className="space-y-3">
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-ink-muted uppercase">Required</p>
            <Chips fields={required} tone="required" />
          </div>
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-ink-muted uppercase">Optional</p>
            <Chips fields={optional} tone="optional" />
          </div>
        </div>
      </Section>

      <Section title="Required columns" intro="Every file needs these. The import wizard will not finish until all of them are matched.">
        <FieldList fields={required} />
      </Section>

      {groups.map(({ group, fields }) => (
        <Section key={group.key} title={group.label}>
          <FieldList fields={fields} />
        </Section>
      ))}

      <Section title="File requirements">
        <FileRules rules={guide.file_rules} />
      </Section>

      <div className="flex items-start gap-3 rounded-xl border border-info-border bg-info-surface p-4 text-sm text-info-ink">
        <ShieldCheck size={18} className="shrink-0 mt-0.5" />
        <p>
          No real Social Security numbers are needed. Leave the SSN column out and Studio makes a placeholder from
          the employee ID. Anything sent in that column is stored as given, so it should never be a real SSN.
        </p>
      </div>
    </div>
  );
}

export default function CensusGuide() {
  const [guide, setGuide] = useState<CensusGuideData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCensusGuide()
      .then((data) => { if (!cancelled) setGuide(data); })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load the census guide');
      });
    return () => { cancelled = true; };
  }, []);

  if (error) {
    return <div className="p-6 text-sm text-danger-ink">{error}</div>;
  }
  if (!guide) {
    return (
      <div className="flex items-center justify-center gap-2 p-12 text-sm text-ink-muted">
        <Loader2 size={16} className="animate-spin" /> Loading census guide…
      </div>
    );
  }
  return <CensusGuideContent guide={guide} />;
}
