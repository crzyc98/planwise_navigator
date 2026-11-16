import React, { useEffect, useState } from 'react';
import { getScenarioRunChanges, RunChangesResponse } from '../services/api';
import { summarizeRunChanges } from './comparisonIntegrity';

/** "Since the previous run" lines; pure view for tests and reuse. */
export function RunChangesLines({ result }: Readonly<{ result: RunChangesResponse }>) {
  const summary = summarizeRunChanges(result);
  return (
    <section aria-label="Since the previous run" className="text-xs space-y-0.5">
      <p>{summary.headline}</p>
      {summary.changes.length > 0 && (
        <ul className="list-disc pl-4 space-y-0.5">
          {summary.changes.map(change => <li key={change}>{change}</li>)}
        </ul>
      )}
      {summary.missing && <p className="opacity-80">{summary.missing}</p>}
    </section>
  );
}

type FetchState =
  | { status: 'idle' }
  | { status: 'ready'; key: string; result: RunChangesResponse }
  | { status: 'failed'; key: string };

/**
 * What changed between the scenario's previous run and its selected result
 * (#1186). Refetches when the selected result changes; a failed request
 * leaves the page working and says so quietly.
 */
export default function RunChangesSince({
  workspaceId,
  scenarioId,
  resultRunId,
}: Readonly<{ workspaceId: string; scenarioId: string; resultRunId: string | null | undefined }>) {
  const key = workspaceId && scenarioId && resultRunId ? `${workspaceId}|${scenarioId}|${resultRunId}` : '';
  const [state, setState] = useState<FetchState>({ status: 'idle' });

  useEffect(() => {
    if (!key) return undefined;
    const controller = new AbortController();
    getScenarioRunChanges(workspaceId, scenarioId, controller.signal)
      .then(result => setState({ status: 'ready', key, result }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          console.warn('Changes since the previous run failed to load', error);
          setState({ status: 'failed', key });
        }
      });
    return () => controller.abort();
  }, [key, workspaceId, scenarioId]);

  if (!key || state.status === 'idle' || state.key !== key) return null;
  if (state.status === 'failed') {
    return <p className="text-xs opacity-80">Couldn't load what changed since the previous run.</p>;
  }
  return <RunChangesLines result={state.result} />;
}
