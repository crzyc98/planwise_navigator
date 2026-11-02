import { useConfigContext } from './ConfigContext';
import type { Scenario } from '../../services/api';

interface CopyScenarioModalProps {
  readonly availableScenarios: Scenario[];
  readonly onClose: () => void;
}

export function CopyScenarioModal({ availableScenarios, onClose }: CopyScenarioModalProps) {
  const { copyScenarioConfig } = useConfigContext();

  return (
    <div className="fixed inset-0 bg-overlay bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-surface-raised rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">
        <div className="p-6 border-b border-border flex-shrink-0">
          <h2 className="text-xl font-bold text-ink">Copy Configuration from Scenario</h2>
          <p className="text-sm text-ink-muted mt-1">Select a scenario to copy its settings into this one</p>
        </div>
        <div className="p-6 overflow-y-auto flex-1 space-y-3">
          {availableScenarios.length === 0 ? (
            <p className="text-ink-muted text-center py-8">No other scenarios available to copy from</p>
          ) : (
            availableScenarios.map(scenario => (
              <button
                key={scenario.id}
                onClick={async () => {
                  try {
                    // Load the source exactly as a normal scenario load does, so newer
                    // settings (including ones only hydrated from the resolved engine
                    // config, or not modeled by the form at all) carry over on save.
                    await copyScenarioConfig(scenario.id);
                    onClose();
                  } catch (error) {
                    console.error('Failed to copy scenario config:', error);
                  }
                }}
                className="w-full text-left p-4 border border-border rounded-lg hover:border-fidelity-green hover:bg-success-surface transition-colors"
              >
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-semibold text-ink">{scenario.name}</h3>
                    <p className="text-sm text-ink-muted mt-1">{scenario.description || 'No description'}</p>
                  </div>
                  <span className={`px-2 py-1 text-xs font-medium rounded ${scenario.status === 'completed' ? 'bg-success-surface text-success-ink' : scenario.status === 'running' ? 'bg-info-surface text-info-ink' : 'bg-surface-subtle text-ink-muted'}`}>
                    {scenario.status || 'draft'}
                  </span>
                </div>
              </button>
            ))
          )}
        </div>
        <div className="p-4 border-t border-border bg-surface-subtle flex-shrink-0 rounded-b-xl">
          <button
            onClick={onClose}
            className="px-4 py-2 text-ink-muted hover:bg-surface-disabled rounded-lg transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
