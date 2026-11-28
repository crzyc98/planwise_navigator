/**
 * The Multi-Year Cost and Compensation matrices on Cost Comparison. Every
 * figure comes from `buildCostSummary`, the same object the summary workbook
 * is built from.
 */
import React from 'react';
import type { DCPlanCohort } from '../services/api';
import {
  formatCurrency,
  formatPercent,
  formatSigned,
  type ScenarioSummary,
  type SummaryYear,
} from './costSummary';
import { describeDifference, formatCostBand, formatDifference, type CostBandView, type SeedRangeRow } from './seedRanges';

const VALUE_CELL = 'px-6 py-4 whitespace-nowrap text-right text-sm';
const SUB_CELL = 'px-6 py-2 whitespace-nowrap text-right text-xs';
const SUB_LABEL = 'px-6 py-2 whitespace-nowrap border-r border-border pl-12 text-xs';
const TOTAL_CELL = 'bg-surface-subtle/50 border-l border-border';
const NO_VALUE = <span className="text-xs text-ink-subtle italic">--</span>;

function Header({ years }: Readonly<{ years: number[] }>) {
  return (
    <thead className="bg-surface-subtle font-bold">
      <tr>
        <th className="px-6 py-4 text-left text-xs text-ink-muted uppercase tracking-wider border-r border-border">
          Scenario Name
        </th>
        {years.map(y => (
          <th key={y} className="px-6 py-2 text-center text-[10px] text-ink-subtle uppercase">
            {y}
          </th>
        ))}
        <th className="px-6 py-4 text-right text-xs text-ink uppercase tracking-wider bg-surface-subtle border-l border-border">
          Total
        </th>
        <th className="px-6 py-4 text-right text-xs text-ink uppercase tracking-wider bg-surface-subtle">
          Variance
        </th>
      </tr>
    </thead>
  );
}

function NameCell({ name, isAnchor }: Readonly<{ name: string; isAnchor: boolean }>) {
  return (
    <td className="px-6 py-4 whitespace-nowrap border-r border-border">
      <div className="flex items-center">
        <div className={`w-2 h-2 rounded-full mr-2 ${isAnchor ? 'bg-info-solid' : 'bg-brand-green'}`} />
        <span className={`text-sm font-bold ${isAnchor ? 'text-info-ink' : 'text-ink'}`}>
          {name}
          {isAnchor && (
            <span className="ml-2 text-[8px] font-bold bg-info-surface text-info-ink px-1 py-0.5 rounded uppercase">
              Anchor
            </span>
          )}
        </span>
      </div>
    </td>
  );
}

function Variance({ value, text }: Readonly<{ value: number | null; text: (value: number) => string }>) {
  if (value === null) return NO_VALUE;
  return (
    <span className={`px-2 py-1 text-xs font-bold rounded ${value >= 0 ? 'bg-warning-surface text-warning-ink' : 'bg-success-surface text-success-ink'}`}>
      {text(value)}
    </span>
  );
}

