import type { ReactNode } from 'react';
import { useConfigContext } from './ConfigContext';
import { InputField } from './InputField';
import { calculateMatchCap } from './constants';
import type { FormData, MatchTier } from './types';

type Config = Record<string, any>;
type Contribution = 'Match' | 'Core';

/** Overlay saved metadata for copy only; backend reconciliation remains authoritative. */
export function resolveDisplayConfig(base: Config = {}, overrides: Config = {}): Config {
  const result = { ...base };
  for (const [key, value] of Object.entries(overrides)) {
    result[key] = value && typeof value === 'object' && !Array.isArray(value)
      ? resolveDisplayConfig(base[key] ?? {}, value)
      : value;
  }
  return result;
}

/** A failing draft remains editable; the review path reports its actual error. */
export function dcDisplayConfig(workspace: Config, original: Config, buildDraft: (() => Config) | undefined, resolved?: Config | null): Config {
  let draft: Config;
  try {
    draft = buildDraft?.() ?? original;
  } catch {
    draft = original;
  }
  const baseline = {
    employer_match: resolved?.employer_match ?? {},
    employer_core_contribution: resolved?.employer_core_contribution ?? {},
  };
  return resolveDisplayConfig(resolveDisplayConfig(baseline, workspace), draft);
}

export function DCPlanPanel({ id, title, summary, children, enabled = true, control }: {
  id: string; title: string; summary: string; children: ReactNode;
  enabled?: boolean; control?: ReactNode;
}) {
  // Native disclosure handles manual collapse. React updates `open` only when
  // enabled changes, so unrelated form edits preserve the user's choice.
  return (
    <div className="rounded-lg border border-border bg-surface-raised sm:col-span-6">
      {control && <div className="p-4 pb-0">{control}</div>}
    <details id={id} open={enabled}>
      <summary className="cursor-pointer rounded-lg p-4 focus-visible:outline-2 focus-visible:outline-fidelity-green">
        <span className="font-semibold text-ink">{title}</span>
        <span className="mt-1 block text-xs font-normal text-ink-muted break-words">{summary}</span>
      </summary>
      <div className="grid grid-cols-1 gap-y-6 gap-x-4 p-4 pt-0 sm:grid-cols-6 min-w-0">{children}</div>
    </details>
    </div>
  );
}

function waiverSummary(form: FormData, kind: Contribution, config: Config): string {
  const eligibility = config[kind === 'Match' ? 'employer_match' : 'employer_core_contribution']?.eligibility ?? {};
  const explicitWaiver = config.dc_plan?.[`${kind.toLowerCase()}_allow_new_hires`];
  const hasUITenure = config.dc_plan?.[`${kind.toLowerCase()}_min_tenure_years`] != null;
  const waiver = explicitWaiver ?? (hasUITenure ? Number(form[`dc${kind}MinTenureYears`]) === 0 : eligibility.allow_new_hires);
  if (waiver == null) return `derived from service requirement (${Number(form[`dc${kind}MinTenureYears`]) === 0 ? 'allowed' : 'not allowed'})`;
  return `${waiver ? 'allowed' : 'not allowed'} by ${explicitWaiver != null ? 'the saved Studio setting' : hasUITenure ? 'the Studio service requirement' : 'inherited configuration'}`;
}

function usesLegacyMatchPolicy(kind: Contribution, config: Config): boolean {
  return kind === 'Match' && config.employer_match?.apply_eligibility === false &&
    !Object.keys(config.dc_plan ?? {}).some(key => /^match_(min_|require_|allow_)/.test(key));
}

