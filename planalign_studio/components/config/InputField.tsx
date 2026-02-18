import React from 'react';

export interface InputFieldProps {
  label: string;
  name: string;
  value: any;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  type?: string;
  width?: string;
  suffix?: string;
  helper?: string;
  step?: string;
  min?: number;
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
}) => (
  <div className={`sm:${width}`}>
    <label className="block text-sm font-medium text-gray-700">{label}</label>
    <div className="mt-1 relative rounded-md shadow-sm">
      <input
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