const points = (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(2)} pp`;
const offsetText = (value: number) => value === 0 ? '$0' : `-${formatCurrency(value)}`;

interface CostMatrixProps {
  summary: ScenarioSummary[];
  years: number[];
  names: Record<string, string>;
  cohort: DCPlanCohort;
  netActive: boolean;
  policyReducesCost: boolean;
  grandfatherLoading: boolean;
  /** P10–P90 seed bands for gross cost; undefined when hidden or not run. */
  seedRangeFor?: (scenarioId: string) => SeedRangeRow | undefined;
}

function SeedBand({ band, className = '' }: Readonly<{ band: CostBandView | null | undefined; className?: string }>) {
  if (!band) return null;
  return (
    <div className={`text-[10px] text-ink-subtle ${className}`} title={`P10–P90 across ${band.n_seeds} seeds`}>
      {formatCostBand(band)}
    </div>
  );
}

function MissingYear({ year, cohort, small }: Readonly<{ year: SummaryYear; cohort: DCPlanCohort; small?: boolean }>) {
  // 134-new-hire-cohort (FR-012): a year with no cohort employees is
  // distinguishable from a computed $0.
  return (
    <td className={`${small ? SUB_CELL : VALUE_CELL} text-ink-subtle font-mono italic`}>
      {cohort !== 'all' ? <span title={year.notes.employer_cost}>—</span> : '-'}
    </td>
  );
}

function GrossRow({ scenario, props }: Readonly<{ scenario: ScenarioSummary; props: CostMatrixProps }>) {
  const { totals } = scenario;
  const unavailable = props.grandfatherLoading ? 'loading…' : 'unavailable';
  const seedRange = props.seedRangeFor?.(scenario.scenario_id);
  const delta = totals.employer_cost_vs_anchor;
  return (
    <tr className={`hover:bg-surface-subtle transition-colors ${scenario.is_anchor ? 'bg-info-surface/30' : ''}`}>
      <NameCell name={props.names[scenario.scenario_id] ?? scenario.scenario_id} isAnchor={scenario.is_anchor} />
      {scenario.years.map(year => {
        if (!year.has_data) return <MissingYear key={year.year} year={year} cohort={props.cohort} />;
        if (year.employer_cost === null) {
          return (
            <td key={year.year} className={`${VALUE_CELL} text-warning-ink font-mono italic`}>
              <span title={year.notes.employer_cost}>{unavailable}</span>
            </td>
          );
        }
        return (
          <td key={year.year} className={`${VALUE_CELL} text-ink-muted font-mono`}>
            {formatCurrency(year.employer_cost)}
            <SeedBand band={seedRange?.years.get(year.year)} />
          </td>
        );
      })}
      <td className={`${VALUE_CELL} text-ink font-bold font-mono ${TOTAL_CELL}`}>
        {totals.employer_cost === null ? unavailable : formatCurrency(totals.employer_cost)}
        {totals.employer_cost !== null && <SeedBand band={seedRange?.total} className="font-normal" />}
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-right">
        <Variance value={delta} text={formatSigned} />
        {!scenario.is_anchor && delta !== null && seedRange?.difference && (
          <div className="mt-1.5 text-[10px] text-ink-subtle font-mono" title={describeDifference(delta, seedRange.difference)}>
            {formatDifference(seedRange.difference)}
          </div>
        )}
      </td>
    </tr>
  );
}

function RateRow({ scenario, cohort }: Readonly<{ scenario: ScenarioSummary; cohort: DCPlanCohort }>) {
  const { totals } = scenario;
  return (
    <tr className="bg-surface-subtle/20">
      <td title="Employer match + core (or selected net/cohort cost) divided by IRS-capped prorated compensation for all employees, including ineligible and terminated employees." className={`${SUB_LABEL} font-medium text-ink-muted`}>
        Employer cost / capped pay (all employees)
      </td>
      {scenario.years.map(year => year.has_data ? (
        <td key={year.year} className={`${SUB_CELL} text-ink-muted font-mono`}>
          {year.cost_pct_of_capped_pay === null ? 'unavailable' : formatPercent(year.cost_pct_of_capped_pay, 2)}
        </td>
      ) : <MissingYear key={year.year} year={year} cohort={cohort} small />)}
      <td className={`${SUB_CELL} font-bold text-ink font-mono ${TOTAL_CELL}`}>
        {totals.cost_pct_of_capped_pay === null ? 'unavailable' : formatPercent(totals.cost_pct_of_capped_pay, 2)}
      </td>
      <td className="px-6 py-2 whitespace-nowrap text-right">
        <Variance value={totals.cost_pct_vs_anchor_pp} text={points} />
      </td>
    </tr>
  );
}

function NotApplicable({ note }: Readonly<{ note?: string }>) {
  return <span className="italic text-ink-subtle" title={note}>n/a</span>;
}

function OffsetRows({ scenario, policyReducesCost }: Readonly<{ scenario: ScenarioSummary; policyReducesCost: boolean }>) {
  const { totals } = scenario;
  return (
    <>
      <tr className="bg-surface-subtle/20">
        <td className={`${SUB_LABEL} text-ink-muted`}>Forfeiture offset</td>
        {scenario.years.map(year => (
          <td key={year.year} className={`${SUB_CELL} font-mono ${year.forfeiture_offset === null ? '' : 'text-success-ink'}`}>
            {year.forfeiture_offset === null
              ? <NotApplicable note={year.notes.forfeiture_offset} />
              : offsetText(year.forfeiture_offset)}
          </td>
        ))}
        <td className={`${SUB_CELL} text-success-ink font-mono ${TOTAL_CELL}`}>
          {totals.forfeiture_offset === null
            ? <NotApplicable note={totals.notes.forfeiture_offset} />
            : offsetText(totals.forfeiture_offset)}
        </td>
        <td className={`${SUB_CELL} text-ink-subtle italic`}>--</td>
      </tr>
      {!policyReducesCost && (
        <tr className="bg-surface-subtle/20">
          <td className={`${SUB_LABEL} text-ink-muted`}>Reallocated to participants</td>
          {scenario.years.map(year => (
            <td key={year.year} className={`${SUB_CELL} text-ink-muted font-mono`}>
              {year.reallocated_to_participants === null
                ? <NotApplicable note={year.notes.reallocated_to_participants} />
                : formatCurrency(year.reallocated_to_participants)}
            </td>
          ))}
          <td className={`${SUB_CELL} text-ink-muted font-mono ${TOTAL_CELL}`}>
            {totals.reallocated_to_participants === null
              ? <NotApplicable note={totals.notes.reallocated_to_participants} />
              : formatCurrency(totals.reallocated_to_participants)}
          </td>
          <td className={`${SUB_CELL} text-ink-subtle italic`}>--</td>
        </tr>
      )}
    </>
  );
}

function NetRow({ scenario }: Readonly<{ scenario: ScenarioSummary }>) {
  const { totals } = scenario;
  return (
    <tr className="bg-surface-subtle/40">
      <td className={`${SUB_LABEL} font-bold text-ink`}>Net employer cost</td>
      {scenario.years.map(year => year.net_employer_cost === null ? (
        <td key={year.year} className={`${SUB_CELL} text-ink-subtle font-mono italic`}>
          <span title={year.notes.net_employer_cost}>gross only</span>
        </td>
      ) : (
        <td key={year.year} className={`${SUB_CELL} font-bold text-ink font-mono`}>
          {formatCurrency(year.net_employer_cost)}
        </td>
      ))}
      <td className={`${SUB_CELL} font-bold text-ink font-mono ${TOTAL_CELL}`}>
        {totals.net_employer_cost === null ? 'unavailable' : formatCurrency(totals.net_employer_cost)}
      </td>
      <td className="px-6 py-2 whitespace-nowrap text-right">
        <Variance value={totals.net_employer_cost_vs_anchor} text={formatSigned} />
      </td>
    </tr>
  );
}

export function CostMatrixTable(props: Readonly<CostMatrixProps>) {
  return (
    <table className="min-w-full divide-y divide-border">
      <Header years={props.years} />
      <tbody className="divide-y divide-border bg-surface-raised">
        {props.summary.map(scenario => (
          <React.Fragment key={scenario.scenario_id}>
            <GrossRow scenario={scenario} props={props} />
            <RateRow scenario={scenario} cohort={props.cohort} />
            {/* #444: offset and net are *additional* rows, shown only in the Net view. */}
            {props.netActive && <OffsetRows scenario={scenario} policyReducesCost={props.policyReducesCost} />}
            {props.netActive && <NetRow scenario={scenario} />}
          </React.Fragment>
        ))}
      </tbody>
    </table>
  );
}

export function CompensationMatrixTable({ summary, years, names }: Readonly<{
  summary: ScenarioSummary[];
  years: number[];
  names: Record<string, string>;
}>) {
  return (
    <table className="min-w-full divide-y divide-border">
      <Header years={years} />
      <tbody className="divide-y divide-border bg-surface-raised">
        {summary.map(scenario => (
          <tr key={scenario.scenario_id} className={`hover:bg-surface-subtle transition-colors ${scenario.is_anchor ? 'bg-info-surface/30' : ''}`}>
            <NameCell name={names[scenario.scenario_id] ?? scenario.scenario_id} isAnchor={scenario.is_anchor} />
            {scenario.years.map(year => (
              <td key={year.year} className={`${VALUE_CELL} text-ink-muted font-mono`}>
                {year.total_compensation === null ? '-' : formatCurrency(year.total_compensation)}
              </td>
            ))}
            <td className={`${VALUE_CELL} text-ink font-bold font-mono ${TOTAL_CELL}`}>
              {scenario.totals.total_compensation === null ? 'unavailable' : formatCurrency(scenario.totals.total_compensation)}
            </td>
            <td className="px-6 py-4 whitespace-nowrap text-right">
              <Variance value={scenario.totals.total_compensation_vs_anchor} text={formatSigned} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
