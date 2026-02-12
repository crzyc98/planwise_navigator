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
      <div className="border-b border-gray-100 pb-4">
        <h2 className="text-lg font-bold text-gray-900">Advanced Execution Settings</h2>
        <p className="text-sm text-gray-500">Configure engine performance, logging, and validation rules.</p>
      </div>

      {/* System Configuration */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
          <h3 className="text-sm font-bold text-gray-900 flex items-center mb-4">
            <Server size={16} className="mr-2 text-blue-500" /> System Resources
          </h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-700">Enable Multithreading</span>
              <input
                type="checkbox"
                name="enableMultithreading"
                checked={formData.enableMultithreading}
                onChange={handleChange}
                className="h-5 w-5 text-fidelity-green focus:ring-fidelity-green border-gray-300 rounded"
              />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-700">Checkpoint Frequency</span>
              <select
                name="checkpointFrequency"
                value={formData.checkpointFrequency}
                onChange={handleChange}
                className="text-sm border-gray-300 rounded-md shadow-sm focus:ring-fidelity-green focus:border-fidelity-green"
              >
                <option value="year">Every Year</option>
                <option value="stage">Every Stage (Debug)</option>
                <option value="none">Disabled (Fastest)</option>
              </select>
            </div>
            <div className="pt-2 border-t border-gray-100">
              <label className="block text-xs font-medium text-gray-500 mb-1">Max Memory Limit (GB)</label>
              <input
                type="number"
                name="memoryLimitGB"
                value={formData.memoryLimitGB}
                onChange={handleChange}
                className="w-full text-sm border-gray-300 rounded-md p-1.5 border"
              />
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
          <h3 className="text-sm font-bold text-gray-900 flex items-center mb-4">
            <Shield size={16} className="mr-2 text-purple-500" /> Safety & Logging
          </h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-700">Strict Schema Validation</span>
              <input
                type="checkbox"
                name="strictValidation"
                checked={formData.strictValidation}
                onChange={handleChange}
                className="h-5 w-5 text-fidelity-green focus:ring-fidelity-green border-gray-300 rounded"
              />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-700">Logging Level</span>
              <select
                name="logLevel"
                value={formData.logLevel}
                onChange={handleChange}
                className="text-sm border-gray-300 rounded-md shadow-sm focus:ring-fidelity-green focus:border-fidelity-green"
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
        <div className="border border-red-200 rounded-lg p-6 bg-red-50/50">
          <h3 className="text-sm font-bold text-red-700 flex items-center mb-2">
            <AlertTriangle size={16} className="mr-2" /> Danger Zone
          </h3>
          <p className="text-sm text-gray-600 mb-4">
            Irreversible actions that affect this scenario's simulation data.
          </p>

          <div className="flex items-center justify-between bg-white p-4 rounded-md border border-red-200">
            <div>
              <p className="text-sm font-medium text-gray-900">Delete Simulation Database</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Removes all simulation results so you can run a fresh simulation. Configuration is preserved.
              </p>
            </div>
            <div className="flex items-center gap-2">
              {dbDeleteStatus === 'confirming' ? (
                <>
                  <button
                    onClick={() => setDbDeleteStatus('idle')}
                    className="px-3 py-1.5 text-sm text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
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
                    className="px-3 py-1.5 text-sm text-white bg-red-600 hover:bg-red-700 rounded-md transition-colors font-medium"
                  >
                    Yes, delete it
                  </button>
                </>
              ) : dbDeleteStatus === 'deleting' ? (
                <span className="text-sm text-gray-500">Deleting...</span>
              ) : dbDeleteStatus === 'success' ? (
                <span className="text-sm text-green-600 flex items-center gap-1">
                  <Check size={14} /> {dbDeleteMessage}
                </span>
              ) : dbDeleteStatus === 'error' ? (
                <span className="text-sm text-red-600">{dbDeleteMessage}</span>
              ) : (
                <button
                  onClick={() => setDbDeleteStatus('confirming')}
                  className="px-3 py-1.5 text-sm text-red-600 border border-red-300 hover:bg-red-50 rounded-md transition-colors flex items-center gap-1.5"
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
