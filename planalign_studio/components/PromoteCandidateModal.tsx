import { useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import {
  ApiError,
  Candidate,
  promoteOptimizerCandidate,
  Scenario,
  ScenarioNameConflictError,
} from '../services/api';

interface PromoteCandidateModalProps {
  readonly runId: string;
  readonly candidate: Candidate;
  readonly workspaceId: string;
  readonly availableScenarios: Scenario[];
  readonly onClose: () => void;
  readonly onPromoted: (scenario: Scenario) => void;
}

function defaultScenarioName(scenario: Scenario | undefined): string {
  return `${scenario?.name ?? 'Scenario'} + optimizer candidate`;
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.detail ?? `${error.status} ${error.statusText}`;
  return error instanceof Error ? error.message : String(error);
}

export function PromoteCandidateModal({
  runId,
  candidate,
  workspaceId,
  availableScenarios,
  onClose,
  onPromoted,
}: PromoteCandidateModalProps) {
  const [sourceScenarioId, setSourceScenarioId] = useState(availableScenarios[0]?.id ?? '');
  const [name, setName] = useState(defaultScenarioName(availableScenarios[0]));
  const [description, setDescription] = useState('');
  const [force, setForce] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestedName, setSuggestedName] = useState<string | null>(null);
  const requiresOverride = candidate.status !== 'feasible';

  useEffect(() => {
    if (!sourceScenarioId && availableScenarios[0]) {
      setSourceScenarioId(availableScenarios[0].id);
      setName((currentName) =>
        currentName === defaultScenarioName(undefined)
          ? defaultScenarioName(availableScenarios[0])
          : currentName
      );
    }
  }, [availableScenarios, sourceScenarioId]);

  function handleSourceScenarioChange(nextId: string) {
    const sourceScenario = availableScenarios.find((scenario) => scenario.id === nextId);
    setSourceScenarioId(nextId);
    setName(defaultScenarioName(sourceScenario));
    setError(null);
    setSuggestedName(null);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!sourceScenarioId || !name.trim() || (requiresOverride && !force)) return;

    setApplying(true);
    setError(null);
    setSuggestedName(null);
    try {
      const scenario = await promoteOptimizerCandidate(runId, candidate.candidate_id, {
        workspaceId,
        sourceScenarioId,
        name: name.trim(),
        description: description.trim() || undefined,
        force: requiresOverride ? force : false,
      });
      onPromoted(scenario);
      onClose();
    } catch (submissionError) {
      if (submissionError instanceof ScenarioNameConflictError) {
        setError(submissionError.detail);
        setSuggestedName(submissionError.suggestedName);
      } else {
        setError(errorText(submissionError));
      }
    } finally {
      setApplying(false);
    }
  }

  const cannotSubmit = !sourceScenarioId || !name.trim() || applying || (requiresOverride && !force);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay bg-opacity-50">
      <div className="mx-4 flex max-h-[80vh] w-full max-w-xl flex-col rounded-xl bg-surface-raised shadow-xl">
        <div className="flex shrink-0 items-start justify-between border-b border-border p-6">
          <div>
            <h2 className="text-xl font-bold text-ink">Create Scenario from Candidate</h2>
            <p className="mt-1 text-sm text-ink-muted">
              Create an editable scenario using candidate {candidate.candidate_id}.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={applying}
            className="rounded p-1 text-ink-muted transition-colors hover:bg-surface-disabled disabled:cursor-not-allowed"
            aria-label="Close"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <div className="flex-1 space-y-5 overflow-y-auto p-6">
            {requiresOverride && (
              <div className="flex items-start gap-3 rounded-lg border border-warning-border bg-warning-surface p-4">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning-ink" />
                <div className="text-sm text-warning-ink">
                  <p>
                    This candidate has status <strong>{candidate.status}</strong> and needs an explicit override to promote.
                  </p>
                  <label className="mt-3 flex cursor-pointer items-start gap-2">
                    <input
                      type="checkbox"
                      checked={force}
                      onChange={(event) => setForce(event.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-border-strong text-fidelity-green focus:ring-fidelity-green"
                    />
                    <span>I understand this candidate is {candidate.status}; promote anyway.</span>
                  </label>
                </div>
              </div>
            )}

            {availableScenarios.length === 0 ? (
              <div className="rounded-lg border border-warning-border bg-warning-surface p-4 text-sm text-warning-ink">
                No source scenarios are available in this workspace. Create a source scenario before promoting a candidate.
              </div>
            ) : (
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-ink">Source scenario</span>
                <select
                  value={sourceScenarioId}
                  onChange={(event) => handleSourceScenarioChange(event.target.value)}
                  disabled={applying}
                  className="w-full rounded-md border border-border-strong bg-surface-raised p-2 text-sm text-ink shadow-sm focus:border-fidelity-green focus:ring-fidelity-green disabled:cursor-not-allowed"
                >
                  {availableScenarios.map((scenario) => (
                    <option key={scenario.id} value={scenario.id}>
                      {scenario.name}
                    </option>
                  ))}
                </select>
                <span className="mt-1 block text-xs text-ink-muted">
                  The candidate values will be applied to this scenario's current configuration.
                </span>
              </label>
            )}

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-ink">Scenario name</span>
              <input
                type="text"
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                  setSuggestedName(null);
                }}
                maxLength={100}
                disabled={applying}
                className="w-full rounded-md border border-border-strong bg-surface-raised p-2 text-sm text-ink shadow-sm focus:border-fidelity-green focus:ring-fidelity-green disabled:cursor-not-allowed"
                required
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-ink">Description <span className="font-normal text-ink-muted">(optional)</span></span>
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                disabled={applying}
                rows={3}
                className="w-full resize-y rounded-md border border-border-strong bg-surface-raised p-2 text-sm text-ink shadow-sm focus:border-fidelity-green focus:ring-fidelity-green disabled:cursor-not-allowed"
              />
            </label>

            {error && (
              <div className="rounded-lg border border-danger-border bg-danger-surface p-3 text-sm text-danger-ink">
                <p>{error}</p>
                {suggestedName && (
                  <button
                    type="button"
                    onClick={() => {
                      setName(suggestedName);
                      setSuggestedName(null);
                    }}
                    className="mt-2 font-medium text-danger-ink underline underline-offset-2"
                  >
                    Use suggested name: {suggestedName}
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="flex shrink-0 justify-end gap-2 rounded-b-xl border-t border-border bg-surface-subtle p-4">
            <button
              type="button"
              onClick={onClose}
              disabled={applying}
              className="rounded-lg px-4 py-2 text-ink-muted transition-colors hover:bg-surface-disabled disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={cannotSubmit}
              className="rounded-lg bg-fidelity-green px-4 py-2 font-medium text-ink-inverse transition-colors hover:bg-fidelity-dark disabled:cursor-not-allowed disabled:bg-surface-disabled"
            >
              {applying ? 'Creating...' : 'Create scenario'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
