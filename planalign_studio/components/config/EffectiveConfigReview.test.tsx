import type { ReactElement, ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EffectiveConfigReview, eligibilityReviewChanges, formatDraftValue, formatPreviewError, matchEligibilityReview, matchRuleSummary, redactReviewValue, reviewChanges, type ConfigurationReviewDraft } from './EffectiveConfigReview';
import { previewConfiguration, type ConfigPreview } from '../../services/api';

const hooks = vi.hoisted(() => ({ slot: 0, cells: [] as unknown[], cleanups: [] as (() => void)[] }));
vi.mock('react', async importOriginal => ({
  ...await importOriginal<typeof import('react')>(),
  useState: (initial: unknown) => {
    const slot = hooks.slot++;
    if (!(slot in hooks.cells)) hooks.cells[slot] = initial;
    return [hooks.cells[slot], (value: unknown) => { hooks.cells[slot] = value; }];
  },
  useRef: (initial: unknown) => {
    const slot = hooks.slot++;
    return hooks.cells[slot] ??= { current: initial };
  },
  useEffect: (effect: () => (() => void)) => {
    const slot = hooks.slot++;
    if (!(slot in hooks.cells)) { hooks.cells[slot] = true; const cleanup = effect(); if (cleanup) hooks.cleanups.push(cleanup); }
  },
}));
vi.mock('../../services/api', () => ({ previewConfiguration: vi.fn() }));

type Props = { children?: ReactNode; onClick?: () => Promise<void> | void; disabled?: boolean };
function button(node: ReactNode, label: string): ReactElement<Props> | undefined {
  if (Array.isArray(node)) return node.map(child => button(child, label)).find(Boolean);
  if (!node || typeof node !== 'object' || !('props' in node)) return;
  const element = node as ReactElement<Props>;
  return element.type === 'button' && element.props.children === label ? element : button(element.props.children, label);
}
const baseline: ConfigPreview = { configuration: { simulation: { random_seed: 129 }, new_hire: { strategy: 'fixed', target_percentile: 80 } }, engine_variables: { cola_rate: 0.02, random_seed: 129 }, scope: 'Excludes runtime environment overrides and census validation.' };
const resolved: ConfigPreview = { ...baseline, engine_variables: { cola_rate: 0.03, random_seed: 129, promotion_base_increase_pct: 0.19,
  auto_enrollment_enabled: false, auto_enrollment_scope: 'new_hires_only', auto_enrollment_default_deferral_rate: 0.06, new_hire_opt_out_rate: 0.08, employer_match_enabled: true,
  match_tiers: [{ employee_min: 0, employee_max: 0.03, match_rate: 1 }, { employee_min: 0.03, employee_max: 0.05, match_rate: 0.5 }], match_cap_percent: 0.04,
  employer_core_points_schedule: [{ min_points: 20, rate: 0.03 }], core_allow_experienced_terminations: true,
  deferral_escalation_cap: 0.1, deferral_match_response_upward_maximize_rate: 0.65,
} };
let review: ConfigurationReviewDraft;
const onSave = vi.fn<() => Promise<boolean>>();
const onClose = vi.fn();
const onEdit = vi.fn();
function render(overrides: Partial<Parameters<typeof EffectiveConfigReview>[0]> = {}) {
  hooks.slot = 0;
  return EffectiveConfigReview({ review, stale: false, saving: false, onSave, onClose, onEdit, ...overrides });
}
const settle = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };

it('shows preview 422 field problems in readable text', () => {
  const error = { status: 422, detail: JSON.stringify({ errors: [{ field: 'plan_year_start_date', message: 'must be a valid ISO date' }] }) };
  expect(formatPreviewError(error)).toBe('plan_year_start_date: must be a valid ISO date');
});

