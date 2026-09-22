import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useOutletContext, useParams, useSearchParams } from 'react-router-dom';
import { ListFilter } from 'lucide-react';

import { LayoutContextType } from '../Layout';
import { EventListResponse, EventRecord, listEvents, listScenarios, Scenario } from '../../services/api';
import EventDetailDrawer from './EventDetailDrawer';
import EventFilterBar, { buildEventQueryParams, EventFilters } from './EventFilterBar';
import EventResultsTable from './EventResultsTable';

const PAGE_SIZE = 50;

function readFilters(searchParams: URLSearchParams): EventFilters {
  return {
    simulation_year: searchParams.get('simulation_year') ?? '',
    event_type: searchParams.get('event_type') ?? '',
    event_category: searchParams.get('event_category') ?? '',
    employee_id: searchParams.get('employee_id') ?? '',
  };
}

function readPage(searchParams: URLSearchParams): number {
  const page = Number(searchParams.get('page') ?? '1');
  return Number.isInteger(page) && page > 0 ? page : 1;
}

export default function EventExplorerPage() {
  const { activeWorkspace } = useOutletContext<LayoutContextType>();
  const params = useParams<{ workspaceId?: string; scenarioId?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const workspaceId = params.workspaceId ?? activeWorkspace.id;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const scenarioId = params.scenarioId ?? scenarios[0]?.id ?? '';
  const filters = useMemo(() => readFilters(searchParams), [searchParams]);
  const page = readPage(searchParams);
  const [result, setResult] = useState<EventListResponse | null>(null);
  const [selected, setSelected] = useState<EventRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void listScenarios(workspaceId).then((items) => setScenarios(items.filter((item) => item.status === 'completed')));
  }, [workspaceId]);

  const query = useMemo(() => buildEventQueryParams(filters), [filters]);
  useEffect(() => {
    if (!scenarioId) return;
    setLoading(true);
    setError(null);
    void listEvents(workspaceId, scenarioId, { ...query, page, page_size: PAGE_SIZE })
      .then(setResult)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : 'Unable to load events.'))
      .finally(() => setLoading(false));
  }, [workspaceId, scenarioId, query, page]);

  const updateFilters = useCallback((changes: Partial<EventFilters>) => {
    const updated = new URLSearchParams(searchParams);
    Object.entries(changes).forEach(([key, value]) => {
      if (value) updated.set(key, value); else updated.delete(key);
    });
    updated.delete('page');
    setSearchParams(updated);
  }, [searchParams, setSearchParams]);

  const selectScenario = (nextScenarioId: string) => {
    const suffix = searchParams.size ? `?${searchParams.toString()}` : '';
    navigate(`/w/${encodeURIComponent(workspaceId)}/events/${encodeURIComponent(nextScenarioId)}${suffix}`);
  };
  const setPage = (nextPage: number) => {
    const updated = new URLSearchParams(searchParams);
    if (nextPage === 1) updated.delete('page'); else updated.set('page', String(nextPage));
    setSearchParams(updated);
  };

  return (
    <main className="space-y-5 p-6">
      <header><h1 className="flex items-center gap-2 text-2xl font-bold text-ink"><ListFilter className="text-fidelity-green" />Event Audit Explorer</h1><p className="text-sm text-ink-muted">Browse immutable yearly workforce events for the selected scenario.</p></header>
      <EventFilterBar scenarios={scenarios} scenarioId={scenarioId} filters={filters} onScenarioChange={selectScenario} onFiltersChange={updateFilters} />
      {!scenarioId ? <div className="rounded-xl border border-dashed border-border p-10 text-center text-ink-muted">Choose a completed scenario to browse events.</div> : loading ? <p className="text-sm text-ink-muted">Loading events…</p> : error ? <p className="rounded border border-danger-ink bg-danger-surface p-3 text-sm text-danger-ink">{error}</p> : <><EventResultsTable workspaceId={workspaceId} scenarioId={scenarioId} events={result?.events ?? []} onSelect={setSelected} /><footer className="flex items-center justify-between text-sm text-ink-muted"><span>{result ? `${result.total} events` : '0 events'}</span><div className="flex items-center gap-3"><button className="rounded border border-border px-3 py-1 disabled:opacity-50" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page}</span><button className="rounded border border-border px-3 py-1 disabled:opacity-50" disabled={!result || page * PAGE_SIZE >= result.total} onClick={() => setPage(page + 1)}>Next</button></div></footer></>}
      {selected && <EventDetailDrawer workspaceId={workspaceId} scenarioId={scenarioId} event={selected} onClose={() => setSelected(null)} />}
    </main>
  );
}
