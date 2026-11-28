// Employer match formula editor, shared by the plan-wide design and the grandfathered new-hire design.
import { Info, X } from 'lucide-react';
import { NumericInput } from './NumericInput';
import { TenureGradedMatchEditor } from './TenureGradedMatchEditor';
import { MATCH_TEMPLATES, calculateMatchCap } from './constants';
import { tierSummary } from './DCPlanPanels';
import { validateMatchTiers } from './formulaValidation';
import type { FormScope, FormulaFieldsProps } from './formScope';

export function MatchFormulaControl({ scope }: { scope: FormScope }) {
  const { formData, handleChange } = scope;
  return <div className="flex items-center justify-between mb-2">
           <h4 className="text-sm font-semibold text-ink">Employer Match Formula</h4>
           <label htmlFor="dcplan-match-enabled" className="flex items-center">
             <input
               id="dcplan-match-enabled"
               type="checkbox"
               name="dcMatchEnabled"
               checked={formData.dcMatchEnabled}
               onChange={handleChange}
               className="h-4 w-4 text-brand-ink rounded"
             />
             <span className="ml-2 text-sm text-ink-muted">Enabled</span>
           </label>
         </div>;
}

export function MatchFormulaFields({ scope, idPrefix = 'dcplan', eligibility }: FormulaFieldsProps) {
  const { formData, setFormData } = scope;
  return <>
         <p className="sm:col-span-6 text-xs text-ink-muted -mt-4 mb-2">Configure employer matching contributions on employee deferrals</p>

         {formData.dcMatchEnabled && (<>
         {/* E046: Match Mode Selector */}
         <div className="sm:col-span-3">
           <label htmlFor={`${idPrefix}-match-mode`} className="block text-sm font-medium text-ink-muted">Match Calculation Mode</label>
           <select
             id={`${idPrefix}-match-mode`}
             value={formData.dcMatchMode}
             onChange={(e) => setFormData(prev => ({ ...prev, dcMatchMode: e.target.value }))}
             className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-border-strong focus:outline-none focus:ring-brand-green focus:border-brand-green sm:text-sm rounded-md border shadow-sm"
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
                     className="w-16 shadow-sm focus:ring-brand-green focus:border-brand-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-ink-muted">to</span>
                   <NumericInput integer allowEmpty type="number" min={0} value={tier.maxPoints ?? ''}
                     placeholder="&#8734;"
                     onChange={(e) => {
                       const newTiers = [...formData.dcPointsMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], maxPoints: e.target.value === '' ? null : parseInt(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                     }}
                     className="w-16 shadow-sm focus:ring-brand-green focus:border-brand-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-ink-muted">pts | 0% to</span>
                   <NumericInput type="number" step="1" min={0} max={100} value={tier.maxDeferralPct}
                     onChange={(e) => {
                       const newTiers = [...formData.dcPointsMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], maxDeferralPct: parseFloat(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                     }}
                     className="w-14 shadow-sm focus:ring-brand-green focus:border-brand-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
                   />
                   <span className="text-sm text-ink-muted">% deferrals &#8594;</span>
                   <NumericInput type="number" step="5" min={0} max={200} value={tier.matchRate}
                     onChange={(e) => {
                       const newTiers = [...formData.dcPointsMatchTiers];
                       newTiers[idx] = { ...newTiers[idx], matchRate: parseFloat(e.target.value) || 0 };
                       setFormData(prev => ({ ...prev, dcPointsMatchTiers: newTiers }));
                     }}
                     className="w-16 shadow-sm focus:ring-brand-green focus:border-brand-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
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
               className="mt-3 text-sm text-brand-ink hover:text-success-ink flex items-center gap-1"
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
           <label htmlFor={`${idPrefix}-match-template`} className="block text-sm font-medium text-ink-muted">Start from Template</label>
           <select
             id={`${idPrefix}-match-template`}
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
             className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-border-strong focus:outline-none focus:ring-brand-green focus:border-brand-green sm:text-sm rounded-md border shadow-sm"
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
                   className="w-16 shadow-sm focus:ring-brand-green focus:border-brand-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
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
                   className="w-16 shadow-sm focus:ring-brand-green focus:border-brand-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
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
                   className="w-16 shadow-sm focus:ring-brand-green focus:border-brand-green sm:text-sm border-border-strong rounded-md p-1 border text-center"
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
             className="mt-3 text-sm text-brand-ink hover:text-success-ink flex items-center gap-1"
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
         {eligibility}
         </>)}

  </>;
}
