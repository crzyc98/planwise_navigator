import { useEffect, useState } from 'react';
import { getEnsembleCostRanges, type ScenarioCostRange } from '../services/api';

/**
 * Seed ranges for the scenarios of the comparison currently loaded, so they
 * are requested once per loaded comparison (not again while a new selection
 * loads) and never laid against another comparison's figures. They are
 * secondary to the point figures, so a failed request leaves the page as it
 * was (logged, not shown).
 */
export function useEnsembleCostRanges(
  workspaceId: string | undefined,
  loadedScenarioIds: string[],
  anchorScenarioId: string,
): ScenarioCostRange[] {
  const ids = loadedScenarioIds.join(',');
  const key = workspaceId && anchorScenarioId && loadedScenarioIds.includes(anchorScenarioId)
    ? `${workspaceId}|${anchorScenarioId}|${ids}`
    : null;
  const [loaded, setLoaded] = useState<{ key: string; ranges: ScenarioCostRange[] } | null>(null);

  useEffect(() => {
    if (key === null || !workspaceId) return;
    let cancelled = false;
    getEnsembleCostRanges(workspaceId, ids.split(','), anchorScenarioId)
      .then(response => { if (!cancelled) setLoaded({ key, ranges: response.scenarios }); })
      .catch((err: unknown) => console.warn('Seed ranges unavailable:', err));
    return () => { cancelled = true; };
  }, [key, workspaceId, ids, anchorScenarioId]);

  return loaded !== null && loaded.key === key ? loaded.ranges : [];
}
