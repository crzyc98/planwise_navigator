import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertTriangle, CheckCircle, HelpCircle } from 'lucide-react';
import { ComparisonIntegrityResponse, getComparisonIntegrity } from '../services/api';
import { IntegrityLine, IntegrityTone, summarizeIntegrity } from './comparisonIntegrity';

const TONE_STYLES: Record<IntegrityTone, { line: string; Icon: typeof CheckCircle; icon: string }> = {
  ok: { line: 'text-ink-muted', Icon: CheckCircle, icon: 'text-success-ink' },
  warning: {
    line: 'bg-warning-surface text-warning-ink border border-warning-border rounded-lg px-3 py-2',
    Icon: AlertTriangle,
    icon: 'text-warning-ink',
  },
  unknown: {
    line: 'bg-surface-subtle text-ink border border-border rounded-lg px-3 py-2',
    Icon: HelpCircle,
    icon: 'text-ink-muted',
  },
};

function VerdictLine({ line, diffHref }: Readonly<{ line: IntegrityLine; diffHref: string }>) {
  const { line: lineClass, Icon, icon } = TONE_STYLES[line.tone];
  return (
    <li className={`flex gap-2 text-xs ${lineClass}`}>
      <Icon size={14} className={`mt-0.5 shrink-0 ${icon}`} aria-hidden="true" />
      <div className="space-y-1">
        <p>
          {line.headline}{' '}
          <Link to={diffHref} className="underline underline-offset-2 hover:opacity-80">
            See differences
          </Link>
        </p>
        {line.details.length > 0 && (
          <ul className="list-disc pl-4 space-y-0.5">
            {line.details.map(detail => <li key={detail}>{detail}</li>)}
          </ul>
        )}
        {line.notes.map(note => <p key={note} className="text-ink-subtle">{note}</p>)}
      </div>
    </li>
  );
}

/** One verdict line per compared scenario; pure view for tests and reuse. */
export function ComparisonIntegrityLines({
  result,
  diffBase,
}: Readonly<{ result: ComparisonIntegrityResponse; diffBase: string }>) {
  const summary = summarizeIntegrity(result);
  const href = (scenarioId: string) =>
    `${diffBase}/analytics/diff?${new URLSearchParams({ a: result.anchor_scenario_id, b: scenarioId })}`;
  return (
    <section aria-label="Like-for-like check" className="space-y-1.5">
      <ul className="space-y-1.5">
        {summary.lines.map(line => (
          <VerdictLine key={line.scenarioId} line={line} diffHref={href(line.scenarioId)} />
        ))}
      </ul>
      {summary.anchorNotes.map(note => <p key={note} className="text-xs text-ink-subtle">{note}</p>)}
    </section>
  );
}

type FetchState =
  | { status: 'idle' }
  | { status: 'ready'; key: string; result: ComparisonIntegrityResponse }
  | { status: 'failed'; key: string };

/**
 * Says whether each compared scenario differs from the anchor only in plan
 * design. Refetches when the selection or anchor changes; a failed check
 * leaves the page working and says the check is unavailable.
 */
export default function ComparisonIntegrityBanner({
  workspaceId,
  scenarioIds,
  anchorId,
}: Readonly<{ workspaceId: string | undefined; scenarioIds: string[]; anchorId: string | undefined }>) {
  const { workspaceId: routeWorkspaceId } = useParams<{ workspaceId: string }>();
  const ids = anchorId ? [...new Set([anchorId, ...scenarioIds])] : [];
  const idList = ids.join(',');
  const key = workspaceId && anchorId && ids.length >= 2 ? `${workspaceId}|${anchorId}|${idList}` : '';
  const [state, setState] = useState<FetchState>({ status: 'idle' });

  useEffect(() => {
    if (!key || !workspaceId || !anchorId) return undefined;
    const controller = new AbortController();
    getComparisonIntegrity(workspaceId, idList.split(','), anchorId, controller.signal)
      .then(result => setState({ status: 'ready', key, result }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          console.warn('Like-for-like check failed', error);
          setState({ status: 'failed', key });
        }
      });
    return () => controller.abort();
  }, [key, idList, workspaceId, anchorId]);

  if (!key || state.status === 'idle' || state.key !== key) return null;
  if (state.status === 'failed') {
    return <p className="text-xs text-ink-subtle">Couldn't check whether these scenarios are like-for-like.</p>;
  }
  return (
    <ComparisonIntegrityLines
      result={state.result}
      diffBase={routeWorkspaceId ? `/w/${routeWorkspaceId}` : ''}
    />
  );
}
