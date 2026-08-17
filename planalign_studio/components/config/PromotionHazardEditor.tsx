import { useState } from 'react';
import { AlertTriangle, Check } from 'lucide-react';
import { useConfigContext } from './ConfigContext';

export function PromotionHazardEditor() {
  const { promotionHazardConfig, setPromotionHazardConfig, saveStatus } = useConfigContext();
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  const handleBaseChange = (field: 'base_rate' | 'level_dampener_factor', value: string) => {
    if (!promotionHazardConfig) return;
    setPromotionHazardConfig({
      ...promotionHazardConfig,
      base: {
        ...promotionHazardConfig.base,
        [field]: parseFloat(value) / 100 || 0,
      },
    });
    setValidationErrors([]);
  };

  const handleAgeMultiplierChange = (index: number, value: string) => {
    if (!promotionHazardConfig) return;
    const updated = [...promotionHazardConfig.age_multipliers];
    updated[index] = { ...updated[index], multiplier: parseFloat(value) || 0 };
    setPromotionHazardConfig({ ...promotionHazardConfig, age_multipliers: updated });
    setValidationErrors([]);
  };

  const handleTenureMultiplierChange = (index: number, value: string) => {
    if (!promotionHazardConfig) return;
    const updated = [...promotionHazardConfig.tenure_multipliers];
    updated[index] = { ...updated[index], multiplier: parseFloat(value) || 0 };
    setPromotionHazardConfig({ ...promotionHazardConfig, tenure_multipliers: updated });
    setValidationErrors([]);
  };

  if (!promotionHazardConfig) {
    return (
      <div className="bg-surface-subtle p-6 rounded-lg border border-border mt-6">
        <h3 className="text-sm font-semibold text-ink mb-2">Promotion Hazard</h3>
        <div className="flex items-center justify-center py-6">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-fidelity-green"></div>
          <span className="ml-3 text-ink-muted text-sm">Loading promotion hazard config...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-surface-subtle p-6 rounded-lg border border-border mt-6">
      <h3 className="text-sm font-semibold text-ink mb-2">Promotion Hazard</h3>
      <p className="text-xs text-ink-muted mb-4">
        Configure the base promotion rate, level dampener, and age/tenure multipliers that drive promotion probabilities in the simulation.
        Formula: base_rate &times; tenure_multiplier &times; age_multiplier &times; max(0, 1 - level_dampener &times; (level - 1)), capped at 100%.
      </p>

      {/* Validation Errors */}
      {validationErrors.length > 0 && (
        <div className="bg-danger-surface border border-danger-border rounded-lg p-3 mb-4">
          <div className="flex items-start">
            <AlertTriangle className="w-4 h-4 text-danger-ink mr-2 mt-0.5" />
            <div>
              <h4 className="text-danger-ink font-medium text-sm">Validation Errors</h4>
              <ul className="mt-1 space-y-1">
                {validationErrors.map((err, idx) => (
                  <li key={idx} className="text-xs text-danger-ink">{err}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {saveStatus === 'success' && (
        <div className="bg-success-surface border border-success-border rounded-lg p-3 mb-4">
          <div className="flex items-center">
            <Check className="w-4 h-4 text-success-ink mr-2" />
            <span className="text-success-ink text-sm">Configuration saved successfully.</span>
          </div>
        </div>
      )}

      {/* Base Parameters */}
      <div className="mb-6">
        <h4 className="text-xs font-semibold text-ink-muted uppercase tracking-wider mb-3">Base Parameters</h4>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="promo-base-rate" className="block text-xs text-ink-muted mb-1">Base Rate (%)</label>
            <input
              id="promo-base-rate"
              type="number"
              step="0.1"
              min="0"
              max="100"
              value={parseFloat((promotionHazardConfig.base.base_rate * 100).toFixed(4))}
              onChange={(e) => handleBaseChange('base_rate', e.target.value)}
              className="w-full shadow-sm focus:ring-fidelity-green focus:border-fidelity-green text-sm border-border-strong rounded-md p-2 border"
            />
            <p className="mt-1 text-xs text-ink-subtle">Stored as {promotionHazardConfig.base.base_rate}</p>
          </div>
          <div>
            <label htmlFor="promo-level-dampener" className="block text-xs text-ink-muted mb-1">Level Dampener (%)</label>
            <input
              id="promo-level-dampener"
              type="number"
              step="0.1"
              min="0"
              max="100"
              value={parseFloat((promotionHazardConfig.base.level_dampener_factor * 100).toFixed(4))}
              onChange={(e) => handleBaseChange('level_dampener_factor', e.target.value)}
              className="w-full shadow-sm focus:ring-fidelity-green focus:border-fidelity-green text-sm border-border-strong rounded-md p-2 border"
            />
            <p className="mt-1 text-xs text-ink-subtle">Stored as {promotionHazardConfig.base.level_dampener_factor}</p>
          </div>
        </div>
      </div>

      {/* Age Multipliers Table */}
      <div className="mb-6">
        <h4 className="text-xs font-semibold text-ink-muted uppercase tracking-wider mb-3">Age Multipliers</h4>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 px-3 font-medium text-ink-muted">Age Band</th>
                <th className="text-left py-2 px-3 font-medium text-ink-muted">Multiplier</th>
              </tr>
            </thead>
            <tbody>
              {promotionHazardConfig.age_multipliers.map((m, idx) => (
                <tr key={m.age_band} className="border-b border-border">
                  <td className="py-2 px-3 text-ink-muted">{m.age_band}</td>
                  <td className="py-2 px-3">
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      value={m.multiplier}
                      onChange={(e) => handleAgeMultiplierChange(idx, e.target.value)}
                      className="w-24 px-2 py-1 border rounded text-sm border-border-strong"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Tenure Multipliers Table */}
      <div className="mb-6">
        <h4 className="text-xs font-semibold text-ink-muted uppercase tracking-wider mb-3">Tenure Multipliers</h4>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 px-3 font-medium text-ink-muted">Tenure Band</th>
                <th className="text-left py-2 px-3 font-medium text-ink-muted">Multiplier</th>
              </tr>
            </thead>
            <tbody>
              {promotionHazardConfig.tenure_multipliers.map((m, idx) => (
                <tr key={m.tenure_band} className="border-b border-border">
                  <td className="py-2 px-3 text-ink-muted">{m.tenure_band}</td>
                  <td className="py-2 px-3">
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      value={m.multiplier}
                      onChange={(e) => handleTenureMultiplierChange(idx, e.target.value)}
                      className="w-24 px-2 py-1 border rounded text-sm border-border-strong"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
