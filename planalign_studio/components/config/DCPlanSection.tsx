import { OptOutBandsEditor } from './OptOutBandsEditor';
import { NumericInput } from './NumericInput';
import { useEffect, useState } from 'react';
import { AlertTriangle, BarChart3, X } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { InputField } from './InputField';
import { DEFAULT_FORM_DATA, DEFAULT_VOLUNTARY_DEFERRAL_BASE_RATES,
  DEFERRAL_SPREAD_MIN, DEFERRAL_SPREAD_MAX } from './constants';
import { analyzeOptOutRate, OptOutRateAnalysisResult } from '../../services/api';
import { VoluntaryDeferralRatesEditor } from './VoluntaryDeferralRatesEditor';
import { DCPlanPanel, EmployerEligibilityEditor, coreSummary, dcDisplayConfig, matchSummary } from './DCPlanPanels';
import { EnrollmentRateInput } from './EnrollmentRateInput';
import { BelowDefaultEditor } from './BelowDefaultEditor';
import { EasyEnrollEditor } from './EasyEnrollEditor';
import { DeferralRateChangesEditor } from './DeferralRateChangesEditor';
import { belowDefaultSummary, easyEnrollSummary, deferralRateChangesSummary } from './participantBehaviorConfig';
import { MatchFormulaControl, MatchFormulaFields } from './MatchFormulaFields';
import { CoreFormulaControl, CoreFormulaFields } from './CoreFormulaFields';
import type { FormScope } from './formScope';
import { GrandfatheredDesignControl, GrandfatheredDesignFields, useLockedDesigns } from './GrandfatheredDesignPanel';
import { grandfatheredDesignSummary } from './grandfatheredDesignSummary';

