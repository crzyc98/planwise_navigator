/** Prefer the exact Baseline name; accept capitalization/spacing differences. */
export function baselineScenarioId(scenarios: { id: string; name: string }[]): string | null {
  return (scenarios.find(scenario => scenario.name === 'Baseline')
    ?? scenarios.find(scenario => scenario.name.trim().toLowerCase() === 'baseline'))?.id ?? null;
}
