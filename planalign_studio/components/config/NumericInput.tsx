import React, { useEffect, useId, useRef, useState } from 'react';

export interface NumericInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Steppers are reserved for counts/durations, not rates or identifiers. */
  showStepper?: boolean;
  integer?: boolean;
  allowEmpty?: boolean;
}

export function numericError(value: string, { min, max, integer, allowEmpty }: NumericInputProps): string {
  if (!value.trim()) return allowEmpty ? '' : 'Enter a number; use 0 only if you mean zero.';
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value) || !Number.isFinite(Number(value))) return 'Enter a valid number.';
  const number = Number(value);
  if (integer && !Number.isInteger(number)) return 'Enter a whole number.';
  if (min !== undefined && number < Number(min)) return `Enter ${min} or more.`;
  if (max !== undefined && number > Number(max)) return `Enter ${max} or less.`;
  return '';
}

/** Keep unfinished input local instead of allowing legacy handlers to coerce it to zero. */
export function NumericInput({ value, onChange, onBlur, onFocus, className = '',
  showStepper = false, integer = false, allowEmpty, placeholder, step: _step, type: _type,
  ...props }: NumericInputProps) {
  const optional = allowEmpty ?? placeholder === '∞';
  const [draft, setDraft] = useState(String(value ?? ''));
  const [error, setError] = useState('');
  const errorId = useId();
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    setDraft(previous => previous.trim() && Number(previous) === Number(value) ? previous : String(value ?? ''));
    setError('');
    input.current?.setCustomValidity('');
  }, [value]);
  const constraints = { ...props, integer, allowEmpty: optional };
  return <>
    <input {...props} ref={input} value={draft} placeholder={placeholder}
      type={showStepper ? 'number' : 'text'} inputMode={integer ? 'numeric' : 'decimal'}
      step={showStepper && Number.isInteger(Number(value)) ? 1 : 'any'} data-config-number="true"
      className={`${className} tabular-nums ${error ? 'border-danger-border' : ''}`}
      aria-invalid={!!error || props['aria-invalid'] || undefined}
      aria-describedby={[props['aria-describedby'], error ? errorId : ''].filter(Boolean).join(' ') || undefined}
      onFocus={event => { event.currentTarget.select(); onFocus?.(event); }}
      onChange={event => {
        const next = event.currentTarget.value;
        const message = numericError(next, constraints);
        setDraft(next); setError(message); event.currentTarget.setCustomValidity(message);
        if (!message) onChange?.(event);
      }}
      onBlur={event => {
        // Preserve untouched inherited values even if newer editor constraints differ.
        const changed = draft !== String(value ?? '');
        const message = changed ? numericError(draft, constraints) : error;
        setError(message); event.currentTarget.setCustomValidity(message);
        if (!message) onBlur?.(event);
      }} />
    {error && <span id={errorId} role="alert" className="block text-xs text-danger-ink mt-1">{error}</span>}
  </>;
}

/** Review and Run must not bypass a local unfinished edit. */
export function validateNumericInputs(): boolean {
  const inputs = document.querySelectorAll?.<HTMLInputElement>('[data-config-number]');
  for (const input of inputs ?? []) {
    if (input.matches(':disabled') || !input.validity.customError) continue;
    let parent = input.parentElement;
    while (parent) {
      if (parent instanceof HTMLDetailsElement) parent.open = true;
      parent = parent.parentElement;
    }
    input.focus(); input.reportValidity();
    return false;
  }
  return true;
}
