import React, { useMemo, useState } from 'react';
import { AlertTriangle, Download, FileSearch, Loader2, RefreshCw } from 'lucide-react';
import {
  downloadEvidencePack,
  EvidenceFigure,
  EvidenceMetric,
  EvidencePackEnvelope,
  getScenarioEvidencePack,
} from '../services/api';

const METRICS: Array<{ id: EvidenceMetric; label: string }> = [
  { id: 'active_headcount', label: 'Active headcount' },
  { id: 'total_compensation', label: 'Total compensation' },
  { id: 'employer_match_cost', label: 'Employer match cost' },
  { id: 'total_employer_plan_cost', label: 'Total employer plan cost' },
  { id: 'participation_rate', label: 'Participation rate' },
  { id: 'avg_deferral_rate', label: 'Average deferral rate' },
];

interface Props {
  workspaceId: string;
  scenarioId: string;
  startYear: number;
  endYear: number;
}

function formatFigure(figure: EvidenceFigure): string {
  if (figure.status === 'defined') {
    const value = Number(figure.value ?? 0);
    if (figure.unit === 'currency') {
      return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
    }
    if (figure.unit === 'count') return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);
    if (figure.unit === 'rate') return `${(value * 100).toFixed(2)}%`;
    return `${value.toFixed(2)}%`;
  }
  return `${figure.status === 'suppressed' ? 'Suppressed' : 'Undefined'} — ${figure.reason}`;
}

function FigureValue({ figure }: { figure: EvidenceFigure }) {
  return <span title={figure.value === null ? figure.reason ?? undefined : `Canonical: ${figure.value}`}>{formatFigure(figure)}</span>;
}

