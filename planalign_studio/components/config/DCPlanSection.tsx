import { useEffect, useState } from 'react';
import { AlertTriangle, BarChart3, Info, X } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { InputField } from './InputField';
import { MATCH_TEMPLATES, calculateMatchCap, DEFAULT_FORM_DATA } from './constants';
import { analyzeOptOutRate, OptOutRateAnalysisResult } from '../../services/api';
import { TenureGradedMatchEditor } from './TenureGradedMatchEditor';
import { VoluntaryDeferralRatesEditor } from './VoluntaryDeferralRatesEditor';

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

export function DCPlanSection() {
  const { formData, setFormData, handleChange, inputProps, activeWorkspace } = useConfigContext();

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

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-border pb-4">
        <h2 className="text-lg font-bold text-ink">401(k) / DC Plan Config</h2>
        <p className="text-sm text-ink-muted">Configure retirement plan eligibility, matching rules, and vesting.</p>
      </div>

      <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6">
         <div className="sm:col-span-6 bg-success-surface p-4 rounded-lg border border-success-border mb-2 flex items-start">
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
               <p className="text-xs text-success-ink mt-0.5">New hires will be automatically enrolled upon eligibility.</p>
            </div>
         </div>

         <InputField label="Eligibility Period" {...inputProps('dcEligibilityMonths')} type="number" suffix="Months" helper="Wait period before joining" />
         <InputField label="Default Deferral Rate" {...inputProps('dcDefaultDeferral')} type="number" step="0.5" suffix="%" helper="Initial contribution for auto-enrolled" />

         {/* E084: Auto-Enrollment Advanced Settings */}
         {formData.dcAutoEnroll && (
           <>
             <InputField label="Enrollment Window" {...inputProps('dcAutoEnrollWindowDays')} type="number" suffix="Days" helper="Days after hire for auto-enrollment" min={30} />
             <InputField label="Opt-Out Grace Period" {...inputProps('dcAutoEnrollOptOutGracePeriod')} type="number" suffix="Days" helper="Days to opt out without penalty" min={0} />
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
               <p className="mt-1 text-xs text-ink-muted">Who gets auto-enrolled</p>
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
               <p className="mt-1 text-xs text-ink-muted">Auto-enroll employees hired on/after this date</p>
             </div>

             {/* Opt-Out Assumptions Section */}
             <div className="sm:col-span-6 mt-4">
               <div className="flex items-center justify-between mb-3">
                 <h4 className="text-sm font-semibold text-ink">Opt-Out Assumptions</h4>
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
               <p className="text-xs text-ink-muted mb-3">Set the overall target opt-out rate. Demographic sensitivity is applied automatically behind the scenes.</p>

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
                     <input
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
                 <InputField label="Target Opt-Out Rate" {...inputProps('dcOptOutRateTarget')} type="number" step="0.5" suffix="%" helper="Overall average opt-out rate across all demographics" min={0} max={100} />
               </div>

               {/* Derived rates preview */}
               <details className="text-xs text-ink-muted">
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
             </div>
           </>
         )}

         {/* New Hire Enrollment Rates (issue #652) */}
         <div className="sm:col-span-6 mt-4">
           <h4 className="text-sm font-semibold text-ink mb-1">New Hire Enrollment Rates</h4>
           <p className="text-xs text-ink-muted mb-3">
             Exact percentages applied to eligible new hires in their hire year. Whatever
             is left over auto-enrolls. Leave a field empty to keep the demographic model
             for that decision. These do not affect continuing employees.
           </p>
           <div className="grid grid-cols-1 gap-y-4 gap-x-4 sm:grid-cols-6">
             <InputField
               label="New Hire Voluntary Enrollment %"
               name="dcVoluntaryEnrollmentRate"
               value={formData.dcVoluntaryEnrollmentRate}
               onChange={handleChange}
               type="number"
               step="1"
               suffix="%"
               helper="Share of eligible new hires who enroll on their own (0–100%). Empty = demographic rates."
               min={0}
               max={100}
               placeholder="Default"
             />
             <InputField
               label="New Hire Opt-Out %"
               name="dcNewHireOptOutRate"
               value={formData.dcNewHireOptOutRate}
               onChange={handleChange}
               type="number"
               step="1"
               suffix="%"
               helper="Share of auto-enrolled new hires who opt out (0–100%). Empty = demographic opt-out model."
               min={0}
               max={100}
               placeholder="Default"
             />
           </div>
           {formData.dcVoluntaryEnrollmentRate !== '' && (Number(formData.dcVoluntaryEnrollmentRate) < 0 || Number(formData.dcVoluntaryEnrollmentRate) > 100) && (
             <p className="mt-1 text-xs text-danger-ink">New hire voluntary enrollment must be between 0% and 100%.</p>
           )}
           {formData.dcNewHireOptOutRate !== '' && (Number(formData.dcNewHireOptOutRate) < 0 || Number(formData.dcNewHireOptOutRate) > 100) && (
             <p className="mt-1 text-xs text-danger-ink">New hire opt-out must be between 0% and 100%.</p>
           )}
         </div>

         <VoluntaryDeferralRatesEditor
           rates={formData.dcVoluntaryDeferralBaseRates}
           onChange={(rates) => setFormData(prev => ({ ...prev, dcVoluntaryDeferralBaseRates: rates }))}
           workspaceId={activeWorkspace?.id}
           censusDataPath={formData.censusDataPath}
         />

         {/* Match Magnet dial (Feature 102) */}
         <div className="sm:col-span-6 mt-4">
           <div className="flex items-center justify-between mb-1">
             <h4 className="text-sm font-semibold text-ink">Match Magnet</h4>
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
           <p className="text-xs text-ink-muted mb-3">Models employees who defer just enough to capture the full employer match: a fraction of below-ceiling voluntary enrollees snap up to the match ceiling. Raise the "snap" share to counteract a declining average deferral when there is no auto-enrollment.</p>
           <div className="grid grid-cols-1 gap-y-4 gap-x-4 sm:grid-cols-6">
             <InputField label="Snap to Match" {...inputProps('dcMatchMagnetProbability')} type="number" step="1" suffix="%" helper="Share of below-ceiling enrollees who snap to the match ceiling (0–100%)." min={0} max={100} />
             <InputField label="Max Voluntary Deferral" {...inputProps('dcMaxVoluntaryDeferral')} type="number" step="1" suffix="%" helper="Upper bound on voluntary deferral selection, including magnet-snapped rates." min={1} max={100} />
           </div>
         </div>

         <div className="col-span-6 h-px bg-surface-disabled my-2"></div>
         <div className="sm:col-span-6 mt-2">
           <div className="flex items-center justify-between mb-1">
             <h4 className="text-sm font-semibold text-ink">Match-Responsive Deferral Adjustment</h4>
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
           <p className="text-xs text-ink-muted mb-3">In the first projection year, models active enrolled employees changing deferrals in response to the employer-match ceiling. This is distinct from Match Magnet, which affects voluntary enrollment behavior.</p>
           <div className="grid grid-cols-1 gap-y-4 gap-x-4 sm:grid-cols-6">
             <InputField
               label="Increase Deferral Response"
               {...inputProps('dcMatchResponseUpwardParticipation')}
               type="number"
               step="1"
               suffix="%"
               helper="Share of eligible employees below the match ceiling who increase deferrals (0–100%)."
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
                   onChange={handleChange}
                   className="h-4 w-4 text-fidelity-green rounded"
                 />
                 <span className="ml-2 text-sm text-ink-muted">Allow Deferral Decreases</span>
               </label>
               <InputField
                 label="Decrease Deferral Response"
                 {...inputProps('dcMatchResponseDownwardParticipation')}
                 type="number"
                 step="1"
                 suffix="%"
                 helper="Share of eligible employees above the match ceiling who decrease deferrals (default: 5%)."
                 min={0}
                 max={100}
               />
             </div>
           </div>
         </div>

         <div className="col-span-6 h-px bg-surface-disabled my-2"></div>
         <div className="sm:col-span-6 flex items-center justify-between mb-2">
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
         </div>
         <p className="col-span-6 text-xs text-ink-muted -mt-4 mb-2">Configure employer matching contributions on employee deferrals</p>

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
                 <div key={idx} className="flex items-center gap-2 bg-surface-raised p-2 rounded border border-border">
                   <span className="text-xs text-ink-muted w-4">{idx + 1}.</span>
                   <input type="number" min={0} value={tier.minPoints}
                     onChange={(e) => {
                       const newTiers = [...formData.dcPointsMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], minPoints: parseInt(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                     }}
                     className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-ink-muted">to</span>
                   <input type="number" min={0} value={tier.maxPoints ?? ''}
                     placeholder="&#8734;"
                     onChange={(e) => {
                       const newTiers = [...formData.dcPointsMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], maxPoints: e.target.value === '' ? null : parseInt(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                     }}
                     className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-ink-muted">pts | 0% to</span>
                   <input type="number" step="1" min={0} max={100} value={tier.maxDeferralPct}
                     onChange={(e) => {
                       const newTiers = [...formData.dcPointsMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], maxDeferralPct: parseFloat(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                     }}
                     className="w-14 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-ink-muted">% deferrals &#8594;</span>
                   <input type="number" step="5" min={0} max={200} value={tier.matchRate}
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
           <p className="mt-1 text-xs text-ink-muted">Select a template, then customize tiers below</p>
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
         </div>

         {/* Editable Match Tiers */}
         <div className="sm:col-span-6 bg-surface-subtle p-4 rounded-lg border border-border">
           <span className="block text-sm font-medium text-ink-muted mb-3">Match Tiers (editable)</span>
           <div className="space-y-2">
             {formData.dcMatchTiers.map((tier, idx) => (
               <div key={idx} className="flex items-center gap-2 bg-surface-raised p-2 rounded border border-border">
                 <span className="text-xs text-ink-muted w-4">{idx + 1}.</span>
                 <input
                   type="number"
                   step="0.5"
                   min={0}
                   max={100}
                   value={tier.deferralMin}
                   onChange={(e) => {
                     const newTiers = [...formData.dcMatchTiers];
                     newTiers[idx] = { ...newTiers[idx], deferralMin: parseFloat(e.target.value) || 0 };
                     setFormData(prev => ({ ...prev, dcMatchTiers: newTiers }));
                   }}
                   className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                 />
                 <span className="text-sm text-ink-muted">% to</span>
                 <input
                   type="number"
                   step="0.5"
                   min={0}
                   max={100}
                   value={tier.deferralMax}
                   onChange={(e) => {
                     const newTiers = [...formData.dcMatchTiers];
                     newTiers[idx] = { ...newTiers[idx], deferralMax: parseFloat(e.target.value) || 0 };
                     setFormData(prev => ({ ...prev, dcMatchTiers: newTiers }));
                   }}
                   className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                 />
                 <span className="text-sm text-ink-muted">% deferrals &#8594;</span>
                 <input
                   type="number"
                   step="5"
                   min={0}
                   max={200}
                   value={tier.matchRate}
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
           <div className="col-span-6 bg-info-surface border border-info-border p-3 rounded-lg flex items-start gap-2">
             <Info size={16} className="text-info-ink mt-0.5 flex-shrink-0" />
             <div>
               <p className="text-sm text-info-ink font-medium">Safe Harbor Plan Selected</p>
               <p className="text-xs text-info-ink mt-1">
                 {formData.dcMatchTemplate === 'safe_harbor'
                   ? 'Safe Harbor Basic: 100% match on first 3% + 50% match on next 2%. Satisfies ADP/ACP nondiscrimination tests.'
                   : 'QACA Safe Harbor: 100% match on first 1% + 50% match on next 5%. Includes automatic enrollment requirements.'}
               </p>
             </div>
           </div>
         )}
         </>)}

         {/* E084: Match Eligibility Section */}
         <div className="col-span-6 h-px bg-surface-disabled my-2"></div>
         <h4 className="col-span-6 text-sm font-semibold text-ink">Match Eligibility Requirements</h4>
         <p className="col-span-6 text-xs text-ink-muted -mt-4 mb-2">Configure who qualifies for employer match contributions</p>

         <InputField label="Min. Tenure" {...inputProps('dcMatchMinTenureYears')} type="number" suffix="Years" helper="Years of service required" min={0} />
         <InputField label="Min. Annual Hours" {...inputProps('dcMatchMinHoursAnnual')} type="number" suffix="Hours" helper="Hours worked per year" min={0} />

         <div className="sm:col-span-6 flex items-center">
           <input
             type="checkbox"
             id="dcMatchRequireYearEndActive"
             checked={formData.dcMatchRequireYearEndActive}
             onChange={(e) => {
               const checked = e.target.checked;
               setFormData(prev => ({
                 ...prev,
                 dcMatchRequireYearEndActive: checked,
                 dcMatchAllowTerminatedNewHires: !checked,
                 dcMatchAllowExperiencedTerminations: !checked,
               }));
             }}
             className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-border-strong rounded"
           />
           <div className="ml-2">
             <label htmlFor="dcMatchRequireYearEndActive" className="block text-sm text-ink-muted">Last Day Working Rule</label>
             <p className="text-xs text-ink-muted">
               {formData.dcMatchRequireYearEndActive
                 ? 'Enabled — only employees active at year-end receive match contributions'
                 : 'Disabled — terminated employees may still receive match contributions'}
             </p>
           </div>
         </div>
         </>)}

         {/* E084: Core Contribution Section */}
         <div className="col-span-6 h-px bg-surface-disabled my-2"></div>
         <div className="sm:col-span-6 flex items-center justify-between mb-2">
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
         </div>
         <p className="col-span-6 text-xs text-ink-muted -mt-4 mb-2">Automatic employer contribution regardless of employee deferral</p>

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
                     <div key={idx} className="flex items-center gap-3 text-sm">
                       <span className="text-ink-muted w-8">{idx + 1}.</span>
                       <input type="number" min={0} value={tier.minAge} onChange={(e) => {
                         const schedule = [...formData.dcCoreAgeSchedule];
                         schedule[idx] = { ...tier, minAge: Number(e.target.value) };
                         setFormData((prev: any) => ({ ...prev, dcCoreAgeSchedule: schedule }));
                       }} className="w-16 px-2 py-1 border border-border-strong rounded text-center" />
                       <span className="text-ink-muted">to</span>
                       <input type="number" min={0} value={tier.maxAge ?? ''} placeholder="∞" onChange={(e) => {
                         const schedule = [...formData.dcCoreAgeSchedule];
                         schedule[idx] = { ...tier, maxAge: e.target.value ? Number(e.target.value) : null };
                         setFormData((prev: any) => ({ ...prev, dcCoreAgeSchedule: schedule }));
                       }} className="w-16 px-2 py-1 border border-border-strong rounded text-center" />
                       <span className="text-ink-muted">age →</span>
                       <input type="number" min={0} step="0.5" value={tier.rate} onChange={(e) => {
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
                     <div key={idx} className="flex items-center gap-3 text-sm">
                       <span className="text-ink-muted w-8">{idx + 1}.</span>
                       <input
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
                       <input
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
                       <input
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
                    <div key={idx} className="flex items-center gap-3 text-sm">
                      <span className="text-ink-muted w-8">{idx + 1}.</span>
                      <input
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
                      <input
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
                      <input
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

             <InputField label="Min. Tenure" {...inputProps('dcCoreMinTenureYears')} type="number" suffix="Years" helper="Years of service required" min={0} />
             <InputField label="Min. Annual Hours" {...inputProps('dcCoreMinHoursAnnual')} type="number" suffix="Hours" helper="Hours worked per year" min={0} />

             <div className="sm:col-span-6 flex items-center">
               <input
                 type="checkbox"
                 id="dcCoreRequireYearEndActive"
                 checked={formData.dcCoreRequireYearEndActive}
                 onChange={(e) => {
                   const checked = e.target.checked;
                   setFormData(prev => ({
                     ...prev,
                     dcCoreRequireYearEndActive: checked,
                     dcCoreAllowTerminatedNewHires: !checked,
                     dcCoreAllowExperiencedTerminations: !checked,
                   }));
                 }}
                 className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-border-strong rounded"
               />
               <div className="ml-2">
                 <label htmlFor="dcCoreRequireYearEndActive" className="block text-sm text-ink-muted">Last Day Working Rule</label>
                 <p className="text-xs text-ink-muted">
                   {formData.dcCoreRequireYearEndActive
                     ? 'Enabled — only employees active at year-end receive core contributions'
                     : 'Disabled — terminated employees may still receive core contributions'}
                 </p>
               </div>
             </div>
           </>
         )}

         <div className="col-span-6 h-px bg-surface-disabled my-2"></div>
         <div className="sm:col-span-6 flex items-center justify-between mb-2">
             <h4 className="text-sm font-semibold text-ink">Auto-Escalation</h4>
             <label htmlFor="dcplan-auto-escalation" className="flex items-center">
                 <input id="dcplan-auto-escalation" type="checkbox" name="dcAutoEscalation" checked={formData.dcAutoEscalation} onChange={(e) => {
                  const checked = e.target.checked;
                  setFormData(prev => ({
                    ...prev,
                    dcAutoEscalation: checked,
                    // Auto-populate hire date cutoff with 1/1 of the simulation start year
                    ...(checked && !prev.dcEscalationHireDateCutoff ? { dcEscalationHireDateCutoff: `${prev.startYear}-01-01` } : {}),
                  }));
                }} className="h-4 w-4 text-fidelity-green rounded" />
                 <span className="ml-2 text-sm text-ink-muted">Enabled</span>
             </label>
         </div>
         {formData.dcAutoEscalation && (
           <>
             <InputField label="Annual Increase" {...inputProps('dcEscalationRate')} type="number" step="0.5" suffix="%" helper="Yearly step-up" />
             <InputField label="Escalation Cap" {...inputProps('dcEscalationCap')} type="number" suffix="%" helper="Max deferral rate" />
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
             <InputField label="First Escalation Delay" {...inputProps('dcEscalationDelayYears')} type="number" suffix="Years" helper="Wait after enrollment" min={0} />
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
      </div>
    </div>
  );
}
