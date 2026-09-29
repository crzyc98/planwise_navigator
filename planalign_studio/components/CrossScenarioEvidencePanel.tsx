import React, { useState } from 'react';
import { AlertTriangle, Download, FileSearch, Info, Loader2, RefreshCw } from 'lucide-react';
import {
  CrossScenarioEvidencePackEnvelope,
  CrossScenarioFigure,
  downloadEvidencePack,
  EvidenceMetric,
  getCrossScenarioEvidencePack,
} from '../services/api';
import { EVIDENCE_METRICS, FigureValue } from './EvidencePackPanel';

type PackWarning = CrossScenarioEvidencePackEnvelope['pack']['warnings'][number];

interface Props {
  workspaceId: string;
  scenarioA: string;
  scenarioB: string;
  nameA: string;
  nameB: string;
  years: number[];
}

const WARNING_STYLES: Record<PackWarning['severity'], string> = {
  critical: 'border-danger-border bg-danger-surface text-danger-ink',
  caution: 'border-warning-border bg-warning-surface text-warning-ink',
  info: 'border-border bg-info-surface text-info-ink',
};

/** Label a figure's citations as `QA.value, QB.value`, one per scenario store. */
export function citationLabel(figure: Pick<CrossScenarioFigure, 'citations'>): string {
  return figure.citations.map(citation => `${citation.query_id}.${citation.result_column}`).join(', ');
}

export function differencesSummary(count: number): string {
  if (count === 0) return 'No configuration differences cited';
  return `${count} configuration difference${count === 1 ? '' : 's'} cited`;
}

function WarningBanner({ warning }: { warning: PackWarning }) {
  const Icon = warning.severity === 'info' ? Info : AlertTriangle;
  return (
    <div className={`flex rounded-lg border p-3 text-sm ${WARNING_STYLES[warning.severity]}`}>
      <Icon size={17} className="mr-2 shrink-0" />{warning.message}
    </div>
  );
}

function Citations({ figure }: { figure: CrossScenarioFigure }) {
  return (
    <details>
      <summary className="cursor-pointer font-mono text-xs">
        {citationLabel(figure)}
      </summary>
      {figure.citations.map(citation => (
        <pre key={citation.query_id} className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap rounded bg-surface-inverse p-2 text-xs text-ink-subtle">
          {`-- ${citation.query_id}: ${citation.result_store}\n${citation.query}`}
        </pre>
      ))}
    </details>
  );
}

