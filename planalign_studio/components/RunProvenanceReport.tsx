import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CheckCircle,
  Clipboard,
  Download,
  FileJson,
  FileText,
  Loader2,
  ShieldCheck,
  XCircle,
} from 'lucide-react';

import {
  downloadRunProvenanceBundle,
  downloadRunProvenanceFile,
  getRunProvenance,
  ProvenanceReportEnvelope,
} from '../services/api';

function display(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Unavailable';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
}

function formatTimestamp(value: string | null): string {
  return value ? new Date(value).toLocaleString() : 'Unavailable';
}

function formatDuration(value: number | null): string {
  if (value === null) return 'Unavailable';
  if (value < 60) return `${value.toFixed(1)} seconds`;
  return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
}

function dispositionStyle(disposition: string): string {
  if (disposition === 'fully_verified') return 'border-emerald-200 bg-emerald-50 text-emerald-800';
  if (disposition === 'incomplete') return 'border-amber-200 bg-amber-50 text-amber-800';
  return 'border-red-200 bg-red-50 text-red-800';
}

function dispositionIcon(disposition: string): React.ReactNode {
  if (disposition === 'fully_verified') return <CheckCircle size={20} />;
  if (disposition === 'incomplete') return <AlertTriangle size={20} />;
  return <XCircle size={20} />;
}

function Section({
  title,
  children,
}: Readonly<{ title: string; children: React.ReactNode }>) {
  return (
    <section className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
      <h2 className="border-b border-gray-100 px-5 py-4 font-semibold text-gray-900">{title}</h2>
      <div className="p-5">{children}</div>
    </section>
  );
}

function EvidenceValue({ label, value, mono = false }: Readonly<{
  label: string;
  value: unknown;
  mono?: boolean;
}>) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className={`mt-1 break-all text-sm text-gray-900 ${mono ? 'font-mono' : ''}`}>
        {display(value)}
      </dd>
    </div>
  );
}

