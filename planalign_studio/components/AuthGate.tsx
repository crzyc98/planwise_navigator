import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Activity, AlertCircle, Loader2, Lock } from 'lucide-react';
import { APP_NAME } from '../constants';
import {
  ApiError,
  AUTH_REQUIRED_EVENT,
  getAuthSession,
  signInWithToken,
  signOutSession,
} from '../services/api';

export interface AuthContextValue {
  authRequired: boolean;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  authRequired: false,
  signOut: async () => undefined,
});

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

export interface SignInScreenProps {
  expired?: boolean;
  onSignedIn: () => void;
}

export function SignInScreen({ expired = false, onSignedIn }: Readonly<SignInScreenProps>) {
  const [token, setToken] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (!token.trim() || submitting) return;

    setSubmitting(true);
    setError(null);
    try {
      await signInWithToken(token);
      setToken('');
      onSignedIn();
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 401) {
        setError(err.detail || 'Invalid access token.');
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Unable to sign in. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface-subtle p-6">
      <div className="w-full max-w-md overflow-hidden rounded-xl border border-border bg-surface-raised shadow-lg">
        <div className="border-b border-border bg-surface-subtle px-6 py-5">
          <div className="flex items-center gap-3">
            <Activity className="h-7 w-7 flex-shrink-0 text-brand-ink" />
            <div>
              <h1 className="text-lg font-bold tracking-tight text-ink">{APP_NAME}</h1>
              <p className="text-xs text-ink-muted">Studio Sign In</p>
            </div>
          </div>
          <p className="mt-3 text-sm text-ink-muted">
            {expired
              ? 'Your session has expired. Enter the API access token to continue.'
              : 'Enter the API access token to open Studio.'}
          </p>
        </div>

        <form onSubmit={(event) => { void handleSubmit(event); }} className="space-y-4 p-6">
          <div>
            <label
              htmlFor="studio-access-token"
              className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-ink-muted"
            >
              <Lock className="h-4 w-4 text-ink-subtle" />
              Access token
            </label>
            <input
              id="studio-access-token"
              type="password"
              autoComplete="current-password"
              autoFocus
              value={token}
              onChange={(event) => setToken(event.target.value)}
              disabled={submitting}
              placeholder="Enter access token"
              className="w-full rounded-lg border border-border-strong bg-surface-input px-3 py-2 text-sm text-ink placeholder:text-ink-subtle focus:border-brand-green focus:outline-none focus:ring-2 focus:ring-focus/30 disabled:bg-surface-disabled disabled:text-ink-disabled"
            />
          </div>

          {error && (
            <p
              role="alert"
              className="rounded-lg border border-danger-border bg-danger-surface px-3 py-2 text-sm text-danger-ink"
            >
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting || !token.trim()}
            className="flex w-full items-center justify-center rounded-lg bg-brand-green px-4 py-2 text-sm font-medium text-ink-inverse transition-colors hover:bg-brand-dark disabled:cursor-not-allowed disabled:bg-surface-disabled disabled:text-ink-disabled"
          >
            {submitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Signing in...
              </>
            ) : (
              'Sign in'
            )}
          </button>
        </form>
      </div>
    </main>
  );
}

type GateState =
  | { phase: 'checking' }
  | { phase: 'error'; message: string }
  | { phase: 'sign_in'; expired: boolean }
  | { phase: 'ready'; authRequired: boolean };

export interface AuthGateProps {
  children: React.ReactNode;
}

export default function AuthGate({ children }: Readonly<AuthGateProps>) {
  const [state, setState] = useState<GateState>({ phase: 'checking' });

  const checkSession = useCallback(async () => {
    setState({ phase: 'checking' });
    try {
      const session = await getAuthSession();
      if (session.auth_required && !session.authenticated) {
        setState({ phase: 'sign_in', expired: false });
      } else {
        setState({ phase: 'ready', authRequired: session.auth_required });
      }
    } catch (err: unknown) {
      setState({
        phase: 'error',
        message: err instanceof Error ? err.message : 'Unable to reach the PlanAlign API.',
      });
    }
  }, []);

  useEffect(() => {
    void checkSession();
  }, [checkSession]);

  useEffect(() => {
    const handleAuthRequired = (): void => {
      setState({ phase: 'sign_in', expired: true });
    };
    window.addEventListener(AUTH_REQUIRED_EVENT, handleAuthRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, handleAuthRequired);
  }, []);

  const signOut = useCallback(async (): Promise<void> => {
    try {
      await signOutSession();
    } catch {
      // Return to sign-in even if the session has already expired server-side.
    }
    setState({ phase: 'sign_in', expired: false });
  }, []);

  const authRequired = state.phase === 'ready' ? state.authRequired : false;
  const contextValue = useMemo<AuthContextValue>(
    () => ({ authRequired, signOut }),
    [authRequired, signOut],
  );

  if (state.phase === 'checking') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-subtle p-6">
        <div className="flex flex-col items-center">
          <Loader2 className="mb-3 h-10 w-10 animate-spin text-brand-ink" />
          <p className="text-sm font-medium text-ink-muted">Checking session...</p>
        </div>
      </div>
    );
  }

  if (state.phase === 'error') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-subtle p-6">
        <div className="flex max-w-md flex-col items-center text-center">
          <AlertCircle className="mb-3 h-10 w-10 text-danger-ink" />
          <p className="mb-2 text-sm font-medium text-ink">Unable to connect to the API</p>
          <p className="mb-4 text-xs text-ink-muted">{state.message}</p>
          <button
            type="button"
            onClick={() => { void checkSession(); }}
            className="rounded-lg bg-brand-green px-4 py-2 text-sm font-medium text-ink-inverse hover:bg-brand-dark"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (state.phase === 'sign_in') {
    return (
      <SignInScreen
        expired={state.expired}
        onSignedIn={() => setState({ phase: 'ready', authRequired: true })}
      />
    );
  }

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
}