export function eligibilitySummary(form: FormData, kind: Contribution, config: Config = {}): string {
  if (usesLegacyMatchPolicy(kind, config)) {
    return '0 years service; 1000 annual hours; year-end employment requirement on; ' +
      'terminated hire-year exception excluded; terminated experienced-employee exception excluded; ' +
      'new-hire service waiver not applicable (no service requirement).';
  }
  const prefix = `dc${kind}` as const;
  return `${form[`${prefix}MinTenureYears`]} years service; ${form[`${prefix}MinHoursAnnual`]} annual hours; ` +
    `year-end employment requirement ${form[`${prefix}RequireYearEndActive`] ? 'on, subject to exceptions' : 'off'}; ` +
    `terminated hire-year exception ${form[`${prefix}AllowTerminatedNewHires`] ? 'allowed' : 'excluded'}; ` +
    `terminated experienced-employee exception ${form[`${prefix}AllowExperiencedTerminations`] ? 'allowed' : 'excluded'}; ` +
    `new-hire service waiver ${waiverSummary(form, kind, config)}.`;
}

export function EmployerEligibilityEditor({ kind, config }: { kind: Contribution; config: Config }) {
  const { formData, inputProps, handleChange } = useConfigContext();
  const prefix = `dc${kind}` as const;
  const requireActive = formData[`${prefix}RequireYearEndActive`];
  const allowHireYear = formData[`${prefix}AllowTerminatedNewHires`];
  const allowExperienced = formData[`${prefix}AllowExperiencedTerminations`];
  const custom = requireActive ? allowHireYear || allowExperienced : !allowHireYear || !allowExperienced;
  const legacySimpleMatch = usesLegacyMatchPolicy(kind, config);
  const flags = [
    ['RequireYearEndActive', 'Require active employment at year-end'],
    ['AllowTerminatedNewHires', 'Allow terminated hire-year employees'],
    ['AllowExperiencedTerminations', 'Allow terminated experienced employees'],
  ] as const;
  return <>
    <div className="sm:col-span-6 text-xs text-ink-muted space-y-1">
      <h4 className="text-sm font-semibold text-ink">{kind} eligibility</h4>
      <p>{eligibilitySummary(formData, kind, config)}</p>
      {custom && <p>Custom {legacySimpleMatch ? 'saved detailed ' : ''}policy combination. Each setting is preserved independently.</p>}
      <p>These requirements apply to the employer {kind.toLowerCase()} contribution. No separate eligibility switch is needed. Zero service or hours means no minimum for that requirement.</p>
      {legacySimpleMatch && <details><summary className="cursor-pointer">Previously saved eligibility settings</summary><p>Older detailed settings are retained in the configuration but are not in effect. The controls show the current requirements; editing them saves the complete displayed policy.</p></details>}
      <p>Global Studio settings shown. {config.plan_design_parameters
        ? 'Per-design overrides are configured; each assigned design may resolve different eligibility rules.'
        : 'Inherited eligibility is shown from the loaded configuration; backend reconciliation remains authoritative.'}</p>
    </div>
    <InputField label={`${kind} minimum service`} {...inputProps(`${prefix}MinTenureYears`)} type="number" suffix="Years" helper="Years of service required, subject to the new-hire waiver above." min={0} />
    <InputField label={`${kind} minimum annual hours`} {...inputProps(`${prefix}MinHoursAnnual`)} type="number" suffix="Hours" helper="Modeled annual hours, prorated for employment periods." min={0} />
    <div className="sm:col-span-6 space-y-2">
      {flags.map(([suffix, label]) => {
        const name = `${prefix}${suffix}` as const;
        return <label key={name} htmlFor={name} className="flex items-center gap-2 text-sm text-ink-muted">
          <input id={name} name={name} type="checkbox" checked={formData[name]} onChange={handleChange} className="h-4 w-4 shrink-0 text-fidelity-green rounded" />
          {label}
        </label>;
      })}
      <p className="text-xs text-ink-muted">These flags are independent. Allowed exceptions can qualify despite the year-end requirement; excluded termination categories remain excluded even when that requirement is off. Service and hours rules still apply.</p>
    </div>
  </>;
}

