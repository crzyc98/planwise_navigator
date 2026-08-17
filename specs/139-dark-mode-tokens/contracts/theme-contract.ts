/**
 * Normative design contract for feature 139. This file documents the intended
 * public frontend interfaces; implementation types live under
 * planalign_studio/theme and planalign_studio/hooks.
 */

export type ThemePreference = 'system' | 'light' | 'dark';
export type ResolvedTheme = 'light' | 'dark';

export interface ThemeContextValue {
  /** User intent. `system` is represented by no persisted override. */
  preference: ThemePreference;
  /** Concrete theme currently applied to the document. */
  resolvedTheme: ResolvedTheme;
  /** Set System, Light, or Dark without remounting application routes. */
  setPreference: (preference: ThemePreference) => void;
  /** Select the opposite of the currently resolved theme as an explicit value. */
  toggleTheme: () => void;
  /** Remove the explicit value and resume live operating-system following. */
  resetTheme: () => void;
}

export type CategoricalRamp = readonly [
  string,
  string,
  string,
  string,
  string,
  string,
];

export interface ChartTheme {
  mode: ResolvedTheme;
  grid: {
    line: string;
    cursor: string;
    reference: string;
  };
  axis: {
    line: string;
    tick: string;
    label: string;
  };
  tooltip: {
    contentStyle: Readonly<{
      backgroundColor: string;
      borderColor: string;
      color: string;
      borderRadius: string;
    }>;
    cursorStyle: Readonly<{ fill: string }>;
    text: string;
    mutedText: string;
  };
  /** Neutral readable legend text; swatches carry series identity. */
  legendText: string;
  categorical: CategoricalRamp;
  semantic: {
    primary: string;
    positive: string;
    negative: string;
    neutral: string;
    warning: string;
    anchor: string;
    frontierOutline: string;
    contribution: {
      employee: string;
      match: string;
      core: string;
      total: string;
    };
  };
  /** Preserve current over-capacity behavior with normalized modulo lookup. */
  colorAt: (index: number) => string;
}

export interface ThemeHooks {
  useTheme: () => ThemeContextValue;
  useChartTheme: () => ChartTheme;
}

/**
 * Persistence contract:
 * - one versioned per-origin key;
 * - only `light` and `dark` are persisted;
 * - key absence, invalid data, or a storage exception means `system`;
 * - bootstrap and provider accept exactly the same values/key.
 */
export interface ThemePersistenceContract {
  readonly storageKey: string;
  readExplicitPreference: () => Exclude<ThemePreference, 'system'> | null;
  writeExplicitPreference: (
    preference: Exclude<ThemePreference, 'system'>,
  ) => void;
  clearExplicitPreference: () => void;
}
