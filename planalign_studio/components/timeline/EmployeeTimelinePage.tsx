import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useOutletContext, useParams, useSearchParams } from 'react-router-dom';
import { Copy, Users } from 'lucide-react';
import { LayoutContextType } from '../Layout';
import { EmployeeTimelineResponse, listScenarios, Scenario, timelineUrl } from '../../services/api';
import EmployeeSearch from './EmployeeSearch';
import TimelineColumn from './TimelineColumn';

export default function EmployeeTimelinePage() {
  const { activeWorkspace } = useOutletContext<LayoutContextType>();
  const params = useParams<{ workspaceId?: string; scenarioId?: string; employeeId?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const workspaceId = params.workspaceId ?? activeWorkspace.id;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const scenarioId = params.scenarioId ?? scenarios[0]?.id ?? '';
  const employeeId = decodeURIComponent(params.employeeId ?? '').trim();
  const compareId = searchParams.get('compare') ?? '';
  const [left, setLeft] = useState<EmployeeTimelineResponse | null>(null);
  const [right, setRight] = useState<EmployeeTimelineResponse | null>(null);

  useEffect(() => { void listScenarios(workspaceId).then((items) => setScenarios(items.filter((item) => item.status === 'completed'))); }, [workspaceId]);
  const alignedYears = useMemo(() => compareId
    ? [...new Set([...(left?.available_years ?? []), ...(right?.available_years ?? [])])].sort((a, b) => a - b)
    : undefined, [compareId, left, right]);
  const leftLoaded = useCallback((response: EmployeeTimelineResponse) => setLeft(response), []);
  const rightLoaded = useCallback((response: EmployeeTimelineResponse) => setRight(response), []);

  const selectScenario = (next: string) => {
    if (employeeId) navigate(timelineUrl(workspaceId, next, employeeId));
    else navigate('/timeline');
  };
  const selectEmployee = (next: string) => navigate(timelineUrl(workspaceId, scenarioId, next));
  const setCompare = (next: string) => {
    const updated = new URLSearchParams(searchParams);
    if (next) updated.set('compare', next); else updated.delete('compare');
    setSearchParams(updated);
  };
  const copyLink = () => void navigator.clipboard.writeText(`${window.location.origin}${window.location.pathname}#${timelineUrl(workspaceId, scenarioId, employeeId, compareId || undefined)}`);

  return (
    <main className="space-y-5 p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="flex items-center gap-2 text-2xl font-bold text-gray-900"><Users className="text-fidelity-green" />Employee Timeline</h1><p className="text-sm text-gray-500">Read the event story alongside each year-end state.</p></div>
        {employeeId && <button onClick={copyLink} className="flex items-center gap-2 rounded border px-3 py-2 text-sm"><Copy size={16} />Copy link</button>}
      </header>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm font-medium">Scenario<select className="mt-1 w-full rounded border px-3 py-2" value={scenarioId} onChange={(e) => selectScenario(e.target.value)}><option value="">Select a completed scenario</option>{scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}</select></label>
        {employeeId && <label className="text-sm font-medium">Compare with<select className="mt-1 w-full rounded border px-3 py-2" value={compareId} onChange={(e) => setCompare(e.target.value)}><option value="">No comparison</option>{scenarios.filter((scenario) => scenario.id !== scenarioId).map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}</select></label>}
      </div>
      {scenarioId && <EmployeeSearch workspaceId={workspaceId} scenarioId={scenarioId} onSelect={selectEmployee} />}
      {employeeId && scenarioId && (
        <div className={compareId ? 'grid gap-6 xl:grid-cols-2' : ''}>
          <TimelineColumn workspaceId={workspaceId} scenarioId={scenarioId} employeeId={employeeId} scenarioLabel={scenarios.find((item) => item.id === scenarioId)?.name ?? scenarioId} alignedYears={alignedYears} onLoaded={leftLoaded} />
          {compareId && <TimelineColumn workspaceId={workspaceId} scenarioId={compareId} employeeId={employeeId} scenarioLabel={scenarios.find((item) => item.id === compareId)?.name ?? compareId} alignedYears={alignedYears} onLoaded={rightLoaded} />}
        </div>
      )}
      {!employeeId && <div className="rounded-xl border border-dashed border-gray-300 p-10 text-center text-gray-500">Choose a scenario, then search for an employee.</div>}
    </main>
  );
}
