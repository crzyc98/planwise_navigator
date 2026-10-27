import { NumericInput } from './NumericInput';
import { useEffect, useState } from 'react';
import { AlertTriangle, BarChart3, Info, X } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { InputField } from './InputField';
import { MATCH_TEMPLATES, calculateMatchCap, DEFAULT_FORM_DATA, DEFAULT_VOLUNTARY_DEFERRAL_BASE_RATES,
  DEFERRAL_SPREAD_MIN, DEFERRAL_SPREAD_MAX } from './constants';
import { analyzeOptOutRate, OptOutRateAnalysisResult } from '../../services/api';
import { TenureGradedMatchEditor } from './TenureGradedMatchEditor';
import { VoluntaryDeferralRatesEditor } from './VoluntaryDeferralRatesEditor';
import { DCPlanPanel, EmployerEligibilityEditor, coreSummary, dcDisplayConfig, matchSummary, tierSummary } from './DCPlanPanels';
import { EnrollmentRateInput } from './EnrollmentRateInput';
import { BelowDefaultEditor } from './BelowDefaultEditor';
import { EasyEnrollEditor } from './EasyEnrollEditor';
import { DeferralRateChangesEditor } from './DeferralRateChangesEditor';
import { belowDefaultSummary, easyEnrollSummary, deferralRateChangesSummary } from './participantBehaviorConfig';

// A blank cutoff is removed from the export, so dbt applies its default (dbt_project.yml).
const ENGINE_DEFAULT_HIRE_CUTOFF = '2020-01-01';
const hireCutoffLabel = (cutoff: string) => cutoff || `${ENGINE_DEFAULT_HIRE_CUTOFF} (engine default)`;

/**
 * The lowest base core rate any employee could receive, as a percentage.
 *
 * Mirrors `min_schedule_rate` in permitted_disparity.py: with a varying
 * schedule, §401(l) binds on the *lowest* band, since an employee in that band
 * may not receive a disparity exceeding their own base rate.
 */
export function minCoreBaseRatePercent(formData: any): number | null {
  const tierMin = (tiers: Array<{ rate: number }>) =>
    tiers.length ? Math.min(...tiers.map((t) => Number(t.rate) || 0)) : null;

  switch (formData.dcCoreStatus) {
    case 'graded_by_service':
      return tierMin(formData.dcCoreGradedSchedule ?? []);
    case 'points_based':
      return tierMin(formData.dcCorePointsSchedule ?? []);
    case 'age_banded':
      return tierMin(formData.dcCoreAgeSchedule ?? []);
    default:
      return Number(formData.dcCoreContributionRate) || 0;
  }
}

/**
 * Warn when the disparity rate exceeds the base rate — the §401(l) constraint
 * that needs no wage-base lookup and is by far the most common violation.
 *
 * Deliberately partial. The permitted-disparity *factor* (5.7% / 5.4% / 4.3%,
 * by integration level relative to that year's taxable wage base) depends on
 * seed data the browser does not have, so the server stays authoritative and
 * this never claims a configuration is legal — only that one is not.
 */
export function validateCoreIntegration(formData: any): string[] {
  if (!formData.dcCoreIntegrationEnabled) return [];

  const disparity = Number(formData.dcCoreIntegrationDisparityRate) || 0;
  const baseRate = minCoreBaseRatePercent(formData);
  const warnings: string[] = [];

  if (baseRate !== null && disparity > baseRate) {
    const scope =
      formData.dcCoreStatus === 'flat'
        ? 'the base core rate'
        : 'the lowest band of the core schedule';
    warnings.push(
      `Disparity rate ${disparity}% exceeds ${scope} (${baseRate}%). Under §401(l) the ` +
        `disparity may not exceed the base rate, so this run will be rejected. Either ` +
        `raise the base rate to ${disparity}% or lower the disparity to ${baseRate}%.`
    );
  }

  if (disparity > 5.7) {
    warnings.push(
      `Disparity rate ${disparity}% exceeds the maximum permitted disparity factor of 5.7%.`
    );
  }

  return warnings;
}

export function validateMatchTiers(
  tiers: Array<{ min: number; max: number | null }>,
  label: string,
): string[] {
  const warnings: string[] = [];
  if (tiers.length === 0) return warnings;
  const sorted = [...tiers].sort((a, b) => a.min - b.min);
  if (sorted[0].min !== 0) {
    warnings.push(`First tier starts at ${sorted[0].min} — should start at 0 to cover all employees`);
  }
  for (let i = 0; i < sorted.length; i++) {
    const t = sorted[i];
    if (t.max !== null && t.max <= t.min) {
      warnings.push(`Tier ${i + 1}: max (${t.max}) must be greater than min (${t.min})`);
    }
  }
  for (let i = 0; i < sorted.length - 1; i++) {
    const currMax = sorted[i].max;
    const nextMin = sorted[i + 1].min;
    if (currMax === null) {
      warnings.push(`Tier ${i + 1} has no upper bound but is not the last tier — tiers after it will never apply`);
      continue;
    }
    if (currMax < nextMin) {
      warnings.push(`Gap: ${label} ${currMax}–${nextMin} is not covered between tier ${i + 1} and ${i + 2}`);
    } else if (currMax > nextMin) {
      warnings.push(`Overlap: ${label} ${nextMin}–${currMax} is covered by both tier ${i + 1} and ${i + 2}`);
    }
  }
  return warnings;
}

export function getDeferralSpreadClipping(
  baseRates: Record<string, number>,
  maxLift: number,
  maxVoluntaryDeferral: number,
): { maxBaseRate: number; spreadCeiling: number } | null {
  const rates = Object.values(baseRates).map(Number).filter(Number.isFinite);
  if (rates.length === 0 || maxLift <= 0 || maxVoluntaryDeferral <= 0) return null;

  const maxBaseRate = Math.max(...rates);
  const spreadCeiling = maxBaseRate + maxLift;
  return spreadCeiling > maxVoluntaryDeferral
    ? { maxBaseRate, spreadCeiling }
    : null;
}

