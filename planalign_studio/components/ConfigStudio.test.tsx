import type { ReactElement, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConfigShell } from './ConfigStudio';
import { type ConfigContextType, useConfigContext } from './config/ConfigContext';
import { EffectiveConfigReview } from './config/EffectiveConfigReview';

const navigate = vi.hoisted(() => vi.fn());
const hooks = vi.hoisted(() => ({ slot: 0, cells: [] as unknown[] }));
vi.mock('../hooks/useWorkspaceNavigation', () => ({ useWorkspaceNavigate: () => navigate }));
vi.mock('./config/ConfigContext', () => ({ useConfigContext: vi.fn(), ConfigProvider: vi.fn() }));
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
}));

interface Props { children?: ReactNode; onClick?: () => Promise<void> | void; disabled?: boolean }
function find(node: ReactNode, predicate: (element: ReactElement<Props>) => boolean): ReactElement<Props> | undefined {
  if (Array.isArray(node)) return node.map(child => find(child, predicate)).find(Boolean);
  if (!node || typeof node !== 'object' || !('props' in node)) return;
  const element = node as ReactElement<Props>;
  return predicate(element) ? element : find(element.props.children, predicate);
}
const runButton = (tree: ReactNode) => find(tree, element => element.type === 'button' && Array.isArray(element.props.children) && element.props.children.some(child => child === 'Save & Run' || child === 'Run Simulation'))!;
const reviewPanel = (tree: ReactNode) => find(tree, element => element.type === EffectiveConfigReview) as ReactElement<Parameters<typeof EffectiveConfigReview>[0]> | undefined;
const save = vi.fn<() => Promise<boolean>>();
let context: ConfigContextType;
let draft: Record<string, unknown>;
function shell(overrides: Partial<ConfigContextType> = {}) {
  context = { ...context, ...overrides };
  vi.mocked(useConfigContext).mockReturnValue(context);
  hooks.slot = 0;
  return ConfigShell();
}

