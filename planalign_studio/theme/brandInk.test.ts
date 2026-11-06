import { describe, expect, it } from 'vitest';

const sources = import.meta.glob<string>(
  ['../**/*.tsx', '!../node_modules/**', '!../dist/**'],
  { query: '?raw', import: 'default', eager: true },
);

describe('brand text colors', () => {
  it('uses theme-aware brand ink, since fixed brand greens are unreadable in dark mode', () => {
    const offenders = Object.entries(sources)
      .filter(([, source]) => /\btext-brand-(green|dark)\b/.test(source))
      .map(([path]) => path);

    expect(Object.keys(sources).length).toBeGreaterThan(50);
    expect(offenders).toEqual([]);
  });
});
