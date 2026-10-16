import { Gauge } from 'lucide-react';
import { SimulationSection } from './SimulationSection';
import { CompensationSection } from './CompensationSection';
import { NewHireSection } from './NewHireSection';
import { TurnoverSection } from './TurnoverSection';
import { useConfigContext } from './ConfigContext';
import { InputField } from './InputField';
import { PromotionHazardEditor } from './PromotionHazardEditor';
import { SegmentationSection } from './SegmentationSection';

/**
 * Curated "essentials" view (#358): surfaces only the most-frequently-configured
 * workforce parameters for a typical scenario, so an analyst can set up quickly
 * and with confidence. The full detail for each area lives under "Advanced".
 *
 * Each underlying section is rendered in its `essentials` variant — the SAME
 * components against the SAME ConfigContext state, so edits here and under
 * Advanced are interchangeable and persist identically.
 */
export function WorkforceParametersSection() {
  const { formData, inputProps, promotionHazardConfig, bandConfig } = useConfigContext();
  const ageSummary = formData.newHireAgeDistribution.map(row => `${row.age}: ${(row.weight * 100).toFixed(0)}%`).join(', ');
  const paySummary = formData.jobLevelCompensation.map(row => `${row.name}: $${row.minComp.toLocaleString()}–$${row.maxComp.toLocaleString()}`).join('; ');
  const adjustments = formData.levelMarketAdjustments.filter(row => row.adjustment !== 0);
  return (
    <div className="space-y-10 animate-fadeIn">
      <div className="border-b border-border pb-4">
        <div className="flex items-center gap-2">
          <Gauge className="h-5 w-5 text-fidelity-green" />
          <h2 className="text-lg font-bold text-ink">Workforce Parameters</h2>
        </div>
        <p className="text-sm text-ink-muted">
          Set the projection period, workforce change and pay assumptions, then review the detailed assumptions.
        </p>
      </div>

      <SimulationSection variant="essentials" />
      <TurnoverSection variant="essentials" />
      <CompensationSection variant="essentials" />
      <details className="rounded-lg border border-border p-4">
        <summary className="cursor-pointer text-ink marker:text-ink-muted">
          <span className="font-semibold">New-hire assumptions</span>
          <span className="block mt-2 text-sm text-ink-muted">Age profile ({formData.newHireAgeDistribution.length} buckets): {ageSummary}. Part-time: {formData.partTimeNewHirePct}%. Market: {formData.marketScenario}.</span>
          <span className="block mt-1 text-sm text-ink-muted">Pay ranges ({formData.jobLevelCompensation.length} levels): {paySummary}.</span>
          <span className="block mt-1 text-xs text-ink-muted">Retained unsupported controls: {formData.newHireStrategy}, P{formData.targetPercentile}, variance ±{formData.newHireCompVariance}%; level mode {formData.levelDistributionMode}{formData.levelDistributionMode === 'fixed' ? ` (${formData.newHireLevelDistribution.map(row => `${row.name} ${row.percentage}%`).join(', ')})` : ''}{adjustments.length ? `; level adjustments: ${adjustments.map(row => `L${row.level} ${row.adjustment}%`).join(', ')}` : ''}.</span>
        </summary>
        <div className="pt-6"><NewHireSection /></div>
      </details>
      <details className="rounded-lg border border-border p-4">
        <summary className="cursor-pointer text-ink marker:text-ink-muted">
          <span className="font-semibold">Advanced workforce assumptions</span>
          <span className="block mt-2 text-sm text-ink-muted">Seed {formData.seed}; promotion rate multiplier {formData.promoRateMultiplier}×{promotionHazardConfig ? `; base promotion rate ${(promotionHazardConfig.base.base_rate * 100).toFixed(1)}%; level dampener ${(promotionHazardConfig.base.level_dampener_factor * 100).toFixed(1)}%; age multipliers: ${promotionHazardConfig.age_multipliers.map(row => `${row.age_band} ${row.multiplier}×`).join(', ')}; tenure multipliers: ${promotionHazardConfig.tenure_multipliers.map(row => `${row.tenure_band} ${row.multiplier}×`).join(', ')}` : '; promotion hazards loading'}.</span>
          <span className="block mt-1 text-sm text-ink-muted">{bandConfig ? `Age bands: ${bandConfig.age_bands.map(band => `${band.band_label} [${band.min_value}, ${band.max_value})`).join(', ')}. Tenure bands: ${bandConfig.tenure_bands.map(band => `${band.band_label} [${band.min_value}, ${band.max_value})`).join(', ')}.` : 'Age and tenure bands loading.'}</span>
        </summary>
        <div className="pt-6 space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-6">
            <InputField label="Random Seed" {...inputProps('seed')} type="number" helper="Identical inputs and seed reproduce the same simulation." />
            <InputField label="Promotion Rate Multiplier" {...inputProps('promoRateMultiplier')} type="number" step="0.1" suffix="×" />
          </div>
          <PromotionHazardEditor />
          <SegmentationSection />
        </div>
      </details>
    </div>
  );
}
