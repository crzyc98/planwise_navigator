import React, { Children, isValidElement, type ReactElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_FORM_DATA } from './constants';
import { DCPlanSection } from './DCPlanSection';
import { EmployerEligibilityEditor, coreSummary, dcDisplayConfig, eligibilitySummary, matchSummary, tierSummary } from './DCPlanPanels';
import { EnrollmentRateInput } from './EnrollmentRateInput';
import type { FormData } from './types';

const state = vi.hoisted(() => ({ formData: {} as FormData, savedFormData: null as FormData | null, config: {} as Record<string, any>, resolved: null as Record<string, any> | null, draftError: false, scenarioId: undefined as string | undefined }));
vi.mock('./ConfigContext', () => ({
  useConfigContext: () => ({
    formData: state.formData,
    savedFormData: state.savedFormData,
    activeWorkspace: { id: 'synthetic' },
    originalConfig: state.config,
    workspaceConfig: state.config,
    scenarioId: state.scenarioId,
    resolvedEngineVariables: state.resolved,
    buildDraftConfig: () => {
      if (state.draftError) throw new Error('Ambiguous custom row metadata');
      return state.config;
    },
    setFormData: (update: (previous: FormData) => FormData) => {
      state.formData = update(state.formData);
    },
    handleChange: (event: React.ChangeEvent<HTMLInputElement>) => {
      const { name, type, checked, value } = event.target;
      state.formData = { ...state.formData, [name]: type === 'checkbox' ? checked : value };
    },
    inputProps: (name: keyof FormData) => ({ name, value: state.formData[name], onChange: vi.fn() }),
  }),
}));
vi.mock('react', async importOriginal => {
  const actual = await importOriginal<typeof import('react')>();
  return {
    ...actual,
    // No DOM package is required: inspect the component's control handlers and
    // render its real inputs with the existing server-rendering test convention.
    useState: (initial: unknown) => [initial, vi.fn()],
    useEffect: vi.fn(),
  };
});

type ControlProps = { name?: string; id?: string; checked?: boolean; children?: ReactNode; onChange?: (event: React.ChangeEvent<HTMLInputElement>) => void };

function elements(node: ReactNode): ReactElement<ControlProps>[] {
  return Children.toArray(node).flatMap(child => {
    if (!isValidElement<ControlProps>(child)) return [];
    return [child, ...elements(child.props.children)];
  });
}

function toggle(name: string, checked: boolean): void {
  const nodes = [DCPlanSection(), EmployerEligibilityEditor({ kind: 'Match', config: state.config }), EmployerEligibilityEditor({ kind: 'Core', config: state.config })];
  const control = nodes.flatMap(elements).find(element => element.type === 'input' && element.props.name === name);
  expect(control).toBeDefined();
  control!.props.onChange!({ target: { name, type: 'checkbox', checked } } as React.ChangeEvent<HTMLInputElement>);
}

const render = () => renderToStaticMarkup(<DCPlanSection />);
const input = (html: string, name: string) => html.match(new RegExp(`<input[^>]*(?:name|id)="${name}"[^>]*>`))?.[0] ?? '';

beforeEach(() => {
  state.config = {};
  state.savedFormData = null;
  state.resolved = null;
  state.draftError = false;
  state.scenarioId = undefined;
  state.formData = {
    ...DEFAULT_FORM_DATA,
    dcVoluntaryEnrollmentRate: '30',
    dcNewHireOptOutRate: '8',
    dcAutoEnroll: true,
    dcVoluntaryEnrollmentMode: 'specified',
    dcNewHireOptOutMode: 'specified',
  };
});

