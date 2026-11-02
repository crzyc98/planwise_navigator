import { ApiError } from '../services/api';

/** Prefer the exact Baseline name; accept capitalization/spacing differences. */
export function baselineScenarioId(scenarios: { id: string; name: string }[]): string | null {
  return (scenarios.find(scenario => scenario.name === 'Baseline')
    ?? scenarios.find(scenario => scenario.name.trim().toLowerCase() === 'baseline'))?.id ?? null;
}

/** The 409 the API returns when the target scenario has no matching completed run. */
export function isMissingRunError(e: unknown): boolean {
  return e instanceof ApiError && e.status === 409
    && typeof e.detail === 'string' && e.detail.startsWith('No completed simulation matches');
}
