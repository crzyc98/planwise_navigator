import type { ReactNode } from 'react';
import { ApiError } from '../../services/api';
import { Tone, TONE_CLASSES } from './paramFitHelpers';

/** Coerce any error (incl. FastAPI 422 detail arrays) to a display string. */
export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.detail ?? `${error.status} ${error.statusText}`;
  return error instanceof Error ? error.message : String(error);
}

/** Numbered step heading, matching the Optimizer page. */
export function StepHeader({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-fidelity-green text-sm font-semibold text-ink-inverse">
        {n}
      </span>
      <div>
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        <p className="text-sm text-ink-muted">{children}</p>
      </div>
    </div>
  );
}

export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-semibold uppercase ${TONE_CLASSES[tone]}`}>
      {children}
    </span>
  );
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: Tone }) {
  return (
    <div className={`rounded-lg border p-3 ${tone ? TONE_CLASSES[tone] : 'border-border bg-surface-raised'}`}>
      <div className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</div>
      <div className="mt-1 text-lg font-semibold text-ink">{value}</div>
    </div>
  );
}
