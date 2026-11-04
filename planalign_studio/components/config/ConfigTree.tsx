import { describeConfigValue, describeScalar, humanizeKey } from './describeConfigValue';

type Row = Record<string, unknown>;
const isRow = (value: unknown): value is Row =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

function TreeValue({ name, value, parent }: Readonly<{ name: string; value: unknown; parent: string }>) {
  if (isRow(value)) {
    return Object.keys(value).length
      ? <ConfigTree name={name} value={value} className="mt-1 border-l border-border pl-3" />
      : <span className="text-ink-muted">None</span>;
  }
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-ink-muted">None</span>;
    return (
      <ul className="mt-0.5 list-disc space-y-0.5 pl-5">
        {value.map((item, index) => <li key={index}>{describeConfigValue(name, item, name)}</li>)}
      </ul>
    );
  }
  return <span>{describeScalar(name, value, parent)}</span>;
}

/** Readable nested view of a configuration object (replaces raw JSON dumps). */
export function ConfigTree({ value, name = '', className = '' }: Readonly<{ value: unknown; name?: string; className?: string }>) {
  if (!isRow(value)) return <div className={`text-xs ${className}`}><TreeValue name={name} value={value} parent="" /></div>;
  return (
    <dl className={`space-y-1 text-xs ${className}`}>
      {Object.entries(value).map(([key, child]) => (
        <div key={key} className={isRow(child) || Array.isArray(child) ? '' : 'flex flex-wrap gap-x-2'}>
          <dt className="text-ink-muted">{humanizeKey(key)}{isRow(child) || Array.isArray(child) ? '' : ':'}</dt>
          <dd className="break-words text-ink"><TreeValue name={key} value={child} parent={name} /></dd>
        </div>
      ))}
    </dl>
  );
}