export default function EvidencePackPanel({ workspaceId, scenarioId, startYear, endYear }: Props) {
  const years = useMemo(() => Array.from({ length: endYear - startYear + 1 }, (_, index) => startYear + index), [startYear, endYear]);
  const [metric, setMetric] = useState<EvidenceMetric>('employer_match_cost');
  const [baseYear, setBaseYear] = useState(startYear);
  const [targetYear, setTargetYear] = useState(endYear);
  const [envelope, setEnvelope] = useState<EvidencePackEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const validYears = baseYear < targetYear;

  const load = async () => {
    if (!validYears) return;
    setLoading(true);
    setError(null);
    try {
      const next = await getScenarioEvidencePack(workspaceId, scenarioId, metric, baseYear, targetYear);
      setEnvelope(next);
    } catch (reason) {
      setEnvelope(null);
      setError(reason instanceof Error ? reason.message : 'Unable to compute evidence pack');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-3 rounded-lg border border-gray-200 bg-white p-4 md:grid-cols-4">
        <label className="text-sm text-gray-700">Metric
          <select aria-label="Evidence metric" value={metric} onChange={event => setMetric(event.target.value as EvidenceMetric)} className="mt-1 w-full rounded border border-gray-300 p-2">
            {METRICS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </label>
        <label className="text-sm text-gray-700">Base year
          <select aria-label="Base year" value={baseYear} onChange={event => setBaseYear(Number(event.target.value))} className="mt-1 w-full rounded border border-gray-300 p-2">
            {years.map(year => <option key={year} value={year}>{year}</option>)}
          </select>
        </label>
        <label className="text-sm text-gray-700">Target year
          <select aria-label="Target year" value={targetYear} onChange={event => setTargetYear(Number(event.target.value))} className="mt-1 w-full rounded border border-gray-300 p-2">
            {years.map(year => <option key={year} value={year}>{year}</option>)}
          </select>
        </label>
        <div className="flex items-end">
          <button onClick={() => void load()} disabled={loading || !validYears} className="flex w-full items-center justify-center rounded bg-fidelity-green px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
            {loading ? <Loader2 size={15} className="mr-2 animate-spin" /> : <RefreshCw size={15} className="mr-2" />}
            {loading ? 'Computing evidence pack…' : 'Build evidence pack'}
          </button>
        </div>
        {!validYears && <p className="text-sm text-red-700 md:col-span-4">Target year must be later than base year.</p>}
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error} <button onClick={() => void load()} className="ml-2 font-medium underline">Retry</button></div>}
      {!envelope && !loading && !error && <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500"><FileSearch className="mx-auto mb-2" />Choose a metric and year pair, then build an evidence pack.</div>}

      {envelope && (
        <div className="space-y-4">
          {envelope.pack.warnings.map(warning => (
            <div key={warning.code} className={`flex rounded-lg border p-3 text-sm ${warning.severity === 'critical' ? 'border-red-300 bg-red-50 text-red-900' : 'border-amber-300 bg-amber-50 text-amber-900'}`}>
              <AlertTriangle size={17} className="mr-2 shrink-0" />{warning.message}
            </div>
          ))}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-200 bg-white p-4">
            <div>
              <h3 className="font-semibold text-gray-900">{envelope.pack.change.label}: {baseYear} to {targetYear}</h3>
              <p className="text-sm text-gray-600"><FigureValue figure={envelope.pack.change.base_value} /> → <FigureValue figure={envelope.pack.change.target_value} /> · Change <FigureValue figure={envelope.pack.change.total_change} /></p>
              <p className="mt-1 text-sm text-gray-600">Base population: <FigureValue figure={envelope.pack.change.base_population} /> · Target population: <FigureValue figure={envelope.pack.change.target_population} /></p>
              <p className="mt-1 text-xs text-gray-500">Run {envelope.pack.provenance.run_id} · {envelope.pack.provenance.verification_disposition}</p>
            </div>
            <button onClick={() => downloadEvidencePack(envelope)} disabled={loading} className="flex items-center rounded border border-fidelity-green px-3 py-2 text-sm font-medium text-fidelity-green disabled:opacity-50"><Download size={15} className="mr-2" />Export Evidence Pack</button>
          </div>
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
            <h4 className="font-semibold text-emerald-950">Executive interpretation</h4>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-emerald-950">{envelope.pack.executive_summary.map(item => <li key={item}>{item}</li>)}</ul>
          </div>
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
            <table className="w-full text-left text-sm"><thead className="bg-gray-50"><tr><th className="p-3">Driver</th><th className="p-3">Contribution</th><th className="p-3">Share</th><th className="p-3">Population</th><th className="p-3">Citation</th></tr></thead>
              <tbody>{envelope.pack.drivers.map(driver => <tr key={driver.id} className="border-t"><td className="p-3"><div className="font-medium">{driver.label}</div><div className="text-xs text-gray-500">{driver.description}</div>{driver.base_rate && driver.target_rate && <div className="mt-1 text-xs font-medium text-gray-700">Effective rate: <FigureValue figure={driver.base_rate} /> → <FigureValue figure={driver.target_rate} /></div>}</td><td className="p-3"><FigureValue figure={driver.contribution} /></td><td className="p-3"><FigureValue figure={driver.share_of_change} /></td><td className="p-3"><FigureValue figure={driver.population.count} /> {driver.population.label}</td><td className="p-3"><details><summary className="cursor-pointer font-mono text-xs">Q1.{driver.contribution.citation.result_column}</summary><pre className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap rounded bg-gray-950 p-2 text-xs text-gray-100">{driver.contribution.citation.query}</pre></details></td></tr>)}</tbody>
            </table>
          </div>
          <div className={`rounded-lg border p-4 ${envelope.pack.residual.largest_contribution ? 'border-red-300 bg-red-50' : envelope.pack.residual.material ? 'border-amber-300 bg-amber-50' : 'border-gray-200 bg-white'}`}>
            <h4 className="font-semibold">Residual</h4><p className="text-sm"><FigureValue figure={envelope.pack.residual.contribution} /> · <FigureValue figure={envelope.pack.residual.share_of_change} /></p>
          </div>
          <p className="rounded-lg bg-gray-100 p-3 text-sm text-gray-700">{envelope.pack.population_note}</p>
        </div>
      )}
    </div>
  );
}
