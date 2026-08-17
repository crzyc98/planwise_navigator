import type { CSSProperties } from 'react';

import paletteSource from './chart-palettes.json';
import type { ResolvedTheme } from './theme';

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
    contentStyle: CSSProperties;
    cursorStyle: { fill: string };
    text: string;
    mutedText: string;
  };
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
  colorAt: (index: number) => string;
}

function toCategoricalRamp(colors: string[]): CategoricalRamp {
  if (colors.length !== 6) {
    throw new Error(`Chart palette must contain 6 colors; received ${colors.length}`);
  }
  return colors as unknown as CategoricalRamp;
}

function colorAt(ramp: CategoricalRamp, index: number): string {
  const length = ramp.length;
  const normalizedIndex = ((index % length) + length) % length;
  return ramp[normalizedIndex];
}

function createChartTheme(
  mode: ResolvedTheme,
  categorical: CategoricalRamp,
): ChartTheme {
  const isDark = mode === 'dark';
  const grid = isDark ? '#343633' : '#E5E7EB';
  const axis = isDark ? '#B7BBB3' : '#6B7280';
  const tooltipBackground = isDark ? '#1A1A19' : '#FFFFFF';
  const tooltipText = isDark ? '#F5F5F4' : '#111827';
  const mutedText = isDark ? '#D1D5DB' : '#4B5563';

  return Object.freeze({
    mode,
    grid: Object.freeze({
      line: grid,
      cursor: isDark ? '#2D2F2C' : '#F3F4F6',
      reference: isDark ? '#73776F' : '#9CA3AF',
    }),
    axis: Object.freeze({ line: axis, tick: axis, label: mutedText }),
    tooltip: Object.freeze({
      contentStyle: Object.freeze({
        backgroundColor: tooltipBackground,
        borderColor: grid,
        color: tooltipText,
        borderRadius: '8px',
      }),
      cursorStyle: Object.freeze({ fill: isDark ? '#2D2F2C' : '#F3F4F6' }),
      text: tooltipText,
      mutedText,
    }),
    legendText: tooltipText,
    categorical,
    semantic: Object.freeze({
      primary: isDark ? '#4CAF50' : '#00853F',
      positive: isDark ? '#4CAF50' : '#00853F',
      negative: isDark ? '#F07A54' : '#D55E00',
      neutral: isDark ? '#A8ACA4' : '#6B7280',
      warning: isDark ? '#D18A18' : '#D97706',
      anchor: isDark ? '#E7E5E4' : '#1E293B',
      frontierOutline: isDark ? '#FFFFFF' : '#000000',
      contribution: Object.freeze({
        employee: categorical[0],
        match: categorical[1],
        core: categorical[2],
        total: categorical[3],
      }),
    }),
    colorAt: (index: number) => colorAt(categorical, index),
  });
}

const lightRamp = toCategoricalRamp(paletteSource.runtime.light);
const darkRamp = toCategoricalRamp(paletteSource.runtime.dark);

export const CHART_THEMES: Readonly<Record<ResolvedTheme, ChartTheme>> = Object.freeze({
  light: createChartTheme('light', lightRamp),
  dark: createChartTheme('dark', darkRamp),
});
