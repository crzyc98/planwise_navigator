import { Gauge } from 'lucide-react';
import { SimulationSection } from './SimulationSection';
import { CompensationSection } from './CompensationSection';
import { NewHireSection } from './NewHireSection';
import { TurnoverSection } from './TurnoverSection';

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
  return (
    <div className="space-y-10 animate-fadeIn">
      <div className="border-b border-border pb-4">
        <div className="flex items-center gap-2">
          <Gauge className="h-5 w-5 text-fidelity-green" />
          <h2 className="text-lg font-bold text-ink">Workforce Parameters</h2>
        </div>
        <p className="text-sm text-ink-muted">
          The essentials for a typical scenario. Everything else lives under Advanced Settings.
        </p>
      </div>

      <SimulationSection variant="essentials" />
      <CompensationSection variant="essentials" />
      <NewHireSection variant="essentials" />
      <TurnoverSection variant="essentials" />
    </div>
  );
}
