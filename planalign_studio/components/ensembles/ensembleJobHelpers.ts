import { ApiError } from '../../services/api';
import type { EnsembleEstimate, EnsembleJob, EnsembleJobStatus } from '../../services/api';

/** Seed-count bounds the API enforces (planalign_api/models/ensemble_job.py). */
export const MIN_SEEDS = 5;
export const MAX_SEEDS = 50;
export const DEFAULT_SEEDS = 10;

/** Why the range varies, and what it is not. Shown wherever an ensemble is run or read. */
export const RANGE_DISCLAIMER =
  'The P10–P90 range shows how results move across random seeds for hiring, termination and promotion draws. ' +
  "Enrollment draws don't change with the seed, so they don't widen the range. " +
  "It is the spread of simulated outcomes, not a statistical margin of error.";

export type Tone = 'success' | 'warning' | 'danger' | 'neutral' | 'info';

export const TONE_CLASSES: Record<Tone, string> = {
  success: 'border-success-border bg-success-surface text-success-ink',
  warning: 'border-warning-border bg-warning-surface text-warning-ink',
  danger: 'border-danger-border bg-danger-surface text-danger-ink',
  neutral: 'border-border bg-surface-subtle text-ink-muted',
  info: 'border-info-border bg-info-surface text-info-ink',
};

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.detail ?? err.message;
  return err instanceof Error ? err.message : 'Something went wrong.';
}

export function isActive(status: EnsembleJobStatus): boolean {
  return status === 'queued' || status === 'running';
}

/** A seed count the API will accept, or null. */
export function parseSeedCount(raw: string): number | null {
  if (!/^\d+$/.test(raw.trim())) return null;
  const value = Number(raw);
  return value >= MIN_SEEDS && value <= MAX_SEEDS ? value : null;
}

/** "2026–2030", or "2026" for a one-year ensemble. */
export function yearRange(start: number, end: number): string {
  return start === end ? `${start}` : `${start}–${end}`;
}

/**
 * Start sends only the seed count, so the API re-reads the scenario. If its years or base seed
 * changed since the estimate, say so rather than let the started job differ silently.
 */
export function startMismatch(reviewed: EnsembleEstimate, started: Pick<EnsembleJob, 'seeds' | 'start_year' | 'end_year'>): string | null {
  const reviewedYears = yearRange(reviewed.start_year, reviewed.end_year);
  const startedYears = yearRange(started.start_year, started.end_year);
  if (reviewedYears !== startedYears) {
    return `Started with ${startedYears} instead of the reviewed ${reviewedYears} because the scenario changed.`;
  }
  const sameSeeds =
    reviewed.seeds.length === started.seeds.length && reviewed.seeds.every((seed, i) => seed === started.seeds[i]);
  return sameSeeds ? null : 'Started with different seeds than the reviewed estimate because the scenario changed.';
}

/** "about 25 min", "about 2 h 10 min", "under 1 min". */
export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  if (minutes < 1) return 'under 1 min';
  if (minutes < 60) return `about ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `about ${hours} h` : `about ${hours} h ${rest} min`;
}

/** Disk in MB below 1 GB, otherwise GB with one decimal. */
export function formatDisk(mib: number): string {
  if (mib < 1024) return `${Math.max(1, Math.round(mib))} MB`;
  return `${(mib / 1024).toFixed(1)} GB`;
}

export function timeBasisLabel(basis: EnsembleEstimate['time_basis']): string {
  return basis === 'measured'
    ? "Based on this scenario's last run."
    : "Rough estimate; this scenario hasn't run yet.";
}

export function estimateSummary(estimate: EnsembleEstimate): string {
  const years = yearRange(estimate.start_year, estimate.end_year);
  const runs = estimate.run_count === 1 ? '1 run' : `${estimate.run_count} runs`;
  return `${runs} of ${years}, ${formatDuration(estimate.estimated_seconds)}, up to ${formatDisk(estimate.estimated_disk_mib)} of disk while it runs.`;
}

export function progressLabel(job: Pick<EnsembleJob, 'status' | 'progress'>): string {
  if (job.status === 'queued') return 'Waiting for another simulation to finish';
  const { seeds_total: total, seeds_completed: done, seeds_failed: failed, current_seed: current } = job.progress;
  const parts = [`${done} of ${total} seeds done`];
  if (failed > 0) parts.push(`${failed} failed`);
  const base = parts.join(', ');
  return current === null ? base : `${base} · running seed ${current}`;
}

export interface StatusCopy {
  label: string;
  tone: Tone;
  /** One plain sentence on what happened; null when the label says it all. */
  detail: string | null;
}

/** Status chip and outcome sentence for one job. */
export function statusCopy(job: Pick<EnsembleJob, 'status' | 'error' | 'progress' | 'failed_seeds' | 'seed_count'>): StatusCopy {
  switch (job.status) {
    case 'queued':
      return { label: 'Queued', tone: 'info', detail: 'Waiting for another simulation to finish.' };
    case 'running':
      return { label: 'Running', tone: 'info', detail: null };
    case 'completed':
      return { label: 'Completed', tone: 'success', detail: null };
    case 'partial': {
      const failed = job.failed_seeds.length || job.progress.seeds_failed;
      return {
        label: 'Partial',
        tone: 'warning',
        detail: `${failed} of ${job.seed_count} seeds failed; the results use the ${job.seed_count - failed} that finished.`,
      };
    }
    case 'cancelled':
      return { label: 'Cancelled', tone: 'neutral', detail: 'Cancelled before it finished; no results were kept.' };
    case 'failed':
      return failedCopy(job.error);
  }
}

function failedCopy(error: EnsembleJob['error']): StatusCopy {
  // The API words an interrupted job's message itself ("Studio restarted while this ensemble was queued...").
  return {
    label: error?.kind === 'interrupted' ? 'Interrupted' : 'Failed',
    tone: 'danger',
    detail: error?.message ?? 'The ensemble stopped before it finished.',
  };
}
