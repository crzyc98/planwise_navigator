import { useChartTheme } from '../hooks/useChartTheme';
import { componentKey, componentShare, type CostChartRow } from './costBreakdown';

interface Props {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: CostChartRow }>;
  label?: string | number;
  scenarioIds: string[];
  names: Record<string, string>;
  colors: Record<string, string>;
}

const currency = (value: number) => value.toLocaleString('en-US', {
  style: 'currency', currency: 'USD', minimumFractionDigits: 2,
});

export default function CostBreakdownTooltip({ active, payload, label, scenarioIds, names, colors }: Props) {
  const theme = useChartTheme();
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  return (
    <div style={theme.tooltip.contentStyle}>
      <div className="font-bold mb-2">{label}</div>
      {scenarioIds.map(id => {
        const match = row[componentKey(id, 'match')];
        const core = row[componentKey(id, 'core')];
        if (match == null || core == null) return null;
        const total = match + core;
        return (
          <div key={id} className="mb-2 text-xs">
            <div className="font-bold" style={{ color: colors[id] }}>{names[id] || id}</div>
            <div>Employer match: {currency(match)} ({componentShare(match, total)})</div>
            <div>Non-elective core: {currency(core)} ({componentShare(core, total)})</div>
            <div className="font-bold">Total: {currency(total)}</div>
          </div>
        );
      })}
    </div>
  );
}
