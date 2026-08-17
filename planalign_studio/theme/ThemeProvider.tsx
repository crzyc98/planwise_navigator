import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {
  clearExplicitThemePreference,
  isExplicitThemePreference,
  readExplicitThemePreference,
  resolveTheme,
  SYSTEM_THEME_QUERY,
  THEME_STORAGE_KEY,
  ThemeContext,
  type ResolvedTheme,
  type ThemePreference,
  writeExplicitThemePreference,
} from './theme';

interface ThemeProviderProps {
  children: React.ReactNode;
}

function createMediaQuery(): MediaQueryList | null {
  return typeof window === 'undefined'
    ? null
    : window.matchMedia(SYSTEM_THEME_QUERY);
}

function initialPreference(): ThemePreference {
  return readExplicitThemePreference() ?? 'system';
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const mediaQueryRef = useRef<MediaQueryList | null>(null);
  if (mediaQueryRef.current === null) {
    mediaQueryRef.current = createMediaQuery();
  }

  const [preference, setPreferenceState] = useState<ThemePreference>(initialPreference);
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() =>
    resolveTheme(initialPreference(), mediaQueryRef.current ?? undefined),
  );

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.style.colorScheme = resolvedTheme;
  }, [resolvedTheme]);

  useEffect(() => {
    const mediaQuery = mediaQueryRef.current;
    if (preference !== 'system' || !mediaQuery) return;

    const handleSystemThemeChange = (event: MediaQueryListEvent) => {
      setResolvedTheme(event.matches ? 'dark' : 'light');
    };
    mediaQuery.addEventListener('change', handleSystemThemeChange);
    return () => mediaQuery.removeEventListener('change', handleSystemThemeChange);
  }, [preference]);

  useEffect(() => {
    const handleStorageChange = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY) return;
      const next = isExplicitThemePreference(event.newValue)
        ? event.newValue
        : 'system';
      setPreferenceState(next);
      setResolvedTheme(resolveTheme(next, mediaQueryRef.current ?? undefined));
    };
    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  const setPreference = useCallback((next: ThemePreference) => {
    if (next === 'system') {
      clearExplicitThemePreference();
    } else {
      writeExplicitThemePreference(next);
    }
    setPreferenceState(next);
    setResolvedTheme(resolveTheme(next, mediaQueryRef.current ?? undefined));
  }, []);

  const toggleTheme = useCallback(() => {
    setPreference(resolvedTheme === 'dark' ? 'light' : 'dark');
  }, [resolvedTheme, setPreference]);

  const resetTheme = useCallback(() => {
    setPreference('system');
  }, [setPreference]);

  const value = useMemo(
    () => ({
      preference,
      resolvedTheme,
      setPreference,
      toggleTheme,
      resetTheme,
    }),
    [preference, resolvedTheme, resetTheme, setPreference, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