function PackBody({ envelope, nameA, nameB }: { envelope: CrossScenarioEvidencePackEnvelope; nameA: string; nameB: string }) {
  const { pack } = envelope;
  const { change, residual } = pack;
  const differences = pack.config_differences ?? [];
  return (
    <div className="space-y-4">
      {(pack.warnings ?? []).map((warning, index) => <WarningBanner key={`${warning.code}-${index}`} warning={warning} />)}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface-raised p-4">
        <div>
          <h3 className="font-semibold text-ink">{change.label}, {change.year}</h3>
          <p className="text-sm text-ink-muted">{nameA} <FigureValue figure={change.value_a} /> · {nameB} <FigureValue figure={change.value_b} /> · Difference (B − A) <FigureValue figure={change.total_change} /></p>
          <p className="mt-1 text-sm text-ink-muted">Populations: <FigureValue figure={change.population_a} /> (A) · <FigureValue figure={change.population_b} /> (B)</p>
          <p className="mt-1 text-xs text-ink-muted">
            A: run {pack.provenance_a.run_id} · {pack.provenance_a.verification_disposition} — B: run {pack.provenance_b.run_id} · {pack.provenance_b.verification_disposition}
          </p>
        </div>
        <button onClick={() => downloadEvidencePack(envelope)} className="flex items-center rounded border border-fidelity-green px-3 py-2 text-sm font-medium text-fidelity-green"><Download size={15} className="mr-2" />Export Evidence Pack</button>
      </div>
      <div className="rounded-lg border border-success-border bg-success-surface p-4">
        <h4 className="font-semibold text-success-ink">Executive interpretation</h4>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-success-ink">{pack.executive_summary.map(item => <li key={item}>{item}</li>)}</ul>
      </div>
      <details className="rounded-lg border border-border bg-surface-raised p-4 text-sm">
        <summary className="cursor-pointer font-semibold text-ink">
          {differencesSummary(differences.length)}
        </summary>
        <ul className="mt-2 space-y-1 text-ink-muted">
          {differences.map(item => <li key={item.path}><code>{item.path}</code>: {item.value_a ?? '—'} → {item.value_b ?? '—'}</li>)}
        </ul>
      </details>
      <div className="overflow-x-auto rounded-lg border border-border bg-surface-raised">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-subtle"><tr><th className="p-3">Driver</th><th className="p-3">Contribution</th><th className="p-3">Share</th><th className="p-3">Population (A / B)</th><th className="p-3">Citation</th></tr></thead>
          <tbody>
            {pack.drivers.map(driver => (
              <tr key={driver.id} className="border-t">
                <td className="p-3">
                  <div className="font-medium">{driver.label}</div>
                  <div className="text-xs text-ink-muted">{driver.description}</div>
                  {driver.rate_a && driver.rate_b && <div className="mt-1 text-xs font-medium text-ink-muted">Effective rate: <FigureValue figure={driver.rate_a} /> (A) vs <FigureValue figure={driver.rate_b} /> (B)</div>}
                </td>
                <td className="p-3"><FigureValue figure={driver.contribution} /></td>
                <td className="p-3"><FigureValue figure={driver.share_of_change} /></td>
                <td className="p-3"><FigureValue figure={driver.population.count_a} /> / <FigureValue figure={driver.population.count_b} /> {driver.population.label}</td>
                <td className="p-3"><Citations figure={driver.contribution} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={`rounded-lg border p-4 ${residual.largest_contribution ? 'border-danger-border bg-danger-surface' : residual.material ? 'border-warning-border bg-warning-surface' : 'border-border bg-surface-raised'}`}>
        <h4 className="font-semibold">Residual</h4><p className="text-sm"><FigureValue figure={residual.contribution} /> · <FigureValue figure={residual.share_of_change} /></p>
      </div>
      <p className="rounded-lg bg-surface-subtle p-3 text-sm text-ink-muted">{pack.population_note}</p>
    </div>
  );
}

export default function CrossScenarioEvidencePanel({ workspaceId, scenarioA, scenarioB, nameA, nameB, years }: Props) {
  const [metric, setMetric] = useState<EvidenceMetric>('total_employer_plan_cost');
  const [year, setYear] = useState(years.at(-1) ?? 0);
  const [envelope, setEnvelope] = useState<CrossScenarioEvidencePackEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setEnvelope(await getCrossScenarioEvidencePack(workspaceId, scenarioA, scenarioB, metric, year));
    } catch (reason) {
      setEnvelope(null);
      setError(reason instanceof Error ? reason.message : 'Unable to compute evidence pack');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section id="explain-difference" className="scroll-mt-4 space-y-4 rounded-xl border border-border bg-surface-raised p-5 shadow-sm">
      <div>
        <h2 className="font-semibold text-ink">Explain the difference</h2>
        <p className="text-sm text-ink-muted">Decompose one metric's gap between {nameA} (A) and {nameB} (B) into cited drivers and configuration differences.</p>
      </div>
      <div className="grid gap-3 rounded-lg border border-border bg-surface-subtle p-4 md:grid-cols-3">
        <label className="text-sm text-ink-muted">Metric
          <select aria-label="Evidence metric" value={metric} onChange={event => setMetric(event.target.value as EvidenceMetric)} className="mt-1 w-full rounded border border-border-strong p-2">
            {EVIDENCE_METRICS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </label>
        <label className="text-sm text-ink-muted">Year
          <select aria-label="Evidence year" value={year} onChange={event => setYear(Number(event.target.value))} className="mt-1 w-full rounded border border-border-strong p-2">
            {years.map(item => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <div className="flex items-end">
          <button onClick={() => void load()} disabled={loading || years.length === 0} className="flex w-full items-center justify-center rounded bg-fidelity-green px-3 py-2 text-sm font-medium text-ink-inverse disabled:opacity-50">
            {loading ? <Loader2 size={15} className="mr-2 animate-spin" /> : <RefreshCw size={15} className="mr-2" />}
            {loading ? 'Computing evidence pack…' : 'Build evidence pack'}
          </button>
        </div>
      </div>
      {error && <div className="rounded-lg border border-danger-border bg-danger-surface p-3 text-sm text-danger-ink">{error} <button onClick={() => void load()} className="ml-2 font-medium underline">Retry</button></div>}
      {!envelope && !loading && !error && <div className="rounded-lg border border-dashed border-border-strong p-8 text-center text-sm text-ink-muted"><FileSearch className="mx-auto mb-2" />Choose a metric and year, then build an evidence pack.</div>}
      {envelope && <PackBody envelope={envelope} nameA={nameA} nameB={nameB} />}
    </section>
  );
}