describe('Configuration review and Run', () => {
  beforeEach(() => {
    vi.clearAllMocks(); hooks.slot = 0; hooks.cells = [];
    vi.stubGlobal('document', { activeElement: null });
    vi.stubGlobal('HTMLElement', class {});
    vi.stubGlobal('requestAnimationFrame', (callback: () => void) => { callback(); return 1; });
    draft = { simulation: { start_year: 2025, end_year: 2027 } };
    context = {
      currentScenario: { name: 'Scenario A' }, scenarioId: 'a', scenarioLoading: false,
      dirtySections: new Set(), isDirty: true, handleSaveConfig: save,
      saveStatus: 'idle', saveMessage: '', activeWorkspace: { id: 'w', name: 'Workspace A' },
      originalConfig: { simulation: { start_year: 2025, end_year: 2026 } }, buildDraftConfig: () => draft,
    } as unknown as ConfigContextType;
    save.mockResolvedValue(true);
  });

  it('opens review before dirty Run and saves only after explicit confirmation', async () => {
    await runButton(shell()).props.onClick!();
    expect(save).not.toHaveBeenCalled(); expect(navigate).not.toHaveBeenCalled();
    const tree = shell(); const panel = reviewPanel(tree)!;
    expect(panel.props.review.draft).toEqual(draft);
    expect(panel.props.review.targetName).toBe('Scenario A');
    expect(panel.props.review.runAfterSave).toBe(true);
    expect(find(tree, element => element.type === 'fieldset')!.props.disabled).toBe(true);
    expect(await panel.props.onSave()).toBe(true);
    expect(save).toHaveBeenCalledOnce();
    expect(navigate).toHaveBeenCalledExactlyOnceWith('/simulate?scenario=a');
  });

  it('cancels without persistence or navigation', async () => {
    await runButton(shell()).props.onClick!();
    reviewPanel(shell())!.props.onClose();
    expect(reviewPanel(shell())).toBeUndefined();
    expect(save).not.toHaveBeenCalled(); expect(navigate).not.toHaveBeenCalled();
  });

  it('keeps clean Run unchanged without saving', async () => {
    await runButton(shell({ isDirty: false })).props.onClick!();
    expect(save).not.toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledExactlyOnceWith('/simulate?scenario=a');
  });

  it('commits buffered edits before deciding whether Run requires review', async () => {
    const tree = shell({ isDirty: false });
    class BufferedInput extends HTMLElement {
      blur() { draft = { simulation: { end_year: 2031 } }; shell({ isDirty: true }); }
    }
    vi.stubGlobal('document', { activeElement: new BufferedInput() });
    await runButton(tree).props.onClick!();
    expect(reviewPanel(shell())!.props.review.draft).toEqual(draft);
    expect(save).not.toHaveBeenCalled(); expect(navigate).not.toHaveBeenCalled();
  });

  it.each(['draft', 'scenario', 'workspace'])('prevents saving a review after the %s changes', async kind => {
    await runButton(shell()).props.onClick!();
    if (kind === 'draft') draft = { simulation: { start_year: 2030 } };
    const tree = shell(kind === 'scenario' ? { scenarioId: 'b' } : kind === 'workspace' ? { activeWorkspace: { ...context.activeWorkspace, id: 'other' } } : {});
    const panel = reviewPanel(tree)!;
    expect(panel.props.stale).toBe(true);
    expect(await panel.props.onSave()).toBe(false);
    expect(save).not.toHaveBeenCalled(); expect(navigate).not.toHaveBeenCalled();
  });

  it('preserves the review and draft after failed save', async () => {
    save.mockResolvedValue(false);
    await runButton(shell()).props.onClick!();
    expect(await reviewPanel(shell())!.props.onSave()).toBe(false);
    expect(reviewPanel(shell())).toBeDefined();
    expect(navigate).not.toHaveBeenCalled();
  });

  it('prevents duplicate persistence and does not navigate to a new scope', async () => {
    let finish!: (success: boolean) => void;
    save.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    await runButton(shell()).props.onClick!();
    const panel = reviewPanel(shell())!;
    const pending = panel.props.onSave();
    expect(await panel.props.onSave()).toBe(false);
    shell({ scenarioId: 'b' }); finish(true); await pending;
    expect(save).toHaveBeenCalledOnce(); expect(navigate).not.toHaveBeenCalled();
  });

  it('disables Run and editor during a pending save', async () => {
    const tree = shell({ saveStatus: 'saving' });
    expect(find(tree, element => element.type === 'fieldset')!.props.disabled).toBe(true);
    expect(runButton(tree).props.disabled).toBe(true);
    await runButton(tree).props.onClick!();
    expect(save).not.toHaveBeenCalled(); expect(navigate).not.toHaveBeenCalled();
  });

  it('opens review for Save without requesting a run', () => {
    const tree = shell();
    find(tree, element => element.type === 'button' && JSON.stringify(element.props.children).includes('Review changes'))!.props.onClick!();
    const panel = reviewPanel(shell())!;
    expect(panel.props.review.runAfterSave).toBe(false);
    expect(save).not.toHaveBeenCalled();
  });

  it('shows draft-build errors without locking the editor and permits a corrected review', async () => {
    const original = context.buildDraftConfig;
    await runButton(shell({ buildDraftConfig: () => { throw new Error('Custom rows need separate edits'); } })).props.onClick!();
    const tree = shell();
    expect(reviewPanel(tree)).toBeUndefined();
    expect(JSON.stringify(tree)).toContain('Custom rows need separate edits');
    expect(find(tree, element => element.type === 'fieldset')!.props.disabled).toBe(false);
    await runButton(shell({ buildDraftConfig: original })).props.onClick!();
    expect(reviewPanel(shell())).toBeDefined();
    expect(save).not.toHaveBeenCalled();
  });

  it('restores focus to the captured trigger after closing review, including blurred Run', async () => {
    const callbacks: (() => void)[] = [];
    vi.stubGlobal('requestAnimationFrame', (callback: () => void) => { callbacks.push(callback); return 1; });
    const focus = vi.fn();
    class Trigger extends HTMLElement {
      isConnected = true;
      matches = () => false;
      focus = focus;
      blur() { vi.stubGlobal('document', { activeElement: null }); }
    }
    const trigger = new Trigger();
    vi.stubGlobal('document', { activeElement: trigger });
    await runButton(shell()).props.onClick!();
    reviewPanel(shell())!.props.onClose();
    expect(focus).not.toHaveBeenCalled();
    shell(); callbacks.forEach(callback => callback());
    expect(focus).toHaveBeenCalledOnce();
  });
});
