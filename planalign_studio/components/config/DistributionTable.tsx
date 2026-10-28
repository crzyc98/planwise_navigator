import { NumericInput } from './NumericInput';
import { distributionTotal, invalidDistribution } from './participantBehaviorConfig';

interface Props {
  titleId: string;
  rows: { value: number; share: number }[];
  valueHeading: string;
  valueLabel?: string;
  weightLabel?: string;
  shareHeading: string;
  rowLabel: string;
  removeLabel?: string;
  valueSuffix: string;
  shareSuffix?: string;
  integer?: boolean;
  max?: number;
  active: boolean;
  errorId: string;
  invalidValue: (index: number) => boolean;
  onChange: (index: number, changes: { value?: number; share?: number }) => void;
  onRemove: (index: number) => void;
  onAdd: () => void;
  addLabel: string;
}

/** Shared editable percentage distribution for starting-rate assumptions. */
export function DistributionTable(props: Props) {
  const { rows, active, errorId } = props;
  const errorProps = (invalid: boolean) => ({
    'aria-invalid': invalid && active || undefined,
    'aria-describedby': invalid && active ? errorId : undefined,
  });
  const inputClass = 'w-20 px-2 py-1 border border-border-strong rounded text-sm disabled:bg-surface-disabled';
  const buttonClass = 'px-3 py-1.5 text-sm border border-border-strong rounded-lg disabled:opacity-50';
  return <>
    <div className="overflow-x-auto">
      <table className="w-full text-sm" aria-labelledby={props.titleId}>
        <thead><tr className="border-b border-border"><th scope="col" className="text-left p-2">{props.valueHeading}</th><th scope="col" className="text-left p-2">{props.shareHeading}</th><th scope="col" className="text-left p-2">Actions</th></tr></thead>
        <tbody>{rows.map((row, index) => <tr key={index} className="border-b border-border">
          <td className="p-2 whitespace-nowrap"><NumericInput aria-label={`${props.rowLabel} ${index + 1} ${props.valueLabel ?? (props.integer ? 'in percentage points' : 'contribution rate')}`} value={row.value} integer={props.integer} min={props.integer ? 1 : 0} max={props.max} className={inputClass}
            {...errorProps(props.invalidValue(index))} onChange={event => props.onChange(index, { value: Number(event.target.value) })} /> {props.valueSuffix}</td>
          <td className="p-2 whitespace-nowrap"><NumericInput aria-label={`${props.rowLabel} ${index + 1} ${props.weightLabel ?? (props.integer ? 'weight' : 'share')}`} value={row.share} min={0} max={100} className={inputClass}
            {...errorProps(invalidDistribution(rows.map(item => item.share)))} onChange={event => props.onChange(index, { share: Number(event.target.value) })} /> %{props.shareSuffix}</td>
          <td className="p-2"><button type="button" className={buttonClass} disabled={rows.length === 1} aria-label={`Remove ${props.removeLabel ?? props.rowLabel.toLowerCase()} ${index + 1}`}
            onClick={() => props.onRemove(index)}>Remove</button></td>
        </tr>)}</tbody>
      </table>
    </div>
    <p className="text-xs text-ink-muted">Total {props.integer ? 'weight' : 'share'}: {distributionTotal(rows.map(row => row.share))}%</p>
    <button type="button" className={buttonClass} onClick={props.onAdd}>{props.addLabel}</button>
  </>;
}
