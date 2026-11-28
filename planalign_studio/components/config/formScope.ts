import type React from 'react';
import type { FormData } from './types';

/** The form a formula editor reads and writes: the plan-wide form, or one plan design's view of it. */
export interface FormScope {
  formData: FormData;
  setFormData: (update: (previous: FormData) => FormData) => void;
  handleChange: (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => void;
  inputProps: (name: string) => {
    name: string;
    value: FormData[keyof FormData];
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => void;
  };
}

export interface FormulaFieldsProps {
  scope: FormScope;
  /** Prefix for element ids, so two copies of an editor can share a page. */
  idPrefix?: string;
  /** Plan-wide eligibility rules, shown only with the plan-wide formula. */
  eligibility?: React.ReactNode;
}