describe('independent employer eligibility policies', () => {
  const combinations = [false, true].flatMap(requireActive => [false, true].flatMap(allowHireYear =>
    [false, true].map(allowExperienced => ({ requireActive, allowHireYear, allowExperienced })),
  ));

  for (const kind of ['Match', 'Core'] as const) {
    it.each(combinations)(`${kind} preserves custom eligibility flags %j`, ({ requireActive, allowHireYear, allowExperienced }) => {
      const prefix = `dc${kind}` as const;
      state.formData = {
        ...state.formData,
        [`${prefix}RequireYearEndActive`]: requireActive,
        [`${prefix}AllowTerminatedNewHires`]: allowHireYear,
        [`${prefix}AllowExperiencedTerminations`]: allowExperienced,
      };
      const original = structuredClone(state.formData);
      const html = renderToStaticMarkup(<EmployerEligibilityEditor kind={kind} config={state.config} />);
      expect(html).toContain(`year-end employment requirement ${requireActive ? 'on, subject to exceptions' : 'off'}`);
      expect(html).toContain(`terminated hire-year exception ${allowHireYear ? 'allowed' : 'excluded'}`);
      expect(html).toContain(`terminated experienced-employee exception ${allowExperienced ? 'allowed' : 'excluded'}`);
      expect(html).not.toContain('only employees active at year-end');
      for (const suffix of ['RequireYearEndActive', 'AllowTerminatedNewHires', 'AllowExperiencedTerminations'] as const) {
        const field = `${prefix}${suffix}` as const;
        toggle(field, !original[field]);
        expect(state.formData).toEqual({ ...original, [field]: !original[field] });
        toggle(field, original[field]);
        expect(state.formData).toEqual(original);
      }
    });
  }

  it('describes independent service/hours and inherited new-hire waivers without claiming universal rules', () => {
    state.formData.dcMatchMinTenureYears = 2;
    state.formData.dcMatchMinHoursAnnual = 850;
    state.formData.dcCoreMinTenureYears = 3;
    state.formData.dcCoreMinHoursAnnual = 1100;
    const config = {
      employer_match: { eligibility: { allow_new_hires: true } },
      employer_core_contribution: { eligibility: { allow_new_hires: false } },
      plan_design_parameters: { design_a: {} },
    };
    expect(eligibilitySummary(state.formData, 'Match', config)).toContain('2 years service; 850 annual hours');
    expect(eligibilitySummary(state.formData, 'Match', config)).toContain('waiver allowed by inherited configuration');
    expect(eligibilitySummary(state.formData, 'Core', config)).toContain('3 years service; 1100 annual hours');
    expect(eligibilitySummary(state.formData, 'Core', config)).toContain('waiver not allowed by inherited configuration');
    const html = renderToStaticMarkup(<EmployerEligibilityEditor kind="Match" config={config} />);
    expect(html).toContain('Per-design overrides are configured');
    expect(html).toContain('annual hours');
  });

  it('identifies the legacy simple match policy instead of presenting detailed controls as universal', () => {
    const html = renderToStaticMarkup(<EmployerEligibilityEditor kind="Match" config={{ employer_match: { apply_eligibility: false } }} />);
    expect(html).toContain('legacy active-at-year-end and 1,000-hour rule');
    expect(html).toContain('Editing detailed eligibility settings enables the detailed policy');
  });

  it('summarizes the active legacy rule even when inactive detailed settings allow exceptions', () => {
    state.formData.dcMatchMinTenureYears = 3;
    state.formData.dcMatchMinHoursAnnual = 500;
    state.formData.dcMatchRequireYearEndActive = false;
    state.formData.dcMatchAllowTerminatedNewHires = true;
    state.formData.dcMatchAllowExperiencedTerminations = true;
    const config = { employer_match: { apply_eligibility: false, eligibility: { allow_new_hires: true } } };
    const summary = eligibilitySummary(state.formData, 'Match', config);
    expect(summary).toContain('0 years service; 1000 annual hours; year-end employment requirement on');
    expect(summary).toContain('terminated hire-year exception excluded');
    expect(summary).toContain('terminated experienced-employee exception excluded');
    expect(summary).toContain('saved detailed settings are inactive');
    expect(matchSummary(state.formData, config)).toContain(summary);
    expect(eligibilitySummary(state.formData, 'Core', config)).not.toContain('Legacy');

    // A Studio override activates detailed matching in the existing exporter.
    const draft = { ...config, dc_plan: { match_min_hours_annual: 500 } };
    expect(eligibilitySummary(state.formData, 'Match', draft)).toContain('3 years service; 500 annual hours');
    expect(eligibilitySummary(state.formData, 'Match', draft)).toContain('terminated hire-year exception allowed');
  });

  it('uses resolved core waiver metadata when the raw configuration omits eligibility', () => {
    state.formData.dcCoreEnabled = true;
    state.formData.dcCoreMinTenureYears = 0;
    state.resolved = { employer_core_contribution: { eligibility: { allow_new_hires: false } } };
    expect(render()).toContain('new-hire service waiver not allowed by inherited configuration');
    const edited = dcDisplayConfig({}, {}, () => ({ dc_plan: { core_min_tenure_years: 0 } }), state.resolved);
    expect(eligibilitySummary(state.formData, 'Core', edited)).toContain('waiver allowed by the Studio service requirement');
  });

  it('keeps the editor usable when draft construction rejects ambiguous custom metadata', () => {
    state.draftError = true;
    state.config = { employer_core_contribution: { eligibility: { allow_new_hires: false } } };
    state.formData.dcCoreEnabled = true;
    expect(render()).toContain('new-hire service waiver not allowed by inherited configuration');
    expect(render()).toContain('Plan provisions');
    expect(state.config).toEqual({ employer_core_contribution: { eligibility: { allow_new_hires: false } } });
  });
});

