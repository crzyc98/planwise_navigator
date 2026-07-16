import React, { FormEvent, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { EmployeeSearchResult, searchEmployees, timelineUrl } from '../../services/api';

interface Props { workspaceId: string; scenarioId: string; onSelect: (employeeId: string) => void; }

export default function EmployeeSearch({ workspaceId, scenarioId, onSelect }: Readonly<Props>) {
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [year, setYear] = useState('');
  const [level, setLevel] = useState('');
  const [enrolled, setEnrolled] = useState('');
  const [escalations, setEscalations] = useState('');
  const [results, setResults] = useState<EmployeeSearchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  const runSearch = (nextPage = 1) => searchEmployees(workspaceId, scenarioId, {
    q: q || undefined, status: status || undefined, year: year ? Number(year) : undefined,
    level: level ? Number(level) : undefined, enrolled: enrolled ? enrolled === 'true' : undefined,
    has_escalations: escalations ? escalations === 'true' : undefined, page: nextPage, page_size: 25,
  }).then((response) => { setResults(response.results); setTotal(response.total); setPage(response.page); });

  useEffect(() => {
    if (q.trim().length < 2) return;
    const timer = window.setTimeout(() => { void runSearch(1); }, 250);
    return () => window.clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, workspaceId, scenarioId]);

  const submit = (event: FormEvent) => { event.preventDefault(); void runSearch(1); };
  return (
    <div className="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
      <form onSubmit={submit} className="grid gap-2 md:grid-cols-3 lg:grid-cols-6">
        <input aria-label="Employee ID" className="rounded border px-3 py-2 lg:col-span-2" placeholder="Employee ID" value={q} onChange={(e) => setQ(e.target.value)} />
        <input aria-label="Status" className="rounded border px-3 py-2" placeholder="Status" value={status} onChange={(e) => setStatus(e.target.value)} />
        <input aria-label="Level" className="rounded border px-3 py-2" type="number" placeholder="Level" value={level} onChange={(e) => setLevel(e.target.value)} />
        <input aria-label="Year" className="rounded border px-3 py-2" type="number" placeholder="Year" value={year} onChange={(e) => setYear(e.target.value)} />
        <button className="rounded bg-fidelity-green px-3 py-2 font-medium text-white">Find employees</button>
        <select aria-label="Enrollment" className="rounded border px-3 py-2" value={enrolled} onChange={(e) => setEnrolled(e.target.value)}><option value="">Any enrollment</option><option value="true">Enrolled</option><option value="false">Not enrolled</option></select>
        <select aria-label="Escalations" className="rounded border px-3 py-2" value={escalations} onChange={(e) => setEscalations(e.target.value)}><option value="">Any escalation</option><option value="true">Has escalations</option><option value="false">No escalations</option></select>
      </form>
      {results.length > 0 ? (
        <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b"><th>ID</th><th>Status</th><th>Level</th><th>Compensation</th><th>Year</th></tr></thead><tbody>{results.map((row) => <tr key={row.employee_id} className="border-b"><td className="py-2"><Link className="font-medium text-fidelity-green hover:underline" to={timelineUrl(workspaceId, scenarioId, row.employee_id)} onClick={() => onSelect(row.employee_id)}>{row.employee_id}</Link></td><td>{row.employment_status ?? '—'}</td><td>{row.level_id ?? '—'}</td><td>{row.current_compensation?.toLocaleString() ?? '—'}</td><td>{row.simulation_year}</td></tr>)}</tbody></table></div>
      ) : total === 0 && (q || status || level || year || enrolled || escalations) ? <p className="text-sm text-gray-500">No employees match these filters.</p> : null}
      {total > 25 && <div className="flex items-center gap-3"><button disabled={page === 1} onClick={() => void runSearch(page - 1)}>Previous</button><span>Page {page}</span><button disabled={page * 25 >= total} onClick={() => void runSearch(page + 1)}>Next</button></div>}
    </div>
  );
}
