import { createContext } from 'react';

export type ThemePreference = 'system' | 'light' | 'dark';
export type ExplicitThemePreference = Exclude<ThemePreference, 'system'>;
export type ResolvedTheme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'planalign.theme.v1';
export const SYSTEM_THEME_QUERY = '(prefers-color-scheme: dark)';

export interface ThemeContextValue {
  preference: ThemePreference;
  resolvedTheme: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
  toggleTheme: () => void;
  resetTheme: () => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function isExplicitThemePreference(
  value: string | null,
): value is ExplicitThemePreference {
  return value === 'light' || value === 'dark';
}

export function readExplicitThemePreference(): ExplicitThemePreference | null {
  try {
    if (typeof window === 'undefined') return null;
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isExplicitThemePreference(value) ? value : null;
  } catch {
    return null;
  }
}

export function writeExplicitThemePreference(
  preference: ExplicitThemePreference,
): void {
  try {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(THEME_STORAGE_KEY, preference);
    }
  } catch {
    // Storage may be unavailable in hardened/private browser contexts.
  }
}

export function clearExplicitThemePreference(): void {
  try {
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(THEME_STORAGE_KEY);
    }
  } catch {
    // System preference remains a safe fallback when storage is unavailable.
  }
}

export function resolveSystemTheme(mediaQuery?: MediaQueryList): ResolvedTheme {
  if (typeof window === 'undefined') return 'light';
  const query = mediaQuery ?? window.matchMedia(SYSTEM_THEME_QUERY);
  return query.matches ? 'dark' : 'light';
}

export function resolveTheme(
  preference: ThemePreference,
  mediaQuery?: MediaQueryList,
): ResolvedTheme {
  return preference === 'system' ? resolveSystemTheme(mediaQuery) : preference;
}
