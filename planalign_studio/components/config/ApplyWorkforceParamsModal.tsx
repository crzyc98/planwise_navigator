import { useState } from 'react';
import { Check, X, AlertTriangle, ArrowLeft, Info } from 'lucide-react';
import { applyWorkforceParams, Scenario, WorkforceParamsApplyResult } from '../../services/api';

interface ApplyWorkforceParamsModalProps {
  readonly availableScenarios: Scenario[];
  readonly sourceScenarioId: string;
  readonly workspaceId: string;
  readonly onClose: () => void;
}

const WORKFORCE_CATEGORIES = [
  'Compensation settings (merit, COLA, promotion rates)',
  'Workforce & turnover rates',
  'Growth targets',
  'New hire demographics & strategy',
  'Promotion hazard config',
  'Age & tenure bands',
];

type Step = 'select' | 'confirm' | 'result';

export function ApplyWorkforceParamsModal({
  availableScenarios,
  sourceScenarioId,
  workspaceId,
  onClose,
}: ApplyWorkforceParamsModalProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [step, setStep] = useState<Step>('select');
  const [applying, setApplying] = useState(false);
  const [result, setResult] = useState<WorkforceParamsApplyResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedScenarios = availableScenarios.filter(s => selectedIds.has(s.id));

  function toggleScenario(id: string) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleAll() {
    if (selectedIds.size === availableScenarios.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(availableScenarios.map(s => s.id)));
    }
  }

  async function handleApply() {
    setApplying(true);
    setError(null);
    try {
      const res = await applyWorkforceParams(
        workspaceId,
        sourceScenarioId,
        Array.from(selectedIds)
      );
      setResult(res);
      setStep('result');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred');
      setStep('result');
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-overlay bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-surface-raised rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-border flex-shrink-0">
          <h2 className="text-xl font-bold text-ink">
            {step === 'select' && 'Apply Workforce Params to Other Scenarios'}
            {step === 'confirm' && 'Confirm Changes'}
            {step === 'result' && 'Apply Results'}
          </h2>
          <p className="text-sm text-ink-muted mt-1">
            {step === 'select' && 'Select scenarios to receive this scenario\'s workforce parameters'}
            {step === 'confirm' && 'Review what will be overwritten before applying'}
            {step === 'result' && 'Summary of applied changes'}
          </p>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1">
          {step === 'select' && (
            <SelectStep
              scenarios={availableScenarios}
              selectedIds={selectedIds}
              onToggle={toggleScenario}
              onToggleAll={toggleAll}
            />
          )}
          {step === 'confirm' && (
            <ConfirmStep scenarios={selectedScenarios} />
          )}
          {step === 'result' && (
            <ResultStep result={result} error={error} />
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border bg-surface-subtle flex-shrink-0 rounded-b-xl flex justify-between">
          {step === 'select' && (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 text-ink-muted hover:bg-surface-disabled rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => setStep('confirm')}
                disabled={selectedIds.size === 0}
                className="px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg hover:bg-fidelity-dark transition-colors disabled:bg-surface-disabled disabled:cursor-not-allowed font-medium"
              >
                Apply to {selectedIds.size} Scenario{selectedIds.size !== 1 ? 's' : ''}
              </button>
            </>
          )}
          {step === 'confirm' && (
            <>
              <button
                onClick={() => setStep('select')}
                disabled={applying}
                className="px-4 py-2 text-ink-muted hover:bg-surface-disabled rounded-lg transition-colors flex items-center"
              >
                <ArrowLeft size={16} className="mr-1" />
                Back
              </button>
              <button
                onClick={handleApply}
                disabled={applying}
                className="px-4 py-2 bg-warning-solid text-ink-inverse rounded-lg hover:bg-warning-solid-hover transition-colors disabled:bg-surface-disabled disabled:cursor-not-allowed font-medium"
              >
                {applying ? (
                  <>
                    <span className="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-border mr-2 align-middle" />
                    Applying...
                  </>
                ) : (
                  'Confirm & Apply'
                )}
              </button>
            </>
          )}
          {step === 'result' && (
            <div className="w-full flex justify-end">
              {error && !result && (
                <button
                  onClick={() => { setError(null); setStep('confirm'); }}
                  className="px-4 py-2 text-ink-muted hover:bg-surface-disabled rounded-lg transition-colors mr-2"
                >
                  Retry
                </button>
              )}
              <button
                onClick={onClose}
                className="px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg hover:bg-fidelity-dark transition-colors font-medium"
              >
                Done
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SelectStep({
  scenarios,
  selectedIds,
  onToggle,
  onToggleAll,
}: {
  readonly scenarios: Scenario[];
  readonly selectedIds: Set<string>;
  readonly onToggle: (id: string) => void;
  readonly onToggleAll: () => void;
}) {
  if (scenarios.length === 0) {
    return (
      <p className="text-ink-muted text-center py-8">No other scenarios available</p>
    );
  }

  const allSelected = selectedIds.size === scenarios.length;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-ink-muted">
          {selectedIds.size} of {scenarios.length} selected
        </span>
        <button
          onClick={onToggleAll}
          className="text-sm text-fidelity-green hover:text-fidelity-dark font-medium"
        >
          {allSelected ? 'Deselect All' : 'Select All'}
        </button>
      </div>
      {scenarios.map(scenario => (
        <label
          key={scenario.id}
          className={`flex items-start p-4 border rounded-lg cursor-pointer transition-colors ${
            selectedIds.has(scenario.id)
              ? 'border-fidelity-green bg-success-surface'
              : 'border-border hover:border-border-strong'
          }`}
        >
          <input
            type="checkbox"
            checked={selectedIds.has(scenario.id)}
            onChange={() => onToggle(scenario.id)}
            className="mt-1 mr-3 h-4 w-4 text-fidelity-green rounded border-border-strong focus:ring-fidelity-green"
          />
          <div className="flex-1">
            <div className="flex justify-between items-start">
              <div>
                <span className="font-semibold text-ink">{scenario.name}</span>
                <p className="text-sm text-ink-muted mt-0.5">
                  {scenario.description || 'No description'}
                </p>
              </div>
              <span className={`px-2 py-1 text-xs font-medium rounded ml-2 ${
                scenario.status === 'completed'
                  ? 'bg-success-surface text-success-ink'
                  : scenario.status === 'running'
                    ? 'bg-info-surface text-info-ink'
                    : 'bg-surface-subtle text-ink-muted'
              }`}>
                {scenario.status || 'draft'}
              </span>
            </div>
          </div>
        </label>
      ))}
    </div>
  );
}

function ConfirmStep({ scenarios }: { readonly scenarios: Scenario[] }) {
  return (
    <div className="space-y-5">
      <div className="bg-warning-surface border border-warning-border rounded-lg p-4 flex items-start">
        <AlertTriangle className="h-5 w-5 text-warning-ink mt-0.5 flex-shrink-0" />
        <p className="ml-3 text-sm text-warning-ink">
          This will overwrite workforce parameters in{' '}
          <strong>{scenarios.length} scenario{scenarios.length !== 1 ? 's' : ''}</strong>.
          DC plan parameters will not be affected.
        </p>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-ink-muted mb-2">Target Scenarios</h3>
        <ul className="space-y-1">
          {scenarios.map(s => (
            <li key={s.id} className="text-sm text-ink-muted flex items-center">
              <span className="w-1.5 h-1.5 bg-surface-disabled rounded-full mr-2" />
              {s.name}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-ink-muted mb-2">Parameters That Will Be Overwritten</h3>
        <ul className="space-y-1">
          {WORKFORCE_CATEGORIES.map(cat => (
            <li key={cat} className="text-sm text-ink-muted flex items-center">
              <span className="w-1.5 h-1.5 bg-warning-solid rounded-full mr-2" />
              {cat}
            </li>
          ))}
        </ul>
      </div>

      <div className="bg-info-surface border border-info-border rounded-lg p-3 flex items-start">
        <Info className="h-4 w-4 text-info-ink mt-0.5 flex-shrink-0" />
        <p className="ml-2 text-xs text-info-ink">
          DC plan parameters (match formula, core contribution, deferral escalation, eligibility, enrollment) will remain unchanged in target scenarios.
        </p>
      </div>
    </div>
  );
}

function ResultStep({
  result,
  error,
}: {
  readonly result: WorkforceParamsApplyResult | null;
  readonly error: string | null;
}) {
  if (error && !result) {
    return (
      <div className="text-center py-6">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-danger-surface mb-3">
          <X className="h-6 w-6 text-danger-ink" />
        </div>
        <p className="text-ink font-medium">Failed to apply workforce parameters</p>
        <p className="text-sm text-ink-muted mt-1">{error}</p>
      </div>
    );
  }

  if (!result) return null;

  const allSuccess = result.total_failed === 0;

  return (
    <div className="space-y-4">
      <div className="text-center py-2">
        <div className={`inline-flex items-center justify-center w-12 h-12 rounded-full mb-3 ${
          allSuccess ? 'bg-success-surface' : 'bg-warning-surface'
        }`}>
          {allSuccess ? (
            <Check className="h-6 w-6 text-success-ink" />
          ) : (
            <AlertTriangle className="h-6 w-6 text-warning-ink" />
          )}
        </div>
        <p className="text-ink font-medium">
          {allSuccess
            ? `Workforce parameters applied to ${result.total_applied} scenario${result.total_applied !== 1 ? 's' : ''}`
            : `Applied to ${result.total_applied}, failed for ${result.total_failed}`}
        </p>
      </div>

      <div className="space-y-2">
        {result.results.map(r => (
          <div
            key={r.scenario_id}
            className={`flex items-center justify-between p-3 rounded-lg border ${
              r.success
                ? 'border-success-border bg-success-surface'
                : 'border-danger-border bg-danger-surface'
            }`}
          >
            <span className="text-sm font-medium text-ink">
              {r.scenario_name || r.scenario_id}
            </span>
            {r.success ? (
              <Check className="h-4 w-4 text-success-ink" />
            ) : (
              <span className="text-xs text-danger-ink">{r.error}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
