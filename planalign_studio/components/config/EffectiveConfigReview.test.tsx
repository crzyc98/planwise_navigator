import type { ReactElement, ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EffectiveConfigReview, eligibilityReviewChanges, formatDraftValue, matchEligibilityReview, matchRuleSummary, redactReviewValue, reviewChanges, type ConfigurationReviewDraft } from './EffectiveConfigReview';
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
