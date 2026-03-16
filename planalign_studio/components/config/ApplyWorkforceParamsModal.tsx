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
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-200 flex-shrink-0">
          <h2 className="text-xl font-bold text-gray-900">
            {step === 'select' && 'Apply Workforce Params to Other Scenarios'}
            {step === 'confirm' && 'Confirm Changes'}
            {step === 'result' && 'Apply Results'}
          </h2>
          <p className="text-sm text-gray-500 mt-1">
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
        <div className="p-4 border-t border-gray-200 bg-gray-50 flex-shrink-0 rounded-b-xl flex justify-between">
          {step === 'select' && (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 text-gray-700 hover:bg-gray-200 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => setStep('confirm')}
                disabled={selectedIds.size === 0}
                className="px-4 py-2 bg-fidelity-green text-white rounded-lg hover:bg-fidelity-dark transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed font-medium"
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
                className="px-4 py-2 text-gray-700 hover:bg-gray-200 rounded-lg transition-colors flex items-center"
              >
                <ArrowLeft size={16} className="mr-1" />
                Back
              </button>
              <button
                onClick={handleApply}
                disabled={applying}
                className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed font-medium"
              >
                {applying ? (
                  <>
                    <span className="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2 align-middle" />
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
                  className="px-4 py-2 text-gray-700 hover:bg-gray-200 rounded-lg transition-colors mr-2"
                >
                  Retry
                </button>
              )}
              <button
                onClick={onClose}
                className="px-4 py-2 bg-fidelity-green text-white rounded-lg hover:bg-fidelity-dark transition-colors font-medium"
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
      <p className="text-gray-500 text-center py-8">No other scenarios available</p>
    );
  }

  const allSelected = selectedIds.size === scenarios.length;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-500">
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
              ? 'border-fidelity-green bg-green-50'
              : 'border-gray-200 hover:border-gray-300'
          }`}
        >
          <input
            type="checkbox"
            checked={selectedIds.has(scenario.id)}
            onChange={() => onToggle(scenario.id)}
            className="mt-1 mr-3 h-4 w-4 text-fidelity-green rounded border-gray-300 focus:ring-fidelity-green"
          />
          <div className="flex-1">
            <div className="flex justify-between items-start">
              <div>
                <span className="font-semibold text-gray-900">{scenario.name}</span>
                <p className="text-sm text-gray-500 mt-0.5">
                  {scenario.description || 'No description'}
                </p>
              </div>
              <span className={`px-2 py-1 text-xs font-medium rounded ml-2 ${
                scenario.status === 'completed'
                  ? 'bg-green-100 text-green-700'
                  : scenario.status === 'running'
                    ? 'bg-blue-100 text-blue-700'
                    : 'bg-gray-100 text-gray-600'
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
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start">
        <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5 flex-shrink-0" />
        <p className="ml-3 text-sm text-amber-800">
          This will overwrite workforce parameters in{' '}
          <strong>{scenarios.length} scenario{scenarios.length !== 1 ? 's' : ''}</strong>.
          DC plan parameters will not be affected.
        </p>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Target Scenarios</h3>
        <ul className="space-y-1">
          {scenarios.map(s => (
            <li key={s.id} className="text-sm text-gray-600 flex items-center">
              <span className="w-1.5 h-1.5 bg-gray-400 rounded-full mr-2" />
              {s.name}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Parameters That Will Be Overwritten</h3>
        <ul className="space-y-1">
          {WORKFORCE_CATEGORIES.map(cat => (
            <li key={cat} className="text-sm text-gray-600 flex items-center">
              <span className="w-1.5 h-1.5 bg-amber-400 rounded-full mr-2" />
              {cat}
            </li>
          ))}
        </ul>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 flex items-start">
        <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
        <p className="ml-2 text-xs text-blue-700">
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
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-red-100 mb-3">
          <X className="h-6 w-6 text-red-600" />
        </div>
        <p className="text-gray-900 font-medium">Failed to apply workforce parameters</p>
        <p className="text-sm text-gray-500 mt-1">{error}</p>
      </div>
    );
  }

  if (!result) return null;

  const allSuccess = result.total_failed === 0;

  return (
    <div className="space-y-4">
      <div className="text-center py-2">
        <div className={`inline-flex items-center justify-center w-12 h-12 rounded-full mb-3 ${
          allSuccess ? 'bg-green-100' : 'bg-amber-100'
        }`}>
          {allSuccess ? (
            <Check className="h-6 w-6 text-green-600" />
          ) : (
            <AlertTriangle className="h-6 w-6 text-amber-600" />
          )}
        </div>
        <p className="text-gray-900 font-medium">
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
                ? 'border-green-200 bg-green-50'
                : 'border-red-200 bg-red-50'
            }`}
          >
            <span className="text-sm font-medium text-gray-800">
              {r.scenario_name || r.scenario_id}
            </span>
            {r.success ? (
              <Check className="h-4 w-4 text-green-600" />
            ) : (
              <span className="text-xs text-red-600">{r.error}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