describe('Effective configuration review', () => {
  beforeEach(() => {
    vi.clearAllMocks(); hooks.slot = 0; hooks.cells = []; hooks.cleanups = [];
    vi.stubGlobal('document', { activeElement: null }); vi.stubGlobal('HTMLElement', class {});
    review = { workspaceId: 'w', scenarioId: 'a', targetName: 'Scenario A', runAfterSave: false,
      saved: { compensation: { cola_rate: 0.02 } }, draft: { compensation: { cola_rate: 0.03 }, unknown: { retained: 42 }, setup: { census_parquet_path: '/private/personnel.parquet' } } };
    vi.mocked(previewConfiguration).mockResolvedValueOnce(baseline).mockResolvedValueOnce(resolved);
    onSave.mockResolvedValue(true);
  });

  it('resolves the exact saved and reviewed payloads and requires explicit Save', async () => {
    const first = render();
    expect(button(first, 'Save configuration')!.props.disabled).toBe(true);
    await button(first, 'Save configuration')!.props.onClick!(); expect(onSave).not.toHaveBeenCalled();
    await settle();
    expect(previewConfiguration).toHaveBeenNthCalledWith(1, 'w', review.saved, 'scenario');
    expect(previewConfiguration).toHaveBeenNthCalledWith(2, 'w', review.draft, 'scenario');
    await button(render(), 'Save configuration')!.props.onClick!();
    expect(onSave).toHaveBeenCalledOnce();
  });

  it('reviews participant behavior with analyst labels, percentage units and inactive explanations', async () => {
    vi.mocked(previewConfiguration).mockReset();
    const behavior = {
      deferral_escalation_enabled: true, deferral_escalation_mode: 'participant_elected',
      deferral_escalation_participant_elected_signup_probability: 0.0125,
      enrollment_match_magnet_downward_enabled: true, auto_enrollment_enabled: false,
      below_default_share_tiers: [{ max_auto_enroll_default_rate: 0.03, share: 0.1 }, { max_auto_enroll_default_rate: null, share: 0.15 }],
      below_default_steps: [{ pp: 1, weight: 0.75 }, { pp: 3, weight: 0.25 }],
    };
    vi.mocked(previewConfiguration).mockResolvedValue({ ...baseline, engine_variables: behavior });
    render(); await settle();
    const html = renderToStaticMarkup(render());
    for (const label of ['Enrollment in automatic contribution increases', 'Employees who sign up for automatic increases',
      'Pull starting rates down to the full-match rate', 'Choosing a rate below the auto-enrollment default', 'How far below the default']) {
      expect(html).toContain(label);
    }
    expect(html).toContain('Participant-elected (employees sign up)');
    expect(html).toContain('1.25%');
    expect(html).toContain('Auto-enrollment default up to 3%: 10% choose below; Higher auto-enrollment defaults: 15% choose below');
    expect(html).toContain('1 percentage point below (75%); 3 percentage points below (25%)');
    expect(html).toContain('Inactive while automatic enrollment is off; saved value retained.');
    // Saved-to-draft changes use the same units as resolved engine assumptions.
    expect(formatDraftValue('dc_plan.escalation_mode', 'automatic')).toBe('Automatic (everyone unless they opt out)');
    expect(formatDraftValue('dc_plan.escalation_participant_elected_signup_probability', 0.0125)).toBe('1.25%');
    expect(formatDraftValue('dc_plan.below_default_share_tiers', behavior.below_default_share_tiers)).toContain('3%: 10%');
    expect(formatDraftValue('dc_plan.below_default_steps', behavior.below_default_steps)).toContain('1 percentage point below (75%)');
  });

  it.each([true, false])('reviews contribution rate changes with inactive explanations, enabled=%s', async enabled => {
    vi.mocked(previewConfiguration).mockReset();
    const settings = {
      deferral_rate_changes_enabled: enabled,
      deferral_rate_changes_with_escalation_increase_probability: 0.0325,
      deferral_rate_changes_with_escalation_decrease_probability: 0.15,
      deferral_rate_changes_without_escalation_increase_probability: 0.25,
      deferral_rate_changes_without_escalation_decrease_probability: 0.075,
      deferral_rate_changes_increase_steps: [{ pp: 1, weight: 0.375 }, { pp: 3, weight: 0.625 }],
      deferral_rate_changes_decrease_shares: [{ share: 0.5, weight: 1 }],
      deferral_rate_changes_post_escalation_decrease_window_days: 90,
      deferral_rate_changes_post_escalation_decrease_leaves_escalation: false,
      deferral_rate_changes_stop_probability: 0.015,
      deferral_rate_changes_restart_probability: 0,
    };
    vi.mocked(previewConfiguration).mockResolvedValue({ ...baseline, engine_variables: { ...settings, deferral_escalation_enabled: false } });
    review.draft = { dc_plan: settings };
    render(); await settle();
    const html = renderToStaticMarkup(render()).split('Other active custom settings')[0];
    for (const label of ['Model employees changing their own contribution rate', 'In automatic increases: raise their rate',
      'In automatic increases: lower their rate', 'Not in automatic increases: raise their rate',
      'Not in automatic increases: lower their rate', 'How much people raise', 'How much people lower',
      'Stop contributing', 'Restart after stopping', 'These people also leave automatic increases']) expect(html).toContain(label);
    for (const value of ['3.25%', '15%', '25%', '7.5%', '1.5%', '0%', '90 days',
      '1 percentage point (37.5%); 3 percentage points (62.5%)', '50% of current rate (100%)']) expect(html).toContain(value);
    expect(html.match(/Inactive while contribution rate changes are off; saved value retained./g) ?? []).toHaveLength(enabled ? 0 : 10);
    expect(html.match(/Inactive while automatic increases are off; saved value retained./g) ?? []).toHaveLength(enabled ? 2 : 0);
    if (enabled) expect(html).toContain('Stopped employees stay enrolled at 0%; a restart returns them to their earlier rate.');
    expect(html).not.toMatch(/\b(?:AIP|D7|PR|Phase)\b/);
    for (const [key, value] of Object.entries(settings)) {
      const formatted = formatDraftValue(`dc_plan.${key}`, value);
      expect(formatted).not.toContain('weight');
      if (key.endsWith('probability')) expect(formatted).toContain('%');
    }
    expect(formatDraftValue('dc_plan.deferral_rate_changes_post_escalation_decrease_window_days', 90)).toBe('90 days');
    expect(formatDraftValue('dc_plan.deferral_rate_changes_enabled', false)).toBe('Off');
    expect(formatDraftValue('dc_plan.deferral_rate_changes_post_escalation_decrease_leaves_escalation', true)).toBe('On');
  });

  it.each([true, false])('reviews Easy Enroll in percentage units with auto-enrollment=%s', async autoEnrollment => {
    vi.mocked(previewConfiguration).mockReset();
    const easyEnroll = { easy_enroll_enabled: true, easy_enroll_channel_share_with_auto_enrollment: 0.57,
      easy_enroll_channel_share_without_auto_enrollment: 0.45, easy_enroll_escalation_cap: 0.125,
      easy_enroll_packages: [{ rate: 0.065, share: 0.3 }, { rate: 0.1, share: 0.7 }],
      auto_enrollment_enabled: autoEnrollment, deferral_escalation_enabled: false };
    vi.mocked(previewConfiguration).mockResolvedValue({ ...baseline, engine_variables: easyEnroll });
    render(); await settle();
    const html = renderToStaticMarkup(render()).split('Other active custom settings')[0];
    expect(html).toContain('Offer Easy Enroll packages');
    expect(html).toContain('6.5% contribution, chosen by 30%; 10% contribution, chosen by 70%');
    expect(html).toContain('12.5%');
    expect(html).toContain('57%');
    expect(html).toContain('45%');
    expect(html).toContain('Easy Enroll members get automatic increases even when plan-wide automatic increases are off.');
    const inactive: string[] = html.match(/<dt[^>]*>Easy Enroll share[^<]*<\/dt><dd[\s\S]*?<\/dd>/g) ?? [];
    expect(inactive.find(row => row.includes('Inactive for this plan'))).toContain(autoEnrollment ? 'plans without auto-enrollment' : 'plans with auto-enrollment');
    expect(formatDraftValue('dc_plan.easy_enroll_escalation_cap', 0.125)).toBe('12.5%');
    expect(formatDraftValue('dc_plan.easy_enroll_channel_share_with_auto_enrollment', 0.57)).toBe('57%');
    expect(formatDraftValue('dc_plan.easy_enroll_channel_share_without_auto_enrollment', 0.45)).toBe('45%');
    expect(formatDraftValue('dc_plan.easy_enroll_packages', easyEnroll.easy_enroll_packages)).toContain('6.5% contribution, chosen by 30%');
    expect(formatDraftValue('dc_plan.easy_enroll_enabled', false)).toBe('Off');
  });

  it('marks retained Easy Enroll fields inactive when packages are not offered', async () => {
    vi.mocked(previewConfiguration).mockReset();
    vi.mocked(previewConfiguration).mockResolvedValue({ ...baseline, engine_variables: {
      easy_enroll_enabled: false, easy_enroll_channel_share_with_auto_enrollment: 0.57,
      easy_enroll_channel_share_without_auto_enrollment: 0.45, easy_enroll_escalation_cap: 0.1,
      easy_enroll_packages: [{ rate: 0.06, share: 1 }], auto_enrollment_enabled: true,
    } });
    render(); await settle();
    const html = renderToStaticMarkup(render()).split('Other active custom settings')[0];
    expect(html.match(/Inactive while Easy Enroll is off; saved value retained./g)).toHaveLength(4);
  });

  it.each([false, true])('marks sign-up assumptions inactive for automatic enrollment in increases, enabled=%s', async enabled => {
    vi.mocked(previewConfiguration).mockReset();
    vi.mocked(previewConfiguration).mockResolvedValue({ ...baseline, engine_variables: {
      deferral_escalation_enabled: enabled, deferral_escalation_mode: 'automatic',
      deferral_escalation_participant_elected_signup_probability: 0.02,
    } });
    render(); await settle();
    const html = renderToStaticMarkup(render());
    expect(html).toContain(enabled ? 'Inactive when employees join automatic contribution increases automatically'
      : 'Inactive while automatic contribution increases are off');
    expect(html).toContain('2%');
  });

  it('reviews the sweep schedule and retained inactive settings', async () => {
    vi.mocked(previewConfiguration).mockReset();
    vi.mocked(previewConfiguration).mockResolvedValue({ ...baseline, engine_variables: {
      auto_enrollment_enabled: false, reenrollment_sweep_enabled: true,
      reenrollment_sweep_interval_years: 3, reenrollment_sweep_first_year: null,
    } });
    render(); await settle();
    const html = renderToStaticMarkup(render());
    expect(html).toContain('Periodic re-enrollment sweep');
    expect(html).toContain('Sweep interval (years)');
    expect(html).toContain('Start year + sweep interval');
    expect(formatDraftValue('dc_plan.reenrollment_sweep_first_year', null)).toBe('Start year + sweep interval');
    expect(html).toContain('Sweep settings inactive; saved values retained.');
  });

  it('shows authoritative promotion values, demographic mode, custom schedules and inherited inactive values', async () => {
    render(); await settle();
    const html = renderToStaticMarkup(render());
    expect(html).toContain('19%'); expect(html).toContain('random seed');
    expect(html).toContain('Demographic model');
    expect(html).toContain('points schedule');
    expect(html).toContain('allow experienced terminations');
    expect(html).toContain('100% match on employee contributions from 0% to 3%');
    expect(html).toContain('Maximum formula match: 4%');
    expect(html).toContain('New hires only'); expect(html).toContain('Off');
    expect(html).toContain('6%'); expect(html).toContain('8%');
    expect(html).toContain('Inactive while automatic enrollment is off; saved value retained.');
    expect(html).toContain('strategy:'); expect(html).toContain('fixed');
    expect(html).toContain('Inherited'); expect(html).toContain('Scenario override');
    expect(html).toContain('mapping unverified');
    expect(html).toContain('42'); expect(html).not.toContain('/private/personnel.parquet');
    expect(html).toContain('Excludes runtime');
  });

  it('never saves after resolution fails and allows return to editing', async () => {
    vi.mocked(previewConfiguration).mockReset().mockRejectedValue(new Error('Start year must be a whole year'));
    render(); await settle();
    const tree = render();
    expect(renderToStaticMarkup(tree)).toContain('Start year must be a whole year');
    expect(button(tree, 'Save configuration')!.props.disabled).toBe(true);
    await button(tree, 'Save configuration')!.props.onClick!(); expect(onSave).not.toHaveBeenCalled();
    button(tree, 'Back to editing')!.props.onClick!(); expect(onClose).toHaveBeenCalledOnce();
  });

  it('describes the analyst match edit in plain language in the Changes table', () => {
    review.saved = { dc_plan: { match_template: 'tiered', match_tiers: resolved.engine_variables.match_tiers } };
    review.draft = { dc_plan: { match_template: 'simple', match_tiers: [
      { employee_min: 0, employee_max: 0.04, match_rate: 1 },
    ] } };
    const html = renderToStaticMarkup(render()).split('Inactive saved settings')[0];
    expect(html).toContain('Employer match template');
    expect(html).toContain('Tiered Match');
    expect(html).toContain('Simple Match');
    expect(html).toContain('Employer match formula');
    expect(html).toContain('100% on the first 3%; then 50% on the next 2%');
    expect(html).toContain('100% on the first 4%');
    expect(html).not.toContain('employee_max');
  });

  it('permits a verified corrected draft when the saved configuration is invalid', async () => {
    vi.mocked(previewConfiguration).mockReset().mockRejectedValueOnce(new Error('Saved start year invalid')).mockResolvedValueOnce(resolved);
    render(); await settle();
    const tree = render();
    expect(renderToStaticMarkup(tree)).toContain('engine comparison is unavailable');
    expect(button(tree, 'Save configuration')!.props.disabled).toBe(false);
    await button(tree, 'Save configuration')!.props.onClick!();
    expect(onSave).toHaveBeenCalledOnce();
  });

  it('prevents a stale resolved draft from being saved', async () => {
    render(); await settle();
    const tree = render({ stale: true });
    expect(button(tree, 'Save configuration')!.props.disabled).toBe(true);
    await button(tree, 'Save configuration')!.props.onClick!(); expect(onSave).not.toHaveBeenCalled();
    expect(renderToStaticMarkup(tree)).toContain('draft or target changed');
  });

  it('discards resolution after the panel is closed', async () => {
    let finish!: (value: ConfigPreview) => void;
    vi.mocked(previewConfiguration).mockReset().mockReturnValue(new Promise(resolve => { finish = resolve; }));
    render(); hooks.cleanups.forEach(cleanup => cleanup()); finish(resolved); await settle();
    expect(hooks.cells[0]).toBeNull();
  });

  it('retains failed-save feedback and prevents duplicate save requests', async () => {
    render(); await settle();
    let finish!: (value: boolean) => void;
    onSave.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const save = button(render(), 'Save configuration')!.props.onClick!;
    const pending = save(); await save(); expect(onSave).toHaveBeenCalledOnce();
    finish(false); await pending;
    expect(renderToStaticMarkup(render())).toContain('Your edits are preserved');
  });

  it('traps Tab among visible controls and ignores summaries inside closed details', () => {
    const tree = render();
    const first = { getClientRects: () => [{}], focus: vi.fn() };
    const last = { getClientRects: () => [{}], focus: vi.fn() };
    const hidden = { getClientRects: () => [], focus: vi.fn() };
    const ref = hooks.cells.find(cell => !!cell && typeof cell === 'object' && 'current' in cell && cell.current === null) as { current: unknown };
    ref.current = { querySelectorAll: () => [first, last, hidden] };
    vi.stubGlobal('document', { activeElement: last });
    const preventDefault = vi.fn();
    tree.props.onKeyDown({ key: 'Tab', shiftKey: false, preventDefault } as never);
    expect(preventDefault).toHaveBeenCalledOnce();
    expect(first.focus).toHaveBeenCalledOnce();
    expect(hidden.focus).not.toHaveBeenCalled();
    vi.stubGlobal('document', { activeElement: first });
    tree.props.onKeyDown({ key: 'Tab', shiftKey: true, preventDefault } as never);
    expect(last.focus).toHaveBeenCalledOnce();
  });
});

