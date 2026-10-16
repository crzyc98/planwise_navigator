import type { ReactElement, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CompensationSection } from './CompensationSection';
import { NewHireSection } from './NewHireSection';
import { useConfigContext, type ConfigContextType } from './ConfigContext';
import { DEFAULT_FORM_DATA } from './constants';
import { solveCompensationGrowth, analyzePartTimePct, analyzeAgeDistribution, analyzeCompensation, type CompensationSolverResponse } from '../../services/api';

// Exercise the component handlers and real preview hook with deterministic hook
// storage. This repository has no DOM test dependency.
const hooks = vi.hoisted(() => ({ slot: 0, cells: [] as unknown[], effects: [] as (() => void)[] }));
vi.mock('react', async importOriginal => ({
  ...await importOriginal<typeof import('react')>(),
  useRef: (initial: unknown) => {
    const slot = hooks.slot++;
    return hooks.cells[slot] ??= { current: initial };
  },
  useState: (initial: unknown) => {
    const slot = hooks.slot++;
    if (!(slot in hooks.cells)) hooks.cells[slot] = initial;
    return [hooks.cells[slot], (value: unknown) => { hooks.cells[slot] = value; }];
  },
  useEffect: (effect: () => (() => void)) => {
    const slot = hooks.slot++;
    if (!(slot in hooks.cells)) { hooks.cells[slot] = true; hooks.effects.push(effect()); }
  },
}));
vi.mock('./ConfigContext', () => ({ useConfigContext: vi.fn() }));
vi.mock('../../services/api', () => ({ solveCompensationGrowth: vi.fn(), analyzePartTimePct: vi.fn(), analyzeAgeDistribution: vi.fn(), analyzeCompensation: vi.fn() }));

type Props = { children?: ReactNode; onClick?: () => Promise<void> | void; disabled?: boolean };
function button(node: ReactNode, text: string): ReactElement<Props> | undefined {
  if (Array.isArray(node)) return node.map(child => button(child, text)).find(Boolean);
  if (!node || typeof node !== 'object' || !('props' in node)) return;
  const element = node as ReactElement<Props>;
  if (element.type === 'button' && element.props.children === text) return element;
  return button(element.props.children, text);
}

let context: ConfigContextType;
const result = { cola_rate: 3, merit_budget: 4, promotion_increase: 15, promotion_budget: 1.5,
  achieved_growth_rate: 6, warnings: [] } as unknown as CompensationSolverResponse;
function render() { hooks.slot = 0; return CompensationSection({ variant: 'essentials' }); }
function renderNewHires() { hooks.slot = 0; return NewHireSection({}); }
async function calculate() { await button(render(), 'Calculate suggested settings')!.props.onClick!(); }

