import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { BandGroupResult, EmployeeImpactPage, getEmployeeImpacts, timelineUrl, WinnersLosersResponse } from '../services/api';

export type ImpactFilters = { age_band?: string; tenure_band?: string };

export function impactCurrency(amount: number): string {
  return amount.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function BandImpactTable({ bands, onSelect }: Readonly<{
  bands: BandGroupResult[]; onSelect: (label: string) => void;
}>) {
  return <div className="overflow-x-auto mt-4"><table className="w-full text-sm text-right">
    <thead><tr className="border-b border-border"><th className="text-left p-2">Band / employees</th><th className="p-2">Increases</th><th className="p-2">Decreases</th><th className="p-2">Net change</th><th className="p-2">Average</th></tr></thead>
    <tbody>{bands.map(band => <tr key={band.band_label} className="border-b border-border">
      <td className="text-left p-2"><button className="text-fidelity-green underline" onClick={() => onSelect(band.band_label)} aria-label={`View employees in ${band.band_label}`}>{band.band_label} ({band.total})</button></td>
      <td className="p-2">{impactCurrency(band.total_increases)}</td><td className="p-2">{impactCurrency(band.total_decreases)}</td><td className="p-2">{impactCurrency(band.net_contribution_change)}</td><td className="p-2">{impactCurrency(band.average_change)}</td>
    </tr>)}</tbody>
  </table></div>;
}

export function EmployeeImpactTable({ page, workspaceId }: Readonly<{ page: EmployeeImpactPage; workspaceId: string }>) {
  if (page.total === 0) return <p className="py-4 text-ink-muted">No compared employees in this group.</p>;
  return <div className="overflow-x-auto"><table className="w-full text-sm text-right">
    <thead><tr className="border-b border-border"><th className="text-left p-2">Employee ID / timeline</th><th className="p-2">Plan A</th><th className="p-2">Plan B</th><th className="p-2">Change (B − A)</th><th className="p-2">Outcome</th></tr></thead>
    <tbody>{page.employees.map(row => <tr key={row.employee_id} className="border-b border-border">
      <td className="text-left p-2"><Link className="text-fidelity-green underline" to={timelineUrl(workspaceId, page.plan_a_scenario_id, row.employee_id, page.plan_b_scenario_id)}>{row.employee_id}</Link></td>
      <td className="p-2">{impactCurrency(row.plan_a_amount)}</td><td className="p-2">{impactCurrency(row.plan_b_amount)}</td><td className="p-2">{impactCurrency(row.delta)}</td><td className="p-2 capitalize">{row.status}</td>
    </tr>)}</tbody>
  </table></div>;
}

export default function WinnersLosersDetails({ workspaceId, comparison, filters, onClose, onRefresh }: Readonly<{
  workspaceId: string; comparison: WinnersLosersResponse; filters: ImpactFilters; onClose: () => void; onRefresh: () => void;
}>) {
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<EmployeeImpactPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const age = filters.age_band;
  const tenure = filters.tenure_band;
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => { heading.current?.focus(); }, []);

  useEffect(() => {
    let current = true;
    setPage(null);
    setError(null);
    getEmployeeImpacts(workspaceId, comparison, { age_band: age, tenure_band: tenure }, offset)
      .then(data => { if (current) setPage(data); })
      .catch((err: unknown) => { if (current) setError(err instanceof Error ? err.message : 'Failed to load employees'); });
    return () => { current = false; };
  }, [workspaceId, comparison, age, tenure, offset, retry]);

  return <section className="bg-surface-raised p-6 rounded-xl border border-border space-y-4" aria-label="Employee contribution detail" aria-live="polite">
    <div className="flex items-center justify-between"><h3 ref={heading} tabIndex={-1} className="text-lg font-semibold">Employee contribution detail — {age ?? 'All ages'} · {tenure ?? 'All tenures'}</h3><button className="text-fidelity-green underline" onClick={onClose}>Close detail</button></div>
    <p className="text-sm text-ink-muted">Year {comparison.final_year} · Plan A run: {comparison.plan_a_run_id ?? 'Legacy result (run ID unavailable)'} · Plan B run: {comparison.plan_b_run_id ?? 'Legacy result (run ID unavailable)'}</p>
    <p className="text-sm text-ink-muted">Timeline links open both scenarios’ currently selected results.</p>
    {error ? <div role="alert"><p className="text-danger-ink">{error}</p><div className="flex gap-4"><button className="text-fidelity-green underline" onClick={onRefresh}>Refresh comparison</button><button className="text-fidelity-green underline" onClick={() => setRetry(value => value + 1)}>Retry employee detail</button></div></div> : !page ? <p role="status">Loading employees…</p> : <>
      <p className="text-sm text-ink-muted">{page.total} compared employees · Group net change: {impactCurrency(page.net_contribution_change)} · Average: {impactCurrency(page.average_change)}</p>
      <EmployeeImpactTable page={page} workspaceId={workspaceId} />
      <div className="flex gap-4 items-center text-sm"><button disabled={offset === 0} className="text-fidelity-green disabled:text-ink-subtle" onClick={() => setOffset(Math.max(0, offset - page.limit))}>Previous employees</button><span>{page.total ? `${offset + 1}–${Math.min(offset + page.limit, page.total)} of ${page.total}` : '0 of 0'}</span><button disabled={offset + page.limit >= page.total} className="text-fidelity-green disabled:text-ink-subtle" onClick={() => setOffset(offset + page.limit)}>Next employees</button></div>
    </>}
  </section>;
}
