import { useState, useEffect } from 'react';

// E044: Helper component for salary range inputs with onBlur commit pattern
export function CompensationInput({ value, onCommit, hasError, step = 500, min = 0 }: {
  value: number;
  onCommit: (v: number) => void;
  hasError?: boolean;
  step?: number;
  min?: number;
}) {
  const [localValue, setLocalValue] = useState(String(value));

  useEffect(() => {
    setLocalValue(String(value));
  }, [value]);

  const commit = () => {
    const parsed = parseFloat(localValue) || 0;
    const clamped = Math.max(parsed, min);
    onCommit(clamped);
    setLocalValue(String(clamped));
  };

  return (
    <input
      type="number"
      step={step}
      min={min}
      value={localValue}
      onChange={(e) => setLocalValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === 'Enter') commit(); }}
      className={`w-36 shadow-sm sm:text-sm rounded-md p-1 border text-right focus:ring-fidelity-green focus:border-fidelity-green ${
        hasError ? 'border-red-500' : 'border-gray-300'
      }`}
    />
  );
}