export function DCPlanSection() {
  const { formData, savedFormData, setFormData, handleChange, inputProps, activeWorkspace, workspaceConfig, originalConfig, buildDraftConfig, resolvedEngineVariables } = useConfigContext();
  const displayConfig = dcDisplayConfig(workspaceConfig, originalConfig, buildDraftConfig, resolvedEngineVariables);
  const responseConfig = displayConfig.deferral_match_response as Record<string, unknown> | undefined;
  const voluntaryMode = formData.dcVoluntaryEnrollmentMode ?? (formData.dcVoluntaryEnrollmentRate === '' ? 'demographic' : 'specified');
  const optOutMode = formData.dcNewHireOptOutMode ?? (formData.dcNewHireOptOutRate === '' ? 'demographic' : 'specified');
  const rateSource = (mode: string, value: string) => mode === 'specified' ? `${value}% specified` : mode === 'demographic' ? 'demographic model' : 'inherited setting';
  const responseMaximizers = Number(responseConfig?.upward_maximize_rate ?? 0.6) * 100;
  const responsePartialGap = Number(responseConfig?.upward_partial_increase_factor ?? 0.5) * 100;
  const waitingMonths = Number(formData.dcEligibilityMonths);
  const waitingPeriodUnchanged = savedFormData != null && Number(savedFormData.dcEligibilityMonths) === waitingMonths;
  const waitingPeriodDays = Number(((waitingPeriodUnchanged ? waitingMonths : Math.trunc(waitingMonths)) * 30).toFixed(6));
  const waitingPeriodHelper = waitingPeriodUnchanged && !Number.isInteger(waitingMonths)
    ? `Existing waiting period: ${waitingPeriodDays} days; edits use whole modeled months of 30 days.`
    : `Each modeled month equals 30 days. Resolved waiting period: ${waitingPeriodDays} days.`;

  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<OptOutRateAnalysisResult | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [lookbackYears, setLookbackYears] = useState(3);

  const handleMatchCensus = async (years = lookbackYears) => {
    if (!formData.censusDataPath) {
      setAnalysisError('Upload a census file first to use Match Census');
      return;
    }
    if (!activeWorkspace?.id) return;
    setAnalyzing(true);
    setAnalysis(null);
    setAnalysisError(null);
    try {
      const result = await analyzeOptOutRate(activeWorkspace.id, {
        file_path: formData.censusDataPath,
        lookback_years: years,
      });
      setAnalysis(result);
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : 'Failed to analyze census for opt-out rate');
    } finally {
      setAnalyzing(false);
    }
  };

  // Base rates are held in formData as percent (6 === 6%); buildConfigPayload
  // is what divides by 100. Falls back to the shipped mid-career/moderate rate.
  const midCareerModerateRate =
    Number(formData.dcVoluntaryDeferralBaseRates?.mid_career_moderate
      ?? DEFAULT_VOLUNTARY_DEFERRAL_BASE_RATES.mid_career_moderate);
  const deferralSpreadClipping = getDeferralSpreadClipping(
    formData.dcVoluntaryDeferralBaseRates ?? DEFAULT_VOLUNTARY_DEFERRAL_BASE_RATES,
    Number(formData.dcDeferralSpreadMaxLift),
    Number(formData.dcMaxVoluntaryDeferral),
  );

  // Hard-bound the spread to 0-10pp. The `max` attribute only governs the
  // steppers -- a typed value lands in formData unchecked -- and the bound is
  // what lets the default cap (25%) clear every segment without a warning.
  const handleDeferralSpreadChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { value } = e.target;
    const clamped = value === ''
      ? ''
      : String(Math.min(Math.max(Number(value), DEFERRAL_SPREAD_MIN), DEFERRAL_SPREAD_MAX));
    setFormData(prev => ({ ...prev, dcDeferralSpreadMaxLift: clamped }));
  };

  const handleApply = () => {
    if (!analysis || analysis.suggested_rate === null) return;
    const pct = parseFloat((analysis.suggested_rate * 100).toFixed(1));
    setFormData(prev => ({ ...prev, dcOptOutRateTarget: pct }));
    setAnalysis(null);
  };

  // Re-fetch when lookback changes while preview is open
  useEffect(() => {
    if (analysis !== null) {
      const timer = setTimeout(() => handleMatchCensus(lookbackYears), 500);
      return () => clearTimeout(timer);
    }
  }, [lookbackYears]); // eslint-disable-line react-hooks/exhaustive-deps

  const autoEnrollmentControl = <div className="bg-success-surface p-4 rounded-lg border border-success-border flex items-start">
            <input
                 type="checkbox"
                 name="dcAutoEnroll"
                 id="dcAutoEnroll"
                 checked={formData.dcAutoEnroll}
                 onChange={handleChange}
                 className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-border-strong rounded mt-1"
            />
            <div className="ml-3">
               <label htmlFor="dcAutoEnroll" className="block text-sm font-medium text-success-ink">Enable Auto-Enrollment</label>
               <p className="text-xs text-success-ink mt-0.5">Automatically enroll eligible employees within the scope and timing rules below.</p>
            </div>
         </div>;

  const sweepGroups = [
    formData.dcReenrollmentSweepIncludeNonContributors && '0% contributors',
    formData.dcReenrollmentSweepIncludeBelowDefault && 'below the default',
    formData.dcReenrollmentSweepIncludeBelowAipCap && 'below the automatic-increase cap',
  ].filter(Boolean).join(', ') || 'no groups selected';

  const renderEligibilityFields = () => <>
      <DCPlanPanel id="dcplan-auto-enrollment-settings" title="Automatic enrollment" summary={formData.dcAutoEnroll ? `Enabled; periodic re-enrollment sweep ${formData.dcReenrollmentSweepEnabled ? `${formData.dcReenrollmentSweepMethod === 'into_aip' ? 'into automatic increases' : 'at the default rate'}, every ${formData.dcReenrollmentSweepIntervalYears} years, first ${formData.dcReenrollmentSweepFirstYear || Number(formData.startYear) + Number(formData.dcReenrollmentSweepIntervalYears)}; ${sweepGroups}; ${formData.dcReenrollmentSweepDeclineProbability}% of contributors decline` : 'off'}.` : 'Off; sweep, default deferral and opt-out assumptions retained.'} enabled={formData.dcAutoEnroll} control={autoEnrollmentControl}>
         <p className="sm:col-span-6 text-xs font-medium text-ink-muted">Plan rules</p>
         <InputField label="Default Deferral Rate" {...inputProps('dcDefaultDeferral')} type="number" step="0.5" suffix="%" disabled={!formData.dcAutoEnroll} helper={formData.dcAutoEnroll ? 'Initial contribution for auto-enrolled employees.' : 'Inactive while auto-enrollment is off. Saved value is retained.'} />
         <InputField label="Modeled opt-out delay" {...inputProps('dcAutoEnrollOptOutGracePeriod')} type="number" suffix="Days" disabled={!formData.dcAutoEnroll} helper={formData.dcAutoEnroll ? 'Hire-year opt-out date: eligibility + enrollment delay + this delay. Continuing-employee branch: June 15.' : 'Inactive while auto-enrollment is off. Saved value is retained.'} min={0} />
         <fieldset disabled={!formData.dcAutoEnroll} className="sm:col-span-6 disabled:opacity-60">
           <label htmlFor="dcReenrollmentSweepEnabled" className="flex items-center gap-2 text-sm font-medium text-ink">
             <input id="dcReenrollmentSweepEnabled" name="dcReenrollmentSweepEnabled" type="checkbox" checked={formData.dcReenrollmentSweepEnabled} onChange={handleChange} aria-describedby="reenrollment-sweep-help" className="h-4 w-4 text-fidelity-green rounded" />
             Periodic re-enrollment sweep
           </label>
           <p id="reenrollment-sweep-help" className="mt-1 text-xs text-ink-muted">Choose who to include and how their contributions start. Employees at 0% can opt out again; contributors can decline. Automatic increases continue in later years.</p>
           <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-6">
             <InputField label="Every" {...inputProps('dcReenrollmentSweepIntervalYears')} type="number" min={1} step="1" suffix="years" disabled={!formData.dcAutoEnroll || !formData.dcReenrollmentSweepEnabled} />
             <InputField label="First sweep year" {...inputProps('dcReenrollmentSweepFirstYear')} type="number" step="1" disabled={!formData.dcAutoEnroll || !formData.dcReenrollmentSweepEnabled} helper={`Optional; blank starts in ${Number(formData.startYear) + Number(formData.dcReenrollmentSweepIntervalYears)} (start year + interval).`} />
           </div>
           <fieldset disabled={!formData.dcAutoEnroll || !formData.dcReenrollmentSweepEnabled} className="mt-3 space-y-3">
             <label className="block text-sm text-ink" htmlFor="dcReenrollmentSweepMethod">Sweep method</label>
             <select id="dcReenrollmentSweepMethod" name="dcReenrollmentSweepMethod" value={formData.dcReenrollmentSweepMethod} onChange={handleChange} className="rounded border border-border bg-surface p-2 text-sm">
               <option value="enroll_at_default">Enroll at the default rate</option>
               <option value="into_aip">Sweep into automatic increases</option>
             </select>
             <p className="text-xs text-ink-muted">Sweeping into automatic increases keeps contributors at their current rate. Employees at 0% start with one annual increase.</p>
             <label htmlFor="dcReenrollmentSweepIncludeNonContributors" className="flex items-center gap-2 text-sm text-ink">
               <input id="dcReenrollmentSweepIncludeNonContributors" name="dcReenrollmentSweepIncludeNonContributors" type="checkbox" checked={formData.dcReenrollmentSweepIncludeNonContributors} onChange={handleChange} />
               Not contributing (0%)
             </label>
             <label htmlFor="dcReenrollmentSweepIncludeBelowDefault" className="flex items-center gap-2 text-sm text-ink">
               <input id="dcReenrollmentSweepIncludeBelowDefault" name="dcReenrollmentSweepIncludeBelowDefault" type="checkbox" checked={formData.dcReenrollmentSweepIncludeBelowDefault} onChange={handleChange} />
               Contributing below the default rate
             </label>
             <label htmlFor="dcReenrollmentSweepIncludeBelowAipCap" className="flex items-center gap-2 text-sm text-ink">
               <input id="dcReenrollmentSweepIncludeBelowAipCap" name="dcReenrollmentSweepIncludeBelowAipCap" type="checkbox" checked={formData.dcReenrollmentSweepIncludeBelowAipCap} onChange={handleChange} />
               Contributing below the automatic-increase cap
             </label>
             <InputField label="Share of contributors who decline" {...inputProps('dcReenrollmentSweepDeclineProbability')} type="number" min={0} max={100} step="1" suffix="%" disabled={!formData.dcAutoEnroll || !formData.dcReenrollmentSweepEnabled} />
           </fieldset>
           {formData.dcAutoEnroll && formData.dcReenrollmentSweepEnabled && (formData.dcAutoEnrollScope === 'new_hires_only' || Boolean(formData.dcAutoEnrollHireDateCutoff)) && <p role="note" className="mt-3 text-sm text-warning-ink">This sweep includes all legacy hires, not only employees hired after the auto-enrollment cutoff.</p>}
           {(!formData.dcAutoEnroll || !formData.dcReenrollmentSweepEnabled) && <p className="mt-2 text-xs text-ink-muted">Sweep settings inactive; saved values are retained.</p>}
         </fieldset>
         {optOutFields}
      </DCPlanPanel>

      <DCPlanPanel id="dcplan-shared-enrollment-settings" title="Shared enrollment rules" summary="Eligibility, timing, scope, and voluntary enrollment remain active when automatic enrollment is off.">
             <div className="sm:col-span-6">
               <p className="mt-1 text-sm text-ink-muted">These rules also apply to voluntary enrollment. Turning automatic enrollment off does not turn them off.</p>
               <p className="mt-3 text-xs font-medium text-ink-muted">Plan rules</p>
             </div>
             <InputField label="Eligibility waiting period" {...inputProps('dcEligibilityMonths')} type="number" suffix="Months" helper={`Applies to plan eligibility for voluntary and automatic enrollment. ${waitingPeriodHelper}`} />
             <InputField label="New-hire enrollment delay after eligibility" {...inputProps('dcAutoEnrollWindowDays')} type="number" suffix="Days" helper="Hire-year enrollment branch: eligibility date + this delay. Continuing-employee branch: January 15. This timing also applies to voluntary enrollment when auto-enrollment is off." min={30} />
             <div className="sm:col-span-3">
               <label htmlFor="dcplan-enrollment-scope" className="block text-sm font-medium text-ink-muted">Enrollment Scope</label>
               <select
                 id="dcplan-enrollment-scope"
                 name="dcAutoEnrollScope"
                 value={formData.dcAutoEnrollScope}
                 onChange={handleChange}
                 className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-border-strong focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
               >
                 <option value="new_hires_only">New Hires Only</option>
                 <option value="all_eligible">All Eligible Employees</option>
               </select>
               <p className="mt-1 text-xs text-ink-muted">Scope gates the modeled enrollment branch, including voluntary enrollment when auto-enrollment is off. Already enrolled employees are excluded.</p>
             </div>
             <div className="sm:col-span-3">
               <label htmlFor="dcplan-enroll-hire-cutoff" className="block text-sm font-medium text-ink-muted">Hire Date Cutoff</label>
               <input
                 id="dcplan-enroll-hire-cutoff"
                 type="date"
                 name="dcAutoEnrollHireDateCutoff"
                 value={formData.dcAutoEnrollHireDateCutoff}
                 onChange={handleChange}
                 className="mt-1 block w-full pl-3 pr-3 py-2 text-base border-border-strong focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
               />
               <p className="mt-1 text-xs text-ink-muted">Inclusive hire cutoff for the scope rules below. Leave blank to use the engine default ({ENGINE_DEFAULT_HIRE_CUTOFF}). Changing enrollment settings does not reset this date.</p>
             </div>
             <div className="sm:col-span-6 rounded-lg border border-border bg-surface-subtle p-3 text-xs text-ink-muted">
               <p><strong>First year ({formData.startYear}):</strong> Plan-eligible employees hired on or after {hireCutoffLabel(formData.dcAutoEnrollHireDateCutoff)}.</p>
               <p className="mt-1"><strong>Later years:</strong> {formData.dcAutoEnrollScope === 'new_hires_only'
                 ? 'Only current-year hires who meet plan eligibility; the hire cutoff is not reapplied.'
                 : `All plan-eligible employees hired on or after ${hireCutoffLabel(formData.dcAutoEnrollHireDateCutoff)}; the cutoff still applies.`}</p>
               {!formData.dcAutoEnroll && <p className="mt-1">Auto-enrollment is off. Default deferral and opt-out settings are inactive; draft values are retained for re-enabling. Voluntary enrollment and plan eligibility remain available.</p>}
             </div>
             {voluntaryEnrollmentFields}

      </DCPlanPanel>
  </>;

  const optOutFields = <>
             {/* Opt-Out Assumptions Section */}
             <fieldset disabled={!formData.dcAutoEnroll} className="sm:col-span-6 mt-4 disabled:opacity-60">
               <div className="flex items-center justify-between mb-3">
                 <h5 className="text-sm font-semibold text-ink">Employee behavior assumptions — opt-outs</h5>
                 <div className="flex items-center gap-2">
                   <button
                     type="button"
                     onClick={() => handleMatchCensus()}
                     disabled={analyzing || !formData.censusDataPath}
                     title={!formData.censusDataPath ? 'Upload a census file first' : 'Analyze census to suggest opt-out rate'}
                     className="flex items-center gap-1 px-2 py-1 text-xs bg-fidelity-green text-ink-inverse rounded hover:bg-success-solid-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                   >
                     <BarChart3 size={12} />
                     {analyzing ? 'Analyzing…' : 'Match Census'}
                   </button>
                   <button
                     type="button"
                     onClick={() => setFormData(prev => ({
                       ...prev,
                       dcOptOutRateTarget: DEFAULT_FORM_DATA.dcOptOutRateTarget,
                     }))}
                     className="text-xs text-fidelity-green hover:text-success-ink font-medium"
                   >
                     Reset to Default
                   </button>
                 </div>
               </div>
               <p className="text-xs text-ink-muted mb-3">
                 Target opt-out rate for <strong>continuing employees</strong>. Demographic
                 sensitivity is applied automatically behind the scenes.
                 {' '}New-hire opt-outs follow the selected rate source below; this target supplies the demographic model when that decision uses demographic rates.
               </p>

               {/* Match Census error */}
               {analysisError && (
                 <div className="mb-3 flex items-start gap-2 p-2 rounded bg-danger-surface border border-danger-border text-xs text-danger-ink">
                   <X size={12} className="mt-0.5 shrink-0" />
                   <span>{analysisError}</span>
                   <button type="button" onClick={() => setAnalysisError(null)} className="ml-auto text-danger-ink hover:text-danger-ink"><X size={12} /></button>
                 </div>
               )}

               {/* Match Census preview panel */}
               {analysis && (
                 <div className="mb-4 p-3 rounded-lg border border-success-border bg-success-surface text-xs">
                   <div className="flex items-center justify-between mb-2">
                     <span className="font-semibold text-success-ink">Census Match Preview</span>
                     <button type="button" onClick={() => setAnalysis(null)} className="text-success-ink hover:text-success-ink"><X size={12} /></button>
                   </div>

                   {/* Lookback input (US2) */}
                   <div className="flex items-center gap-2 mb-3">
                     <label className="text-success-ink font-medium whitespace-nowrap">Lookback (years):</label>
                     <NumericInput integer
                       type="number"
                       min={1}
                       max={50}
                       step={1}
                       value={lookbackYears}
                       onChange={e => setLookbackYears(Math.max(1, parseInt(e.target.value) || 1))}
                       className="w-16 px-2 py-0.5 border border-success-border rounded text-xs focus:outline-none focus:ring-1 focus:ring-fidelity-green"
                     />
                   </div>

                   {/* Low-confidence warning (T025) */}
                   {analysis.eligible_count > 0 && analysis.eligible_count < 20 && (
                     <div className="flex items-center gap-1 mb-2 text-warning-ink bg-warning-surface border border-warning-border rounded px-2 py-1">
                       <AlertTriangle size={11} />
                       <span>Small sample — only {analysis.eligible_count} employee(s) in window. Consider a longer lookback.</span>
                     </div>
                   )}

                   {/* Excluded null tenure note (T026) */}
                   {analysis.excluded_null_tenure > 0 && (
                     <p className="text-ink-muted mb-2">{analysis.excluded_null_tenure} employee(s) excluded (missing hire date)</p>
                   )}

                   {analysis.suggested_rate !== null ? (
                     <>
                       <div className="grid grid-cols-2 gap-x-4 gap-y-1 mb-3 text-success-ink">
                         <span>Employees in window:</span><span className="font-medium">{analysis.eligible_count}</span>
                         <span>Non-participants:</span><span className="font-medium">{analysis.non_participant_count}</span>
                         <span>Suggested rate:</span><span className="font-semibold text-base text-success-ink">{(analysis.suggested_rate * 100).toFixed(1)}%</span>
                       </div>
                       <div className="flex gap-2">
                         <button
                           type="button"
                           onClick={handleApply}
                           className="px-3 py-1 text-xs bg-fidelity-green text-ink-inverse rounded hover:bg-success-solid-hover transition-colors font-medium"
                         >
                           Apply {(analysis.suggested_rate * 100).toFixed(1)}%
                         </button>
                         <button
                           type="button"
                           onClick={() => setAnalysis(null)}
                           className="px-3 py-1 text-xs border border-success-border text-success-ink rounded hover:bg-success-surface transition-colors"
                         >
                           Dismiss
                         </button>
                       </div>
                     </>
                   ) : (
                     <p className="text-success-ink">{analysis.message ?? 'No eligible employees found in the lookback window.'}</p>
                   )}
                 </div>
               )}

               <div className="grid grid-cols-1 gap-y-4 gap-x-4 sm:grid-cols-6 mb-4">
                 <InputField label="Target Opt-Out Rate" {...inputProps('dcOptOutRateTarget')} type="number" step="0.5" suffix="%" helper="Demographic opt-out target for continuing employees and any new hires using the demographic model." min={0} max={100} />
               </div>

               {/* Derived rates preview */}
               <details open={formData.dcAutoEnroll} className="text-xs text-ink-muted">
                 <summary className="cursor-pointer hover:text-ink-muted font-medium">View derived demographic rates</summary>
                 <div className="mt-2 grid grid-cols-2 gap-x-8 gap-y-1 pl-2">
                   <p className="font-medium text-ink-muted col-span-2 mt-1">By Age</p>
                   <span>Young (18-30): {(Number(formData.dcOptOutRateTarget) * 1.8).toFixed(1)}%</span>
                   <span>Mid-Career (31-45): {(Number(formData.dcOptOutRateTarget) * 1.1).toFixed(1)}%</span>
                   <span>Mature (46-55): {(Number(formData.dcOptOutRateTarget) * 0.7).toFixed(1)}%</span>
                   <span>Senior (55+): {(Number(formData.dcOptOutRateTarget) * 0.4).toFixed(1)}%</span>
                   <p className="font-medium text-ink-muted col-span-2 mt-1">By Income</p>
                   <span>Low Income: {(Number(formData.dcOptOutRateTarget) * 1.3).toFixed(1)}%</span>
                   <span>Moderate: {(Number(formData.dcOptOutRateTarget) * 1.0).toFixed(1)}%</span>
                   <span>High: {(Number(formData.dcOptOutRateTarget) * 0.8).toFixed(1)}%</span>
                   <span>Executive: {(Number(formData.dcOptOutRateTarget) * 0.5).toFixed(1)}%</span>
                 </div>
               </details>
             </fieldset>
             <EnrollmentRateInput kind="optOut" />
  </>;

  const voluntaryEnrollmentFields = <>
         {/* New Hire Enrollment Rates (issue #652) */}
         <div className="sm:col-span-6 mt-4">
           <h5 className="text-sm font-semibold text-ink mb-1">Voluntary enrollment assumptions</h5>
           <p className="text-xs font-medium text-ink-muted mb-2">Employee behavior assumptions</p>
           <p className="text-xs text-ink-muted mb-3">
             Exact percentages applied to eligible new hires in their hire year. {formData.dcAutoEnroll
               ? 'Remaining new hires in the enrollment scope may auto-enroll, subject to opt-outs.'
               : 'Auto-enrollment is off; remaining new hires are not automatically enrolled.'}{' '}
             Choose the voluntary enrollment rate source. Enrollment also depends on the shared scope and timing rules above.
           </p>
           <div className="grid grid-cols-1 gap-y-4 gap-x-4 sm:grid-cols-6">
             <EnrollmentRateInput kind="voluntary" />
           </div>
           {formData.dcAutoEnroll && voluntaryMode === 'specified' && optOutMode === 'specified' && formData.dcVoluntaryEnrollmentRate !== '' && formData.dcNewHireOptOutRate !== ''
             && Number(formData.dcVoluntaryEnrollmentRate) >= 0
             && Number(formData.dcVoluntaryEnrollmentRate) <= 100
             && Number(formData.dcNewHireOptOutRate) >= 0
             && Number(formData.dcNewHireOptOutRate) <= 100 && (
             <p className="mt-2 text-xs text-ink-muted">
               Resulting split of eligible new hires within the enrollment scope:{' '}
               <strong>{Number(formData.dcVoluntaryEnrollmentRate).toFixed(0)}%</strong> voluntary,{' '}
               <strong>{((100 - Number(formData.dcVoluntaryEnrollmentRate)) * (100 - Number(formData.dcNewHireOptOutRate)) / 100).toFixed(1)}%</strong> auto-enrolled,{' '}
               <strong>{((100 - Number(formData.dcVoluntaryEnrollmentRate)) * Number(formData.dcNewHireOptOutRate) / 100).toFixed(1)}%</strong> opted out.
             </p>
           )}
         </div>

  </>;

  const startingRateFields = <>
         <VoluntaryDeferralRatesEditor
           rates={formData.dcVoluntaryDeferralBaseRates}
           onChange={(rates) => setFormData(prev => ({ ...prev, dcVoluntaryDeferralBaseRates: rates }))}
           workspaceId={activeWorkspace?.id}
           censusDataPath={formData.censusDataPath}
         />

         {/* Deferral Spread (issue #652) */}
         <div className="sm:col-span-6 mt-4">
           <h4 className="text-sm font-semibold text-ink mb-1">Deferral Rate Spread</h4>
           <p className="text-xs text-ink-muted mb-3">
             Without this, every enrollee in a segment above receives the identical rate,
             so the distribution shows one spike per segment. Turn it on and the segment
             rate becomes a <strong>floor</strong> that employees move up from — nobody
             goes below it. Applies only to employees who enroll during the simulation,
             not to auto-enrolled employees (who get the plan default) or census employees.
           </p>
           <div className="grid grid-cols-1 gap-y-4 gap-x-4 sm:grid-cols-6">
             <InputField
               label="Max Upward Spread"
               name="dcDeferralSpreadMaxLift"
               value={formData.dcDeferralSpreadMaxLift}
               onChange={handleDeferralSpreadChange}
               type="number"
               step="1"
               suffix="pp"
               helper={`Percentage points above the segment rate (${DEFERRAL_SPREAD_MIN}-${DEFERRAL_SPREAD_MAX}pp). 0 = off (every enrollee gets exactly the table value).`}
               min={DEFERRAL_SPREAD_MIN}
               max={DEFERRAL_SPREAD_MAX}
             />
           </div>
           {Number(formData.dcDeferralSpreadMaxLift) > 0 && (
             <p className="mt-2 text-xs text-ink-muted">
               A segment at {midCareerModerateRate}% would spread across{' '}
               {Array.from({ length: Math.min(Number(formData.dcDeferralSpreadMaxLift), 4) + 1 }, (_, i) => {
                 const weights = [40, 30, 15, 10, 5];
                 return `${(midCareerModerateRate + i).toFixed(0)}% (${weights[i]}%)`;
               }).join(', ')}
               . Raises the average deferral rate, and therefore projected employer match cost.
             </p>
           )}
           {deferralSpreadClipping && (
             <div
               className="mt-2 flex items-start gap-1.5 rounded border border-warning-border bg-warning-surface p-2 text-xs text-warning-ink"
               role="alert"
             >
               <AlertTriangle className="mt-0.5 h-3 w-3 flex-shrink-0" />
               <p>
                 The highest segment starts at {deferralSpreadClipping.maxBaseRate}% and can
                 spread to {deferralSpreadClipping.spreadCeiling}%, above the{' '}
                 {formData.dcMaxVoluntaryDeferral}% Max Voluntary Deferral. Rates above that
                 cap will be clipped; raise the cap or lower the spread to preserve them.
               </p>
             </div>
           )}
         </div>

         <div className="sm:col-span-6 h-px bg-surface-disabled my-2" />
         <BelowDefaultEditor form={formData} onChange={changes => setFormData(prev => ({ ...prev, ...changes }))} />

  </>;

  const responseFields = <>
         {/* Match Magnet dial (Feature 102) */}
         <div className="sm:col-span-6 mt-4">
           <div className="flex items-center justify-between mb-1">
             <h4 className="text-sm font-semibold text-ink">New enrollees seeking the full match</h4>
             <label htmlFor="dcplan-match-magnet-enabled" className="flex items-center">
               <input
                 id="dcplan-match-magnet-enabled"
                 type="checkbox"
                 name="dcMatchMagnetEnabled"
                 checked={formData.dcMatchMagnetEnabled}
                 onChange={handleChange}
                 className="h-4 w-4 text-fidelity-green rounded"
               />
               <span className="ml-2 text-sm text-ink-muted">Enabled</span>
             </label>
           </div>
           <details id="dcplan-match-magnet-settings" open={formData.dcMatchMagnetEnabled}>
           <summary className="cursor-pointer text-sm font-medium mb-3">New-enrollee response assumptions</summary>
           <p className="text-xs text-ink-muted mb-3">Models new voluntary enrollees who increase their contributions to the rate needed for the full employer match. The selected share applies only to those starting below that rate.</p>
           <div className="grid grid-cols-1 gap-y-4 gap-x-4 sm:grid-cols-6">
             <InputField label="Share seeking the full match" {...inputProps('dcMatchMagnetProbability')} type="number" step="1" suffix="%" disabled={!formData.dcMatchMagnetEnabled} helper={formData.dcMatchMagnetEnabled ? 'Share of below-ceiling voluntary enrollees who increase to the full-match rate (0–100%).' : 'Inactive while new-enrollee match seeking is off. Saved value is retained.'} min={0} max={100} />
             <div className="sm:col-span-6">
               <label htmlFor="dcplan-match-magnet-downward" className="flex items-start gap-2 text-sm text-ink-muted">
                 <input id="dcplan-match-magnet-downward" type="checkbox" name="dcMatchMagnetDownwardEnabled" checked={formData.dcMatchMagnetDownwardEnabled} onChange={handleChange}
                   disabled={!formData.dcMatchMagnetEnabled || !formData.dcAutoEnroll} aria-describedby="dcplan-match-magnet-downward-help" className="mt-1 h-4 w-4 text-fidelity-green rounded disabled:opacity-50" />
                 Also pull rates down to the full-match rate when it is below the auto-enrollment default
               </label>
               <p id="dcplan-match-magnet-downward-help" className="mt-1 text-xs text-ink-muted">Applies only to employees whose starting rate is between the full-match rate and the auto-enrollment default. Rates above the default are never lowered. Uses the same {formData.dcMatchMagnetProbability}% probability as the upward pull. {!formData.dcAutoEnroll ? 'Inactive while auto-enrollment is off. Saved value is retained.' : !formData.dcMatchMagnetEnabled ? 'Inactive while new-enrollee match seeking is off. Saved value is retained.' : ''}</p>
             </div>
           </div>
           </details>
           <div className="grid grid-cols-1 gap-4 sm:grid-cols-6 mt-4">
             <InputField label="Max Voluntary Deferral" {...inputProps('dcMaxVoluntaryDeferral')} type="number" step="1" suffix="%" helper="Shared upper bound on voluntary deferral selection and spread, including when match seeking is off." min={1} max={100} />
           </div>
         </div>

         <div className="sm:col-span-6 h-px bg-surface-disabled my-2"></div>
         <div className="sm:col-span-6 mt-2">
           <div className="flex items-center justify-between mb-1">
             <h4 className="text-sm font-semibold text-ink">First-year response by existing participants</h4>
             <label htmlFor="dcplan-match-response-enabled" className="flex items-center">
               <input
                 id="dcplan-match-response-enabled"
                 type="checkbox"
                 name="dcMatchResponseEnabled"
                 checked={formData.dcMatchResponseEnabled}
                 onChange={handleChange}
                 className="h-4 w-4 text-fidelity-green rounded"
               />
               <span className="ml-2 text-sm text-ink-muted">Enabled</span>
             </label>
           </div>
           <details id="dcplan-match-response-settings" open={formData.dcMatchResponseEnabled}>
           <summary className="cursor-pointer text-sm font-medium mb-3">Existing-participant response assumptions</summary>
           <p className="text-xs text-ink-muted mb-3">In the first projection year, models active enrolled employees changing contributions in response to the employer-match ceiling. Current-year new hires are excluded. Some upward responders seek the full match; others close part of the gap according to the inherited response assumptions.</p>
           <p className="text-xs text-ink-muted mb-3">Upward responders seeking the full match: {responseMaximizers}%. Partial responders close {responsePartialGap}% of the gap. IRS limits still apply; the auto-escalation cap does not limit match response.</p>
           <div className="grid grid-cols-1 gap-y-4 gap-x-4 sm:grid-cols-6">
             <InputField
               label="Increase Deferral Response"
               {...inputProps('dcMatchResponseUpwardParticipation')}
               type="number"
               step="1"
               suffix="%"
               disabled={!formData.dcMatchResponseEnabled}
               helper={formData.dcMatchResponseEnabled ? 'Share of eligible employees below the match ceiling who increase deferrals (0–100%).' : 'Inactive while first-year participant response is off. Saved value is retained.'}
               min={0}
               max={100}
             />
             <div className="sm:col-span-3">
               <label htmlFor="dcplan-match-response-downward-enabled" className="flex items-center pt-6">
                 <input
                   id="dcplan-match-response-downward-enabled"
                   type="checkbox"
                   name="dcMatchResponseDownwardEnabled"
                   checked={formData.dcMatchResponseDownwardEnabled}
                   disabled={!formData.dcMatchResponseEnabled}
                   onChange={handleChange}
                   className="h-4 w-4 text-fidelity-green rounded"
                 />
                 <span className="ml-2 text-sm text-ink-muted">Allow Deferral Decreases</span>
               </label>
               <details id="dcplan-match-decreases-settings" open={formData.dcMatchResponseEnabled && formData.dcMatchResponseDownwardEnabled}>
               <summary className="cursor-pointer text-sm font-medium mt-3">Deferral decrease assumptions</summary>
               <InputField
                 label="Decrease Deferral Response"
                 {...inputProps('dcMatchResponseDownwardParticipation')}
                 type="number"
                 step="1"
                 suffix="%"
                 disabled={!formData.dcMatchResponseEnabled || !formData.dcMatchResponseDownwardEnabled}
                 helper={formData.dcMatchResponseEnabled && formData.dcMatchResponseDownwardEnabled ? 'Share of eligible employees above the match ceiling who decrease deferrals.' : 'Inactive while first-year response or deferral decreases are off. Saved value is retained.'}
                 min={0}
                 max={100}
               />
               </details>
             </div>
           </div>
           </details>
         </div>

  </>;

  const matchControl = <div className="flex items-center justify-between mb-2">
           <h4 className="text-sm font-semibold text-ink">Employer Match Formula</h4>
           <label htmlFor="dcplan-match-enabled" className="flex items-center">
             <input
               id="dcplan-match-enabled"
               type="checkbox"
               name="dcMatchEnabled"
               checked={formData.dcMatchEnabled}
               onChange={handleChange}
               className="h-4 w-4 text-fidelity-green rounded"
             />
             <span className="ml-2 text-sm text-ink-muted">Enabled</span>
           </label>
         </div>;
  const matchFields = <>
         <p className="sm:col-span-6 text-xs text-ink-muted -mt-4 mb-2">Configure employer matching contributions on employee deferrals</p>

         {formData.dcMatchEnabled && (<>
         {/* E046: Match Mode Selector */}
         <div className="sm:col-span-3">
           <label htmlFor="dcplan-match-mode" className="block text-sm font-medium text-ink-muted">Match Calculation Mode</label>
           <select
             id="dcplan-match-mode"
             value={formData.dcMatchMode}
             onChange={(e) => setFormData(prev => ({ ...prev, dcMatchMode: e.target.value }))}
             className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-border-strong focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
           >
             <option value="deferral_based">Deferral-Based (match varies by deferral %)</option>
             <option value="graded_by_service">Graded by Service (existing service tiers)</option>
             <option value="tenure_graded">Tenure-Graded (multi-tier schedule by years of service)</option>
             <option value="points_based">Points-Based (match varies by age + tenure points)</option>
             {!['deferral_based', 'graded_by_service', 'tenure_graded', 'points_based'].includes(formData.dcMatchMode) && <option value={formData.dcMatchMode}>Saved custom mode: {formData.dcMatchMode}</option>}
           </select>
           <p className="mt-1 text-xs text-ink-muted">
             {formData.dcMatchMode === 'tenure_graded' && 'Each tenure band has its own multi-tier deferral schedule (e.g. 100% on first 2%, 50% on next 6%)'}
             {formData.dcMatchMode === 'points_based' && 'Points = FLOOR(age) + FLOOR(tenure). Higher points = higher match'}
             {formData.dcMatchMode === 'deferral_based' && 'Traditional: match rate varies by employee deferral percentage'}
             {formData.dcMatchMode === 'graded_by_service' && 'Uses existing graded-by-service schedule'}
           </p>
         </div>

         {/* Feature 099: Tenure-Graded Match Editor */}
         {formData.dcMatchMode === 'tenure_graded' && (
           <TenureGradedMatchEditor
             bands={formData.dcTenureGradedBands}
             onChange={(newBands) => setFormData(prev => ({ ...prev, dcTenureGradedBands: newBands }))}
           />
         )}

         {/* E046: Points-Based Tier Editor */}
         {formData.dcMatchMode === 'points_based' && (
           <div className="sm:col-span-6 bg-surface-subtle p-4 rounded-lg border border-border">
             <span className="block text-sm font-medium text-ink-muted mb-1">Points Match Tiers</span>
             <p className="text-xs text-ink-muted mb-3">Points = FLOOR(age) + FLOOR(years of service). Uses [min, max) intervals.</p>
             <div className="space-y-2">
               {formData.dcPointsMatchTiers.map((tier, idx) => (
                 <div key={idx} className="flex flex-wrap items-center gap-2 bg-surface-raised p-2 rounded border border-border">
                   <span className="text-xs text-ink-muted w-4">{idx + 1}.</span>
                   <NumericInput integer type="number" min={0} value={tier.minPoints}
                     onChange={(e) => {
                       const newTiers = [...formData.dcPointsMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], minPoints: parseInt(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                     }}
                     className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-ink-muted">to</span>
                   <NumericInput integer allowEmpty type="number" min={0} value={tier.maxPoints ?? ''}
                     placeholder="&#8734;"
                     onChange={(e) => {
                       const newTiers = [...formData.dcPointsMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], maxPoints: e.target.value === '' ? null : parseInt(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                     }}
                     className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-ink-muted">pts | 0% to</span>
                   <NumericInput type="number" step="1" min={0} max={100} value={tier.maxDeferralPct}
                     onChange={(e) => {
                       const newTiers = [...formData.dcPointsMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], maxDeferralPct: parseFloat(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                     }}
                     className="w-14 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-ink-muted">% deferrals &#8594;</span>
                   <NumericInput type="number" step="5" min={0} max={200} value={tier.matchRate}
                     onChange={(e) => {
                       const newTiers = [...formData.dcPointsMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], matchRate: parseFloat(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                     }}
                     className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-ink-muted">% match</span>
                   {formData.dcPointsMatchTiers.length > 1 && (
                     <button type="button"
                       onClick={() => {
                         const newTiers = formData.dcPointsMatchTiers.filter((_, i) => i !== idx);
                         setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                       }}
                       className="ml-auto text-danger-ink hover:text-danger-ink p-1"
                     ><X size={16} /></button>
                   )}
                 </div>
               ))}
             </div>
             <button type="button"
               onClick={() => {
                 const last = formData.dcPointsMatchTiers[formData.dcPointsMatchTiers.length - 1];
                 let newMin = 0;
                 if (last) { newMin = (last.maxPoints ?? last.minPoints) + 10; }
                 const updatedTiers = [...formData.dcPointsMatchTiers];
                 if (last && last.maxPoints === null) {
                   updatedTiers[updatedTiers.length - 1] = { ...last, maxPoints: newMin };
                 }
                 const newTier = { minPoints: newMin, maxPoints: null, matchRate: 100, maxDeferralPct: 6 };
                 setFormData(prev => ({ ...prev, dcPointsMatchTiers: [...updatedTiers, newTier] }));
               }}
               className="mt-3 text-sm text-fidelity-green hover:text-success-ink flex items-center gap-1"
             >+ Add Tier</button>
             {formData.dcPointsMatchTiers.length === 0 && (
               <p className="mt-2 text-xs text-warning-ink">Add at least one tier to configure points-based matching</p>
             )}
             {/* E046: Points tier gap/overlap warnings */}
             {(() => {
               const warnings = validateMatchTiers(
                 formData.dcPointsMatchTiers.map(t => ({ min: t.minPoints, max: t.maxPoints })),
                 'points',
               );
               return warnings.length > 0 ? (
                 <div className="mt-3 bg-warning-surface border border-warning-border rounded-md p-3">
                   <p className="text-xs font-medium text-warning-ink mb-1">Tier configuration warnings:</p>
                   <ul className="list-disc list-inside space-y-0.5">
                     {warnings.map((w, i) => (
                       <li key={i} className="text-xs text-warning-ink">{w}</li>
                     ))}
                   </ul>
                   <p className="text-xs text-warning-ink mt-1.5">Tiers use [min, max) intervals — min is inclusive, max is exclusive.</p>
                 </div>
               ) : null;
             })()}
           </div>
         )}

         {/* E084 Phase B: Template selector + editable tiers (only for deferral_based mode) */}
         {formData.dcMatchMode === 'deferral_based' && (
         <div className="sm:col-span-3">
           <label htmlFor="dcplan-match-template" className="block text-sm font-medium text-ink-muted">Start from Template</label>
           <select
             id="dcplan-match-template"
             value={formData.dcMatchTemplate}
             onChange={(e) => {
               const templateKey = e.target.value;
               const template = MATCH_TEMPLATES[templateKey];
               if (template) {
                 setFormData(prev => ({
                   ...prev,
                   dcMatchTemplate: templateKey,
                   dcMatchTiers: template.tiers.map(t => ({ ...t })),
                 }));
               }
             }}
             className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-border-strong focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
           >
             {Object.entries(MATCH_TEMPLATES).map(([key, t]) => (
               <option key={key} value={key}>{t.name}</option>
             ))}
           </select>
           <p className="mt-1 text-xs text-ink-muted">Select a formula template, then customize tiers below. Names describe starting formulas; other plan requirements are configured separately.</p>
         </div>
         )}

         {formData.dcMatchMode === 'deferral_based' && (<>
         <div className="sm:col-span-3">
           <span className="block text-sm font-medium text-ink-muted">Max Employer Match</span>
           <div className="mt-1 bg-surface-subtle rounded-md p-2 border border-border">
             <span className="text-lg font-semibold text-ink">
               {(calculateMatchCap(formData.dcMatchTiers) * 100).toFixed(2)}%
             </span>
             <span className="text-sm text-ink-muted ml-1">of compensation</span>
           </div>
           <p className="mt-1 text-xs text-ink-muted">Auto-calculated from tiers below</p>
           <p className="mt-2 text-sm text-ink">Employee contribution rate needed for full match: <strong>{Math.max(0, ...formData.dcMatchTiers.filter(tier => tier.matchRate > 0).map(tier => tier.deferralMax))}%</strong></p>
         </div>

         {/* Editable Match Tiers */}
         <div className="sm:col-span-6 bg-surface-subtle p-4 rounded-lg border border-border">
           <span className="block text-sm font-medium text-ink-muted mb-3">Match Tiers (editable)</span>
           <p className="text-xs text-ink-muted mb-3">For “100% on the first 4%”, set the first tier from 0% to 4% with a 100% match rate. Additional tiers use cumulative boundaries: “50% on the next 2%” runs from 4% to 6%.</p>
           <p className="text-xs text-ink-muted mb-3">{tierSummary(formData.dcMatchTiers)} Formula examples assume eligible compensation and employees meeting match eligibility; IRS limits and any configured employer cap apply.</p>
           <div className="space-y-2">
             {formData.dcMatchTiers.map((tier, idx) => (
               <div key={idx} className="flex flex-wrap items-center gap-2 bg-surface-raised p-2 rounded border border-border">
                 <span className="text-xs text-ink-muted w-4">{idx + 1}.</span>
                 <span className="text-sm text-ink-muted">Employee contributions</span>
                 <NumericInput
                   type="number"
                   step="0.5"
                   min={0}
                   max={100}
                   value={tier.deferralMin}
                   aria-label={`Tier ${idx + 1} employee contribution start percent`}
                   onChange={(e) => {
                     const newTiers = [...formData.dcMatchTiers];
                     newTiers[idx] = { ...newTiers[idx], deferralMin: parseFloat(e.target.value) || 0 };
                     setFormData(prev => ({ ...prev, dcMatchTiers: newTiers }));
                   }}
                   className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                 />
                 <span className="text-sm text-ink-muted">% to</span>
                 <NumericInput
                   type="number"
                   step="0.5"
                   min={0}
                   max={100}
                   value={tier.deferralMax}
                   aria-label={`Tier ${idx + 1} employee contribution end percent`}
                   onChange={(e) => {
                     const newTiers = [...formData.dcMatchTiers];
                     newTiers[idx] = { ...newTiers[idx], deferralMax: parseFloat(e.target.value) || 0 };
                     setFormData(prev => ({ ...prev, dcMatchTiers: newTiers }));
                   }}
                   className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                 />
                 <span className="text-sm text-ink-muted">%, matched at</span>
                 <NumericInput
                   type="number"
                   step="5"
                   min={0}
                   max={200}
                   value={tier.matchRate}
                   aria-label={`Tier ${idx + 1} employer match rate percent`}
                   onChange={(e) => {
                     const newTiers = [...formData.dcMatchTiers];
                     newTiers[idx] = { ...newTiers[idx], matchRate: parseFloat(e.target.value) || 0 };
                     setFormData(prev => ({ ...prev, dcMatchTiers: newTiers }));
                   }}
                   className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                 />
                 <span className="text-sm text-ink-muted">% match</span>
                 {formData.dcMatchTiers.length > 1 && (
                   <button
                     type="button"
                     onClick={() => {
                       const newTiers = formData.dcMatchTiers.filter((_, i) => i !== idx);
                       setFormData(prev => ({ ...prev, dcMatchTiers: newTiers }));
                     }}
                     className="ml-auto text-danger-ink hover:text-danger-ink p-1"
                   >
                     <X size={16} />
                   </button>
                 )}
               </div>
             ))}
           </div>
           <button
             type="button"
             onClick={() => {
               const lastTier = formData.dcMatchTiers[formData.dcMatchTiers.length - 1];
               const newTier = { deferralMin: lastTier?.deferralMax || 0, deferralMax: (lastTier?.deferralMax || 0) + 2, matchRate: 50 };
               setFormData(prev => ({ ...prev, dcMatchTiers: [...prev.dcMatchTiers, newTier] }));
             }}
             className="mt-3 text-sm text-fidelity-green hover:text-success-ink flex items-center gap-1"
           >
             + Add Tier
           </button>
         </div>

         {/* Safe Harbor Notice */}
         {(formData.dcMatchTemplate === 'safe_harbor' || formData.dcMatchTemplate === 'qaca') && (
           <div className="sm:col-span-6 bg-info-surface border border-info-border p-3 rounded-lg flex items-start gap-2">
             <Info size={16} className="text-info-ink mt-0.5 flex-shrink-0" />
             <div>
               <p className="text-sm text-info-ink font-medium">Formula template selected</p>
               <p className="text-xs text-info-ink mt-1">
                 The saved template name does not verify safe-harbor status or nondiscrimination results. Current matching uses the editable tiers shown above; notice, vesting, eligibility and automatic-enrollment provisions require separate review.
               </p>
             </div>
           </div>
         )}
         </>)}

         <EmployerEligibilityEditor kind="Match" config={displayConfig} />
         </>)}

  </>;

  const coreControl = <div className="flex items-center justify-between mb-2">
           <h4 className="text-sm font-semibold text-ink">Employer Core (Non-Elective) Contribution</h4>
           <label htmlFor="dcplan-core-enabled" className="flex items-center">
             <input
               id="dcplan-core-enabled"
               type="checkbox"
               name="dcCoreEnabled"
               checked={formData.dcCoreEnabled}
               onChange={handleChange}
               className="h-4 w-4 text-fidelity-green rounded"
             />
             <span className="ml-2 text-sm text-ink-muted">Enabled</span>
           </label>
         </div>;
  const coreFields = <>
         <p className="sm:col-span-6 text-xs text-ink-muted -mt-4 mb-2">Automatic employer contribution regardless of employee deferral</p>

         {formData.dcCoreEnabled && (
           <>
             {/* E084: Core Contribution Type */}
             <div className="sm:col-span-3">
               <label htmlFor="dcplan-core-type" className="block text-sm font-medium text-ink-muted">Contribution Type</label>
               <select
                 id="dcplan-core-type"
                 name="dcCoreStatus"
                 value={formData.dcCoreStatus}
                 onChange={handleChange}
                 className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-border-strong focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
               >
                 <option value="flat">Flat Rate (same for all)</option>
                 <option value="graded_by_service">Graded by Service (increases with tenure)</option>
                 <option value="points_based">Points-Based (varies by age + tenure points)</option>
                 <option value="age_banded">Age-Banded (varies by annual age)</option>
                 {!['flat', 'graded_by_service', 'points_based', 'age_banded'].includes(formData.dcCoreStatus) && <option value={formData.dcCoreStatus}>Saved custom mode: {formData.dcCoreStatus}</option>}
               </select>
             </div>

             {/* Flat rate input */}
             {formData.dcCoreStatus === 'flat' && (
               <InputField label="Core Rate" {...inputProps('dcCoreContributionRate')} type="number" step="0.5" suffix="%" helper="% of compensation" min={0} />
             )}

             {formData.dcCoreStatus === 'age_banded' && (
               <div className="sm:col-span-6 bg-surface-subtle p-4 rounded-lg border border-border">
                 <span className="block text-sm font-medium text-ink-muted mb-1">Age-Banded Core Schedule</span>
                 <p className="text-xs text-ink-muted mb-3">Annual age tiers use [min, max) intervals; the final maximum may be blank.</p>
                 <div className="space-y-2">
                   {formData.dcCoreAgeSchedule.map((tier, idx) => (
                     <div key={idx} className="flex flex-wrap items-center gap-3 text-sm">
                       <span className="text-ink-muted w-8">{idx + 1}.</span>
                       <NumericInput type="number" min={0} value={tier.minAge} onChange={(e) => {
                         const schedule = [...formData.dcCoreAgeSchedule];
                         schedule[idx] = { ...tier, minAge: Number(e.target.value) };
                         setFormData((prev: any) => ({ ...prev, dcCoreAgeSchedule: schedule }));
                       }} className="w-16 px-2 py-1 border border-border-strong rounded text-center" />
                       <span className="text-ink-muted">to</span>
                       <NumericInput allowEmpty type="number" min={0} value={tier.maxAge ?? ''} placeholder="∞" onChange={(e) => {
                         const schedule = [...formData.dcCoreAgeSchedule];
                         schedule[idx] = { ...tier, maxAge: e.target.value ? Number(e.target.value) : null };
                         setFormData((prev: any) => ({ ...prev, dcCoreAgeSchedule: schedule }));
                       }} className="w-16 px-2 py-1 border border-border-strong rounded text-center" />
                       <span className="text-ink-muted">age →</span>
                       <NumericInput type="number" min={0} step="0.5" value={tier.rate} onChange={(e) => {
                         const schedule = [...formData.dcCoreAgeSchedule];
                         schedule[idx] = { ...tier, rate: Number(e.target.value) };
                         setFormData((prev: any) => ({ ...prev, dcCoreAgeSchedule: schedule }));
                       }} className="w-20 px-2 py-1 border border-border-strong rounded text-center" />
                       <span className="text-ink-muted">%</span>
                       {formData.dcCoreAgeSchedule.length > 1 && <button type="button" onClick={() => setFormData((prev: any) => ({ ...prev, dcCoreAgeSchedule: prev.dcCoreAgeSchedule.filter((_: any, i: number) => i !== idx) }))} className="text-danger-ink hover:text-danger-ink px-2">✕</button>}
                     </div>
                   ))}
                 </div>
                 <button type="button" onClick={() => {
                   const last = formData.dcCoreAgeSchedule[formData.dcCoreAgeSchedule.length - 1];
                   const newMin = last?.maxAge ?? ((last?.minAge ?? 0) + 10);
                   const schedule = last?.maxAge === null
                     ? [...formData.dcCoreAgeSchedule.slice(0, -1), { ...last, maxAge: newMin }]
                     : [...formData.dcCoreAgeSchedule];
                   setFormData((prev: any) => ({ ...prev, dcCoreAgeSchedule: [...schedule, { minAge: newMin, maxAge: null, rate: last?.rate ?? 1 }] }));
                 }} className="mt-3 text-sm text-fidelity-green hover:text-success-ink font-medium">+ Add Tier</button>
                 {(() => {
                   const warnings = validateMatchTiers(formData.dcCoreAgeSchedule.map(t => ({ min: t.minAge, max: t.maxAge })), 'age');
                   return warnings.length ? <div className="mt-3 bg-warning-surface border border-warning-border rounded-md p-3"><p className="text-xs font-medium text-warning-ink">Tier configuration warnings:</p><ul className="list-disc list-inside">{warnings.map((warning, index) => <li key={index} className="text-xs text-warning-ink">{warning}</li>)}</ul></div> : null;
                 })()}
               </div>
             )}

             {/* E084: Graded Schedule Editor */}
             {formData.dcCoreStatus === 'graded_by_service' && (
               <div className="sm:col-span-6 bg-surface-subtle p-4 rounded-lg border border-border">
                 <span className="block text-sm font-medium text-ink-muted mb-3">Graded Core Schedule</span>
                 <div className="space-y-2">
                   {formData.dcCoreGradedSchedule.map((tier: any, idx: number) => (
                     <div key={idx} className="flex flex-wrap items-center gap-3 text-sm">
                       <span className="text-ink-muted w-8">{idx + 1}.</span>
                       <NumericInput allowEmpty
                         type="number"
                         value={tier.serviceYearsMin}
                         onChange={(e) => {
                           const newSchedule = [...formData.dcCoreGradedSchedule];
                           newSchedule[idx] = { ...tier, serviceYearsMin: Number(e.target.value) };
                           setFormData((prev: any) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
                         }}
                         className="w-16 px-2 py-1 border border-border-strong rounded text-center"
                         min={0}
                       />
                       <span className="text-ink-muted">to</span>
                       <NumericInput
                         type="number"
                         value={tier.serviceYearsMax ?? ''}
                         placeholder="&#8734;"
                         onChange={(e) => {
                           const newSchedule = [...formData.dcCoreGradedSchedule];
                           newSchedule[idx] = { ...tier, serviceYearsMax: e.target.value ? Number(e.target.value) : null };
                           setFormData((prev: any) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
                         }}
                         className="w-16 px-2 py-1 border border-border-strong rounded text-center"
                         min={0}
                       />
                       <span className="text-ink-muted">years &#8594;</span>
                       <NumericInput
                         type="number"
                         value={tier.rate}
                         onChange={(e) => {
                           const newSchedule = [...formData.dcCoreGradedSchedule];
                           newSchedule[idx] = { ...tier, rate: Number(e.target.value) };
                           setFormData((prev: any) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
                         }}
                         step="0.5"
                         className="w-20 px-2 py-1 border border-border-strong rounded text-center"
                         min={0}
                       />
                       <span className="text-ink-muted">%</span>
                       {formData.dcCoreGradedSchedule.length > 1 && (
                         <button
                           type="button"
                           onClick={() => {
                             const newSchedule = formData.dcCoreGradedSchedule.filter((_: any, i: number) => i !== idx);
                             setFormData((prev: any) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
                           }}
                           className="text-danger-ink hover:text-danger-ink px-2"
                         >
                           &#10005;
                         </button>
                       )}
                     </div>
                   ))}
                 </div>
                 <button
                   type="button"
                   onClick={() => {
                     const lastTier = formData.dcCoreGradedSchedule[formData.dcCoreGradedSchedule.length - 1];
                     const newMin = (lastTier?.serviceYearsMax ?? (lastTier?.serviceYearsMin ?? 0) + 5);
                     const updatedSchedule = [...formData.dcCoreGradedSchedule];
                     if (lastTier && lastTier.serviceYearsMax === null) {
                       updatedSchedule[updatedSchedule.length - 1] = { ...lastTier, serviceYearsMax: newMin };
                     }
                     const newSchedule = [
                       ...updatedSchedule,
                       { serviceYearsMin: newMin, serviceYearsMax: null, rate: (lastTier?.rate ?? 1) + 1 }
                     ];
                     setFormData((prev: any) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
                   }}
                   className="mt-3 text-sm text-fidelity-green hover:text-success-ink font-medium"
                 >
                   + Add Tier
                 </button>
                {/* E053: Graded core tier gap/overlap warnings */}
                {(() => {
                  const warnings = validateMatchTiers(
                    formData.dcCoreGradedSchedule.map(t => ({ min: t.serviceYearsMin, max: t.serviceYearsMax })),
                    'service years',
                  );
                  return warnings.length > 0 ? (
                    <div className="mt-3 bg-warning-surface border border-warning-border rounded-md p-3">
                      <p className="text-xs font-medium text-warning-ink mb-1">Tier configuration warnings:</p>
                      <ul className="list-disc list-inside space-y-0.5">
                        {warnings.map((w, i) => (
                          <li key={i} className="text-xs text-warning-ink">{w}</li>
                        ))}
                      </ul>
                      <p className="text-xs text-warning-ink mt-1.5">Tiers use [min, max) intervals — min is inclusive, max is exclusive.</p>
                    </div>
                  ) : null;
                })()}
               </div>
             )}

            {/* E053: Points-Based Core Tier Editor */}
            {formData.dcCoreStatus === 'points_based' && (
              <div className="sm:col-span-6 bg-surface-subtle p-4 rounded-lg border border-border">
                <span className="block text-sm font-medium text-ink-muted mb-1">Points Core Schedule</span>
                <p className="text-xs text-ink-muted mb-3">Points = FLOOR(age) + FLOOR(years of service). Uses [min, max) intervals.</p>
                <div className="space-y-2">
                  {formData.dcCorePointsSchedule.map((tier, idx) => (
                    <div key={idx} className="flex flex-wrap items-center gap-3 text-sm">
                      <span className="text-ink-muted w-8">{idx + 1}.</span>
                      <NumericInput allowEmpty
                        type="number"
                        value={tier.minPoints}
                        onChange={(e) => {
                          const newSchedule = [...formData.dcCorePointsSchedule];
                          newSchedule[idx] = { ...tier, minPoints: Number(e.target.value) };
                          setFormData((prev: any) => ({ ...prev, dcCorePointsSchedule: newSchedule }));
                        }}
                        className="w-16 px-2 py-1 border border-border-strong rounded text-center"
                        min={0}
                      />
                      <span className="text-ink-muted">to</span>
                      <NumericInput
                        type="number"
                        value={tier.maxPoints ?? ''}
                        placeholder="&#8734;"
                        onChange={(e) => {
                          const newSchedule = [...formData.dcCorePointsSchedule];
                          newSchedule[idx] = { ...tier, maxPoints: e.target.value ? Number(e.target.value) : null };
                          setFormData((prev: any) => ({ ...prev, dcCorePointsSchedule: newSchedule }));
                        }}
                        className="w-16 px-2 py-1 border border-border-strong rounded text-center"
                        min={0}
                      />
                      <span className="text-ink-muted">pts &#8594;</span>
                      <NumericInput
                        type="number"
                        value={tier.rate}
                        onChange={(e) => {
                          const newSchedule = [...formData.dcCorePointsSchedule];
                          newSchedule[idx] = { ...tier, rate: Number(e.target.value) };
                          setFormData((prev: any) => ({ ...prev, dcCorePointsSchedule: newSchedule }));
                        }}
                        step="0.5"
                        className="w-20 px-2 py-1 border border-border-strong rounded text-center"
                        min={0}
                      />
                      <span className="text-ink-muted">%</span>
                      {formData.dcCorePointsSchedule.length > 1 && (
                        <button
                          type="button"
                          onClick={() => {
                            const newSchedule = formData.dcCorePointsSchedule.filter((_: any, i: number) => i !== idx);
                            setFormData((prev: any) => ({ ...prev, dcCorePointsSchedule: newSchedule }));
                          }}
                          className="text-danger-ink hover:text-danger-ink px-2"
                        >
                          &#10005;
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => {
                    const lastTier = formData.dcCorePointsSchedule[formData.dcCorePointsSchedule.length - 1];
                    const newMin = (lastTier?.maxPoints ?? (lastTier?.minPoints ?? 0)) + 10;
                    const updatedSchedule = [...formData.dcCorePointsSchedule];
                    if (lastTier && lastTier.maxPoints === null) {
                      updatedSchedule[updatedSchedule.length - 1] = { ...lastTier, maxPoints: newMin };
                    }
                    const newSchedule = [
                      ...updatedSchedule,
                      { minPoints: newMin, maxPoints: null, rate: (lastTier?.rate ?? 1) + 1 }
                    ];
                    setFormData((prev: any) => ({ ...prev, dcCorePointsSchedule: newSchedule }));
                  }}
                  className="mt-3 text-sm text-fidelity-green hover:text-success-ink font-medium"
                >
                  + Add Tier
                </button>
                {formData.dcCorePointsSchedule.length === 0 && (
                  <p className="mt-2 text-xs text-warning-ink">Add at least one tier to configure points-based core contributions</p>
                )}
                {/* E053: Points core tier gap/overlap warnings */}
                {(() => {
                  const warnings = validateMatchTiers(
                    formData.dcCorePointsSchedule.map(t => ({ min: t.minPoints, max: t.maxPoints })),
                    'points',
                  );
                  return warnings.length > 0 ? (
                    <div className="mt-3 bg-warning-surface border border-warning-border rounded-md p-3">
                      <p className="text-xs font-medium text-warning-ink mb-1">Tier configuration warnings:</p>
                      <ul className="list-disc list-inside space-y-0.5">
                        {warnings.map((w, i) => (
                          <li key={i} className="text-xs text-warning-ink">{w}</li>
                        ))}
                      </ul>
                      <p className="text-xs text-warning-ink mt-1.5">Tiers use [min, max) intervals — min is inclusive, max is exclusive.</p>
                    </div>
                  ) : null;
                })()}
              </div>
            )}

             {/* Social Security integration (permitted disparity, §401(l)).
                 Rendered for every contribution type: it modifies whichever base
                 rate the schedule above resolved, rather than replacing it. */}
             <div className="sm:col-span-6 bg-surface-subtle p-4 rounded-lg border border-border">
               <label className="flex items-center gap-2 text-sm font-medium text-ink-muted">
                 <input
                   type="checkbox"
                   name="dcCoreIntegrationEnabled"
                   checked={formData.dcCoreIntegrationEnabled}
                   onChange={handleChange}
                   className="h-4 w-4 text-fidelity-green border-border-strong rounded focus:ring-fidelity-green"
                 />
                 Social Security Integration (Permitted Disparity)
               </label>
               <p className="text-xs text-ink-muted mt-1">
                 Adds an extra rate on compensation above an integration level, on top of the
                 contribution type selected above. Off by default.
               </p>

               {formData.dcCoreIntegrationEnabled && (
                 <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
                   <div>
                     <label htmlFor="dcplan-core-integration-mode" className="block text-sm font-medium text-ink-muted">Integration Level</label>
                     <select
                       id="dcplan-core-integration-mode"
                       name="dcCoreIntegrationLevelMode"
                       value={formData.dcCoreIntegrationLevelMode}
                       onChange={handleChange}
                       className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-border-strong focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
                     >
                       <option value="ss_wage_base">Social Security wage base</option>
                       <option value="percent_of_ss_wage_base">% of the wage base</option>
                       <option value="fixed_dollar">Fixed dollar amount</option>
                     </select>
                   </div>

                   {formData.dcCoreIntegrationLevelMode !== 'ss_wage_base' && (
                     <InputField
                       label={formData.dcCoreIntegrationLevelMode === 'percent_of_ss_wage_base' ? 'Level' : 'Level Amount'}
                       {...inputProps('dcCoreIntegrationLevelValue')}
                       type="number"
                       step={formData.dcCoreIntegrationLevelMode === 'percent_of_ss_wage_base' ? '1' : '1000'}
                       suffix={formData.dcCoreIntegrationLevelMode === 'percent_of_ss_wage_base' ? '%' : '$'}
                       helper={formData.dcCoreIntegrationLevelMode === 'percent_of_ss_wage_base' ? '% of the wage base' : 'Dollar integration level'}
                       min={0}
                     />
                   )}

                   <InputField
                     label="Disparity Rate"
                     {...inputProps('dcCoreIntegrationDisparityRate')}
                     type="number"
                     step="0.1"
                     suffix="%"
                     helper="Extra rate above the level"
                     min={0}
                   />

                   <p className="sm:col-span-3 text-xs text-ink-muted">
                     Under §401(l) the disparity rate may not exceed the lesser of the base
                     contribution rate and the permitted disparity factor (5.7% when the level is
                     the wage base, lower for reduced levels). An excessive rate is rejected when
                     the simulation starts, with the applicable limit named.
                   </p>

                   {(() => {
                     const warnings = validateCoreIntegration(formData);
                     return warnings.length ? (
                       <div className="sm:col-span-3 bg-warning-surface border border-warning-border rounded-md p-3">
                         <p className="text-xs font-medium text-warning-ink mb-1">
                           §401(l) permitted disparity:
                         </p>
                         <ul className="list-disc list-inside space-y-0.5">
                           {warnings.map((warning, index) => (
                             <li key={index} className="text-xs text-warning-ink">{warning}</li>
                           ))}
                         </ul>
                       </div>
                     ) : null;
                   })()}
                 </div>
               )}
             </div>

             <EmployerEligibilityEditor kind="Core" config={displayConfig} />
           </>
         )}

  </>;

  const escalationControl = <div className="flex items-center justify-between mb-2">
             <h4 className="text-sm font-semibold text-ink">Auto-Escalation</h4>
             <label htmlFor="dcplan-auto-escalation" className="flex items-center">
                 <input id="dcplan-auto-escalation" type="checkbox" name="dcAutoEscalation" checked={formData.dcAutoEscalation} onChange={handleChange} className="h-4 w-4 text-fidelity-green rounded" />
                 <span className="ml-2 text-sm text-ink-muted">Enabled</span>
             </label>
         </div>;
  const escalationFields = <>
         <div className="sm:col-span-3">
           <label htmlFor="dcplan-escalation-mode" className="block text-sm font-medium text-ink-muted">Who Gets Increases</label>
           <select id="dcplan-escalation-mode" name="dcEscalationMode" value={formData.dcEscalationMode} onChange={handleChange} disabled={!formData.dcAutoEscalation}
             className="mt-1 block w-full p-2 border border-border-strong rounded-md text-sm disabled:bg-surface-disabled">
             <option value="automatic">Automatic (everyone unless they opt out)</option>
             <option value="participant_elected">Participant-elected (employees sign up)</option>
           </select>
           <p className="mt-1 text-xs text-ink-muted">{formData.dcAutoEscalation ? 'Automatic: everyone is enrolled and may opt out. Participant-elected: only employees who sign up get increases (set the sign-up rate under Employee behavior assumptions).' : 'Inactive while automatic contribution increases are off. Saved value is retained.'}</p>
         </div>
         <InputField label="Escalation Cap" {...inputProps('dcEscalationCap')} type="number" suffix="%" disabled={!formData.dcAutoEscalation} helper="Ceiling for automatic annual increases only. Employees can contribute above this rate, including to receive the full employer match." />
         {formData.dcAutoEscalation && (
           <>
             <InputField label="Annual Increase" {...inputProps('dcEscalationRate')} type="number" step="0.5" suffix="pp" helper="Percentage points added to the employee contribution rate each year." />
             <div className="sm:col-span-3">
               <label htmlFor="dcplan-escalation-effective-date" className="block text-sm font-medium text-ink-muted">Effective Date (MM-DD)</label>
               <input
                 id="dcplan-escalation-effective-date"
                 type="text"
                 name="dcEscalationEffectiveDay"
                 value={formData.dcEscalationEffectiveDay}
                 onChange={handleChange}
                 placeholder="01-01"
                 pattern="\d{2}-\d{2}"
                 className="mt-1 block w-full pl-3 pr-3 py-2 text-base border-border-strong focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
               />
               <p className="mt-1 text-xs text-ink-muted">Annual escalation date (e.g., 01-01 for Jan 1)</p>
             </div>
             <InputField label="First Escalation Delay" {...inputProps('dcEscalationDelayYears')} type="number" suffix="Years" helper="Delay measured in enrollment years: simulation year minus enrollment year, rather than elapsed anniversaries." min={0} />
             <div className="sm:col-span-3">
               <label htmlFor="dcplan-escalation-hire-cutoff" className="block text-sm font-medium text-ink-muted">Hire Date Cutoff</label>
               <input
                 id="dcplan-escalation-hire-cutoff"
                 type="date"
                 name="dcEscalationHireDateCutoff"
                 value={formData.dcEscalationHireDateCutoff}
                 onChange={handleChange}
                 className="mt-1 block w-full pl-3 pr-3 py-2 text-base border-border-strong focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
               />
               <p className="mt-1 text-xs text-ink-muted">Only escalate employees hired on/after this date</p>
             </div>
           </>
         )}
  </>;

  return (
    <div className="space-y-6 animate-fadeIn">
      <div className="border-b border-border pb-4">
        <h2 className="text-lg font-bold text-ink">401(k) / DC Plan Config</h2>
        <p className="text-sm text-ink-muted">Configure plan provisions and the employee behavior assumptions used in the simulation.</p>
      </div>
      <section aria-labelledby="dcplan-provisions" className="space-y-4">
        <h3 id="dcplan-provisions" className="font-bold text-ink">Plan provisions</h3>
        <DCPlanPanel id="dcplan-eligibility-panel" title="Eligibility and enrollment" summary={`Shared waiting period: ${formData.dcEligibilityMonths} modeled months (${waitingPeriodDays} days); automatic enrollment ${formData.dcAutoEnroll ? 'on' : 'off'}; ${formData.dcAutoEnrollScope === 'new_hires_only' ? 'first year uses hire cutoff, later years use current-year hires' : 'all eligible employees, subject to hire cutoff every year'}; hire cutoff ${formData.dcAutoEnrollHireDateCutoff || 'inherited'}; shared hire-year delay ${formData.dcAutoEnrollWindowDays} days. New-hire voluntary enrollment: ${rateSource(voluntaryMode, formData.dcVoluntaryEnrollmentRate)}; ${formData.dcAutoEnroll ? `new-hire opt-out: ${rateSource(optOutMode, formData.dcNewHireOptOutRate)}; continuing opt-out target ${formData.dcOptOutRateTarget}%` : 'opt-out assumptions inactive'}.`}>{renderEligibilityFields()}</DCPlanPanel>
        <DCPlanPanel id="dcplan-match-panel" title="Employer match" summary={matchSummary(formData, displayConfig)} enabled={formData.dcMatchEnabled} control={matchControl}>{matchFields}</DCPlanPanel>
        <DCPlanPanel id="dcplan-core-panel" title="Employer core contribution" summary={coreSummary(formData, displayConfig)} enabled={formData.dcCoreEnabled} control={coreControl}>{coreFields}</DCPlanPanel>
        <DCPlanPanel id="dcplan-escalation-panel" title="Automatic contribution increases" enabled={formData.dcAutoEscalation} control={escalationControl} summary={formData.dcAutoEscalation ? `${formData.dcEscalationMode === 'participant_elected' ? 'Participant-elected (employees sign up)' : 'Automatic (everyone unless they opt out)'}; ${formData.dcEscalationRate} percentage points annually up to ${formData.dcEscalationCap}% on ${formData.dcEscalationEffectiveDay}; delay ${formData.dcEscalationDelayYears} enrollment years; hire cutoff ${formData.dcEscalationHireDateCutoff || 'none configured'}.` : 'Automatic contribution increases off; saved settings retained.'}>{escalationFields}</DCPlanPanel>
      </section>
      <section aria-labelledby="dcplan-behavior" className="space-y-4">
        <h3 id="dcplan-behavior" className="font-bold text-ink">Employee behavior assumptions</h3>
        <DCPlanPanel id="dcplan-increase-behavior-panel" title="Sign-up for automatic increases" enabled={formData.dcAutoEscalation} summary={!formData.dcAutoEscalation ? 'Inactive while automatic contribution increases are off; saved assumptions retained.' : formData.dcEscalationMode === 'participant_elected' ? `${formData.dcEscalationSignupProbability}% of participants sign up for automatic contribution increases.` : 'Employees join automatically unless they opt out; sign-up assumptions are inactive.'}>
          <InputField label="Employees who sign up for automatic increases" {...inputProps('dcEscalationSignupProbability')} type="number" suffix="%" min={0} max={100}
            disabled={!formData.dcAutoEscalation || formData.dcEscalationMode !== 'participant_elected'}
            helper={formData.dcAutoEscalation && formData.dcEscalationMode === 'participant_elected' ? 'Share of enrolled participants who sign up.' : 'Inactive unless employees sign up for increases. Saved value is retained.'} width="col-span-6" />
        </DCPlanPanel>
        <DCPlanPanel id="dcplan-starting-rates-panel" title="Starting employee contribution rates" summary={`Segment rates ${Math.min(...Object.values(formData.dcVoluntaryDeferralBaseRates))}–${Math.max(...Object.values(formData.dcVoluntaryDeferralBaseRates))}%; upward spread ${formData.dcDeferralSpreadMaxLift} percentage points; voluntary cap ${formData.dcMaxVoluntaryDeferral}%. ${belowDefaultSummary(formData)}${deferralSpreadClipping ? ` Warning: spread ceiling ${deferralSpreadClipping.spreadCeiling}% exceeds the cap; rates will be clipped.` : ''}`}>{startingRateFields}</DCPlanPanel>
        <DCPlanPanel id="dcplan-easy-enroll-panel" title="Easy Enroll" enabled={formData.dcEasyEnrollEnabled} summary={easyEnrollSummary(formData)} control={
          <label htmlFor="dcplan-easy-enroll-enabled" className="flex items-center gap-2 text-sm font-medium text-ink-muted">
            <input id="dcplan-easy-enroll-enabled" type="checkbox" name="dcEasyEnrollEnabled" checked={formData.dcEasyEnrollEnabled} onChange={handleChange} className="h-4 w-4 text-fidelity-green rounded" />
            Offer Easy Enroll packages
          </label>
        }><EasyEnrollEditor form={formData} onChange={changes => setFormData(previous => ({ ...previous, ...changes }))} /></DCPlanPanel>
        <DCPlanPanel id="dcplan-rate-changes-panel" title="Changes to contribution rates over time" enabled={formData.dcDeferralRateChangesEnabled} summary={deferralRateChangesSummary(formData)} control={
          <label htmlFor="dcplan-rate-changes-enabled" className="flex items-center gap-2 text-sm font-medium text-ink-muted">
            <input id="dcplan-rate-changes-enabled" type="checkbox" name="dcDeferralRateChangesEnabled" checked={formData.dcDeferralRateChangesEnabled} onChange={handleChange} className="h-4 w-4 text-fidelity-green rounded" />
            Model employees changing their own contribution rate
          </label>
        }><DeferralRateChangesEditor form={formData} onChange={changes => setFormData(previous => ({ ...previous, ...changes }))} /></DCPlanPanel>
        <DCPlanPanel id="dcplan-response-panel" title="Response to the employer match" summary={`New enrollees seeking full match: ${formData.dcMatchMagnetEnabled ? `${formData.dcMatchMagnetProbability}% of below-ceiling voluntary enrollees` : 'off'}; downward pull ${formData.dcAutoEnroll && formData.dcMatchMagnetEnabled ? formData.dcMatchMagnetDownwardEnabled ? `on (same ${formData.dcMatchMagnetProbability}% probability)` : 'off' : 'inactive'}; first-year existing-participant response: ${formData.dcMatchResponseEnabled ? `upward ${formData.dcMatchResponseUpwardParticipation}%, downward ${formData.dcMatchResponseDownwardEnabled ? `${formData.dcMatchResponseDownwardParticipation}%` : 'off'}; ${responseMaximizers}% of upward responders seek full match, others close ${responsePartialGap}% of the gap` : 'off'}.`}>{responseFields}</DCPlanPanel>
      </section>
    </div>
  );
}