// A blank cutoff is removed from the export, so dbt applies its default (dbt_project.yml).
const ENGINE_DEFAULT_HIRE_CUTOFF = '2020-01-01';
const hireCutoffLabel = (cutoff: string) => cutoff || `${ENGINE_DEFAULT_HIRE_CUTOFF} (engine default)`;

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
                 className="h-4 w-4 text-brand-ink focus:ring-brand-green border-border-strong rounded mt-1"
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
             <input id="dcReenrollmentSweepEnabled" name="dcReenrollmentSweepEnabled" type="checkbox" checked={formData.dcReenrollmentSweepEnabled} onChange={handleChange} aria-describedby="reenrollment-sweep-help" className="h-4 w-4 text-brand-ink rounded" />
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
                 className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-border-strong focus:outline-none focus:ring-brand-green focus:border-brand-green sm:text-sm rounded-md border shadow-sm"
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
                 className="mt-1 block w-full pl-3 pr-3 py-2 text-base border-border-strong focus:outline-none focus:ring-brand-green focus:border-brand-green sm:text-sm rounded-md border shadow-sm"
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
                     className="flex items-center gap-1 px-2 py-1 text-xs bg-brand-green text-ink-inverse rounded hover:bg-success-solid-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
                     className="text-xs text-brand-ink hover:text-success-ink font-medium"
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
                       className="w-16 px-2 py-0.5 border border-success-border rounded text-xs focus:outline-none focus:ring-1 focus:ring-brand-green"
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
                           className="px-3 py-1 text-xs bg-brand-green text-ink-inverse rounded hover:bg-success-solid-hover transition-colors font-medium"
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

               <OptOutBandsEditor form={formData} onChange={changes => setFormData(prev => ({ ...prev, ...changes }))} />
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
                 className="h-4 w-4 text-brand-ink rounded"
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
                   disabled={!formData.dcMatchMagnetEnabled || !formData.dcAutoEnroll} aria-describedby="dcplan-match-magnet-downward-help" className="mt-1 h-4 w-4 text-brand-ink rounded disabled:opacity-50" />
                 Also pull rates down to the full-match rate when it is below the auto-enrollment default
               </label>
               <p id="dcplan-match-magnet-downward-help" className="mt-1 text-xs text-ink-muted">On by default. Applies only to employees whose starting rate is between the full-match rate and the auto-enrollment default. Rates above the default are never lowered. Uses the same {formData.dcMatchMagnetProbability}% probability as the upward pull. {!formData.dcAutoEnroll ? 'Inactive while auto-enrollment is off. Saved value is retained.' : !formData.dcMatchMagnetEnabled ? 'Inactive while new-enrollee match seeking is off. Saved value is retained.' : ''}</p>
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
                 className="h-4 w-4 text-brand-ink rounded"
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
                   className="h-4 w-4 text-brand-ink rounded"
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

  const scope: FormScope = { formData, setFormData, handleChange, inputProps };
  const matchControl = <MatchFormulaControl scope={scope} />;
  const grandfather = formData.dcGrandfather?.enabled ? formData.dcGrandfather : null;
  const designNote = (part: string) => grandfather && <p className="sm:col-span-6 text-xs text-info-ink">
    With the grandfathered design on, this {part} applies to employees hired before {grandfather.cutoff || 'the cutoff'}. Set the new-hire version under Grandfathered plan design below.
  </p>;
  const matchFields = <>{designNote('match')}<MatchFormulaFields scope={scope} eligibility={<EmployerEligibilityEditor kind="Match" config={displayConfig} />} /></>;

  const coreControl = <CoreFormulaControl scope={scope} />;
  const coreFields = <>{designNote('core contribution')}<CoreFormulaFields scope={scope} eligibility={<EmployerEligibilityEditor kind="Core" config={displayConfig} />} /></>;
  const lockedDesigns = useLockedDesigns();

  const escalationControl = <div className="flex items-center justify-between mb-2">
             <h4 className="text-sm font-semibold text-ink">Auto-Escalation</h4>
             <label htmlFor="dcplan-auto-escalation" className="flex items-center">
                 <input id="dcplan-auto-escalation" type="checkbox" name="dcAutoEscalation" checked={formData.dcAutoEscalation} onChange={handleChange} className="h-4 w-4 text-brand-ink rounded" />
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
                 className="mt-1 block w-full pl-3 pr-3 py-2 text-base border-border-strong focus:outline-none focus:ring-brand-green focus:border-brand-green sm:text-sm rounded-md border shadow-sm"
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
                 className="mt-1 block w-full pl-3 pr-3 py-2 text-base border-border-strong focus:outline-none focus:ring-brand-green focus:border-brand-green sm:text-sm rounded-md border shadow-sm"
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
        <DCPlanPanel id="dcplan-grandfather-panel" title="Grandfathered plan design (advanced)" summary={grandfatheredDesignSummary(formData, lockedDesigns)} enabled={Boolean(grandfather)} control={<GrandfatheredDesignControl />}><GrandfatheredDesignFields /></DCPlanPanel>
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
            <input id="dcplan-easy-enroll-enabled" type="checkbox" name="dcEasyEnrollEnabled" checked={formData.dcEasyEnrollEnabled} onChange={handleChange} className="h-4 w-4 text-brand-ink rounded" />
            Offer Easy Enroll packages
          </label>
        }><EasyEnrollEditor form={formData} onChange={changes => setFormData(previous => ({ ...previous, ...changes }))} /></DCPlanPanel>
        <DCPlanPanel id="dcplan-rate-changes-panel" title="Changes to contribution rates over time" enabled={formData.dcDeferralRateChangesEnabled} summary={deferralRateChangesSummary(formData)} control={
          <label htmlFor="dcplan-rate-changes-enabled" className="flex items-center gap-2 text-sm font-medium text-ink-muted">
            <input id="dcplan-rate-changes-enabled" type="checkbox" name="dcDeferralRateChangesEnabled" checked={formData.dcDeferralRateChangesEnabled} onChange={handleChange} className="h-4 w-4 text-brand-ink rounded" />
            Model employees changing their own contribution rate
          </label>
        }><DeferralRateChangesEditor form={formData} onChange={changes => setFormData(previous => ({ ...previous, ...changes }))} /></DCPlanPanel>
        <DCPlanPanel id="dcplan-response-panel" title="Response to the employer match" summary={`New enrollees seeking full match: ${formData.dcMatchMagnetEnabled ? `${formData.dcMatchMagnetProbability}% of below-ceiling voluntary enrollees` : 'off'}; downward pull ${formData.dcAutoEnroll && formData.dcMatchMagnetEnabled ? formData.dcMatchMagnetDownwardEnabled ? `on (same ${formData.dcMatchMagnetProbability}% probability)` : 'off' : 'inactive'}; first-year existing-participant response: ${formData.dcMatchResponseEnabled ? `upward ${formData.dcMatchResponseUpwardParticipation}%, downward ${formData.dcMatchResponseDownwardEnabled ? `${formData.dcMatchResponseDownwardParticipation}%` : 'off'}; ${responseMaximizers}% of upward responders seek full match, others close ${responsePartialGap}% of the gap` : 'off'}.`}>{responseFields}</DCPlanPanel>
      </section>
    </div>
  );
}
