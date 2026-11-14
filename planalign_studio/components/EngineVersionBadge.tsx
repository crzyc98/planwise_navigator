import React from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { Scenario } from '../services/api';
import { useWorkspaceNavigate } from '../hooks/useWorkspaceNavigation';

const QUIET = 'bg-surface-subtle text-ink-muted border border-border';

/**
 * "Run on <version>": which engine version produced a scenario's selected
 * result (#1182). A current version is shown quietly; a patch-only gap is
 * quiet with a rerun action; a minor or major gap is a warning, since those
 * releases can change results.
 */
export default function EngineVersionBadge({
  scenario,
  rerunDisabled = false,
}: Readonly<{
  scenario: Pick<Scenario, 'id' | 'result_engine_version' | 'result_engine_version_gap'>;
  rerunDisabled?: boolean;
}>) {
  const navigate = useWorkspaceNavigate();
  const version = scenario.result_engine_version;
  const gap = scenario.result_engine_version_gap;
  if (!version) return null;
  const badge = 'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs';
  if (!gap) {
    return <span className={`${badge} ${QUIET}`}>Run on {version}</span>;
  }
  const warning = gap !== 'patch';
  const tone = warning ? 'bg-warning-surface text-warning-ink border border-warning-border' : QUIET;
  const title = warning
    ? 'This result came from an older engine version, which can give different results. Rerun to update it.'
    : 'This result came from an earlier patch release of the engine.';
  return (
    <span className={`${badge} ${tone}`} title={title}>
      {warning && <AlertTriangle size={12} aria-hidden="true" />}
      Run on {version}
      <button
        type="button"
        onClick={() => navigate(`/simulate?scenario=${encodeURIComponent(scenario.id)}`)}
        disabled={rerunDisabled}
        className="inline-flex items-center gap-0.5 underline underline-offset-2 hover:opacity-80 disabled:opacity-50 disabled:cursor-not-allowed disabled:no-underline"
        title={rerunDisabled ? 'A simulation is already running' : 'Rerun on the current engine version'}
      >
        <RotateCcw size={11} aria-hidden="true" />
        Rerun
      </button>
    </span>
  );
}
