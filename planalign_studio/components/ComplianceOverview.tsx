import { useEffect, useState } from 'react';
import {
  ComplianceEmployeePage, ComplianceMetric, ComplianceStatus, ComplianceSummary,
  getComplianceEmployees,
} from '../services/api';

const money = (value: number | null | undefined) => value == null ? 'Unavailable' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value);
const percent = (value: number | null | undefined) => value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`;
const labels: Record<ComplianceStatus, string> = {
  below_threshold: 'Below threshold', near_limit: 'Near limit', at_limit: 'At limit', over_limit: 'Over limit', unavailable: 'Unavailable',
};

export default function ComplianceOverview({ workspaceId, summary, onOpenTest }: {
  workspaceId: string; summary: ComplianceSummary;
  onOpenTest: (kind: 'adp' | 'acp' | '415') => void;
}) {
  const [selection, setSelection] = useState<{ metric: ComplianceMetric; status?: ComplianceStatus } | null>(null);
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<ComplianceEmployeePage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!selection) return;
    let active = true;
    setLoading(true); setError(null); setPage(null);
    getComplianceEmployees(workspaceId, summary, selection.metric, selection.status, offset)
      .then(value => { if (active) setPage(value); })
      .catch((err: unknown) => { if (active) setError(err instanceof Error ? err.message : 'Unable to load employee detail. Refresh the overview.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [workspaceId, summary, selection, offset]);

  const select = (metric: ComplianceMetric, status?: ComplianceStatus) => {
    setOffset(0); setSelection({ metric, status });
  };
  const measures = [
    { metric: '402g' as const, title: '402(g) deferrals', values: summary.deferrals },
    { metric: '415c' as const, title: '415(c) annual additions', values: summary.annual_additions },
    { metric: '401a17' as const, title: '401(a)(17) compensation cap', values: summary.compensation },
  ];
  const limits = summary.limits;
  const enhanced = limits && limits.super_catch_up_limit > limits.catch_up_limit;
  const ordinaryTitle = limits ? enhanced
    ? `Ordinary catch-up (${limits.catch_up_age_threshold}–${limits.super_catch_up_age_min - 1} and ${limits.super_catch_up_age_max + 1}+)`
    : `Ordinary catch-up (${limits.catch_up_age_threshold}+)` : 'Ordinary catch-up';
  const superTitle = limits ? enhanced ? `Super catch-up (${limits.super_catch_up_age_min}–${limits.super_catch_up_age_max})` : 'Super catch-up (not applicable)' : 'Super catch-up';
  return (
    <section className="space-y-4" aria-label={`Compliance overview for ${summary.scenario_name}`}>
      <div className="bg-surface-raised border border-border rounded-xl p-5 space-y-2">
        <h2 className="text-lg font-semibold text-ink">{summary.scenario_name} · {summary.year}</h2>
        <p className="text-sm text-ink-muted">{summary.participant_count} eligible employees · Warning threshold {percent(summary.warning_threshold)}</p>
        <p className="text-xs text-ink-muted">Run: {summary.run_id ?? 'Legacy result (run ID unavailable)'}</p>
        <p className="text-sm font-medium text-ink">
          {summary.limits ? summary.limits.is_estimated === true ? 'Estimated IRS limits' : summary.limits.is_estimated === false ? 'Recorded non-estimated IRS limits' : 'Limit estimate status unavailable' : 'IRS limits unavailable'}
          {summary.limits?.differs_from_current_seed && ' · Recorded limits differ from current seed'}
        </p>
        {summary.limits && <p className="text-sm text-ink-muted">Base deferral limit {money(summary.limits.base_limit)} · Total with catch-up {money(summary.limits.catch_up_limit)} · Total with super catch-up {money(summary.limits.super_catch_up_limit)} · Annual additions {money(summary.limits.annual_additions_limit)} · Compensation cap {money(summary.limits.compensation_limit)}</p>}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {measures.map(({ metric, title, values }) => <div key={metric} className="bg-surface-raised border border-border rounded-xl p-4 space-y-2">
          <h3 className="font-semibold text-ink">{title}</h3>
          {(Object.keys(labels) as ComplianceStatus[]).map(status => <button key={status} type="button" onClick={() => select(metric, status)} className="w-full flex justify-between text-sm text-ink-muted rounded p-2 hover:bg-surface-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-fidelity-green">
            <span>{metric === '401a17' && status === 'over_limit' ? 'Compensation above cap' : labels[status]}</span><span>{values[status]}</span>
          </button>)}
          <p className="text-sm text-ink">{metric === '401a17' ? 'Compensation excluded by cap' : 'Excess contributions'}: {money(values.excess)}</p>
        </div>)}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {([{ metric: 'catch_up' as const, title: ordinaryTitle, values: summary.catch_up }, { metric: 'super_catch_up' as const, title: superTitle, values: summary.super_catch_up }]).map(({ metric, title, values }) => <div key={metric} className="bg-surface-raised border border-border rounded-xl p-4 space-y-2">
          <button type="button" className="font-semibold text-fidelity-green hover:underline" onClick={() => select(metric)}>{title}</button>
          <p className="text-sm text-ink-muted">{values.eligible_count} age-eligible · {values.utilizing_count} utilizing · {values.available_count} with available contribution data</p>
          <p className="text-sm text-ink">Modeled usage {money(values.used)} / {money(values.capacity)} ({percent(values.utilization)})</p>
          <p className="text-sm text-ink-muted">Remaining catch-up capacity: {money(values.remaining_capacity)}</p>
        </div>)}
      </div>
      <div className="bg-surface-raised border border-border rounded-xl p-4 space-y-2">
        <h3 className="font-semibold text-ink">Existing NDT results</h3>
        <div className="flex flex-wrap gap-4">{summary.ndt.map(test => <button type="button" key={test.test_type} onClick={() => onOpenTest(test.test_type)} className="text-sm text-fidelity-green hover:underline">
          {test.test_type.toUpperCase()}: {test.result.toUpperCase()}{test.margin != null && ` · Margin ${percent(test.margin)}`}
          {test.message && <span className="block text-xs text-ink-muted">{test.message}</span>}
        </button>)}</div>
      </div>
      <ul className="text-xs text-ink-muted list-disc pl-5 space-y-1">{summary.notes.map(note => <li key={note}>{note}</li>)}</ul>
      {selection && <div className="bg-surface-raised border border-border rounded-xl p-4 space-y-3">
        <div className="flex justify-between"><h3 className="font-semibold text-ink">Employee detail · {selection.metric}{selection.status && ` · ${labels[selection.status]}`}</h3><button type="button" className="text-sm text-ink-muted" onClick={() => setSelection(null)}>Close detail</button></div>
        {loading && <p role="status" className="text-sm text-ink-muted">Loading employee detail…</p>}
        {error && <p role="alert" className="text-sm text-danger-ink">{error}</p>}
        {page && <>
          <div className="overflow-x-auto"><table className="w-full text-sm text-ink-muted">
            <thead><tr>{['Employee ID', 'Plan design', 'Age', 'Amount', 'Applicable limit / capacity', 'Headroom / remaining capacity', 'Status'].map(label => <th key={label} className="text-left p-2">{label}</th>)}</tr></thead>
            <tbody>{page.employees.map(employee => {
              const measure = selection.metric === '402g' ? employee.deferrals : selection.metric === '415c' ? employee.annual_additions : employee.compensation;
              const catchUp = selection.metric === 'catch_up' || selection.metric === 'super_catch_up';
              return <tr key={`${employee.employee_id}:${employee.plan_design_id}`} className="border-t border-border">
                <td className="p-2">{employee.employee_id}</td><td className="p-2">{employee.plan_design_id ?? 'Unavailable'}</td><td className="p-2">{employee.age ?? 'Unavailable'}</td>
                <td className="p-2">{money(catchUp ? employee.modeled_catch_up_used : measure.amount)}</td><td className="p-2">{money(catchUp ? employee.catch_up_capacity : measure.limit)}</td><td className="p-2">{money(catchUp ? employee.remaining_catch_up_capacity : measure.headroom)}</td><td className="p-2">{catchUp ? 'Modeled catch-up' : labels[measure.status]}</td>
              </tr>;
            })}</tbody>
          </table></div>
          <div className="flex justify-between items-center text-sm text-ink-muted">
            <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))} className="disabled:opacity-50">Previous</button>
            <span>{page.total === 0 ? 'No employees in this group' : `${offset + 1}–${offset + page.employees.length} of ${page.total}`}</span>
            <button type="button" disabled={offset + page.employees.length >= page.total} onClick={() => setOffset(offset + 50)} className="disabled:opacity-50">Next</button>
          </div>
        </>}
      </div>}
    </section>
  );
}
