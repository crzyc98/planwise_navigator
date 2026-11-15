import { useEffect, useState } from 'react';
import { getEnsembleCostRanges, type ScenarioCostRange } from '../services/api';

/**
 * Seed ranges for the compared scenarios. They are secondary to the point
 * figures, so a failed request leaves the page as it was (logged, not shown).
 */
export function useEnsembleCostRanges(
  workspaceId: string | undefined,
  scenarioIds: string[],
  anchorScenarioId: string,
  enabled: boolean,
): ScenarioCostRange[] {
  const [ranges, setRanges] = useState<ScenarioCostRange[]>([]);
  const key = scenarioIds.join(',');

  useEffect(() => {
    setRanges([]);
    if (!enabled || !workspaceId || !anchorScenarioId || !key.split(',').includes(anchorScenarioId)) {
      return;
    }
    let cancelled = false;
    getEnsembleCostRanges(workspaceId, key.split(','), anchorScenarioId)
      .then(response => { if (!cancelled) setRanges(response.scenarios); })
      .catch((err: unknown) => console.warn('Seed ranges unavailable:', err));
    return () => { cancelled = true; };
  }, [workspaceId, key, anchorScenarioId, enabled]);

  return ranges;
}
