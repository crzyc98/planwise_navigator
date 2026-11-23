import React from 'react';
import type { FormEvent, ReactElement, ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AuthGate, { SignInScreen } from './AuthGate';
import {
  ApiError,
  AUTH_REQUIRED_EVENT,
  fetchWithAuth,
  getAuthSession,
  signInWithToken,
  signOutSession,
} from '../services/api';

const hooks = vi.hoisted(() => ({
  slot: 0,
  cells: [] as unknown[],
  effects: [] as Array<() => void | (() => void)>,
  cleanups: [] as Array<() => void>,
  effectRan: new Set<number>(),
}));

vi.mock('react', async importOriginal => {
  const actual = await importOriginal<typeof import('react')>();
  return {
    ...actual,
    useState: (initial: unknown) => {
      const slot = hooks.slot++;
      if (!(slot in hooks.cells)) {
        hooks.cells[slot] = typeof initial === 'function' ? (initial as () => unknown)() : initial;
      }
      const setState = (next: unknown) => {
        hooks.cells[slot] = typeof next === 'function'
          ? (next as (prev: unknown) => unknown)(hooks.cells[slot])
          : next;
      };
      return [hooks.cells[slot], setState];
    },
    useEffect: (effect: () => void | (() => void)) => {
      const slot = hooks.slot++;
      if (!hooks.effectRan.has(slot)) {
        hooks.effectRan.add(slot);
        hooks.effects.push(effect);
      }
    },
    useCallback: <T extends (...args: never[]) => unknown>(fn: T) => fn,
    useMemo: <T,>(factory: () => T) => factory(),
  };
});

vi.mock('../services/api', async importOriginal => {
  const actual = await importOriginal<typeof import('../services/api')>();
  return {
    ...actual,
    getAuthSession: vi.fn(),
    signInWithToken: vi.fn(),
    signOutSession: vi.fn(),
  };
});

interface ElementProps {
  children?: ReactNode;
  type?: string;
  onChange?: (event: { target: { value: string } }) => void;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  onSignedIn?: () => void;
  expired?: boolean;
  role?: string;
}

function findElement(
  node: ReactNode,
  predicate: (element: ReactElement<ElementProps>) => boolean,
): ReactElement<ElementProps> | undefined {
  if (Array.isArray(node)) {
    return node.map(child => findElement(child, predicate)).find(Boolean);
  }
  if (!node || typeof node !== 'object' || !('props' in node)) return undefined;
  const element = node as ReactElement<ElementProps>;
  return predicate(element) ? element : findElement(element.props.children, predicate);
}

function resetHooks(): void {
  for (const cleanup of hooks.cleanups) cleanup();
  hooks.slot = 0;
  hooks.cells = [];
  hooks.effects = [];
  hooks.cleanups = [];
  hooks.effectRan.clear();
}

function flushEffects(): void {
  const pending = hooks.effects.splice(0);
  for (const effect of pending) {
    const cleanup = effect();
    if (typeof cleanup === 'function') hooks.cleanups.push(cleanup);
  }
}

async function flushMicrotasks(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

function renderGate(): ReactElement<ElementProps> {
  hooks.slot = 0;
  const tree = AuthGate({ children: <div data-app="studio-app">Studio App</div> }) as ReactElement<ElementProps>;
  flushEffects();
  return tree;
}

function renderSignIn(props: { expired?: boolean; onSignedIn: () => void }): ReactElement<ElementProps> {
  hooks.slot = 0;
  return SignInScreen(props) as ReactElement<ElementProps>;
}

describe('AuthGate sign-in flow', () => {
  let listeners: Map<string, Set<EventListener>>;

  beforeEach(() => {
    vi.clearAllMocks();
    resetHooks();
    listeners = new Map();
    vi.stubGlobal('window', {
      addEventListener: (type: string, listener: EventListener) => {
        const set = listeners.get(type) ?? new Set();
        set.add(listener);
        listeners.set(type, set);
      },
      removeEventListener: (type: string, listener: EventListener) => {
        listeners.get(type)?.delete(listener);
      },
      dispatchEvent: (event: Event) => {
        listeners.get(event.type)?.forEach(listener => listener(event));
        return true;
      },
    });
  });

  afterEach(() => {
    resetHooks();
    vi.unstubAllGlobals();
  });

  it('shows the sign-in screen when auth is required and unauthenticated, then hides after sign-in', async () => {
    vi.mocked(getAuthSession).mockResolvedValue({ auth_required: true, authenticated: false });

    renderGate();
    await flushMicrotasks();

    const gated = renderGate();
    expect(gated.type).toBe(SignInScreen);
    expect(gated.props.expired).toBe(false);

    const html = renderToStaticMarkup(<SignInScreen expired={false} onSignedIn={vi.fn()} />);
    expect(html).toContain('type="password"');
    expect(html).toContain('Sign in');

    gated.props.onSignedIn?.();
    const unlocked = renderGate();
    expect(unlocked.type).not.toBe(SignInScreen);
    expect(findElement(unlocked, el => el.props.children === 'Studio App')).toBeDefined();
  });

  it('skips the sign-in screen when authentication is not required', async () => {
    vi.mocked(getAuthSession).mockResolvedValue({ auth_required: false, authenticated: false });

    renderGate();
    await flushMicrotasks();

    const tree = renderGate();
    expect(tree.type).not.toBe(SignInScreen);
    expect(findElement(tree, el => el.props.children === 'Studio App')).toBeDefined();
  });

  it('returns to the sign-in screen when a subsequent API call returns 401', async () => {
    vi.mocked(getAuthSession).mockResolvedValue({ auth_required: true, authenticated: true });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })));

    renderGate();
    await flushMicrotasks();

    const ready = renderGate();
    expect(ready.type).not.toBe(SignInScreen);

    await fetchWithAuth('/api/workspaces');

    const reGated = renderGate();
    expect(reGated.type).toBe(SignInScreen);
    expect(reGated.props.expired).toBe(true);
  });

  it('does not trigger session-expired state when POST /api/auth/session returns 401', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'Invalid PlanAlign API token.' }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    )));

    await fetchWithAuth('/api/auth/session', { method: 'POST', body: JSON.stringify({ token: 'bad' }) });

    expect(dispatchSpy).not.toHaveBeenCalledWith(expect.objectContaining({ type: AUTH_REQUIRED_EVENT }));
  });

  it('sends credentials include and no token header from fetchWithAuth', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await fetchWithAuth('/api/workspaces');

    expect(fetchMock).toHaveBeenCalledWith('/api/workspaces', { credentials: 'include' });
  });

  it('shows an error line when sign-in rejects a token and succeeds on a valid token', async () => {
    const onSignedIn = vi.fn();
    vi.mocked(signInWithToken)
      .mockRejectedValueOnce(new ApiError(401, 'Unauthorized', 'Invalid PlanAlign API token.'))
      .mockResolvedValueOnce(undefined);

    let tree = renderSignIn({ onSignedIn });
    const input = findElement(tree, el => el.type === 'input' && el.props.type === 'password')!;
    input.props.onChange?.({ target: { value: 'wrong-token-value' } });

    tree = renderSignIn({ onSignedIn });
    const form = findElement(tree, el => el.type === 'form')!;
    form.props.onSubmit?.({ preventDefault: vi.fn() } as unknown as FormEvent<HTMLFormElement>);
    await flushMicrotasks();

    tree = renderSignIn({ onSignedIn });
    const alert = findElement(tree, el => el.props.role === 'alert');
    expect(alert?.props.children).toBe('Invalid PlanAlign API token.');
    expect(onSignedIn).not.toHaveBeenCalled();

    const retryInput = findElement(tree, el => el.type === 'input' && el.props.type === 'password')!;
    retryInput.props.onChange?.({ target: { value: 'valid-token-value' } });
    tree = renderSignIn({ onSignedIn });
    const retryForm = findElement(tree, el => el.type === 'form')!;
    retryForm.props.onSubmit?.({ preventDefault: vi.fn() } as unknown as FormEvent<HTMLFormElement>);
    await flushMicrotasks();

    expect(signInWithToken).toHaveBeenLastCalledWith('valid-token-value');
    expect(onSignedIn).toHaveBeenCalledOnce();
  });

  it('signs out via DELETE /api/auth/session and returns to the sign-in screen', async () => {
    vi.mocked(getAuthSession).mockResolvedValue({ auth_required: true, authenticated: true });
    vi.mocked(signOutSession).mockResolvedValue(undefined);

    renderGate();
    await flushMicrotasks();

    const providerTree = renderGate() as unknown as ReactElement<{
      value: { authRequired: boolean; signOut: () => Promise<void> };
    }>;
    expect(providerTree.props.value.authRequired).toBe(true);

    await providerTree.props.value.signOut();
    expect(signOutSession).toHaveBeenCalledOnce();

    const afterSignOut = renderGate();
    expect(afterSignOut.type).toBe(SignInScreen);
    expect(afterSignOut.props.expired).toBe(false);
  });
});