it('redacts nested paths and identity fields while retaining safe unknown settings', () => {
  expect(redactReviewValue({ database_path: '/private/x', extra: [{ email: 'private@example.com', cost: 12 }], notes: '/Users/private/file.csv' }))
    .toEqual({ database_path: '[hidden]', extra: [{ email: '[hidden]', cost: 12 }], notes: '[hidden]' });
  expect(reviewChanges({ x: 1 }, { x: 2, setup: { census_parquet_path: '/private/x' } }))
    .toEqual([{ key: 'setup.census_parquet_path', before: '[hidden]', after: '[hidden]' }, { key: 'x', before: 1, after: 2 }]);
});

it('does not present one global match calculation when plan designs override it', () => {
  expect(matchRuleSummary({ ...resolved.engine_variables, plan_design_parameters: { design_a: {} } })).toContain('vary by assigned plan design');
  expect(matchRuleSummary({ employer_match_enabled: false })).toContain('off');
  expect(matchRuleSummary({ active_match_formula: 'simple', match_formulas: { simple: { match_rate: 0.5, max_match_percentage: 0.06 } } })).toContain('legacy formula label alone does not verify');
});

it('applies the engine default four-percent match cap when it is not exported', () => {
  const tiers = [{ employee_min: 0, employee_max: 0.1, match_rate: 1 }];
  expect(matchRuleSummary({ match_tiers: tiers })).toContain('Maximum formula match: 4%');
  expect(matchRuleSummary({ match_tiers: tiers, match_cap_percent: 0.03 })).toContain('Maximum formula match: 3%');
});

