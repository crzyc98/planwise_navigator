// Employer core formula editor, shared by the plan-wide design and the grandfathered new-hire design.
import { InputField } from './InputField';
import { NumericInput } from './NumericInput';
import { validateCoreIntegration, validateMatchTiers } from './formulaValidation';
import type { FormScope, FormulaFieldsProps } from './formScope';

export function CoreFormulaControl({ scope }: { scope: FormScope }) {
  const { formData, handleChange } = scope;
  return <div className="flex items-center justify-between mb-2">
           <h4 className="text-sm font-semibold text-ink">Employer Core (Non-Elective) Contribution</h4>
           <label htmlFor="dcplan-core-enabled" className="flex items-center">
             <input
               id="dcplan-core-enabled"
               type="checkbox"
               name="dcCoreEnabled"
               checked={formData.dcCoreEnabled}
               onChange={handleChange}
               className="h-4 w-4 text-brand-ink rounded"
             />
             <span className="ml-2 text-sm text-ink-muted">Enabled</span>
           </label>
         </div>;
}

export function CoreFormulaFields({ scope, idPrefix = 'dcplan', eligibility }: FormulaFieldsProps) {
  const { formData, setFormData, handleChange, inputProps } = scope;
  return <>
         <p className="sm:col-span-6 text-xs text-ink-muted -mt-4 mb-2">Automatic employer contribution regardless of employee deferral</p>

         {formData.dcCoreEnabled && (
           <>
             {/* E084: Core Contribution Type */}
             <div className="sm:col-span-3">
               <label htmlFor={`${idPrefix}-core-type`} className="block text-sm font-medium text-ink-muted">Contribution Type</label>
               <select
                 id={`${idPrefix}-core-type`}
                 name="dcCoreStatus"
                 value={formData.dcCoreStatus}
                 onChange={handleChange}
                 className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-border-strong focus:outline-none focus:ring-brand-green focus:border-brand-green sm:text-sm rounded-md border shadow-sm"
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
                         setFormData((prev) => ({ ...prev, dcCoreAgeSchedule: schedule }));
                       }} className="w-16 px-2 py-1 border border-border-strong rounded text-center" />
                       <span className="text-ink-muted">to</span>
                       <NumericInput allowEmpty type="number" min={0} value={tier.maxAge ?? ''} placeholder="∞" onChange={(e) => {
                         const schedule = [...formData.dcCoreAgeSchedule];
                         schedule[idx] = { ...tier, maxAge: e.target.value ? Number(e.target.value) : null };
                         setFormData((prev) => ({ ...prev, dcCoreAgeSchedule: schedule }));
                       }} className="w-16 px-2 py-1 border border-border-strong rounded text-center" />
                       <span className="text-ink-muted">age →</span>
                       <NumericInput type="number" min={0} step="0.5" value={tier.rate} onChange={(e) => {
                         const schedule = [...formData.dcCoreAgeSchedule];
                         schedule[idx] = { ...tier, rate: Number(e.target.value) };
                         setFormData((prev) => ({ ...prev, dcCoreAgeSchedule: schedule }));
                       }} className="w-20 px-2 py-1 border border-border-strong rounded text-center" />
                       <span className="text-ink-muted">%</span>
                       {formData.dcCoreAgeSchedule.length > 1 && <button type="button" onClick={() => setFormData((prev) => ({ ...prev, dcCoreAgeSchedule: prev.dcCoreAgeSchedule.filter((_, i) => i !== idx) }))} className="text-danger-ink hover:text-danger-ink px-2">✕</button>}
                     </div>
                   ))}
                 </div>
                 <button type="button" onClick={() => {
                   const last = formData.dcCoreAgeSchedule[formData.dcCoreAgeSchedule.length - 1];
                   const newMin = last?.maxAge ?? ((last?.minAge ?? 0) + 10);
                   const schedule = last?.maxAge === null
                     ? [...formData.dcCoreAgeSchedule.slice(0, -1), { ...last, maxAge: newMin }]
                     : [...formData.dcCoreAgeSchedule];
                   setFormData((prev) => ({ ...prev, dcCoreAgeSchedule: [...schedule, { minAge: newMin, maxAge: null, rate: last?.rate ?? 1 }] }));
                 }} className="mt-3 text-sm text-brand-ink hover:text-success-ink font-medium">+ Add Tier</button>
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
                   {formData.dcCoreGradedSchedule.map((tier, idx) => (
                     <div key={idx} className="flex flex-wrap items-center gap-3 text-sm">
                       <span className="text-ink-muted w-8">{idx + 1}.</span>
                       <NumericInput allowEmpty
                         type="number"
                         value={tier.serviceYearsMin}
                         onChange={(e) => {
                           const newSchedule = [...formData.dcCoreGradedSchedule];
                           newSchedule[idx] = { ...tier, serviceYearsMin: Number(e.target.value) };
                           setFormData((prev) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
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
                           setFormData((prev) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
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
                           setFormData((prev) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
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
                             const newSchedule = formData.dcCoreGradedSchedule.filter((_, i) => i !== idx);
                             setFormData((prev) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
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
                     setFormData((prev) => ({ ...prev, dcCoreGradedSchedule: newSchedule }));
                   }}
                   className="mt-3 text-sm text-brand-ink hover:text-success-ink font-medium"
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
                          setFormData((prev) => ({ ...prev, dcCorePointsSchedule: newSchedule }));
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
                          setFormData((prev) => ({ ...prev, dcCorePointsSchedule: newSchedule }));
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
                          setFormData((prev) => ({ ...prev, dcCorePointsSchedule: newSchedule }));
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
                            const newSchedule = formData.dcCorePointsSchedule.filter((_, i) => i !== idx);
                            setFormData((prev) => ({ ...prev, dcCorePointsSchedule: newSchedule }));
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
                    setFormData((prev) => ({ ...prev, dcCorePointsSchedule: newSchedule }));
                  }}
                  className="mt-3 text-sm text-brand-ink hover:text-success-ink font-medium"
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
                {/* Optional service minimum: a flat rate until whole years of service reach it. */}
                <label className="mt-4 flex items-center gap-2 text-sm font-medium text-ink-muted">
                  <input
                    type="checkbox"
                    name="dcCorePointsMinServiceEnabled"
                    checked={formData.dcCorePointsMinServiceEnabled}
                    onChange={handleChange}
                    className="h-4 w-4 text-brand-ink border-border-strong rounded focus:ring-brand-green"
                  />
                  Flat rate until a minimum service
                </label>
                {formData.dcCorePointsMinServiceEnabled && (
                  <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
                    <InputField label="Years of service" {...inputProps('dcCorePointsMinServiceYears')} type="number" step="1" min={1} suffix="years" />
                    <InputField label="Rate before that" {...inputProps('dcCorePointsPreServiceRate')} type="number" step="0.5" min={0} suffix="%" />
                    <p className="sm:col-span-3 text-xs text-ink-muted">
                      Employees below the minimum get the flat rate and the points table applies from then on;
                      service is whole years from hire date, and one rate applies for the whole year.
                    </p>
                  </div>
                )}
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
                   className="h-4 w-4 text-brand-ink border-border-strong rounded focus:ring-brand-green"
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
                     <label htmlFor={`${idPrefix}-core-integration-mode`} className="block text-sm font-medium text-ink-muted">Integration Level</label>
                     <select
                       id={`${idPrefix}-core-integration-mode`}
                       name="dcCoreIntegrationLevelMode"
                       value={formData.dcCoreIntegrationLevelMode}
                       onChange={handleChange}
                       className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-border-strong focus:outline-none focus:ring-brand-green focus:border-brand-green sm:text-sm rounded-md border shadow-sm"
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
         {eligibility}
           </>
         )}

  </>;
}
