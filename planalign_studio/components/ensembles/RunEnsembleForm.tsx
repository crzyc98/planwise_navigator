import { useState } from 'react';
import { Loader2, Play } from 'lucide-react';
import { EnsembleEstimate, EnsembleJob, Scenario, estimateEnsemble, startEnsemble } from '../../services/api';
import {
  DEFAULT_SEEDS,
  MAX_SEEDS,
  MIN_SEEDS,
  errorMessage,
  estimateSummary,
  parseSeedCount,
  startMismatch,
  timeBasisLabel,
} from './ensembleJobHelpers';

interface RunEnsembleFormProps {
  readonly workspaceId: string;
  readonly scenarios: Scenario[];
  /** `notice` is set when the started job differs from the reviewed estimate. */
  readonly onStarted: (job: EnsembleJob, notice: string | null) => void;
}

interface Review {
  scenarioId: string;
  scenarioName: string;
  estimate: EnsembleEstimate;
}

const INPUT_CLASS =
  'w-full rounded-md border border-border-strong bg-surface-raised p-2 text-sm text-ink shadow-sm focus:border-brand-green focus:ring-brand-green';

/** Pick a scenario and seed count, review the estimate, then start. */
export function RunEnsembleForm({ workspaceId, scenarios, onStarted }: RunEnsembleFormProps) {
  const [pickedId, setPickedId] = useState('');
  const [seedsRaw, setSeedsRaw] = useState(String(DEFAULT_SEEDS));
  // The estimate is tied to what it was made for; Start runs that scenario and seed count.
  const [review, setReview] = useState<Review | null>(null);
  const [busy, setBusy] = useState<'estimate' | 'start' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const scenarioId = scenarios.some((s) => s.id === pickedId) ? pickedId : (scenarios[0]?.id ?? '');

  // Any change to the inputs invalidates the estimate the analyst is looking at.
  function edit(apply: () => void) {
    apply();
    setReview(null);
    setError(null);
  }

  const seedCount = parseSeedCount(seedsRaw);

  async function requestEstimate() {
    if (seedCount === null || !scenarioId) return;
    setBusy('estimate');
    setError(null);
    try {
      const estimate = await estimateEnsemble(workspaceId, scenarioId, seedCount);
      const scenarioName = scenarios.find((s) => s.id === scenarioId)?.name ?? scenarioId;
      setReview({ scenarioId, scenarioName, estimate });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function start() {
    if (review === null) return;
    setBusy('start');
    setError(null);
    try {
      const job = await startEnsemble(workspaceId, review.scenarioId, review.estimate.seed_count);
      onStarted(job, startMismatch(review.estimate, job));
      setReview(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-[2fr_1fr]">
        <label className="text-sm">
          <span className="mb-1 block text-ink-muted">Scenario</span>
          <select className={INPUT_CLASS} value={scenarioId} onChange={(e) => edit(() => setPickedId(e.target.value))}>
            {scenarios.map((scenario) => (
              <option key={scenario.id} value={scenario.id}>
                {scenario.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-ink-muted">Seeds</span>
          <input
            type="number"
            min={MIN_SEEDS}
            max={MAX_SEEDS}
            step={1}
            className={INPUT_CLASS}
            value={seedsRaw}
            onChange={(e) => edit(() => setSeedsRaw(e.target.value))}
          />
          <span className={`mt-1 block text-xs ${seedCount === null ? 'text-danger-ink' : 'text-ink-muted'}`}>
            {MIN_SEEDS} to {MAX_SEEDS}. More seeds give a steadier range but take longer.
          </span>
        </label>
      </div>

      {review === null ? (
        <button
          type="button"
          onClick={() => void requestEstimate()}
          disabled={seedCount === null || !scenarioId || busy !== null}
          className="flex items-center gap-2 rounded-md bg-brand-green px-4 py-2 text-sm font-medium text-ink-inverse disabled:opacity-50"
        >
          {busy === 'estimate' && <Loader2 size={14} className="animate-spin" />}
          Review estimate
        </button>
      ) : (
        <div className="space-y-3 rounded-lg border border-border bg-surface-subtle p-4 text-sm">
          <p className="font-medium text-ink">
            {review.scenarioName}, {review.estimate.seed_count} seeds
          </p>
          <p className="text-ink">{estimateSummary(review.estimate)}</p>
          <p className="text-xs text-ink-muted">
            {timeBasisLabel(review.estimate.time_basis)} Seeds run one at a time, and the ensemble waits if another simulation is
            running. Only the combined results are kept.
          </p>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void start()}
              disabled={busy !== null}
              className="flex items-center gap-2 rounded-md bg-brand-green px-4 py-2 text-sm font-medium text-ink-inverse disabled:opacity-50"
            >
              {busy === 'start' ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
              Start ensemble
            </button>
            <button
              type="button"
              onClick={() => setReview(null)}
              disabled={busy !== null}
              className="rounded-md border border-border-strong px-3 py-2 text-sm text-ink hover:bg-surface-raised disabled:opacity-50"
            >
              Back
            </button>
          </div>
        </div>
      )}
      {error && <p className="text-sm text-danger-ink">{error}</p>}
    </div>
  );
}