describe('DC Plan provisions and employee assumptions', () => {
  it('places plan provisions before employee behavior in stable native disclosure panels', () => {
    const html = render();
    const ids = ['eligibility', 'match', 'core', 'escalation', 'enrollment', 'starting-rates', 'response'];
    let previous = -1;
    for (const id of ids) {
      const index = html.indexOf(`<details id="dcplan-${id}-panel"`);
      expect(index).toBeGreaterThan(previous);
      previous = index;
    }
    expect(html).toContain('id="dcplan-provisions"');
    expect(html).toContain('id="dcplan-behavior"');
    expect(html).toContain('New enrollees seeking the full match');
    expect(html).toContain('First-year response by existing participants');
    expect(html).toContain('focus-visible:outline');
  });

  it('derives full-match employee thresholds and formula employer maxima from actual tiers', () => {
    state.formData.dcMatchTemplate = 'safe_harbor';
    state.formData.dcMatchTiers = [{ deferralMin: 0, deferralMax: 4, matchRate: 100 }];
    expect(tierSummary(state.formData.dcMatchTiers)).toContain('100% on the first 4%');
    expect(matchSummary(state.formData, {})).toContain('Employee rate for full match: 4%');
    expect(matchSummary(state.formData, {})).toContain('maximum employer match: 4%');
    state.formData.dcMatchTiers.push({ deferralMin: 4, deferralMax: 6, matchRate: 50 });
    expect(tierSummary(state.formData.dcMatchTiers)).toContain('50% on the next 2% (4–6%)');
    expect(tierSummary(state.formData.dcMatchTiers)).toContain('Employee rate for full match: 6%');
    expect(tierSummary(state.formData.dcMatchTiers)).toContain('maximum employer match: 5%');
    const html = render();
    expect(html).toContain('eligible compensation');
    expect(html).toContain('does not verify safe-harbor status');
    expect(html).not.toContain('Satisfies ADP/ACP');
  });

  it.each(['deferral_based', 'graded_by_service', 'tenure_graded', 'points_based', 'custom_future'])(
    'preserves all saved formula schedules while displaying match mode %s', mode => {
      state.formData.dcMatchMode = mode;
      state.config = { dc_plan: { match_graded_schedule: [{ service_years_min: 0, service_years_max: null, match_rate: 70, max_deferral_pct: 8 }] } };
      const original = structuredClone(state.formData);
      const html = render();
      expect(state.formData).toEqual(original);
      expect(html).toContain(`value="${mode}"`);
      expect(matchSummary(state.formData, state.config)).not.toBe('');
      if (mode === 'graded_by_service') expect(matchSummary(state.formData, state.config)).toContain('70');
      if (mode === 'custom_future') expect(html).toContain('Saved custom mode: custom_future');
    },
  );

  it.each(['flat', 'graded_by_service', 'points_based', 'age_banded', 'custom_future'])(
    'preserves inactive core schedules and integration while displaying mode %s', mode => {
      state.formData.dcCoreEnabled = true;
      state.formData.dcCoreStatus = mode;
      state.formData.dcCoreIntegrationEnabled = true;
      state.formData.dcCoreIntegrationDisparityRate = 1.5;
      const original = structuredClone(state.formData);
      const html = render();
      expect(state.formData).toEqual(original);
      expect(html).toContain(`value="${mode}"`);
      expect(coreSummary(state.formData)).toContain('+1.5%');
      expect(coreSummary(state.formData)).toContain('Global eligibility:');
    },
  );

  it('keeps nondefault cutoffs, contribution increments and clipping warnings in collapsed summaries', () => {
    state.formData.dcAutoEscalation = true;
    state.formData.dcEscalationRate = 2.5;
    state.formData.dcEscalationDelayYears = 3;
    state.formData.dcEscalationHireDateCutoff = '2017-04-06';
    state.formData.dcDeferralSpreadMaxLift = '10';
    state.formData.dcMaxVoluntaryDeferral = 20;
    const html = render();
    const summaries = [...html.matchAll(/<summary[^>]*>(.*?)<\/summary>/g)].map(match => match[1]).join(' ');
    expect(summaries).toContain('2.5 percentage points');
    expect(summaries).toContain('3 enrollment years');
    expect(summaries).toContain('2017-04-06');
    expect(summaries).toContain('rates will be clipped');
    expect(html).toContain('rather than elapsed anniversaries');
  });
});

