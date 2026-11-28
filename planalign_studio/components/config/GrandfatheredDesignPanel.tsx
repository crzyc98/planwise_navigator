// Advanced: give employees hired on or after a date their own match and/or core
// formula, inside one simulation (#646). Everything else stays plan-wide.
import { Info } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { CoreFormulaFields } from './CoreFormulaFields';
import { MatchFormulaFields } from './MatchFormulaFields';
import type { FormScope } from './formScope';
import { hasSavedDesigns, inheritedDesignIds, mergedDesignConfig, newGrandfatheredDesign, newHireFormula } from './grandfatheredDesign';
import { coreFormulaSummary, matchFormulaSummary } from './grandfatheredDesignSummary';
import { grandfatheredDesignErrors } from './grandfatheredDesignValidation';
import { newHireScope } from './newHireScope';
import type { FormData, GrandfatheredDesignForm } from './types';

const TURN_OFF_CONFIRM = 'Turn off the grandfathered design?\n\nWhen you save, the new-hire design and its hire-date cutoff are removed from this configuration, and everyone uses the plan on this page. Your entries stay on this page until you save or leave.';
const FIELD = 'mt-1 block w-full px-3 py-2 text-base border-border-strong focus:outline-none focus:ring-brand-green focus:border-brand-green sm:text-sm rounded-md border shadow-sm';

type Update = (changes: Partial<GrandfatheredDesignForm>) => void;

function useDesignUpdate(): Update {
  const { setFormData } = useConfigContext();
  return changes => setFormData(previous => previous.dcGrandfather
    ? { ...previous, dcGrandfather: { ...previous.dcGrandfather, ...changes } } : previous);
}

/** Saved designs Studio can't edit here: kept exactly as saved. */
export function useLockedDesigns(): boolean {
  const { formData, workspaceConfig, originalConfig, scenarioId } = useConfigContext();
  return !formData.dcGrandfather && hasSavedDesigns(mergedDesignConfig(workspaceConfig, scenarioId ? originalConfig : undefined));
}

export function GrandfatheredDesignControl() {
  const { formData, savedFormData, setFormData } = useConfigContext();
  const locked = useLockedDesigns();
  const design = formData.dcGrandfather;
  const toggle = (on: boolean) => {
    const saved = design?.savedActive || savedFormData?.dcGrandfather?.enabled;
    if (!on && saved && !window.confirm(TURN_OFF_CONFIRM)) return;
    // Once a saved setup is turned off, saving clears it (also when inherited from the workspace).
    setFormData(previous => ({ ...previous, dcGrandfather: previous.dcGrandfather
      ? { ...previous.dcGrandfather, enabled: on, savedActive: previous.dcGrandfather.savedActive || Boolean(saved) }
      : newGrandfatheredDesign(previous) }));
  };
  return <div className="flex items-center justify-between mb-2">
    <h4 className="text-sm font-semibold text-ink">Grandfathered Plan Design</h4>
    <label htmlFor="dcplan-grandfather-enabled" className="flex items-center">
      <input id="dcplan-grandfather-enabled" type="checkbox" checked={Boolean(design?.enabled)} disabled={locked}
        onChange={event => toggle(event.target.checked)} className="h-4 w-4 text-brand-ink rounded disabled:opacity-50" />
      <span className="ml-2 text-sm text-ink-muted">Enabled</span>
    </label>
  </div>;
}

function Explainer() {
  return <div className="sm:col-span-6 space-y-3 text-xs text-ink-muted">
    <p>Runs two plan designs in one simulation. Employees hired before the cutoff keep the plan on this page.
      Employees hired on or after it get a different employer match, core contribution, or both. Each employee
      keeps their design in every year. Eligibility rules, automatic enrollment, automatic increases and
      employee behavior assumptions are the same for both designs.</p>
    <div className="bg-info-surface border border-info-border p-3 rounded-lg flex items-start gap-2">
      <Info size={16} className="text-info-ink mt-0.5 flex-shrink-0" />
      <p className="text-info-ink"><strong>Not the same as Cost Comparison.</strong> Its “Grandfather existing employees” option
        combines results from two runs you have already completed. This setting runs both designs inside one simulation.</p>
    </div>
  </div>;
}

function DesignSplitFields({ design, update }: { design: GrandfatheredDesignForm; update: Update }) {
  const names = [
    ['existingDesignId', 'Existing-employee design name', 'dcplan-grandfather-existing-id'],
    ['newHireDesignId', 'New-hire design name', 'dcplan-grandfather-new-id'],
  ] as const;
  return <>
    <div className="sm:col-span-2">
      <label htmlFor="dcplan-grandfather-cutoff" className="block text-sm font-medium text-ink-muted">Hire-date cutoff</label>
      <input id="dcplan-grandfather-cutoff" type="date" value={design.cutoff} onChange={event => update({ cutoff: event.target.value })} className={FIELD} />
      <p className="mt-1 text-xs text-ink-muted">Employees hired on or after this date get the new-hire design.</p>
    </div>
    {names.map(([key, label, id]) => <div key={key} className="sm:col-span-2">
      <label htmlFor={id} className="block text-sm font-medium text-ink-muted">{label}</label>
      <input id={id} type="text" value={design[key]} onChange={event => update({ [key]: event.target.value })} className={FIELD} />
      <p className="mt-1 text-xs text-ink-muted">Shown as the plan design in results.</p>
    </div>)}
  </>;
}