const percent = (value: number) => Number(value.toFixed(2));
export function tierSummary(tiers: MatchTier[]): string {
  if (!tiers.length) return 'No tiers configured';
  const threshold = Math.max(0, ...tiers.filter(tier => tier.matchRate > 0).map(tier => tier.deferralMax));
  return `${tiers.map(tier => tier.deferralMin === 0
    ? `${tier.matchRate}% on the first ${tier.deferralMax}%`
    : `${tier.matchRate}% on the next ${tier.deferralMax - tier.deferralMin}% (${tier.deferralMin}–${tier.deferralMax}%)`).join('; ')}. ` +
    `Employee rate for full match: ${threshold}%; maximum employer match: ${percent(calculateMatchCap(tiers) * 100)}% of eligible compensation.`;
}

export function matchSummary(form: FormData, config: Config): string {
  if (!form.dcMatchEnabled) return 'Disabled; saved formula and eligibility settings retained.';
  let schedule: string;
  switch (form.dcMatchMode) {
    case 'deferral_based': schedule = tierSummary(form.dcMatchTiers); break;
    case 'tenure_graded': schedule = form.dcTenureGradedBands.map(band => `${band.minYears}–${band.maxYears ?? '∞'} service years: ${tierSummary(band.tiers)}`).join(' '); break;
    case 'points_based': schedule = form.dcPointsMatchTiers.map(tier => `${tier.minPoints}–${tier.maxPoints ?? '∞'} points: employee ${tier.maxDeferralPct}% for full match; employer maximum ${percent(tier.maxDeferralPct * tier.matchRate / 100)}% (${tier.matchRate}% match rate)`).join('; '); break;
    default: schedule = `${form.dcMatchMode}; saved service schedule: ${JSON.stringify(config.dc_plan?.match_graded_schedule ?? config.employer_match?.graded_schedule ?? config.employer_match?.service_tiers ?? 'inherited at run time')}`;
  }
  return `${schedule} Global eligibility: ${eligibilitySummary(form, 'Match', config)}${config.plan_design_parameters ? ' Per-design overrides apply; these global rules are not universal.' : ''}`;
}

export function coreSummary(form: FormData, config: Config = {}): string {
  if (!form.dcCoreEnabled) return 'Disabled; saved schedules and eligibility settings retained.';
  let schedule: string;
  switch (form.dcCoreStatus) {
    case 'flat': schedule = `${form.dcCoreContributionRate}% of eligible compensation`; break;
    case 'graded_by_service': schedule = form.dcCoreGradedSchedule.map(tier => `${tier.serviceYearsMin}–${tier.serviceYearsMax ?? '∞'} service years: ${tier.rate}%`).join('; '); break;
    case 'points_based': schedule = form.dcCorePointsSchedule.map(tier => `${tier.minPoints}–${tier.maxPoints ?? '∞'} points: ${tier.rate}%`).join('; '); break;
    case 'age_banded': schedule = form.dcCoreAgeSchedule.map(tier => `${tier.minAge}–${tier.maxAge ?? '∞'} age: ${tier.rate}%`).join('; '); break;
    default: schedule = `Saved custom mode: ${form.dcCoreStatus}`;
  }
  const integrationLevel = form.dcCoreIntegrationLevelMode === 'ss_wage_base' ? 'Social Security wage base'
    : form.dcCoreIntegrationLevelMode === 'percent_of_ss_wage_base' ? `${form.dcCoreIntegrationLevelValue}% of Social Security wage base`
      : `$${form.dcCoreIntegrationLevelValue} fixed level`;
  return `${schedule}. Integration ${form.dcCoreIntegrationEnabled ? `on (${integrationLevel}, +${form.dcCoreIntegrationDisparityRate}%)` : 'off'}. Global eligibility: ${eligibilitySummary(form, 'Core', config)}${config.plan_design_parameters ? ' Per-design overrides apply; these global rules are not universal.' : ''}`;
}