describe('explicit enrollment rate sources', () => {
  function changeMode(kind: 'voluntary' | 'optOut', value: 'inherit' | 'demographic' | 'specified') {
    const select = elements(EnrollmentRateInput({ kind })).find(element => element.type === 'select');
    select!.props.onChange!({ target: { value } } as React.ChangeEvent<HTMLInputElement>);
  }

  it.each(['inherit', 'demographic'] as const)('does not render a fixed split or stored fallback percentage in %s mode', mode => {
    state.formData.dcVoluntaryEnrollmentRate = '65';
    state.formData.dcVoluntaryEnrollmentMode = mode;
    const html = render();
    expect(html).not.toContain('Resulting split');
    const enrollmentSummary = html.match(/<details id="dcplan-enrollment-panel"[^>]*><summary[^>]*>(.*?)<\/summary>/)?.[1] ?? '';
    expect(enrollmentSummary).toContain(mode === 'inherit' ? 'inherited setting' : 'demographic model');
    expect(enrollmentSummary).not.toContain('65%');
  });

  it('preserves explicit zero and retained draft rates when switching sources', () => {
    state.formData.dcVoluntaryEnrollmentRate = '0';
    const original = structuredClone(state.formData);
    expect(render()).toContain('0%</strong> voluntary');
    changeMode('voluntary', 'demographic');
    expect(state.formData).toEqual({ ...original, dcVoluntaryEnrollmentMode: 'demographic' });
    expect(input(render(), 'dcVoluntaryEnrollmentRate')).toBe('');
    changeMode('voluntary', 'inherit');
    expect(state.formData.dcVoluntaryEnrollmentRate).toBe('0');
    changeMode('voluntary', 'specified');
    expect(state.formData).toEqual(original);
    expect(input(render(), 'dcVoluntaryEnrollmentRate')).toContain('value="0"');
  });

  it('keeps opt-out rate sources independent and scopes specified voluntary rates to the hire year', () => {
    const original = structuredClone(state.formData);
    changeMode('optOut', 'demographic');
    expect(state.formData).toEqual({ ...original, dcNewHireOptOutMode: 'demographic' });
    expect(render()).not.toContain('surviving prior-year hires');
    expect(render()).toContain('voluntarily in their hire year');
    expect(render()).toContain('Explicitly clears any inherited flat rate');
  });

  it('shows a scenario workspace source while keeping inheritance distinct from a specified draft rate', () => {
    state.scenarioId = 'synthetic-scenario';
    state.formData.dcVoluntaryEnrollmentMode = 'inherit';
    state.formData.dcVoluntaryEnrollmentRate = '65';
    state.config = { dc_plan: { voluntary_enrollment_rate: 0.25 } };
    const html = renderToStaticMarkup(<EnrollmentRateInput kind="voluntary" />);
    expect(html).toContain('Use inherited setting (25%)');
    expect(input(html, 'dcVoluntaryEnrollmentRate')).toBe('');
    expect(html).not.toContain('65%');
  });

  it('treats an explicit inherited null as demographic rather than falling through to a legacy number', () => {
    state.scenarioId = 'synthetic-scenario';
    state.formData.dcVoluntaryEnrollmentMode = 'inherit';
    state.config = {
      dc_plan: { voluntary_enrollment_rate: null },
      enrollment: { auto_enrollment: { voluntary_enrollment_rate: 0.4 } },
    };
    const html = renderToStaticMarkup(<EnrollmentRateInput kind="voluntary" />);
    expect(html).toContain('Use inherited setting (demographic model)');
    expect(html).not.toContain('40%');
  });

  it.each(['', '-1', '101', 'NaN'])('requires a valid explicitly specified percentage (%s)', value => {
    state.formData.dcVoluntaryEnrollmentRate = value;
    const html = renderToStaticMarkup(<EnrollmentRateInput kind="voluntary" />);
    expect(html).toContain('role="alert"');
    expect(html).toContain('Enter a percentage from 0 to 100');
    expect(input(html, 'dcVoluntaryEnrollmentRate')).toContain('required=""');
    expect(render()).not.toContain('Resulting split');
  });

  it.each(['0', '100'])('accepts explicit percentage boundary %s', value => {
    state.formData.dcVoluntaryEnrollmentRate = value;
    const html = renderToStaticMarkup(<EnrollmentRateInput kind="voluntary" />);
    expect(html).not.toContain('role="alert"');
    expect(input(html, 'dcVoluntaryEnrollmentRate')).toContain(`value="${value}"`);
  });
});