describe('Compensation suggestion preview', () => {
  beforeEach(() => {
    vi.clearAllMocks(); hooks.slot = 0; hooks.cells = []; hooks.effects = [];
    context = { formData: structuredClone(DEFAULT_FORM_DATA), activeWorkspace: { id: 'w' }, scenarioId: 'a', scenarioLoading: false,
      inputProps: (name: string) => ({ name, value: context.formData[name as keyof typeof context.formData], onChange: vi.fn() }),
      setFormData: vi.fn(update => { context.formData = typeof update === 'function' ? update(context.formData) : update; }),
    } as unknown as ConfigContextType;
    vi.mocked(useConfigContext).mockImplementation(() => context);
    vi.mocked(solveCompensationGrowth).mockResolvedValue(result);
  });

  it('calculates without editing, cancels without editing, and applies only explicitly', async () => {
    await calculate();
    expect(context.setFormData).not.toHaveBeenCalled();
    expect(solveCompensationGrowth).toHaveBeenCalledWith('w', expect.objectContaining({ new_hire_comp_ratio: 0.85 }));
    button(render(), 'Cancel')!.props.onClick!();
    expect(context.setFormData).not.toHaveBeenCalled();
    expect(button(render(), 'Apply suggested settings')).toBeUndefined();
    await calculate();
    button(render(), 'Apply suggested settings')!.props.onClick!();
    expect(context.formData.colaRate).toBe(3);
    expect(context.formData.meritBudget).toBe(4);
    expect(context.formData.promoIncrease).toBe(15);
    expect(button(render(), 'Apply suggested settings')).toBeUndefined();
  });

  it('invalidates a suggestion even when changed input is restored', async () => {
    await calculate();
    const before = context.formData.targetGrowthRate;
    context.formData = { ...context.formData, targetGrowthRate: 17 }; render();
    context.formData = { ...context.formData, targetGrowthRate: before };
    const apply = button(render(), 'Apply suggested settings')!;
    expect(apply.props.disabled).toBe(true);
    apply.props.onClick!();
    expect(context.setFormData).not.toHaveBeenCalled();
  });

  it.each(['scenario', 'workspace', 'census', 'buffered number'])('discards an in-flight result after %s changes', async kind => {
    let finish!: (value: CompensationSolverResponse) => void;
    vi.mocked(solveCompensationGrowth).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
    const pending = calculate();
    if (kind === 'scenario') context.scenarioId = 'b';
    if (kind === 'workspace') context.activeWorkspace = { ...context.activeWorkspace, id: 'other' };
    if (kind === 'census') context.formData = { ...context.formData, censusDataPath: 'new.csv' };
    if (kind === 'buffered number') context.formData = { ...context.formData, targetCompensationGrowth: '' as unknown as number };
    render(); finish(result); await pending;
    expect(button(render(), 'Apply suggested settings')).toBeUndefined();
    expect(context.setFormData).not.toHaveBeenCalled();
  });

  it('does not apply a previous scenario preview after navigating back', async () => {
    await calculate(); context.scenarioId = 'b';
    expect(button(render(), 'Apply suggested settings')).toBeUndefined();
    context.scenarioId = 'a';
    expect(button(render(), 'Apply suggested settings')!.props.disabled).toBe(true);
  });

  it('surfaces errors without edits and clears obsolete errors on scope change', async () => {
    vi.mocked(solveCompensationGrowth).mockRejectedValueOnce(new Error('Census unavailable'));
    await calculate();
    expect(JSON.stringify(render())).toContain('Census unavailable');
    context.scenarioId = 'b';
    expect(JSON.stringify(render())).not.toContain('Census unavailable');
    expect(context.setFormData).not.toHaveBeenCalled();
  });

  it.each(['age', 'part-time', 'compensation'])('previews %s census changes without modifying the draft', async kind => {
    vi.mocked(analyzeAgeDistribution).mockResolvedValue({ distribution: [{ age: 30, weight: 1, count: 15, description: '30' }], analysis_type: 'Recent hires', total_employees: 15, as_of_date: '2025-12-31', as_of_date_source: 'inferred', fallback_notice: null, recent_hires_only: true, source_file: 'census.csv' });
    vi.mocked(analyzePartTimePct).mockResolvedValue({ column_present: true, part_time_pct: 0.25, part_time_count: 5, headcount: 20 });
    vi.mocked(analyzeCompensation).mockResolvedValue({ has_level_data: true, levels: [{ level: 1, name: 'Entry', min_compensation: 40000, max_compensation: 60000 }], total_employees: 20, analysis_type: 'Recent hires', recent_hires_only: true } as never);
    // The icon and label live in a fragment within the button.
    const findAll = (node: ReactNode): ReactElement<Props>[] => {
      if (Array.isArray(node)) return node.flatMap(findAll);
      if (!node || typeof node !== 'object' || !('props' in node)) return [];
      const element = node as ReactElement<Props>;
      return element.type === 'button' && JSON.stringify(element.props.children).includes('Suggest from census') ? [element] : findAll(element.props.children);
    };
    const index = ['age', 'part-time', 'compensation'].indexOf(kind);
    await findAll(renderNewHires())[index].props.onClick!();
    expect(context.setFormData).not.toHaveBeenCalled();
    expect(button(renderNewHires(), 'Apply census suggestion')).toBeDefined();
    button(renderNewHires(), 'Cancel')!.props.onClick!();
    expect(context.setFormData).not.toHaveBeenCalled();
    await findAll(renderNewHires())[index].props.onClick!();
    button(renderNewHires(), 'Apply census suggestion')!.props.onClick!();
    expect(context.setFormData).toHaveBeenCalledOnce();
    if (kind === 'age') expect(context.formData.newHireAgeDistribution[0].age).toBe(30);
    if (kind === 'part-time') expect(context.formData.partTimeNewHirePct).toBe(25);
    if (kind === 'compensation') expect(context.formData.jobLevelCompensation[0].minComp).toBe(60000);
  });
});
