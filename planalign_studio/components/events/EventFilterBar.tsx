import React, { useEffect, useState } from 'react';

import { EventListParams, Scenario } from '../../services/api';

export interface EventFilters {
  simulation_year: string;
  event_type: string;
  event_category: string;
  employee_id: string;
}

interface Props {
  scenarios: Scenario[];
  scenarioId: string;
  filters: EventFilters;
  onScenarioChange: (scenarioId: string) => void;
  onFiltersChange: (changes: Partial<EventFilters>) => void;
}

export function buildEventQueryParams(filters: EventFilters): EventListParams {
  const simulationYear = filters.simulation_year.trim();
  const eventType = filters.event_type.trim();
  const eventCategory = filters.event_category.trim();
  const employeeId = filters.employee_id.trim();
  const parsedYear = Number(simulationYear);

  return {
    ...(simulationYear && Number.isFinite(parsedYear) ? { simulation_year: parsedYear } : {}),
    ...(eventType ? { event_type: eventType } : {}),
    ...(eventCategory ? { event_category: eventCategory } : {}),
    ...(employeeId ? { employee_id: employeeId } : {}),
  };
}

export default function EventFilterBar({
  scenarios,
  scenarioId,
  filters,
  onScenarioChange,
  onFiltersChange,
}: Readonly<Props>) {
  const [employeeInput, setEmployeeInput] = useState(filters.employee_id);

  useEffect(() => {
    setEmployeeInput(filters.employee_id);
  }, [filters.employee_id]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (employeeInput !== filters.employee_id) {
        onFiltersChange({ employee_id: employeeInput });
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [employeeInput, filters.employee_id, onFiltersChange]);

  return (
    <section className="rounded-xl border border-border bg-surface-raised p-4">
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
        <label className="text-sm font-medium text-ink">Scenario
          <select className="mt-1 w-full rounded border border-border bg-surface px-3 py-2" value={scenarioId} onChange={(event) => onScenarioChange(event.target.value)}>
            <option value="">Select a completed scenario</option>
            {scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}
          </select>
        </label>
        <label className="text-sm font-medium text-ink">Simulation year
          <input className="mt-1 w-full rounded border border-border bg-surface px-3 py-2" type="number" value={filters.simulation_year} onChange={(event) => onFiltersChange({ simulation_year: event.target.value })} />
        </label>
        <label className="text-sm font-medium text-ink">Event type
          <input className="mt-1 w-full rounded border border-border bg-surface px-3 py-2" value={filters.event_type} onChange={(event) => onFiltersChange({ event_type: event.target.value })} />
        </label>
        <label className="text-sm font-medium text-ink">Event category
          <input className="mt-1 w-full rounded border border-border bg-surface px-3 py-2" value={filters.event_category} onChange={(event) => onFiltersChange({ event_category: event.target.value })} />
        </label>
        <label className="text-sm font-medium text-ink">Employee ID
          <input className="mt-1 w-full rounded border border-border bg-surface px-3 py-2" value={employeeInput} onChange={(event) => setEmployeeInput(event.target.value)} />
        </label>
      </div>
    </section>
  );
}
