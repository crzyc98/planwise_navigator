import { useState } from 'react';
import { Server, Shield, AlertTriangle, Check, Trash2 } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { deleteScenarioDatabase } from '../../services/api';

export function AdvancedSection() {
  const { formData, handleChange, activeWorkspace, scenarioId } = useConfigContext();
  const [dbDeleteStatus, setDbDeleteStatus] = useState<'idle' | 'confirming' | 'deleting' | 'success' | 'error'>('idle');
  const [dbDeleteMessage, setDbDeleteMessage] = useState('');

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-border pb-4">
        <h2 className="text-lg font-bold text-ink">Advanced Execution Settings</h2>
        <p className="text-sm text-ink-muted">Configure engine performance, logging, and validation rules.</p>
      </div>

      {/* System Configuration */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-surface-raised p-6 rounded-lg border border-border shadow-sm">
          <h3 className="text-sm font-bold text-ink flex items-center mb-4">
            <Server size={16} className="mr-2 text-info-ink" /> System Resources
          </h3>
          <div className="space-y-4">
            <label htmlFor="adv-multithreading" className="flex items-center justify-between cursor-pointer">
              <span className="text-sm text-ink-muted">Enable Multithreading</span>
              <input
                id="adv-multithreading"
                type="checkbox"
                name="enableMultithreading"
                checked={formData.enableMultithreading}
                onChange={handleChange}
                className="h-5 w-5 text-fidelity-green focus:ring-fidelity-green border-border-strong rounded"
              />
            </label>
            <div className="flex items-center justify-between">
              <span className="text-sm text-ink-muted">Checkpoint Frequency</span>
              <select
                name="checkpointFrequency"
                value={formData.checkpointFrequency}
                onChange={handleChange}
                className="text-sm border-border-strong rounded-md shadow-sm focus:ring-fidelity-green focus:border-fidelity-green"
              >
                <option value="year">Every Year</option>
                <option value="stage">Every Stage (Debug)</option>
                <option value="none">Disabled (Fastest)</option>
              </select>
            </div>
            <div className="pt-2 border-t border-border">
              <label htmlFor="adv-memory-limit" className="block text-xs font-medium text-ink-muted mb-1">Max Memory Limit (GB)</label>
              <input
                id="adv-memory-limit"
                type="number"
                name="memoryLimitGB"
                value={formData.memoryLimitGB}
                onChange={handleChange}
                className="w-full text-sm border-border-strong rounded-md p-1.5 border"
              />
            </div>
          </div>
        </div>

        <div className="bg-surface-raised p-6 rounded-lg border border-border shadow-sm">
          <h3 className="text-sm font-bold text-ink flex items-center mb-4">
            <Shield size={16} className="mr-2 text-info-ink" /> Safety & Logging
          </h3>
          <div className="space-y-4">
            <label htmlFor="adv-strict-validation" className="flex items-center justify-between cursor-pointer">
              <span className="text-sm text-ink-muted">Strict Schema Validation</span>
              <input
                id="adv-strict-validation"
                type="checkbox"
                name="strictValidation"
                checked={formData.strictValidation}
                onChange={handleChange}
                className="h-5 w-5 text-fidelity-green focus:ring-fidelity-green border-border-strong rounded"
              />
            </label>
            <div className="flex items-center justify-between">
              <span className="text-sm text-ink-muted">Logging Level</span>
              <select
                name="logLevel"
                value={formData.logLevel}
                onChange={handleChange}
                className="text-sm border-border-strong rounded-md shadow-sm focus:ring-fidelity-green focus:border-fidelity-green"
              >
                <option value="DEBUG">DEBUG</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Danger Zone */}
      {scenarioId && activeWorkspace?.id && (
        <div className="border border-danger-border rounded-lg p-6 bg-danger-surface/50">
          <h3 className="text-sm font-bold text-danger-ink flex items-center mb-2">
            <AlertTriangle size={16} className="mr-2" /> Danger Zone
          </h3>
          <p className="text-sm text-ink-muted mb-4">
            Irreversible actions that affect this scenario's simulation data.
          </p>

          <div className="flex items-center justify-between bg-surface-raised p-4 rounded-md border border-danger-border">
            <div>
              <p className="text-sm font-medium text-ink">Delete Simulation Database</p>
              <p className="text-xs text-ink-muted mt-0.5">
                Removes all simulation results so you can run a fresh simulation. Configuration is preserved.
              </p>
            </div>
            <div className="flex items-center gap-2">
              {dbDeleteStatus === 'confirming' ? (
                <>
                  <button
                    onClick={() => setDbDeleteStatus('idle')}
                    className="px-3 py-1.5 text-sm text-ink-muted bg-surface-subtle hover:bg-surface-disabled rounded-md transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={async () => {
                      setDbDeleteStatus('deleting');
                      try {
                        const result = await deleteScenarioDatabase(activeWorkspace.id, scenarioId);
                        setDbDeleteMessage(result.message);
                        setDbDeleteStatus('success');
                        setTimeout(() => setDbDeleteStatus('idle'), 4000);
                      } catch (err) {
                        setDbDeleteMessage(err instanceof Error ? err.message : 'Failed to delete database');
                        setDbDeleteStatus('error');
                        setTimeout(() => setDbDeleteStatus('idle'), 4000);
                      }
                    }}
                    className="px-3 py-1.5 text-sm text-ink-inverse bg-danger-solid hover:bg-danger-solid-hover rounded-md transition-colors font-medium"
                  >
                    Yes, delete it
                  </button>
                </>
              ) : dbDeleteStatus === 'deleting' ? (
                <span className="text-sm text-ink-muted">Deleting...</span>
              ) : dbDeleteStatus === 'success' ? (
                <span className="text-sm text-success-ink flex items-center gap-1">
                  <Check size={14} /> {dbDeleteMessage}
                </span>
              ) : dbDeleteStatus === 'error' ? (
                <span className="text-sm text-danger-ink">{dbDeleteMessage}</span>
              ) : (
                <button
                  onClick={() => setDbDeleteStatus('confirming')}
                  className="px-3 py-1.5 text-sm text-danger-ink border border-danger-border hover:bg-danger-surface rounded-md transition-colors flex items-center gap-1.5"
                >
                  <Trash2 size={14} /> Delete Database
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
