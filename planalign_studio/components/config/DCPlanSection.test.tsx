import React, { Children, isValidElement, type ReactElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_FORM_DATA } from './constants';
import { DCPlanSection } from './DCPlanSection';
import { EmployerEligibilityEditor, coreSummary, dcDisplayConfig, eligibilitySummary, matchSummary, tierSummary } from './DCPlanPanels';
import { EnrollmentRateInput } from './EnrollmentRateInput';
import { DistributionTable } from './DistributionTable';
import { EasyEnrollEditor } from './EasyEnrollEditor';
import { BelowDefaultEditor } from './BelowDefaultEditor';
import { belowDefaultSummary, validateBelowDefaultSettings, easyEnrollSummary, validateEasyEnrollSettings } from './participantBehaviorConfig';
import type { FormData } from './types';
import { buildConfigPayload } from './buildConfigPayload';
import { applyConfigEdits } from './configEdits';

const state = vi.hoisted(() => ({ formData: {} as FormData, savedFormData: null as FormData | null, config: {} as Record<string, unknown>, resolved: null as Record<string, unknown> | null, draftError: false, scenarioId: undefined as string | undefined }));
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
const editorState = vi.hoisted(() => ({ rendering: false, showTiers: false }));
vi.mock('react', async importOriginal => {
  const actual = await importOriginal<typeof import('react')>();
  return {
    ...actual,
    // No DOM package is required: inspect the component's control handlers and
    // render its real inputs with the existing server-rendering test convention.
    useState: (initial: unknown) => editorState.rendering
      ? [editorState.showTiers, (value: boolean) => { editorState.showTiers = value; }]
      : [initial, vi.fn()],
    useEffect: vi.fn(),
  };
});

type ControlProps = { name?: string; id?: string; checked?: boolean; children?: ReactNode; control?: ReactNode; 'aria-label'?: string; onClick?: () => void; onChange?: (event: React.ChangeEvent<HTMLInputElement>) => void };