it('describes actual match requirements without calling eligibility off', () => {
  const eligibility = { minimum_tenure_years: 2, minimum_hours_annual: 750,
    require_active_at_year_end: false, allow_terminated_new_hires: true, allow_new_hires: true };
  const legacy = matchEligibilityReview({ apply_eligibility: false, eligibility });
  expect(legacy).toContain('Minimum service: 0 years; minimum annual hours: 1000');
  expect(legacy).toContain('active employment at year-end: required');
  expect(legacy).toContain('terminated hire-year employees: excluded');
  const edited = matchEligibilityReview({ apply_eligibility: true, eligibility });
  expect(edited).toContain('Minimum service: 2 years; minimum annual hours: 750');
  expect(edited).toContain('active employment at year-end: not required');
  expect(edited).toContain('terminated hire-year employees: allowed');
});

it('reviews a one-year requirement without phantom inherited or activation changes', () => {
  const saved = {};
  const draft = { dc_plan: { match_min_tenure_years: 1, match_min_hours_annual: 1000,
    match_require_year_end_active: true, match_allow_terminated_new_hires: false,
    match_allow_experienced_terminations: false } };
  const before = { employer_match: { apply_eligibility: false, eligibility: {
    minimum_tenure_years: 0, minimum_hours_annual: 1000, require_active_at_year_end: true,
    allow_terminated_new_hires: false, allow_experienced_terminations: false, allow_new_hires: true,
  } } };
  const after = { employer_match: { apply_eligibility: true, eligibility: {
    ...before.employer_match.eligibility, minimum_tenure_years: 1, allow_new_hires: false,
  } } };
  expect(eligibilityReviewChanges(saved, draft, before, after)).toEqual([
    { key: 'dc_plan.match_min_tenure_years', before: 0, after: 1 },
  ]);
  expect(eligibilityReviewChanges(before, after, before, after, true)).toEqual([
    { key: 'employer_match.eligibility.minimum_tenure_years', before: 0, after: 1 },
    { key: 'employer_match.eligibility.allow_new_hires', before: true, after: false },
  ]);
  expect(formatDraftValue('dc_plan.match_min_tenure_years', 1)).toBe('1 year');
  expect(formatDraftValue('dc_plan.match_require_year_end_active', true)).toBe('Required');
});

