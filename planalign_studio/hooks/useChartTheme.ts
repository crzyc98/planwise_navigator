import { CHART_THEMES, ChartTheme } from '../theme/chartTheme';
import { useTheme } from './useTheme';

export function useChartTheme(): ChartTheme {
  const { resolvedTheme } = useTheme();
  return CHART_THEMES[resolvedTheme];
}
