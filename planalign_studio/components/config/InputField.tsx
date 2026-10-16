import React, { useId } from 'react';
import { NumericInput } from './NumericInput';

export interface InputFieldProps {
  readonly label: string;
  readonly name: string;
  readonly value: any;
  readonly onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  readonly type?: string;
  readonly width?: string;
  readonly suffix?: string;
  readonly helper?: string;
  readonly step?: string;
  readonly min?: number;
  readonly max?: number;
  readonly placeholder?: string;
  readonly disabled?: boolean;
}

export const InputField: React.FC<InputFieldProps> = ({
  label,
  name,
  value,
  onChange,
  type = "text",
  width = "col-span-3",
  suffix = "",
  helper = "",
  step = "1",
  min,
  max,
  placeholder,
  disabled = false,
}) => {
  const generatedId = useId();
  const inputId = `input-${name}-${generatedId}`;
  const numeric = type === 'number';
  const duration = /^(Days|Months|Years|Hours)$/i.test(suffix);
  const Input = numeric ? NumericInput : 'input';
  return (
  <div className={`sm:${width}`}>
    <label htmlFor={inputId} className="block text-sm font-medium text-ink-muted">{label}</label>
    <div className="mt-1 flex items-start gap-2">
      <div className="min-w-0 flex-1">
      <Input
        id={inputId}
        type={type}
        name={name}
        value={value}
        onChange={onChange}
        step={step}
        min={min}
        max={max}
        placeholder={placeholder}
        disabled={disabled}
        {...(numeric ? { showStepper: duration, integer: duration || ['seed', 'startYear', 'endYear'].includes(name) } : {})}
        aria-describedby={[suffix ? `${inputId}-unit` : '', helper ? `${inputId}-help` : ''].filter(Boolean).join(' ') || undefined}
        className="shadow-sm focus:ring-fidelity-green focus:border-fidelity-green block w-full sm:text-sm border-border-strong rounded-md p-2 border disabled:bg-surface-disabled disabled:text-ink-muted disabled:cursor-not-allowed"
      />
      </div>
      {suffix && (
        <span id={`${inputId}-unit`} className="shrink-0 pt-2 text-ink-muted text-sm whitespace-nowrap">{suffix}</span>
      )}
    </div>
    {helper && <p id={`${inputId}-help`} className="mt-1 text-xs text-ink-muted">{helper}</p>}
  </div>
  );
};