function DesignChangeChoices({ design, update }: { design: GrandfatheredDesignForm; update: Update }) {
  const choices = [['changeMatch', 'Employer match'], ['changeCore', 'Employer core contribution']] as const;
  return <fieldset className="sm:col-span-6">
    <legend className="text-sm font-medium text-ink-muted">What is different for new hires</legend>
    <div className="mt-2 flex flex-wrap gap-6">
      {choices.map(([key, label]) => <label key={key} htmlFor={`dcplan-grandfather-${key}`} className="flex items-center gap-2 text-sm text-ink">
        <input id={`dcplan-grandfather-${key}`} type="checkbox" checked={design[key]} onChange={event => update({ [key]: event.target.checked })} className="h-4 w-4 text-brand-ink rounded" />
        {label}
      </label>)}
    </div>
    <p className="mt-1 text-xs text-ink-muted">Anything not checked stays the same as for existing employees.</p>
  </fieldset>;
}

function NewHireEditor({ kind, scope, active }: { kind: 'match' | 'core'; scope: FormScope; active: boolean }) {
  const title = kind === 'match' ? 'New-hire employer match' : 'New-hire employer core contribution';
  return <div className="sm:col-span-6 rounded-lg border border-border p-4">
    <h5 className="text-sm font-semibold text-ink mb-4">{title}</h5>
    {active
      ? <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6 min-w-0">
        {kind === 'match'
          ? <MatchFormulaFields scope={scope} idPrefix="dcplan-newhire" />
          : <CoreFormulaFields scope={scope} idPrefix="dcplan-newhire" />}
      </div>
      : <p className="text-xs text-ink-muted">The employer {kind === 'match' ? 'match' : 'core contribution'} is off for this plan. Turn it on above to set one for new hires.</p>}
  </div>;
}

function CohortPreview({ form, design }: { form: FormData; design: GrandfatheredDesignForm }) {
  const newHire = newHireFormula(form, design);
  const cutoff = design.cutoff || 'the cutoff';
  const match = (text: string) => (form.dcMatchEnabled ? text : 'Off');
  const core = (text: string) => (form.dcCoreEnabled ? text : 'Off');
  const rows = [
    { who: `Hired before ${cutoff}`, id: design.existingDesignId, match: match(matchFormulaSummary(form)), core: core(coreFormulaSummary(form)) },
    { who: `Hired on or after ${cutoff}`, id: design.newHireDesignId,
      match: match(design.changeMatch ? matchFormulaSummary(newHire) : 'Same as existing employees'),
      core: core(design.changeCore ? coreFormulaSummary(newHire) : 'Same as existing employees') },
  ];
  const lateCutoff = Number(design.cutoff.slice(0, 4)) > Number(form.endYear);
  return <div className="sm:col-span-6">
    <h5 className="text-sm font-semibold text-ink">Who gets which design</h5>
    <div className="mt-2 overflow-x-auto rounded-lg border border-border">
      <table className="min-w-full text-sm">
        <thead className="bg-surface-subtle text-left text-xs text-ink-muted">
          <tr><th className="p-2 font-medium">Employees</th><th className="p-2 font-medium">Design</th><th className="p-2 font-medium">Employer match</th><th className="p-2 font-medium">Core contribution</th></tr>
        </thead>
        <tbody>{rows.map(row => <tr key={row.who} className="border-t border-border align-top">
          <td className="p-2 text-ink">{row.who}</td><td className="p-2 text-ink">{row.id}</td>
          <td className="p-2 text-ink-muted">{row.match}</td><td className="p-2 text-ink-muted">{row.core}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <p className="mt-2 text-xs text-ink-muted">Based on each employee’s hire date, including people already in the census and hires the simulation adds. An employee keeps their design for the whole simulation.</p>
    {lateCutoff && <p role="note" className="mt-2 text-xs text-warning-ink">The cutoff is after the last simulated year ({form.endYear}), so no one gets the new-hire design.</p>}
  </div>;
}

function DesignProblems({ form }: { form: FormData }) {
  const { workspaceConfig, scenarioId } = useConfigContext();
  const errors = grandfatheredDesignErrors(form, inheritedDesignIds(workspaceConfig, Boolean(scenarioId)));
  if (!errors.length) return null;
  return <div role="alert" className="sm:col-span-6 bg-warning-surface border border-warning-border rounded-md p-3">
    <p className="text-xs font-medium text-warning-ink mb-1">Fix these before saving or running:</p>
    <ul className="list-disc list-inside space-y-0.5">{errors.map(error => <li key={error} className="text-xs text-warning-ink">{error}</li>)}</ul>
  </div>;
}

function LockedNotice() {
  return <p className="sm:col-span-6 text-sm text-ink-muted">This configuration already defines plan designs in a way this editor can’t show,
    for example more than one cutoff, or designs that differ in more than match and core. Studio keeps them exactly as saved.
    Edits to the match and core on this page don’t change them; review what will run under Effective configuration.</p>;
}

export function GrandfatheredDesignFields() {
  const { formData, setFormData, handleChange, inputProps } = useConfigContext();
  const update = useDesignUpdate();
  const locked = useLockedDesigns();
  const design = formData.dcGrandfather;
  if (locked) return <LockedNotice />;
  if (!design?.enabled) return <Explainer />;
  const scope = newHireScope({ formData, setFormData, handleChange, inputProps });
  return <>
    <Explainer />
    <DesignSplitFields design={design} update={update} />
    <DesignChangeChoices design={design} update={update} />
    {design.changeMatch && <NewHireEditor kind="match" scope={scope} active={formData.dcMatchEnabled} />}
    {design.changeCore && <NewHireEditor kind="core" scope={scope} active={formData.dcCoreEnabled} />}
    <CohortPreview form={formData} design={design} />
    <DesignProblems form={formData} />
  </>;
}
