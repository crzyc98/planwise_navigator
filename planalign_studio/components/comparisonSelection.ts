import { listScenarios, Scenario } from '../services/api';

export function hasComparisonResult(scenario: Scenario): boolean {
  return scenario.has_selected_result === true;
}

export function restoreComparisonSelection(
  scenarios: Scenario[], requestedA: string | null, requestedB: string | null,
): [string, string] {
  const available = scenarios.filter(hasComparisonResult);
  const planA = available.find(s => s.id === requestedA)
    ?? available.find(s => s.name.toLowerCase().includes('baseline'))
    ?? available[0];
  const planB = available.find(s => s.id === requestedB && s.id !== planA?.id)
    ?? available.find(s => s.id !== planA?.id);
  return [planA?.id ?? '', planB?.id ?? ''];
}

export async function loadDiffSelection(workspaceId: string, a: string, b: string): Promise<Scenario[]> {
  const scenarios = await listScenarios(workspaceId);
  const selected = [a, b].map(id => scenarios.find(item => item.id === id));
  if (selected.some(item => !item)) throw new Error('Both scenarios must belong to the active workspace.');
  const pair = selected as Scenario[];
  if (!pair.every(hasComparisonResult)) throw new Error('Both scenarios must have successful results before comparison.');
  return pair;
}
