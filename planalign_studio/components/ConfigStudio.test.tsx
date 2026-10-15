import { ReactElement, ReactNode, useRef } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConfigShell } from './ConfigStudio';
import { ConfigContextType, useConfigContext } from './config/ConfigContext';

const navigate = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useWorkspaceNavigation', () => ({ useWorkspaceNavigate: () => navigate }));
vi.mock('./config/ConfigContext', () => ({ useConfigContext: vi.fn(), ConfigProvider: vi.fn() }));
// Inspect the shell's actual button handlers without requiring a DOM dependency.
vi.mock('react', async importOriginal => ({
  ...await importOriginal<typeof import('react')>(),
  useState: (initial: unknown) => [initial, vi.fn()],
  useRef: vi.fn((initial: unknown) => ({ current: initial })),
}));

interface ElementProps { children?: ReactNode; onClick?: () => Promise<void>; disabled?: boolean }

function findRunButton(node: ReactNode): ReactElement<ElementProps> | undefined {
  if (Array.isArray(node)) {
    return node.map(findRunButton).find(Boolean);
  }
  if (!node || typeof node !== 'object' || !('props' in node)) return undefined;
  const element = node as ReactElement<ElementProps>;
  if (element.type === 'button' && Array.isArray(element.props.children)
    && element.props.children.some(child => child === 'Save & Run' || child === 'Run Simulation')) return element;
  return findRunButton(element.props.children);
}

const save = vi.fn<() => Promise<boolean>>();
function shell(overrides: Partial<ConfigContextType> = {}) {
  vi.mocked(useConfigContext).mockReturnValue({
    currentScenario: null, scenarioId: 'synthetic', scenarioLoading: false,
    dirtySections: new Set(), isDirty: true, handleSaveConfig: save,
    saveStatus: 'idle', saveMessage: '', activeWorkspace: { id: 'w' },
    ...overrides,
  } as ConfigContextType);
  const tree = ConfigShell();
  return { tree, button: findRunButton(tree)! };
}

describe('Configure Run action', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('document', { activeElement: null });
    vi.stubGlobal('HTMLElement', class {});
  });

  it('labels dirty edits Save & Run and waits for successful persistence', async () => {
    let finish!: (success: boolean) => void;
    save.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const { button } = shell();
    expect(button.props.children).toContain('Save & Run');
    const pending = button.props.onClick!();
    expect(save).toHaveBeenCalledOnce();
    expect(navigate).not.toHaveBeenCalled();
    await button.props.onClick!();
    expect(save).toHaveBeenCalledOnce();
    finish(true);
    await pending;
    expect(navigate).toHaveBeenCalledExactlyOnceWith('/simulate?scenario=synthetic');
  });

  it.each(['validation', 'network'])('stays on configuration when %s save fails', async () => {
    save.mockResolvedValue(false);
    await shell({ saveStatus: 'error', saveMessage: 'Save failed' }).button.props.onClick!();
    expect(save).toHaveBeenCalledOnce();
    expect(navigate).not.toHaveBeenCalled();
  });

  it('keeps clean runs unchanged without saving', async () => {
    const { button } = shell({ isDirty: false });
    expect(button.props.children).toContain('Run Simulation');
    await button.props.onClick!();
    expect(save).not.toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledExactlyOnceWith('/simulate?scenario=synthetic');
  });

  it('saves edits committed on blur even when the initial render was clean', async () => {
    save.mockResolvedValue(true);
    const { button } = shell({ isDirty: false });
    const dirtyRef = vi.mocked(useRef).mock.results.at(-1)!.value;
    const blur = vi.fn(() => { dirtyRef.current = true; });
    class BufferedInput extends HTMLElement { blur = blur; }
    vi.stubGlobal('document', { activeElement: new BufferedInput() });
    await button.props.onClick!();
    expect(blur).toHaveBeenCalledOnce();
    expect(save).toHaveBeenCalledOnce();
    expect(navigate).toHaveBeenCalledExactlyOnceWith('/simulate?scenario=synthetic');
  });

  it('disables the editor and Run during a pending save', async () => {
    const { tree, button } = shell({ saveStatus: 'saving' });
    expect(tree.type).toBe('fieldset');
    expect(tree.props.disabled).toBe(true);
    expect(button.props.disabled).toBe(true);
    await button.props.onClick!();
    expect(save).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });
});
