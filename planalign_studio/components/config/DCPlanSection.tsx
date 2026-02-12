import { Info, X } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { InputField } from './InputField';
import { MATCH_TEMPLATES, calculateMatchCap } from './constants';

function validateMatchTiers(
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
  const { formData, setFormData, handleChange, inputProps } = useConfigContext();

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-gray-100 pb-4">
        <h2 className="text-lg font-bold text-gray-900">401(k) / DC Plan Config</h2>
        <p className="text-sm text-gray-500">Configure retirement plan eligibility, matching rules, and vesting.</p>
      </div>

      <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6">
         <div className="sm:col-span-6 bg-green-50 p-4 rounded-lg border border-green-100 mb-2 flex items-start">
            <input
                 type="checkbox"
                 name="dcAutoEnroll"
                 checked={formData.dcAutoEnroll}
                 onChange={handleChange}
                 className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300 rounded mt-1"
            />
            <div className="ml-3">
               <label className="block text-sm font-medium text-green-900">Enable Auto-Enrollment</label>
               <p className="text-xs text-green-700 mt-0.5">New hires will be automatically enrolled upon eligibility.</p>
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
               <label className="block text-sm font-medium text-gray-700">Enrollment Scope</label>
               <select
                 name="dcAutoEnrollScope"
                 value={formData.dcAutoEnrollScope}
                 onChange={handleChange}
                 className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
               >
                 <option value="new_hires_only">New Hires Only</option>
                 <option value="all_eligible">All Eligible Employees</option>
               </select>
               <p className="mt-1 text-xs text-gray-500">Who gets auto-enrolled</p>
             </div>
             <div className="sm:col-span-3">
               <label className="block text-sm font-medium text-gray-700">Hire Date Cutoff</label>
               <input
                 type="date"
                 name="dcAutoEnrollHireDateCutoff"
                 value={formData.dcAutoEnrollHireDateCutoff}
                 onChange={handleChange}
                 className="mt-1 block w-full pl-3 pr-3 py-2 text-base border-gray-300 focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
               />
               <p className="mt-1 text-xs text-gray-500">Auto-enroll employees hired on/after this date</p>
             </div>
           </>
         )}

         <div className="col-span-6 h-px bg-gray-200 my-2"></div>
         <h4 className="col-span-6 text-sm font-semibold text-gray-900">Employer Match Formula</h4>

         {/* E046: Match Mode Selector */}
         <div className="sm:col-span-3">
           <label className="block text-sm font-medium text-gray-700">Match Calculation Mode</label>
           <select
             value={formData.dcMatchMode}
             onChange={(e) => setFormData(prev => ({ ...prev, dcMatchMode: e.target.value as any }))}
             className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
           >
             <option value="deferral_based">Deferral-Based (match varies by deferral %)</option>
             <option value="graded_by_service">Graded by Service (existing service tiers)</option>
             <option value="tenure_based">Tenure-Based (match varies by years of service)</option>
             <option value="points_based">Points-Based (match varies by age + tenure points)</option>
           </select>
           <p className="mt-1 text-xs text-gray-500">
             {formData.dcMatchMode === 'tenure_based' && 'Match rate increases with employee years of service'}
             {formData.dcMatchMode === 'points_based' && 'Points = FLOOR(age) + FLOOR(tenure). Higher points = higher match'}
             {formData.dcMatchMode === 'deferral_based' && 'Traditional: match rate varies by employee deferral percentage'}
             {formData.dcMatchMode === 'graded_by_service' && 'Uses existing graded-by-service schedule'}
           </p>
         </div>

         {/* E046: Tenure-Based Tier Editor */}
         {formData.dcMatchMode === 'tenure_based' && (
           <div className="sm:col-span-6 bg-gray-50 p-4 rounded-lg border border-gray-200">
             <label className="block text-sm font-medium text-gray-700 mb-3">Tenure Match Tiers</label>
             <div className="space-y-2">
               {formData.dcTenureMatchTiers.map((tier, idx) => (
                 <div key={idx} className="flex items-center gap-2 bg-white p-2 rounded border border-gray-200">
                   <span className="text-xs text-gray-500 w-4">{idx + 1}.</span>
                   <input type="number" min={0} value={tier.minYears}
                     onChange={(e) => {
                       const newTiers = [...formData.dcTenureMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], minYears: parseInt(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcTenureMatchTiers: newTiers }));
                     }}
                     className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-gray-600">to</span>
                   <input type="number" min={0} value={tier.maxYears ?? ''}
                     placeholder="&#8734;"
                     onChange={(e) => {
                       const newTiers = [...formData.dcTenureMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], maxYears: e.target.value === '' ? null : parseInt(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcTenureMatchTiers: newTiers }));
                     }}
                     className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-gray-600">yrs &#8594;</span>
                   <input type="number" step="5" min={0} max={200} value={tier.matchRate}
                     onChange={(e) => {
                       const newTiers = [...formData.dcTenureMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], matchRate: parseFloat(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcTenureMatchTiers: newTiers }));
                     }}
                     className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-gray-600">% match, max</span>
                   <input type="number" step="1" min={0} max={100} value={tier.maxDeferralPct}
                     onChange={(e) => {
                       const newTiers = [...formData.dcTenureMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], maxDeferralPct: parseFloat(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcTenureMatchTiers: newTiers }));
                     }}
                     className="w-14 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-gray-600">% def</span>
                   {formData.dcTenureMatchTiers.length > 1 && (
                     <button type="button"
                       onClick={() => {
                         const newTiers = formData.dcTenureMatchTiers.filter((_, i) => i !== idx);
                         setFormData(prev => ({ ...prev, dcTenureMatchTiers: newTiers }));
                       }}
                       className="ml-auto text-red-500 hover:text-red-700 p-1"
                     ><X size={16} /></button>
                   )}
                 </div>
               ))}
             </div>
             <button type="button"
               onClick={() => {
                 const last = formData.dcTenureMatchTiers[formData.dcTenureMatchTiers.length - 1];
                 const newMin = last ? (last.maxYears ?? last.minYears + 5) : 0;
                 const updatedTiers = [...formData.dcTenureMatchTiers];
                 if (last && last.maxYears === null) {
                   updatedTiers[updatedTiers.length - 1] = { ...last, maxYears: newMin };
                 }
                 const newTier = { minYears: newMin, maxYears: null, matchRate: 100, maxDeferralPct: 6 };
                 setFormData(prev => ({ ...prev, dcTenureMatchTiers: [...updatedTiers, newTier] }));
               }}
               className="mt-3 text-sm text-fidelity-green hover:text-green-700 flex items-center gap-1"
             >+ Add Tier</button>
             {formData.dcTenureMatchTiers.length === 0 && (
               <p className="mt-2 text-xs text-amber-600">Add at least one tier to configure tenure-based matching</p>
             )}
             {/* E046: Tenure tier gap/overlap warnings */}
             {(() => {
               const warnings = validateMatchTiers(
                 formData.dcTenureMatchTiers.map(t => ({ min: t.minYears, max: t.maxYears })),
                 'tenure years',
               );
               return warnings.length > 0 ? (
                 <div className="mt-3 bg-amber-50 border border-amber-300 rounded-md p-3">
                   <p className="text-xs font-medium text-amber-800 mb-1">Tier configuration warnings:</p>
                   <ul className="list-disc list-inside space-y-0.5">
                     {warnings.map((w, i) => (
                       <li key={i} className="text-xs text-amber-700">{w}</li>
                     ))}
                   </ul>
                   <p className="text-xs text-amber-600 mt-1.5">Tiers use [min, max) intervals — min is inclusive, max is exclusive.</p>
                 </div>
               ) : null;
             })()}
           </div>
         )}

         {/* E046: Points-Based Tier Editor */}
         {formData.dcMatchMode === 'points_based' && (
           <div className="sm:col-span-6 bg-gray-50 p-4 rounded-lg border border-gray-200">
             <label className="block text-sm font-medium text-gray-700 mb-1">Points Match Tiers</label>
             <p className="text-xs text-gray-500 mb-3">Points = FLOOR(age) + FLOOR(years of service). Uses [min, max) intervals.</p>
             <div className="space-y-2">
               {formData.dcPointsMatchTiers.map((tier, idx) => (
                 <div key={idx} className="flex items-center gap-2 bg-white p-2 rounded border border-gray-200">
                   <span className="text-xs text-gray-500 w-4">{idx + 1}.</span>
                   <input type="number" min={0} value={tier.minPoints}
                     onChange={(e) => {
                       const newTiers = [...formData.dcPointsMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], minPoints: parseInt(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                     }}
                     className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-gray-600">to</span>
                   <input type="number" min={0} value={tier.maxPoints ?? ''}
                     placeholder="&#8734;"
                     onChange={(e) => {
                       const newTiers = [...formData.dcPointsMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], maxPoints: e.target.value === '' ? null : parseInt(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                     }}
                     className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-gray-600">pts &#8594;</span>
                   <input type="number" step="5" min={0} max={200} value={tier.matchRate}
                     onChange={(e) => {
                       const newTiers = [...formData.dcPointsMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], matchRate: parseFloat(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                     }}
                     className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-gray-600">% match, max</span>
                   <input type="number" step="1" min={0} max={100} value={tier.maxDeferralPct}
                     onChange={(e) => {
                       const newTiers = [...formData.dcPointsMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], maxDeferralPct: parseFloat(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                     }}
                     className="w-14 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-gray-600">% def</span>
                   {formData.dcPointsMatchTiers.length > 1 && (
                     <button type="button"
                       onClick={() => {
                         const newTiers = formData.dcPointsMatchTiers.filter((_, i) => i !== idx);
                         setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                       }}
                       className="ml-auto text-red-500 hover:text-red-700 p-1"
                     ><X size={16} /></button>
                   )}
                 </div>
               ))}
             </div>
             <button type="button"
               onClick={() => {
                 const last = formData.dcPointsMatchTiers[formData.dcPointsMatchTiers.length - 1];
                 const newMin = last ? (last.maxPoints ?? last.minPoints + 10) : 0;
                 const updatedTiers = [...formData.dcPointsMatchTiers];
                 if (last && last.maxPoints === null) {
                   updatedTiers[updatedTiers.length - 1] = { ...last, maxPoints: newMin };
                 }
                 const newTier = { minPoints: newMin, maxPoints: null, matchRate: 100, maxDeferralPct: 6 };
                 setFormData(prev => ({ ...prev, dcPointsMatchTiers: [...updatedTiers, newTier] }));
               }}
               className="mt-3 text-sm text-fidelity-green hover:text-green-700 flex items-center gap-1"
             >+ Add Tier</button>
             {formData.dcPointsMatchTiers.length === 0 && (
               <p className="mt-2 text-xs text-amber-600">Add at least one tier to configure points-based matching</p>
             )}
             {/* E046: Points tier gap/overlap warnings */}
             {(() => {
               const warnings = validateMatchTiers(
                 formData.dcPointsMatchTiers.map(t => ({ min: t.minPoints, max: t.maxPoints })),
                 'points',
               );
               return warnings.length > 0 ? (
                 <div className="mt-3 bg-amber-50 border border-amber-300 rounded-md p-3">
                   <p className="text-xs font-medium text-amber-800 mb-1">Tier configuration warnings:</p>
                   <ul className="list-disc list-inside space-y-0.5">
                     {warnings.map((w, i) => (
                       <li key={i} className="text-xs text-amber-700">{w}</li>
                     ))}
                   </ul>
                   <p className="text-xs text-amber-600 mt-1.5">Tiers use [min, max) intervals — min is inclusive, max is exclusive.</p>
                 </div>
               ) : null;
             })()}
           </div>
         )}

         {/* E084 Phase B: Template selector + editable tiers (only for deferral_based mode) */}
         {formData.dcMatchMode === 'deferral_based' && (
         <div className="sm:col-span-3">
           <label className="block text-sm font-medium text-gray-700">Start from Template</label>
           <select
             value={formData.dcMatchTemplate}
             onChange={(e) => {
               const templateKey = e.target.value as 'simple' | 'tiered' | 'stretch' | 'safe_harbor' | 'qaca';
               const template = MATCH_TEMPLATES[templateKey];
               if (template) {
                 setFormData(prev => ({
                   ...prev,
                   dcMatchTemplate: templateKey,
                   dcMatchTiers: template.tiers.map(t => ({ ...t })),
                 }));
               }
             }}
             className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
           >
             {Object.entries(MATCH_TEMPLATES).map(([key, t]) => (
               <option key={key} value={key}>{t.name}</option>
             ))}
           </select>
           <p className="mt-1 text-xs text-gray-500">Select a template, then customize tiers below</p>
         </div>
         )}

         {formData.dcMatchMode === 'deferral_based' && (<>
         <div className="sm:col-span-3">
           <label className="block text-sm font-medium text-gray-700">Max Employer Match</label>
           <div className="mt-1 bg-gray-100 rounded-md p-2 border border-gray-200">
             <span className="text-lg font-semibold text-gray-900">
               {(calculateMatchCap(formData.dcMatchTiers) * 100).toFixed(1)}%
             </span>
             <span className="text-sm text-gray-500 ml-1">of compensation</span>
           </div>
           <p className="mt-1 text-xs text-gray-500">Auto-calculated from tiers below</p>
         </div>

         {/* Editable Match Tiers */}
         <div className="sm:col-span-6 bg-gray-50 p-4 rounded-lg border border-gray-200">
           <label className="block text-sm font-medium text-gray-700 mb-3">Match Tiers (editable)</label>
           <div className="space-y-2">
             {formData.dcMatchTiers.map((tier, idx) => (
               <div key={idx} className="flex items-center gap-2 bg-white p-2 rounded border border-gray-200">
                 <span className="text-xs text-gray-500 w-4">{idx + 1}.</span>
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
                   className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                 />
                 <span className="text-sm text-gray-600">% to</span>
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
                   className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                 />
                 <span className="text-sm text-gray-600">% deferrals &#8594;</span>
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
                   className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                 />
                 <span className="text-sm text-gray-600">% match</span>
                 {formData.dcMatchTiers.length > 1 && (
                   <button
                     type="button"
                     onClick={() => {
                       const newTiers = formData.dcMatchTiers.filter((_, i) => i !== idx);
                       setFormData(prev => ({ ...prev, dcMatchTiers: newTiers }));
                     }}
                     className="ml-auto text-red-500 hover:text-red-700 p-1"
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
             className="mt-3 text-sm text-fidelity-green hover:text-green-700 flex items-center gap-1"
           >
             + Add Tier
           </button>
         </div>

         {/* Safe Harbor Notice */}
         {(formData.dcMatchTemplate === 'safe_harbor' || formData.dcMatchTemplate === 'qaca') && (
           <div className="col-span-6 bg-blue-50 border border-blue-200 p-3 rounded-lg flex items-start gap-2">
             <Info size={16} className="text-blue-600 mt-0.5 flex-shrink-0" />
             <div>
               <p className="text-sm text-blue-800 font-medium">Safe Harbor Plan Selected</p>
               <p className="text-xs text-blue-700 mt-1">
                 {formData.dcMatchTemplate === 'safe_harbor'
                   ? 'Safe Harbor Basic: 100% match on first 3% + 50% match on next 2%. Satisfies ADP/ACP nondiscrimination tests.'
                   : 'QACA Safe Harbor: 100% match on first 1% + 50% match on next 5%. Includes automatic enrollment requirements.'}
               </p>
             </div>
           </div>
         )}
         </>)}

         {/* E084: Match Eligibility Section */}
         <div className="col-span-6 h-px bg-gray-200 my-2"></div>
         <h4 className="col-span-6 text-sm font-semibold text-gray-900">Match Eligibility Requirements</h4>
         <p className="col-span-6 text-xs text-gray-500 -mt-4 mb-2">Configure who qualifies for employer match contributions</p>

         <InputField label="Min. Tenure" {...inputProps('dcMatchMinTenureYears')} type="number" suffix="Years" helper="Years of service required" min={0} />
         <InputField label="Min. Annual Hours" {...inputProps('dcMatchMinHoursAnnual')} type="number" suffix="Hours" helper="Hours worked per year" min={0} />

         <div className="sm:col-span-3 flex items-center">
           <input
             type="checkbox"
             name="dcMatchRequireYearEndActive"
             checked={formData.dcMatchRequireYearEndActive}
             onChange={handleChange}
             className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300 rounded"
           />
           <label className="ml-2 block text-sm text-gray-700">Require Active at Year-End</label>
         </div>

         <div className="sm:col-span-3 flex items-center">
           <input
             type="checkbox"
             name="dcMatchAllowTerminatedNewHires"
             checked={formData.dcMatchAllowTerminatedNewHires}
             onChange={handleChange}
             className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300 rounded"
           />
           <label className="ml-2 block text-sm text-gray-700">Allow Terminated New Hires</label>
         </div>

         <div className="sm:col-span-3 flex items-center">
           <input
             type="checkbox"
             name="dcMatchAllowExperiencedTerminations"
             checked={formData.dcMatchAllowExperiencedTerminations}
             onChange={handleChange}
             className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300 rounded"
           />
           <label className="ml-2 block text-sm text-gray-700">Allow Experienced Terminations</label>
         </div>

         {/* E084: Core Contribution Section */}
         <div className="col-span-6 h-px bg-gray-200 my-2"></div>
         <div className="sm:col-span-6 flex items-center justify-between mb-2">
           <h4 className="text-sm font-semibold text-gray-900">Employer Core (Non-Elective) Contribution</h4>
           <div className="flex items-center">
             <input
               type="checkbox"
               name="dcCoreEnabled"
               checked={formData.dcCoreEnabled}
               onChange={handleChange}
               className="h-4 w-4 text-fidelity-green rounded"
             />
             <span className="ml-2 text-sm text-gray-600">Enabled</span>
           </div>
         </div>
         <p className="col-span-6 text-xs text-gray-500 -mt-4 mb-2">Automatic employer contribution regardless of employee deferral</p>

         {formData.dcCoreEnabled && (
           <>
             {/* E084: Core Contribution Type */}
             <div className="sm:col-span-3">
               <label className="block text-sm font-medium text-gray-700">Contribution Type</label>
               <select
                 name="dcCoreStatus"
                 value={formData.dcCoreStatus}
                 onChange={handleChange}
                 className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
               >
                 <option value="flat">Flat Rate (same for all)</option>
                 <option value="graded_by_service">Graded by Service (increases with tenure)</option>
               </select>
             </div>

             {/* Flat rate input */}
             {formData.dcCoreStatus === 'flat' && (
               <InputField label="Core Rate" {...inputProps('dcCoreContributionRate')} type="number" step="0.5" suffix="%" helper="% of compensation" min={0} />
             )}

             {/* E084: Graded Schedule Editor */}
             {formData.dcCoreStatus === 'graded_by_service' && (
               <div className="sm:col-span-6 bg-gray-50 p-4 rounded-lg border border-gray-200">
                 <label className="block text-sm font-medium text-gray-700 mb-3">Graded Core Schedule</label>
                 <div className="space-y-2">
                   {formData.dcCoreGradedSchedule.map((tier: any, idx: number) => (
                     <div key={idx} className="flex items-center gap-3 text-sm">
                       <span className="text-gray-500 w-8">{idx + 1}.</span>
                       <input
                         type="number"
                         value={tier.serviceYearsMin}
                         onChange={(e) => {
                           const newSchedule = [...formData.dcCoreGradedSchedule];
                           newSchedule[idx] = { ...tier, serviceYearsMin: Number(e.target.value) };
                           setFormData((prev: any) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
                         }}
                         className="w-16 px-2 py-1 border border-gray-300 rounded text-center"
                         min={0}
                       />
                       <span className="text-gray-500">to</span>
                       <input
                         type="number"
                         value={tier.serviceYearsMax ?? ''}
                         placeholder="&#8734;"
                         onChange={(e) => {
                           const newSchedule = [...formData.dcCoreGradedSchedule];
                           newSchedule[idx] = { ...tier, serviceYearsMax: e.target.value ? Number(e.target.value) : null };
                           setFormData((prev: any) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
                         }}
                         className="w-16 px-2 py-1 border border-gray-300 rounded text-center"
                         min={0}
                       />
                       <span className="text-gray-500">years &#8594;</span>
                       <input
                         type="number"
                         value={tier.rate}
                         onChange={(e) => {
                           const newSchedule = [...formData.dcCoreGradedSchedule];
                           newSchedule[idx] = { ...tier, rate: Number(e.target.value) };
                           setFormData((prev: any) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
                         }}
                         step="0.5"
                         className="w-20 px-2 py-1 border border-gray-300 rounded text-center"
                         min={0}
                       />
                       <span className="text-gray-500">%</span>
                       {formData.dcCoreGradedSchedule.length > 1 && (
                         <button
                           type="button"
                           onClick={() => {
                             const newSchedule = formData.dcCoreGradedSchedule.filter((_: any, i: number) => i !== idx);
                             setFormData((prev: any) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
                           }}
                           className="text-red-500 hover:text-red-700 px-2"
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
                     const newMin = (lastTier?.serviceYearsMax ?? lastTier?.serviceYearsMin ?? 0) + 1;
                     const newSchedule = [
                       ...formData.dcCoreGradedSchedule,
                       { serviceYearsMin: newMin, serviceYearsMax: null, rate: (lastTier?.rate ?? 1) + 1 }
                     ];
                     setFormData((prev: any) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
                   }}
                   className="mt-3 text-sm text-fidelity-green hover:text-green-700 font-medium"
                 >
                   + Add Tier
                 </button>
               </div>
             )}

             <InputField label="Min. Tenure" {...inputProps('dcCoreMinTenureYears')} type="number" suffix="Years" helper="Years of service required" min={0} />
             <InputField label="Min. Annual Hours" {...inputProps('dcCoreMinHoursAnnual')} type="number" suffix="Hours" helper="Hours worked per year" min={0} />

             <div className="sm:col-span-3 flex items-center">
               <input
                 type="checkbox"
                 name="dcCoreRequireYearEndActive"
                 checked={formData.dcCoreRequireYearEndActive}
                 onChange={handleChange}
                 className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300 rounded"
               />
               <label className="ml-2 block text-sm text-gray-700">Require Active at Year-End</label>
             </div>

             <div className="sm:col-span-3 flex items-center">
               <input
                 type="checkbox"
                 name="dcCoreAllowTerminatedNewHires"
                 checked={formData.dcCoreAllowTerminatedNewHires}
                 onChange={handleChange}
                 className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300 rounded"
               />
               <label className="ml-2 block text-sm text-gray-700">Allow Terminated New Hires</label>
             </div>

             <div className="sm:col-span-3 flex items-center">
               <input
                 type="checkbox"
                 name="dcCoreAllowExperiencedTerminations"
                 checked={formData.dcCoreAllowExperiencedTerminations}
                 onChange={handleChange}
                 className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300 rounded"
               />
               <label className="ml-2 block text-sm text-gray-700">Allow Experienced Terminations</label>
             </div>
           </>
         )}

         <div className="col-span-6 h-px bg-gray-200 my-2"></div>
         <div className="sm:col-span-6 flex items-center justify-between mb-2">
             <h4 className="text-sm font-semibold text-gray-900">Auto-Escalation</h4>
             <div className="flex items-center">
                 <input type="checkbox" name="dcAutoEscalation" checked={formData.dcAutoEscalation} onChange={handleChange} className="h-4 w-4 text-fidelity-green rounded" />
                 <span className="ml-2 text-sm text-gray-600">Enabled</span>
             </div>
         </div>
         {formData.dcAutoEscalation && (
           <>
             <InputField label="Annual Increase" {...inputProps('dcEscalationRate')} type="number" step="0.5" suffix="%" helper="Yearly step-up" />
             <InputField label="Escalation Cap" {...inputProps('dcEscalationCap')} type="number" suffix="%" helper="Max deferral rate" />
             <div className="sm:col-span-3">
               <label className="block text-sm font-medium text-gray-700">Effective Date (MM-DD)</label>
               <input
                 type="text"
                 name="dcEscalationEffectiveDay"
                 value={formData.dcEscalationEffectiveDay}
                 onChange={handleChange}
                 placeholder="01-01"
                 pattern="\d{2}-\d{2}"
                 className="mt-1 block w-full pl-3 pr-3 py-2 text-base border-gray-300 focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
               />
               <p className="mt-1 text-xs text-gray-500">Annual escalation date (e.g., 01-01 for Jan 1)</p>
             </div>
             <InputField label="First Escalation Delay" {...inputProps('dcEscalationDelayYears')} type="number" suffix="Years" helper="Wait after enrollment" min={0} />
             <div className="sm:col-span-3">
               <label className="block text-sm font-medium text-gray-700">Hire Date Cutoff</label>
               <input
                 type="date"
                 name="dcEscalationHireDateCutoff"
                 value={formData.dcEscalationHireDateCutoff}
                 onChange={handleChange}
                 className="mt-1 block w-full pl-3 pr-3 py-2 text-base border-gray-300 focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
               />
               <p className="mt-1 text-xs text-gray-500">Only escalate employees hired on/after this date</p>
             </div>
           </>
         )}
      </div>
    </div>
  );
}
