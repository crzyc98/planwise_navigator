import React, { useEffect, useState } from 'react';
import { EmployeeTimelineResponse, getEmployeeTimeline } from '../../services/api';
import TimelineYear from './TimelineYear';

interface Props {
  workspaceId: string;
  scenarioId: string;
  employeeId: string;
  scenarioLabel?: string;
  alignedYears?: number[];
  onLoaded?: (response: EmployeeTimelineResponse) => void;
}

export default function TimelineColumn({ workspaceId, scenarioId, employeeId, scenarioLabel, alignedYears, onLoaded }: Readonly<Props>) {
  const [data, setData] = useState<EmployeeTimelineResponse | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setError('');
    getEmployeeTimeline(workspaceId, scenarioId, employeeId, { years: 3 })
      .then((response) => { if (active) { setData(response); onLoaded?.(response); } })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'Timeline failed to load'); });
    return () => { active = false; };
  }, [workspaceId, scenarioId, employeeId, onLoaded]);

  if (error) return <div className="rounded-lg bg-red-50 p-4 text-red-700">{error}</div>;
  if (!data) return <div className="p-6 text-center text-gray-500">Loading timeline…</div>;
  if (!data.employee) return <div className="rounded-lg bg-amber-50 p-4 text-amber-800">No records found for this employee in this scenario.</div>;

  const byYear = new Map(data.years.map((year) => [year.simulation_year, year]));
  const displayYears = alignedYears ?? data.available_years;
  const loadedYears = new Set(data.years.map((year) => year.simulation_year));
  const nextYear = data.available_years.find((year) => !loadedYears.has(year));
  const loadMore = () => {
    if (nextYear === undefined) return;
    getEmployeeTimeline(workspaceId, scenarioId, employeeId, { start_year: nextYear, years: 3 })
      .then((response) => {
        const merged = { ...data, years: [...data.years, ...response.years] };
        setData(merged);
        onLoaded?.(merged);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : 'Timeline failed to load'));
  };
  return (
    <div className="min-w-0 space-y-4">
      {scenarioLabel && <h2 className="text-xl font-bold text-gray-900">{scenarioLabel}</h2>}
      <div className="rounded-lg border border-gray-200 bg-white p-3 text-sm text-gray-600">
        <strong className="text-gray-900">{data.employee.employee_id}</strong>
        <span className="ml-3">SSN {data.employee.employee_ssn ?? '—'}</span>
        <span className="ml-3">Born {data.employee.employee_birth_date ?? '—'}</span>
        <span className="ml-3">Hired {data.employee.employee_hire_date ?? '—'}</span>
      </div>
      {displayYears.map((year) => byYear.has(year)
        ? <TimelineYear key={year} year={byYear.get(year)!} />
        : data.available_years.includes(year)
          ? null
          : <div key={year} className="rounded-xl border border-dashed border-gray-300 p-4 text-sm text-gray-500"><strong>{year}</strong>: not simulated in this scenario</div>)}
      {nextYear !== undefined && <button onClick={loadMore} className="w-full rounded-lg border border-fidelity-green px-4 py-2 text-sm font-medium text-fidelity-green">Load more years</button>}
    </div>
  );
}
