import React from 'react';

interface Props {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

/** True for a complete YYYY-MM-DD date, as a date input reports it. */
export function isCensusAsOfDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value));
}

/** The date the census was taken. Required at import. */
export default function CensusAsOfDateField({ value, onChange, disabled }: Props) {
  return (
    <div className="space-y-1">
      <label htmlFor="census-as-of-date" className="block text-sm font-semibold text-ink-muted">
        Census as-of date
      </label>
      <input
        id="census-as-of-date"
        type="date"
        required
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="px-3 py-2 text-sm border border-border rounded-lg bg-surface-raised text-ink"
      />
      <p className="text-xs text-ink-subtle">
        The date this census was taken. We filled in December 31 of the census year read from hire dates;
        change it if the file was pulled on another date. Rows marked inactive with no termination date
        leave the workforce on this date.
      </p>
    </div>
  );
}
