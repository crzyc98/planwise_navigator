import { useCallback, useEffect, useState } from 'react';
import { Scenario, listScenarios } from '../../services/api';
import { errorMessage } from './ensembleJobHelpers';

export type ScenariosState =
  | { status: 'loading' }
  | { status: 'error'; error: string }
  | { status: 'ready'; scenarios: Scenario[] };

/** The workspace's scenarios, keeping "still loading" and "couldn't load" apart from "none". */
export function useWorkspaceScenarios(workspaceId: string): { state: ScenariosState; retry: () => void } {
  const [state, setState] = useState<ScenariosState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!workspaceId) return;
    let alive = true;
    setState({ status: 'loading' });
    listScenarios(workspaceId)
      .then((scenarios) => alive && setState({ status: 'ready', scenarios }))
      .catch((err: unknown) => alive && setState({ status: 'error', error: errorMessage(err) }));
    return () => {
      alive = false;
    };
  }, [workspaceId, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { state, retry };
}
