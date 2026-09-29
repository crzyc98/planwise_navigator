import { useEffect, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import {
  applyParamPack,
  getParamPackApplyPreview,
  ParamFitJob,
  ParamPackAcknowledgement,
  ParamPackApplyError,
  ParamPackApplyPreview,
  Scenario,
  ScenarioNameConflictError,
} from '../../services/api';
import { ACKNOWLEDGEMENT_LABELS } from './paramFitHelpers';
import { errorText } from './paramFitUi';

interface ApplyPackModalProps {
  readonly workspaceId: string;
  readonly job: ParamFitJob;
  readonly scenarios: Scenario[];
  readonly onClose: () => void;
  readonly onApplied: (scenario: Scenario) => void;
}

const fieldClass =
  'w-full rounded-md border border-border-strong bg-surface-raised p-2 text-sm text-ink shadow-sm focus:border-fidelity-green focus:ring-fidelity-green disabled:cursor-not-allowed';

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

/** Review exactly what a pack changes, acknowledge its caveats, create a new scenario. */
export function ApplyPackModal({ workspaceId, job, scenarios, onClose, onApplied }: ApplyPackModalProps) {
  const [sourceId, setSourceId] = useState(job.inputs.base_scenario_id);
  const [preview, setPreview] = useState<ParamPackApplyPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [acknowledged, setAcknowledged] = useState<Set<ParamPackAcknowledgement>>(new Set());
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestedName, setSuggestedName] = useState<string | null>(null);

  useEffect(() => {
    if (!sourceId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPreview(null);
    setAcknowledged(new Set());
    getParamPackApplyPreview(workspaceId, job.job_id, sourceId)
      .then((result) => {
        if (cancelled) return;
        setPreview(result);
        setName(result.suggested_name);
      })
      .catch((previewError) => !cancelled && setError(errorText(previewError)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [workspaceId, job.job_id, sourceId]);

  const required = preview?.required_acknowledgements ?? [];
  const allAcknowledged = required.every((ack) => acknowledged.has(ack));
  const cannotSubmit = !preview || !name.trim() || !allAcknowledged || applying;

  function toggle(ack: ParamPackAcknowledgement) {
    setAcknowledged((current) => {
      const next = new Set(current);
      if (next.has(ack)) next.delete(ack);
      else next.add(ack);
      return next;
    });
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!preview || cannotSubmit) return;
    setApplying(true);
    setError(null);
    setSuggestedName(null);
    try {
      const scenario = await applyParamPack(workspaceId, job.job_id, {
        source_scenario_id: preview.source_scenario_id,
        name: name.trim(),
        description: description.trim() || null,
        pack_fingerprint: preview.pack_fingerprint,
        source_config_fingerprint: preview.source_config_fingerprint,
        acknowledgements: Array.from(acknowledged),
      });
      onApplied(scenario);
    } catch (applyError) {
      if (applyError instanceof ScenarioNameConflictError) {
        setError(applyError.detail);
        setSuggestedName(applyError.suggestedName);
      } else if (applyError instanceof ParamPackApplyError && applyError.stale.length) {
        setError([applyError.detail ?? '', ...applyError.stale.map((item) => item.message)].join(' '));
      } else {
        setError(errorText(applyError));
      }
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay bg-opacity-50">
      <div className="mx-4 flex max-h-[85vh] w-full max-w-3xl flex-col rounded-xl bg-surface-raised shadow-xl">
        <div className="flex shrink-0 items-start justify-between border-b border-border p-6">
          <div>
            <h2 className="text-xl font-bold text-ink">Apply parameter pack</h2>
            <p className="mt-1 text-sm text-ink-muted">
              Creates a new scenario from the source below plus the fitted values. The source scenario is not changed.
            </p>
          </div>
          <button type="button" onClick={onClose} disabled={applying} aria-label="Close" className="rounded p-1 text-ink-muted hover:bg-surface-disabled">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={(event) => void submit(event)} className="flex min-h-0 flex-1 flex-col">
          <div className="flex-1 space-y-5 overflow-y-auto p-6">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-ink">Source scenario</span>
              <select value={sourceId} onChange={(event) => setSourceId(event.target.value)} disabled={applying} className={fieldClass}>
                {scenarios.map((scenario) => (
                  <option key={scenario.id} value={scenario.id}>
                    {scenario.name}
                    {scenario.id === job.inputs.base_scenario_id ? ' (fitted against)' : ''}
                  </option>
                ))}
              </select>
            </label>

            {loading && (
              <p className="flex items-center gap-2 text-sm text-ink-muted">
                <Loader2 size={16} className="animate-spin" /> Preparing the review…
              </p>
            )}

            {preview && <DiffList preview={preview} />}

            {required.length > 0 && (
              <fieldset className="space-y-2 rounded-lg border border-warning-border bg-warning-surface p-4 text-sm text-warning-ink">
                <legend className="px-1 font-medium">Acknowledge before applying</legend>
                {required.map((ack) => (
                  <label key={ack} className="flex cursor-pointer items-start gap-2">
                    <input type="checkbox" checked={acknowledged.has(ack)} onChange={() => toggle(ack)} className="mt-0.5 h-4 w-4" />
                    <span>{ACKNOWLEDGEMENT_LABELS[ack]}</span>
                  </label>
                ))}
              </fieldset>
            )}

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-ink">New scenario name</span>
              <input
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                  setSuggestedName(null);
                }}
                maxLength={100}
                disabled={applying}
                className={fieldClass}
                required
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-ink">
                Description <span className="font-normal text-ink-muted">(optional)</span>
              </span>
              <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={2} disabled={applying} className={fieldClass} />
            </label>

            {error && (
              <div className="rounded-lg border border-danger-border bg-danger-surface p-3 text-sm text-danger-ink">
                <p>{error}</p>
                {suggestedName && (
                  <button type="button" onClick={() => setName(suggestedName)} className="mt-2 font-medium underline underline-offset-2">
                    Use suggested name: {suggestedName}
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="flex shrink-0 justify-end gap-2 rounded-b-xl border-t border-border bg-surface-subtle p-4">
            <button type="button" onClick={onClose} disabled={applying} className="rounded-lg px-4 py-2 text-ink-muted hover:bg-surface-disabled">
              Cancel
            </button>
            <button
              type="submit"
              disabled={cannotSubmit}
              className="rounded-lg bg-fidelity-green px-4 py-2 font-medium text-ink-inverse transition-colors hover:bg-fidelity-dark disabled:cursor-not-allowed disabled:bg-surface-disabled"
            >
              {applying ? 'Creating…' : 'Create scenario'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function DiffList({ preview }: { preview: ParamPackApplyPreview }) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-ink">
        {preview.diff.length} setting{preview.diff.length === 1 ? '' : 's'} will change
      </h3>
      <div className="max-h-64 overflow-auto rounded-md border border-border">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-surface-subtle text-left text-xs uppercase tracking-wide text-ink-muted">
            <tr>
              <th className="px-3 py-2">Setting</th>
              <th className="px-3 py-2">Now</th>
              <th className="px-3 py-2">After</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {preview.diff.map((delta) => (
              <tr key={delta.path}>
                <td className="px-3 py-1.5 font-mono text-xs text-ink">{delta.path}</td>
                <td className="max-w-xs truncate px-3 py-1.5 text-ink-muted" title={formatValue(delta.a)}>{formatValue(delta.a)}</td>
                <td className="max-w-xs truncate px-3 py-1.5 text-ink" title={formatValue(delta.b)}>{formatValue(delta.b)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-muted">
        Also carried with the scenario: {preview.seed_files.join(', ')} (fitted tables layered into every run).
      </p>
    </div>
  );
}