export default function RunProvenanceReport() {
  const { scenarioId, runId } = useParams<{ scenarioId: string; runId: string }>();
  const navigate = useNavigate();
  const [envelope, setEnvelope] = useState<ProvenanceReportEnvelope | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [download, setDownload] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load(): Promise<void> {
      if (!runId) {
        setError('No archived run was selected.');
        setLoading(false);
        return;
      }
      try {
        setLoading(true);
        setError(null);
        const response = await getRunProvenance(runId);
        if (!cancelled) setEnvelope(response);
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : 'Unable to load the provenance report.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [runId]);

  const handleDownload = async (format: 'zip' | 'json' | 'markdown'): Promise<void> => {
    if (!runId) return;
    try {
      setDownload(format);
      setDownloadError(null);
      if (format === 'zip') await downloadRunProvenanceBundle(runId);
      else await downloadRunProvenanceFile(runId, format);
    } catch (caught) {
      setDownloadError(caught instanceof Error ? caught.message : 'Unable to download the audit report.');
    } finally {
      setDownload(null);
    }
  };

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="animate-spin text-fidelity-green" size={44} />
      </div>
    );
  }

  if (error || !envelope) {
    return (
      <div className="flex h-96 flex-col items-center justify-center text-center">
        <AlertCircle className="mb-3 text-red-500" size={44} />
        <h1 className="text-xl font-semibold text-gray-900">Unable to open provenance report</h1>
        <p className="mt-2 max-w-xl text-gray-600">{error ?? 'The archived report is unavailable.'}</p>
        <button
          onClick={() => navigate(scenarioId ? `/simulate/${scenarioId}` : '/simulate')}
          className="mt-5 rounded-lg bg-fidelity-green px-4 py-2 font-medium text-white"
        >
          Back to Run History
        </button>
      </div>
    );
  }

  const { report } = envelope;
  const { evidence } = report;

  return (
    <div className="space-y-6 pb-8">
      <header className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-3">
            <button
              onClick={() => navigate(scenarioId ? `/simulate/${scenarioId}` : '/simulate')}
              className="rounded-lg p-2 text-gray-500 hover:bg-gray-100"
              title="Back to Run History"
            >
              <ArrowLeft size={20} />
            </button>
            <div>
              <p className="text-sm font-medium uppercase tracking-wide text-fidelity-green">Run provenance</p>
              <h1 className="mt-1 text-2xl font-bold text-gray-900">Audit Report</h1>
              <p className="mt-2 break-all font-mono text-xs text-gray-500">{evidence.run.run_id}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => void handleDownload('zip')}
              disabled={download !== null}
              className="flex items-center rounded-lg bg-fidelity-green px-4 py-2 text-sm font-medium text-white hover:bg-fidelity-dark disabled:opacity-60"
            >
              {download === 'zip' ? <Loader2 className="mr-2 animate-spin" size={16} /> : <Download className="mr-2" size={16} />}
              Download Audit Report
            </button>
            <button
              onClick={() => void handleDownload('json')}
              disabled={download !== null}
              className="flex items-center rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-60"
            >
              <FileJson className="mr-2" size={16} /> JSON
            </button>
            <button
              onClick={() => void handleDownload('markdown')}
              disabled={download !== null}
              className="flex items-center rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-60"
            >
              <FileText className="mr-2" size={16} /> Markdown
            </button>
          </div>
        </div>

        <div className={`mt-5 flex items-center gap-3 rounded-lg border p-4 ${dispositionStyle(report.verification_disposition)}`}>
          {dispositionIcon(report.verification_disposition)}
          <div>
            <p className="font-semibold">{report.verification_disposition.replaceAll('_', ' ').toUpperCase()}</p>
            <p className="text-sm">
              Archived status: {evidence.run.status} · {report.missing_evidence.length} evidence finding{report.missing_evidence.length === 1 ? '' : 's'}
            </p>
          </div>
        </div>
        {downloadError && <p className="mt-3 text-sm text-red-600">{downloadError}</p>}
      </header>

      {report.missing_evidence.length > 0 && (
        <Section title="Missing or Unavailable Evidence">
          <div className="space-y-3">
            {report.missing_evidence.map(finding => (
              <div key={`${finding.field_path}-${finding.code}`} className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <code className="text-xs font-semibold text-amber-900">{finding.field_path}</code>
                  <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">{finding.code}</span>
                  {finding.required && <span className="text-xs font-medium text-red-700">Required</span>}
                </div>
                <p className="mt-1 text-sm text-amber-900">{finding.reason}</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section title="Run Identity and Execution">
        <dl className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <EvidenceValue label="Workspace" value={evidence.run.workspace_id} />
          <EvidenceValue label="Scenario design" value={evidence.run.scenario_id} />
          <EvidenceValue label="Plan design" value={evidence.run.plan_design_id} />
          <EvidenceValue label="Random seed" value={evidence.random_seed} mono />
          <EvidenceValue label="Simulation years" value={evidence.run.intended_start_year === null ? null : `${evidence.run.intended_start_year}–${evidence.run.intended_end_year}`} />
          <EvidenceValue label="Completed years" value={evidence.run.completed_years.join(', ') || null} />
          <EvidenceValue label="Started" value={formatTimestamp(evidence.timing.started_at)} />
          <EvidenceValue label="Completed" value={formatTimestamp(evidence.timing.completed_at)} />
          <EvidenceValue label="Duration" value={formatDuration(evidence.timing.duration_seconds)} />
          <EvidenceValue label="Terminal stage" value={evidence.timing.terminal_stage} />
        </dl>
        {evidence.timing.stage_completions.length > 0 && (
          <div className="mt-5 overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500"><tr><th className="px-3 py-2">Year</th><th className="px-3 py-2">Stage</th><th className="px-3 py-2">Completed</th><th className="px-3 py-2 text-right">Seconds</th><th className="px-3 py-2">Outcome</th></tr></thead>
              <tbody>{evidence.timing.stage_completions.map(stage => <tr key={`${stage.simulation_year}-${stage.stage}`} className="border-t border-gray-100"><td className="px-3 py-2">{display(stage.simulation_year)}</td><td className="px-3 py-2">{stage.stage}</td><td className="px-3 py-2">{formatTimestamp(stage.completed_at)}</td><td className="px-3 py-2 text-right">{display(stage.duration_seconds)}</td><td className="px-3 py-2">{stage.outcome}</td></tr>)}</tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Software, Source, and Configuration">
        <dl className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <EvidenceValue label="PlanAlign version" value={evidence.software.planalign_version} />
          <EvidenceValue label="Git commit" value={evidence.software.git_commit_sha} mono />
          <EvidenceValue label="Working tree" value={evidence.software.working_tree_state} />
          <EvidenceValue label="Working-tree fingerprint" value={evidence.software.working_tree_fingerprint} mono />
          <EvidenceValue label="Configuration fingerprint" value={evidence.configuration.fingerprint} mono />
          <EvidenceValue label="Fingerprint method" value={evidence.configuration.fingerprint_method} />
          <EvidenceValue label="Redacted fields" value={evidence.configuration.redactions.join(', ') || 'None'} />
        </dl>
        <details className="mt-5 rounded-lg border border-gray-200 bg-gray-50">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-gray-800">Effective configuration</summary>
          <pre className="max-h-96 overflow-auto border-t border-gray-200 p-4 text-xs text-gray-700">
            {JSON.stringify(evidence.configuration.effective, null, 2)}
          </pre>
        </details>
      </Section>

      <Section title="Input Fingerprints">
        {evidence.census_input ? (
          <dl className="mb-5 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <EvidenceValue label="Census logical name" value={evidence.census_input.logical_name} />
            <EvidenceValue label="Census SHA-256" value={evidence.census_input.sha256} mono />
            <EvidenceValue label="Census records" value={evidence.census_input.record_count} />
            <EvidenceValue label="Census size" value={evidence.census_input.size_bytes} />
            <EvidenceValue label="Census format" value={evidence.census_input.format} />
          </dl>
        ) : <p className="mb-5 text-sm text-gray-500">Census fingerprint unavailable.</p>}
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
              <tr><th className="px-3 py-2">Seed file</th><th className="px-3 py-2">SHA-256</th><th className="px-3 py-2 text-right">Bytes</th></tr>
            </thead>
            <tbody>
              {evidence.seed_files.map(seed => (
                <tr key={seed.logical_name} className="border-t border-gray-100">
                  <td className="px-3 py-2">{seed.logical_name}</td>
                  <td className="px-3 py-2 font-mono text-xs">{seed.sha256}</td>
                  <td className="px-3 py-2 text-right">{seed.size_bytes.toLocaleString()}</td>
                </tr>
              ))}
              {evidence.seed_files.length === 0 && <tr><td colSpan={3} className="px-3 py-4 text-center text-gray-500">No seed fingerprints available.</td></tr>}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Event Counts by Year">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500"><tr><th className="px-3 py-2">Year</th><th className="px-3 py-2">Event type</th><th className="px-3 py-2 text-right">Count</th></tr></thead>
            <tbody>
              {evidence.event_counts.map(item => <tr key={`${item.simulation_year}-${item.event_type}`} className="border-t border-gray-100"><td className="px-3 py-2">{item.simulation_year}</td><td className="px-3 py-2">{item.event_type}</td><td className="px-3 py-2 text-right">{item.count.toLocaleString()}</td></tr>)}
              {evidence.event_counts.length === 0 && <tr><td colSpan={3} className="px-3 py-4 text-center text-gray-500">No completed-year event counts available.</td></tr>}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Annual Workforce Reconciliation">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500"><tr><th className="px-3 py-2">Year</th><th className="px-3 py-2 text-right">Opening</th><th className="px-3 py-2">Source</th><th className="px-3 py-2 text-right">Hires</th><th className="px-3 py-2 text-right">Terminations</th><th className="px-3 py-2 text-right">Expected</th><th className="px-3 py-2 text-right">Actual</th><th className="px-3 py-2 text-right">Variance</th></tr></thead>
            <tbody>
              {evidence.workforce_reconciliations.map(item => <tr key={item.simulation_year} className="border-t border-gray-100"><td className="px-3 py-2">{item.simulation_year}</td><td className="px-3 py-2 text-right">{display(item.opening_workforce)}</td><td className="px-3 py-2">{display(item.opening_source)}</td><td className="px-3 py-2 text-right">{display(item.hires)}</td><td className="px-3 py-2 text-right">{display(item.terminations)}</td><td className="px-3 py-2 text-right">{display(item.expected_closing_workforce)}</td><td className="px-3 py-2 text-right">{display(item.actual_closing_workforce)}</td><td className="px-3 py-2 text-right">{display(item.variance)}</td></tr>)}
              {evidence.workforce_reconciliations.length === 0 && <tr><td colSpan={8} className="px-3 py-4 text-center text-gray-500">No workforce reconciliation available.</td></tr>}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title={`Captured Validation Results — ${evidence.validation_disposition.replaceAll('_', ' ')}`}>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500"><tr><th className="px-3 py-2">Year</th><th className="px-3 py-2">Check</th><th className="px-3 py-2">Severity</th><th className="px-3 py-2">Outcome</th><th className="px-3 py-2 text-right">Affected records</th></tr></thead>
            <tbody>
              {evidence.validation_results.map(item => <tr key={`${item.simulation_year}-${item.check_name}-${item.severity}`} className="border-t border-gray-100"><td className="px-3 py-2">{item.simulation_year}</td><td className="px-3 py-2">{item.check_name}</td><td className="px-3 py-2">{item.severity}</td><td className="px-3 py-2">{item.passed ? <span className="font-medium text-emerald-700">Pass</span> : <span className="font-medium text-red-700">Fail</span>}</td><td className="px-3 py-2 text-right">{display(item.affected_record_count)}</td></tr>)}
              {evidence.validation_results.length === 0 && <tr><td colSpan={5} className="px-3 py-4 text-center text-gray-500">No captured validation results available.</td></tr>}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Integrity Verification and Reviewer Sign-Off">
        <div className="flex items-start gap-3 rounded-lg bg-gray-50 p-4">
          <ShieldCheck className="mt-0.5 shrink-0 text-fidelity-green" size={24} />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-gray-900">{report.digest.algorithm} · {report.digest.canonicalization}</p>
            <code className="mt-2 block break-all text-xs text-gray-600">{report.digest.value}</code>
          </div>
          <button
            onClick={() => {
              void navigator.clipboard.writeText(report.digest.value);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 2000);
            }}
            className="flex shrink-0 items-center rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            <Clipboard className="mr-2" size={15} /> {copied ? 'Copied' : 'Copy digest'}
          </button>
        </div>
        <div className="mt-5 grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
          <EvidenceValue label="Report digest approved" value={report.sign_off.report_digest} mono />
          <EvidenceValue label="Reviewer name" value="______________________________" />
          <EvidenceValue label="Decision" value="______________________________" />
          <EvidenceValue label="Timestamp" value="______________________________" />
          <EvidenceValue label="Comments" value="______________________________" />
        </div>
      </Section>
    </div>
  );
}
