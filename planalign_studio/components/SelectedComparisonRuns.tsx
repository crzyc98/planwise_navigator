import React from 'react';
import { Scenario } from '../services/api';

export default function SelectedComparisonRuns({ scenarios }: Readonly<{ scenarios: Scenario[] }>) {
  return (
    <div className="flex flex-wrap gap-2 text-xs text-ink-muted">
      {scenarios.map(scenario => (
        <span key={scenario.id} className="rounded-lg bg-surface-subtle px-3 py-2">
          {scenario.name}: selected run {scenario.selected_result_run_id ?? 'identity unavailable (legacy result)'}
          {' · '}Latest attempt: {scenario.status}
        </span>
      ))}
    </div>
  );
}
