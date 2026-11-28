import React from 'react';

interface EffectiveYearControlProps {
  /** Null is the first simulation year: designs apply immediately. */
  value: number | null;
  firstYear: number | undefined;
  options: number[];
  anchorName: string | undefined;
  /** Set when another view option can't be combined with a later year. */
  blockedReason: string | null;
  /** Accuracy warnings from the API; shown only while a later year is applied. */
  warnings: string[];
  applied: boolean;
  onChange: (year: number | null) => void;
}

const SELECT = 'rounded-md border border-border bg-surface-raised px-2 py-1 text-xs font-medium normal-case text-ink outline-none focus:ring-1 focus:ring-brand-green disabled:cursor-not-allowed disabled:opacity-50';

/** The year non-anchor scenarios' designs take effect on Cost Comparison (#791). */
export default function EffectiveYearControl(props: Readonly<EffectiveYearControlProps>) {
  const { value, firstYear, options, anchorName, blockedReason, warnings, applied, onChange } = props;
  const anchor = anchorName ?? 'the anchor';
  const description = value === null
    ? "Each scenario's design applies from the first simulation year."
    : `Before ${value}, scenarios other than ${anchor} show ${anchor}'s figures; from ${value} on, their own.`;
  return (
    <div className="-mt-2 mb-6 space-y-2">
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-surface-subtle px-4 py-3">
        <label className="flex items-center gap-2 text-xs font-bold text-ink-muted uppercase tracking-wide">
          Effective year
          <select
            value={value ?? firstYear ?? ''}
            disabled={blockedReason !== null || options.length === 0}
            aria-describedby={blockedReason ? 'effective-year-blocked' : undefined}
            onChange={event => {
              const year = Number(event.target.value);
              onChange(year === firstYear ? null : year);
            }}
            className={SELECT}
          >
            {options.map(year => (
              <option key={year} value={year}>
                {year === firstYear ? `${year} (immediately)` : year}
              </option>
            ))}
          </select>
        </label>
        <span className="text-xs text-ink-muted">{description}</span>
      </div>
      {blockedReason && (
        <p id="effective-year-blocked" className="text-xs text-ink-muted">{blockedReason}</p>
      )}
      {applied && warnings.map(warning => (
        <div key={warning} role="alert" className="rounded-lg border border-warning-border bg-warning-surface px-4 py-2 text-xs text-warning-ink">
          {warning}
        </div>
      ))}
    </div>
  );
}