it('compares dormant legacy requirements against effective rules and retains unrelated changes', () => {
  const before = { employer_match: { apply_eligibility: false, eligibility: {
    minimum_hours_annual: 500, allow_terminated_new_hires: true,
  } }, random_seed: 1 };
  const after = { employer_match: { apply_eligibility: true, eligibility: {
    minimum_hours_annual: 1000, allow_terminated_new_hires: false,
  } }, random_seed: 2 };
  expect(eligibilityReviewChanges(before, after, before, after, true)).toEqual([
    { key: 'random_seed', before: 1, after: 2 },
  ]);
  expect(eligibilityReviewChanges({ dc_plan: { match_min_hours_annual: 1000 } },
    { dc_plan: { match_min_hours_annual: 750 } }, {}, {})).toEqual([
    { key: 'dc_plan.match_min_hours_annual', before: 1000, after: 750 },
  ]);
});

it.each([
  ['dc_plan.match_cap_percent', 0.034999999999999996, '3.5%'],
  ['dc_plan.default_deferral_percent', 6, '6%'],
  ['compensation.merit_budget_percent', 3.5, '3.5%'],
  ['compensation.promotion_compensation.base_increase_pct', 0.125, '12.5%'],
  ['compensation.promotion_compensation.distribution_range', 0.05, '5%'],
  ['dc_plan.max_voluntary_deferral_percent', 0.1, '10%'],
])('formats %s using its explicit storage units', (key, value, expected) => {
  expect(formatDraftValue(key, value)).toBe(expected);
});

it('retains gaps, custom details and inherited values in match review', () => {
  expect(formatDraftValue('dc_plan.match_tiers', undefined)).toBe('Inherited / default');
  expect(formatDraftValue('dc_plan.match_tiers', [])).toBe('No explicit match tiers');
  expect(formatDraftValue('dc_plan.match_tiers', [
    { employee_min: 0.02, employee_max: 0.04, match_rate: 0.5, note: 'retain', file: '/private/x' },
  ])).toBe('50% on employee contributions from 2% to 4% (additional row settings: {"note":"retain","file":"[hidden]"})');
  expect(formatDraftValue('dc_plan.match_tiers', [{ unsupported: true }])).toContain('unsupported');
});