function elements(node: ReactNode): ReactElement<ControlProps>[] {
  return Children.toArray(node).flatMap(child => {
    if (!isValidElement<ControlProps>(child)) return [];
    if (child.type === DistributionTable) return elements(DistributionTable(child.props as unknown as React.ComponentProps<typeof DistributionTable>));
    return [child, ...elements(child.props.children), ...elements(child.props.control)];
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
  editorState.showTiers = false;
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

describe('participant behavior controls', () => {
  const editor = () => {
    editorState.rendering = true;
    try {
      return BelowDefaultEditor({ form: state.formData, onChange: changes => { state.formData = { ...state.formData, ...changes }; } });
    } finally {
      editorState.rendering = false;
    }
  };
  const click = (label: string) => {
    const button = elements(editor()).find(element => element.type === 'button'
      && (element.props.children === label || element.props['aria-label'] === label));
    expect(button).toBeDefined();
    button!.props.onClick!();
  };
  const edit = (label: string, value: string) => {
    const control = elements(editor()).find(element => element.props['aria-label'] === label);
    expect(control).toBeDefined();
    control!.props.onChange!({ target: { value } } as React.ChangeEvent<HTMLInputElement>);
  };

  it('edits the single open tier and expands its table without changing values or materializing keys', () => {
    const original = structuredClone(state.formData);
    const payload = () => buildConfigPayload(state.formData, null, null);
    const saved = payload();
    const single = renderToStaticMarkup(editor());
    expect(single).toContain('aria-expanded="false" aria-controls="dcplan-below-default-shares"');
    expect(single).toContain('Start below the default');
    expect(single).toContain(`At the current ${state.formData.dcDefaultDeferral}% default.`);
    expect(input(single, 'dcplan-below-default-share')).toContain('aria-describedby="dcplan-below-default-share-help"');
    expect(single).not.toContain('Share choosing below the default by auto-enrollment default');
    expect(single.match(/<table /g)).toHaveLength(1); // Only the reductions table has actions.
    click('Vary by auto-enrollment default…');
    const table = renderToStaticMarkup(editor());
    expect(table).toContain('All auto-enrollment defaults');
    expect(table).toContain('aria-expanded="true" aria-controls="dcplan-below-default-shares"');
    expect(state.formData).toEqual(original);
    expect(applyConfigEdits({}, saved, payload())).toEqual({});

    click('Use one share for all defaults');
    expect(renderToStaticMarkup(editor())).toContain('Start below the default');
    expect(state.formData).toEqual(original);
    edit('Start below the default', '12.5');
    expect(state.formData.dcBelowDefaultShareTiers).toEqual([{ max_auto_enroll_default_rate: null, share: 12.5 }]);
    const edited = structuredClone(state.formData);
    click('Vary by auto-enrollment default…');
    const expanded = renderToStaticMarkup(editor());
    expect(expanded).toContain('aria-label="Tier 1 share choosing below"');
    expect(expanded).toContain('value="12.5"');
    expect(expanded).not.toContain('Start below the default');
    expect(state.formData).toEqual(edited);
    expect(applyConfigEdits({}, saved, payload())).toEqual({ dc_plan: {
      below_default_share_tiers: [{ max_auto_enroll_default_rate: null, share: 0.125 }],
    } });
    click('Use one share for all defaults');
    expect(input(renderToStaticMarkup(editor()), 'dcplan-below-default-share')).toContain('value="12.5"');
    expect(state.formData).toEqual(edited);
  });

  it('orders base rates and spread before below-default adjustments and explains the population', () => {
    const html = render();
    const spread = html.indexOf('Deferral Rate Spread');
    const below = html.indexOf('id="dcplan-below-default-title"');
    expect(spread).toBeGreaterThan(html.indexOf('Starting Deferral Rates by Segment'));
    expect(below).toBeGreaterThan(spread);
    expect(html.slice(spread, below)).toContain('h-px bg-surface-disabled');
    expect(html).toContain("Of employees who enroll on their own before automatic enrollment applies, the share who start below the plan&#x27;s default rate. Everyone else starts at the default or higher. Only the row that matches your plan&#x27;s default is used.");
    expect(html).toContain('How far below the default they start');
    expect(html).toContain('How far below the default those employees start. Rates never go below 1%.');
    expect(html).toContain('Share of below-default starters');
    expect(html).toContain('/> pp</td>');
  });

  it('summarizes a zero share without reductions', () => {
    expect(belowDefaultSummary(state.formData)).toBe(`At the ${state.formData.dcDefaultDeferral}% default, no one starts below it.`);
    state.formData.dcBelowDefaultShareTiers = [{ max_auto_enroll_default_rate: null, share: 15 }];
    expect(belowDefaultSummary(state.formData)).toBe(`At the ${state.formData.dcDefaultDeferral}% default, 15% start below it (1 pp: 50%, 2 pp: 30%, 3 pp: 20%).`);
  });

  it.each([3, 2, -1, 101])('links an invalid default ceiling (%s) to the alert and clears it when corrected', ceiling => {
    state.formData.dcBelowDefaultShareTiers = [
      { max_auto_enroll_default_rate: 3, share: 10 },
      { max_auto_enroll_default_rate: ceiling, share: 15 },
      { max_auto_enroll_default_rate: null, share: 20 },
    ];
    const html = renderToStaticMarkup(editor());
    const bad = html.match(/<input[^>]*aria-label="Tier 2 auto-enrollment default ceiling"[^>]*>/)?.[0];
    expect(bad).toContain('aria-invalid="true"');
    expect(bad).toContain('aria-describedby="dcplan-below-default-errors"');
    expect(html).toContain('id="dcplan-below-default-errors" role="alert"');
    expect(validateBelowDefaultSettings(state.formData)).toContain("Each 'default up to' value must be 0–100% and higher than the row above.");
    edit('Tier 2 auto-enrollment default ceiling', '6');
    expect(renderToStaticMarkup(editor())).not.toContain('aria-invalid="true"');
    expect(renderToStaticMarkup(editor())).not.toContain('role="alert"');
  });

  it('links all weights to their total error and clears the wiring after correction', () => {
    edit('Below-default reduction 1 weight', '40');
    const html = renderToStaticMarkup(editor());
    expect(html).toContain('Weights must add up to 100% (now 90%).');
    const weights = html.match(/<input[^>]*aria-label="Below-default reduction \d weight"[^>]*>/g);
    expect(weights).toHaveLength(3);
    for (const weight of weights ?? []) {
      expect(weight).toContain('aria-invalid="true"');
      expect(weight).toContain('aria-describedby="dcplan-below-default-errors"');
    }
    edit('Below-default reduction 1 weight', '50');
    const corrected = renderToStaticMarkup(editor());
    expect(corrected).not.toContain('aria-invalid="true"');
    expect(corrected).not.toContain('dcplan-below-default-errors');
  });

  it.each([false, true].flatMap(enabled => ['automatic', 'participant_elected'].map(mode => ({ enabled, mode }))))(
    'disables the saved sign-up field unless participant-elected increases are enabled: %j', ({ enabled, mode }) => {
      state.formData.dcAutoEscalation = enabled;
      state.formData.dcEscalationMode = mode as FormData['dcEscalationMode'];
      state.formData.dcEscalationSignupProbability = 1.25;
      const html = render();
      const signup = input(html, 'dcEscalationSignupProbability');
      expect(signup).toContain('value="1.25"');
      expect(signup.includes('disabled=""')).toBe(!(enabled && mode === 'participant_elected'));
      const helpId = signup.match(/aria-describedby="[^"]*?([^ "]+-help)"/)?.[1];
      expect(helpId).toBeDefined();
      expect(html).toContain(`id="${helpId}"`);
      expect(html).toContain(enabled && mode === 'participant_elected'
        ? 'Share of enrolled participants who sign up.'
        : 'Inactive unless employees sign up for increases. Saved value is retained.');
      expect(html).toContain('Sign-up for automatic increases');
      expect(html).toContain('Who Gets Increases');
      expect(html).toContain('<div class="sm:col-span-3"><label for="dcplan-escalation-mode"');
      if (enabled) expect(html).toContain('Automatic: everyone is enrolled and may opt out. Participant-elected: only employees who sign up get increases (set the sign-up rate under Employee behavior assumptions).');
      expect(html).toContain('Automatic (everyone unless they opt out)');
      expect(html).toContain('Participant-elected (employees sign up)');
      const select = html.match(/<select[^>]*name="dcEscalationMode"[^>]*>/)?.[0] ?? '';
      expect(select.includes('disabled=""')).toBe(!enabled);
      if (enabled && mode === 'participant_elected') {
        expect(input(html, 'dcEscalationSignupProbability')).toContain('value="1.25"');
        expect(html.indexOf('Employees who sign up for automatic increases')).toBeGreaterThan(html.indexOf('id="dcplan-behavior"'));
      }
      expect(state.formData.dcEscalationSignupProbability).toBe(1.25);
    },
  );

  it('preserves the sign-up assumption across mode and enabled changes', () => {
    state.formData.dcAutoEscalation = true;
    state.formData.dcEscalationSignupProbability = 2;
    const select = elements(DCPlanSection()).find(element => element.props.name === 'dcEscalationMode');
    select!.props.onChange!({ target: { name: 'dcEscalationMode', value: 'participant_elected' } } as React.ChangeEvent<HTMLInputElement>);
    expect(render()).toContain('name="dcEscalationSignupProbability"');
    toggle('dcAutoEscalation', false);
    expect(input(render(), 'dcEscalationSignupProbability')).toContain('disabled=""');
    expect(input(render(), 'dcEscalationSignupProbability')).toContain('value="2"');
    toggle('dcAutoEscalation', true);
    expect(input(render(), 'dcEscalationSignupProbability')).toContain('value="2"');
  });

  it('shows the current default and uses inclusive, ascending tier ceilings', () => {
    state.formData.dcBelowDefaultShareTiers = [{ max_auto_enroll_default_rate: 3, share: 10 }, { max_auto_enroll_default_rate: null, share: 15 }];
    state.formData.dcDefaultDeferral = 3;
    expect(render()).toContain('At the 3% default, 10% start below it (1 pp: 50%, 2 pp: 30%, 3 pp: 20%).');
    state.formData.dcDefaultDeferral = 6;
    const html = render();
    expect(html).toContain('Current plan auto-enrollment default: 6%');
    expect(html).toContain('At the 6% default, 15% start below it (1 pp: 50%, 2 pp: 30%, 3 pp: 20%).');
    expect(html).toContain('Default above 3%');
    expect(html).toContain('How far below the default');
    expect(html).not.toContain('Below-default choices need attention');
    expect(validateBelowDefaultSettings(state.formData)).toEqual([]);
  });

  it('keeps below-default tables visible but inactive with saved values when auto-enrollment is off', () => {
    state.formData.dcBelowDefaultShareTiers = [{ max_auto_enroll_default_rate: null, share: 15 }];
    const original = structuredClone(state.formData);
    toggle('dcAutoEnroll', false);
    const html = render();
    expect(html).toContain('<fieldset disabled="" aria-labelledby="dcplan-below-default-title"');
    expect(html).toContain('Inactive while auto-enrollment is off. Saved values are retained.');
    expect(html).toContain('Choosing a rate below the auto-enrollment default');
    expect(html).toContain('Total weight: 100%');
    toggle('dcAutoEnroll', true);
    expect(state.formData).toEqual(original);
  });

  it('edits and adds/removes tiers while keeping the final open-ended row', () => {
    click('Vary by auto-enrollment default…');
    click('Add tier');
    expect(state.formData.dcBelowDefaultShareTiers).toEqual([{ max_auto_enroll_default_rate: 3, share: 0 }, { max_auto_enroll_default_rate: null, share: 0 }]);
    edit('Tier 1 share choosing below', '10');
    click('Add tier');
    edit('Tier 2 auto-enrollment default ceiling', '6');
    edit('Tier 3 share choosing below', '15');
    expect(validateBelowDefaultSettings(state.formData)).toEqual([]);
    const html = renderToStaticMarkup(editor());
    expect(html).not.toContain('Remove below-default tier 3');
    click('Remove below-default tier 1');
    expect(state.formData.dcBelowDefaultShareTiers).toEqual([{ max_auto_enroll_default_rate: 6, share: 0 }, { max_auto_enroll_default_rate: null, share: 15 }]);
  });

  it('edits step reductions and validates the weight total without silently normalizing it', () => {
    click('Add reduction');
    expect(state.formData.dcBelowDefaultSteps.at(-1)).toEqual({ pp: 4, weight: 0 });
    edit('Below-default reduction 4 in percentage points', '5');
    edit('Below-default reduction 4 weight', '10');
    expect(render()).toContain('Weights must add up to 100% (now 110%).');
    expect(render()).toContain('Total weight: 110%');
    edit('Below-default reduction 1 weight', '40');
    expect(validateBelowDefaultSettings(state.formData)).toEqual([]);
    click('Remove below-default reduction 4');
    expect(render()).toContain('Total weight: 90%');
    expect(render()).toContain('role="alert"');
  });

  it.each([
    [{ max_auto_enroll_default_rate: 6, share: 10 }, { max_auto_enroll_default_rate: 3, share: 15 }, { max_auto_enroll_default_rate: null, share: 15 }],
    [{ max_auto_enroll_default_rate: 3, share: 10 }, { max_auto_enroll_default_rate: 3, share: 15 }, { max_auto_enroll_default_rate: null, share: 15 }],
    [{ max_auto_enroll_default_rate: null, share: 10 }, { max_auto_enroll_default_rate: 6, share: 15 }],
    [{ max_auto_enroll_default_rate: null, share: 10 }, { max_auto_enroll_default_rate: null, share: 15 }],
    [],
  ].map(tiers => ({ tiers })))('reports unordered, duplicate or missing open-ended tiers (%j)', ({ tiers }) => {
    state.formData.dcBelowDefaultShareTiers = tiers;
    expect(validateBelowDefaultSettings(state.formData).length).toBeGreaterThan(0);
    expect(render()).toContain('role="alert"');
    expect(render()).toContain('Below-default choices need attention');
  });

  it.each([{ pp: 1.5, weight: 100 }, { pp: 0, weight: 100 }, { pp: 1, weight: 101 }, { pp: 1, weight: -1 }])(
    'rejects invalid reduction units or weights %j', step => {
      state.formData.dcBelowDefaultSteps = [step];
      expect(validateBelowDefaultSettings(state.formData).length).toBeGreaterThan(0);
      expect(render()).toContain('role="alert"');
    },
  );

  it('places downward match seeking with the upward pull and retains it while inactive', () => {
    state.formData.dcMatchMagnetProbability = 37.5;
    toggle('dcMatchMagnetDownwardEnabled', true);
    const html = render();
    expect(html).toContain('Also pull rates down to the full-match rate when it is below the auto-enrollment default');
    expect(html).toContain('Uses the same 37.5% probability as the upward pull');
    expect(html).toContain('Applies only to employees whose starting rate is between the full-match rate and the auto-enrollment default. Rates above the default are never lowered.');
    expect(html).toContain('id="dcplan-match-magnet-downward-help"');
    expect(input(html, 'dcMatchMagnetDownwardEnabled')).toContain('aria-describedby="dcplan-match-magnet-downward-help"');
    expect(input(html, 'dcMatchMagnetDownwardEnabled')).toContain('disabled:opacity-50');
    expect(html).toContain('downward pull on (same 37.5% probability)');
    toggle('dcMatchMagnetEnabled', false);
    expect(input(render(), 'dcMatchMagnetDownwardEnabled')).toContain('disabled=""');
    expect(state.formData.dcMatchMagnetDownwardEnabled).toBe(true);
    toggle('dcMatchMagnetEnabled', true);
    toggle('dcAutoEnroll', false);
    expect(input(render(), 'dcMatchMagnetDownwardEnabled')).toContain('disabled=""');
    expect(state.formData.dcMatchMagnetDownwardEnabled).toBe(true);
  });
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
    expect(html).toContain('No separate eligibility switch is needed');
    expect(html).toContain('editing them saves the complete displayed policy');
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
    expect(summary).not.toContain('inactive');
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
  it.each([
    ['dcAutoEnroll', 'dcplan-auto-enrollment-settings'],
    ['dcMatchEnabled', 'dcplan-match-panel'],
    ['dcCoreEnabled', 'dcplan-core-panel'],
    ['dcAutoEscalation', 'dcplan-escalation-panel'],
    ['dcMatchMagnetEnabled', 'dcplan-match-magnet-settings'],
    ['dcMatchResponseEnabled', 'dcplan-match-response-settings'],
  ] as const)('expands enabled %s settings and collapses them when disabled', (field, id) => {
    for (const enabled of [true, false]) {
      state.formData[field] = enabled;
      const html = render();
      const tag = html.match(new RegExp(`<details id="${id}"[^>]*>`))?.[0];
      expect(tag).toBeDefined();
      expect(tag!.includes('open=""')).toBe(enabled);
      // The enabling checkbox stays before the collapsible settings.
      expect(html.indexOf(`name="${field}"`)).toBeLessThan(html.indexOf(tag!));
    }
  });

  it('places plan provisions before employee behavior in stable native disclosure panels', () => {
    const html = render();
    const ids = ['eligibility', 'match', 'core', 'escalation', 'starting-rates', 'response'];
    let previous = -1;
    for (const id of ids) {
      const index = html.indexOf(`<details id="dcplan-${id}-panel"`);
      expect(index).toBeGreaterThan(previous);
      previous = index;
    }
    expect(html).toContain('id="dcplan-provisions"');
    expect(html).toContain('id="dcplan-behavior"');
    expect(html).not.toContain('dcplan-enrollment-panel');
    const enrollmentPanel = html.slice(html.indexOf('id="dcplan-eligibility-panel"'), html.indexOf('id="dcplan-match-panel"'));
    const sharedRules = enrollmentPanel.indexOf('Shared enrollment rules');
    expect(enrollmentPanel.indexOf('Employee behavior assumptions — opt-outs')).toBeLessThan(sharedRules);
    expect(enrollmentPanel.indexOf('New-hire opt-out')).toBeLessThan(sharedRules);
    expect(enrollmentPanel.indexOf('Voluntary enrollment assumptions')).toBeGreaterThan(sharedRules);
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
    const enrollmentSummary = html.match(/<details id="dcplan-eligibility-panel"[^>]*><summary[^>]*>(.*?)<\/summary>/)?.[1] ?? '';
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
        expect(html).toContain(`hired on or after ${cutoff || '2020-01-01 (engine default)'}`);
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

  it('keeps voluntary limits independent and collapses the annual escalation cap', () => {
    state.formData.dcMatchMagnetEnabled = false;
    state.formData.dcAutoEscalation = false;
    state.formData.dcMatchResponseEnabled = true;
    const html = render();
    expect(input(html, 'dcMatchMagnetProbability')).toContain('disabled=""');
    expect(input(html, 'dcMaxVoluntaryDeferral')).not.toBe('');
    expect(input(html, 'dcMaxVoluntaryDeferral')).not.toContain('disabled=""');
    expect(input(html, 'dcEscalationCap')).not.toBe('');
    expect(input(html, 'dcEscalationCap')).toContain('disabled=""');
    expect(html).toMatch(/<details id="dcplan-escalation-panel">[\s\S]*?name="dcEscalationCap"[\s\S]*?<\/details>/);
    expect(html).toContain('Employees can contribute above this rate');
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

describe('Easy Enroll controls', () => {
  const editor = () => EasyEnrollEditor({ form: state.formData, onChange: changes => { state.formData = { ...state.formData, ...changes }; } });
  const click = (label: string) => {
    const button = elements(editor()).find(element => element.type === 'button'
      && (element.props.children === label || element.props['aria-label'] === label));
    expect(button).toBeDefined();
    button!.props.onClick!();
  };
  const edit = (label: string, value: string) => {
    const control = elements(editor()).find(element => element.props['aria-label'] === label || element.props.name === label);
    expect(control).toBeDefined();
    control!.props.onChange!({ target: { value } } as React.ChangeEvent<HTMLInputElement>);
  };

  it('places the panel between starting rates and match response, with an accessible persistent toggle', () => {
    const html = render();
    expect(html.indexOf('id="dcplan-starting-rates-panel"')).toBeLessThan(html.indexOf('id="dcplan-easy-enroll-panel"'));
    expect(html.indexOf('id="dcplan-easy-enroll-panel"')).toBeLessThan(html.indexOf('id="dcplan-response-panel"'));
    expect(html).toContain('Offer Easy Enroll packages');
    toggle('dcEasyEnrollEnabled', true);
    expect(state.formData.dcEasyEnrollEnabled).toBe(true);
    expect(render()).toContain('<details id="dcplan-easy-enroll-panel" open="">');
    expect(easyEnrollSummary(state.formData)).toContain('57% of self-enrollees');
  });

  it.each([true, false])('highlights only the applicable share with auto-enrollment=%s', autoEnroll => {
    state.formData = { ...state.formData, dcEasyEnrollEnabled: true, dcAutoEnroll: autoEnroll };
    const html = renderToStaticMarkup(editor());
    const highlighted = html.match(/<div class="rounded p-3 bg-info-surface">[\s\S]*?<\/div><p[\s\S]*?<\/div>/)?.[0] ?? '';
    expect(highlighted).toContain(autoEnroll ? 'Plans with auto-enrollment' : 'Plans without auto-enrollment');
    expect(highlighted).toContain('Applies to this plan');
    expect(html).toContain('rounded p-3 opacity-60');
    expect(html.match(/Applies to this plan/g)).toHaveLength(1);
    expect(easyEnrollSummary(state.formData)).toContain(`${autoEnroll ? 57 : 45}% of self-enrollees`);
  });

  it('retains visible disabled fields and explains the population and independent automatic increases', () => {
    const before = structuredClone(state.formData);
    const html = renderToStaticMarkup(editor());
    expect(html).toContain('<fieldset disabled="" aria-label="Easy Enroll settings"');
    expect(html).toContain('Inactive while Easy Enroll is off. Saved values are retained.');
    expect(html).toContain('Auto-enrolled employees never use Easy Enroll.');
    expect(html).toContain('Easy Enroll members get automatic increases even when plan-wide automatic increases are off.');
    expect(html).toContain('value="57"');
    expect(html).toContain('value="45"');
    expect(html).toContain('value="10"');
    expect(state.formData).toEqual(before);
    expect(html).not.toContain('role="alert"');
    state.formData = { ...state.formData, dcEasyEnrollEnabled: true, dcAutoEscalation: false };
    expect(renderToStaticMarkup(editor())).not.toContain('<fieldset disabled');
  });

  it('adds, edits and removes packages and validates rates and total shares without normalizing', () => {
    state.formData = { ...state.formData, dcEasyEnrollEnabled: true };
    click('Add package');
    expect(state.formData.dcEasyEnrollPackages.at(-1)).toEqual({ rate: 11, share: 0 });
    edit('Easy Enroll package 4 contribution rate', '6');
    edit('Easy Enroll package 4 share', '10');
    let html = renderToStaticMarkup(editor());
    expect(html).toContain('rates must be unique');
    expect(html).toContain('now 110%');
    expect(html).toContain('aria-invalid="true" aria-describedby="dcplan-easy-enroll-errors"');
    edit('Easy Enroll package 4 contribution rate', '12.5');
    edit('Easy Enroll package 1 share', '20');
    expect(validateEasyEnrollSettings(state.formData)).toEqual([]);
    click('Remove Easy Enroll package 4');
    expect(renderToStaticMarkup(editor())).toContain('Total share: 90%');
    edit('Easy Enroll package 1 share', '30');
    click('Remove Easy Enroll package 3');
    click('Remove Easy Enroll package 2');
    edit('Easy Enroll package 1 share', '100');
    html = renderToStaticMarkup(editor());
    expect(html.match(/<button[^>]*aria-label="Remove Easy Enroll package 1"[^>]*>/)?.[0]).toContain('disabled=""');
    expect(validateEasyEnrollSettings(state.formData)).toEqual([]);
    edit('dcEasyEnrollEscalationCap', '12.5');
    edit('dcEasyEnrollShareWithAutoEnrollment', '62.5');
    expect(state.formData).toMatchObject({ dcEasyEnrollEscalationCap: 12.5, dcEasyEnrollShareWithAutoEnrollment: 62.5 });
  });

  it.each([
    [], [{ rate: 0, share: 100 }], [{ rate: -1, share: 100 }], [{ rate: 101, share: 100 }],
    [{ rate: 6, share: 50 }, { rate: 6, share: 50 }], [{ rate: 6, share: 99 }],
    [{ rate: 6, share: -10 }, { rate: 8, share: 110 }], [{ rate: Number.NaN, share: 100 }],
  ].map(packages => ({ packages })))('rejects invalid packages: %j', ({ packages }) => {
    expect(validateEasyEnrollSettings({ ...DEFAULT_FORM_DATA, dcEasyEnrollPackages: packages }).length).toBeGreaterThan(0);
  });
});

describe('periodic re-enrollment sweep controls', () => {
  it('shows the default-off provision and enables the schedule with its toggle', () => {
    expect(render()).toContain('Periodic re-enrollment sweep');
    expect(render()).toContain('Employees at 0% can opt out again');
    expect(input(render(), 'dcReenrollmentSweepIntervalYears')).toContain('disabled=""');
    toggle('dcReenrollmentSweepEnabled', true);
    expect(state.formData.dcReenrollmentSweepEnabled).toBe(true);
    expect(input(render(), 'dcReenrollmentSweepIntervalYears')).not.toContain('disabled=""');
    expect(input(render(), 'dcReenrollmentSweepIntervalYears')).toContain('min="1"');
    expect(input(render(), 'dcReenrollmentSweepFirstYear')).not.toContain('disabled=""');
    expect(render()).toContain(`first ${Number(state.formData.startYear) + 3}`);
  });
  it('retains and displays an inactive schedule when auto-enrollment is off', () => {
    state.formData = { ...state.formData, dcAutoEnroll: false, dcReenrollmentSweepEnabled: true, dcReenrollmentSweepIntervalYears: 2, dcReenrollmentSweepFirstYear: '2027' };
    expect(input(render(), 'dcReenrollmentSweepIntervalYears')).toContain('disabled=""');
    expect(input(render(), 'dcReenrollmentSweepFirstYear')).toContain('value="2027"');
    expect(render()).toContain('Sweep settings inactive; saved values are retained.');
  });
});


describe('sweep target groups and method', () => {
  it('renders both methods, three groups and contributor decline percentage', () => {
    toggle('dcReenrollmentSweepEnabled', true);
    const html = render();
    for (const label of ['Enroll at the default rate', 'Sweep into automatic increases',
      'Not contributing (0%)', 'Contributing below the default rate',
      'Contributing below the automatic-increase cap', 'Share of contributors who decline']) {
      expect(html).toContain(label);
    }
    toggle('dcReenrollmentSweepIncludeBelowDefault', true);
    toggle('dcReenrollmentSweepIncludeBelowAipCap', true);
    expect(state.formData.dcReenrollmentSweepIncludeBelowDefault).toBe(true);
    expect(state.formData.dcReenrollmentSweepIncludeBelowAipCap).toBe(true);
    expect(input(render(), 'dcReenrollmentSweepDeclineProbability')).toContain('value="10"');
  });
  it.each([
    ['new_hires_only', '', true], ['all_eligible', '2020-01-01', true],
    ['all_eligible', '', false],
  ])('shows legacy-hire notice for scope %s and cutoff %s', (scope, cutoff, expected) => {
    state.formData = { ...state.formData, dcAutoEnroll: true, dcReenrollmentSweepEnabled: true,
      dcAutoEnrollScope: scope, dcAutoEnrollHireDateCutoff: cutoff };
    const notice = 'This sweep includes all legacy hires, not only employees hired after the auto-enrollment cutoff.';
    expect(render().includes(notice)).toBe(expected);
    toggle('dcReenrollmentSweepEnabled', false);
    expect(render()).not.toContain(notice);
  });
});