describe('DC Plan enrollment presentation', () => {
  it('shows the explicit-rate split only while auto-enrollment is enabled', () => {
    const on = render();
    expect(on).toContain('64.4%');
    expect(on).toContain('5.6%');
    toggle('dcAutoEnroll', false);
    const off = render();
    expect(off).not.toContain('Resulting split');
    expect(off).not.toContain('64.4%');
    expect(off).toContain('remaining new hires are not automatically enrolled');
    expect(off).not.toContain('Whatever is left over auto-enrolls');
  });

  it('disables auto-only inputs while keeping eligibility, voluntary rates and shared timing accessible', () => {
    toggle('dcAutoEnroll', false);
    const html = render();
    for (const name of ['dcDefaultDeferral', 'dcAutoEnrollOptOutGracePeriod']) {
      expect(input(html, name)).toContain('disabled=""');
    }
    expect(html).toContain('<fieldset disabled=""');
    expect(html).toMatch(/<fieldset disabled=""[^>]*><legend[^>]*>New-hire opt-outs/);
    for (const name of ['dcEligibilityMonths', 'dcVoluntaryEnrollmentRate', 'dcAutoEnrollWindowDays', 'dcAutoEnrollHireDateCutoff']) {
      expect(input(html, name)).not.toContain('disabled=""');
      expect(input(html, name)).not.toBe('');
    }
    expect(html).toContain('Saved value is retained');
  });

  it('restores the exact draft values when auto-enrollment is re-enabled', () => {
    const original = { ...state.formData };
    toggle('dcAutoEnroll', false);
    toggle('dcAutoEnroll', true);
    expect(state.formData).toEqual(original);
    const html = render();
    expect(input(html, 'dcNewHireOptOutRate')).toContain('value="8"');
    expect(html).toMatch(/<fieldset class="[^"]*"><legend[^>]*>New-hire opt-outs/);
    expect(html).toContain('64.4%');
  });

  it.each(['new_hires_only', 'all_eligible'].flatMap(scope => [false, true].map(autoEnroll => ({ scope, autoEnroll }))))(
    'explains first-year and later-year scope and preserves drafts for %j', ({ scope, autoEnroll }) => {
      for (const cutoff of ['', '2020-01-01', '2027-07-01']) {
        state.formData = { ...state.formData, dcAutoEnroll: autoEnroll, dcAutoEnrollScope: scope, dcAutoEnrollHireDateCutoff: cutoff };
        const original = structuredClone(state.formData);
        const html = render();
        expect(html).toContain(`First year (${state.formData.startYear}):`);
        expect(html).toContain(`hired on or after ${cutoff || 'the configured engine cutoff'}`);
        expect(html).toContain('Later years:');
        expect(html).toContain(scope === 'new_hires_only' ? 'the hire cutoff is not reapplied' : 'the cutoff still applies');
        expect(html).toContain('value="new_hires_only"');
        expect(html).toContain('value="all_eligible"');
        expect(html.includes('Resulting split')).toBe(autoEnroll);
        toggle('dcAutoEnroll', !autoEnroll);
        expect(state.formData).toEqual({ ...original, dcAutoEnroll: !autoEnroll });
        toggle('dcAutoEnroll', autoEnroll);
        expect(state.formData).toEqual(original);
      }
    },
  );

  it('shows modeled months as resolved days and distinguishes timing branches', () => {
    state.formData.dcEligibilityMonths = 2;
    const html = render();
    expect(html).toContain('Eligibility waiting period');
    expect(html).toContain('Each modeled month equals 30 days');
    expect(html).toContain('Resolved waiting period: 60 days');
    expect(html).toContain('New-hire enrollment delay after eligibility');
    expect(html).toContain('Continuing-employee branch: January 15');
    expect(html).toContain('Continuing-employee branch: June 15');
    expect(html).not.toContain('without penalty');
  });

  it('retains an inherited 45-day waiting period instead of truncating its displayed 1.5 months', () => {
    state.formData.dcEligibilityMonths = 1.5;
    state.savedFormData = structuredClone(state.formData);
    const html = render();
    expect(html).toContain('Existing waiting period: 45 days; edits use whole modeled months of 30 days.');
    expect(html).toContain('1.5 modeled months (45 days)');
    expect(html).not.toContain('1.5 modeled months (30 days)');
  });

  it('uses whole-month engine conversion when an inherited waiting period is edited', () => {
    state.formData.dcEligibilityMonths = 1.5;
    state.savedFormData = structuredClone(state.formData);
    state.formData.dcEligibilityMonths = 2;
    const html = render();
    expect(html).toContain('Resolved waiting period: 60 days');
    expect(html).toContain('2 modeled months (60 days)');
    expect(html).not.toContain('Existing waiting period: 45 days');
  });

  it.each(['', '2015-04-03'])('does not introduce or reset an escalation hire cutoff (%s)', cutoff => {
    state.formData.dcEscalationHireDateCutoff = cutoff;
    state.formData.dcAutoEscalation = false;
    const original = { ...state.formData };
    toggle('dcAutoEscalation', true);
    expect(state.formData).toEqual({ ...original, dcAutoEscalation: true });
    toggle('dcAutoEscalation', false);
    expect(state.formData).toEqual(original);
  });

  it('retains shared caps when their related optional features are disabled', () => {
    state.formData.dcMatchMagnetEnabled = false;
    state.formData.dcAutoEscalation = false;
    state.formData.dcMatchResponseEnabled = true;
    const html = render();
    expect(input(html, 'dcMatchMagnetProbability')).toContain('disabled=""');
    expect(input(html, 'dcMaxVoluntaryDeferral')).not.toBe('');
    expect(input(html, 'dcMaxVoluntaryDeferral')).not.toContain('disabled=""');
    expect(input(html, 'dcEscalationCap')).not.toBe('');
    expect(input(html, 'dcEscalationCap')).not.toContain('disabled=""');
    expect(html).toContain('first-year match-responsive deferral increases');
    state.formData.dcMatchResponseEnabled = false;
    expect(input(render(), 'dcEscalationCap')).toContain('disabled=""');
  });

  it('disables inactive participant-response controls without resetting their values', () => {
    state.formData.dcMatchResponseEnabled = false;
    const original = structuredClone(state.formData);
    const html = render();
    for (const name of ['dcMatchResponseUpwardParticipation', 'dcMatchResponseDownwardEnabled', 'dcMatchResponseDownwardParticipation']) {
      expect(input(html, name)).toContain('disabled=""');
    }
    toggle('dcMatchResponseEnabled', true);
    expect(state.formData).toEqual({ ...original, dcMatchResponseEnabled: true });
    expect(input(render(), 'dcMatchResponseUpwardParticipation')).not.toContain('disabled=""');
    toggle('dcMatchResponseDownwardEnabled', false);
    expect(input(render(), 'dcMatchResponseDownwardParticipation')).toContain('disabled=""');
  });
});
