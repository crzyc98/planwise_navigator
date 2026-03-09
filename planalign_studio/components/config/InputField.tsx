import React, { useId } from 'react';

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
  min
}) => {
  const generatedId = useId();
  const inputId = `input-${name}-${generatedId}`;
  return (
  <div className={`sm:${width}`}>
    <label htmlFor={inputId} className="block text-sm font-medium text-gray-700">{label}</label>
    <div className="mt-1 relative rounded-md shadow-sm">
      <input
        id={inputId}
        type={type}
        name={name}
        value={value}
        onChange={onChange}
        step={step}
        min={min}
        className="shadow-sm focus:ring-fidelity-green focus:border-fidelity-green block w-full sm:text-sm border-gray-300 rounded-md p-2 border"
      />
      {suffix && (
        <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
          <span className="text-gray-500 sm:text-sm">{suffix}</span>
        </div>
      )}
    </div>
    {helper && <p className="mt-1 text-xs text-gray-500">{helper}</p>}
  </div>
  );
};
