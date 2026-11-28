import type React from 'react';
import { pickFormula } from './designParameters';
import type { FormScope } from './formScope';
import { CORE_FORMULA_KEYS, MATCH_FORMULA_KEYS } from './types';
import type { FormData } from './types';

const FORMULA_KEYS: readonly string[] = [...MATCH_FORMULA_KEYS, ...CORE_FORMULA_KEYS];

/**
 * The plan-wide form as the new-hire design sees it: its own match and core
 * formula over the shared settings. Edits change only the new-hire formula.
 */
export function newHireScope(main: FormScope): FormScope {
  const formula = main.formData.dcGrandfather?.newHireFormula;
  const formData: FormData = { ...main.formData, ...formula };
  const setFormData = (update: (previous: FormData) => FormData) => main.setFormData(previous => {
    const design = previous.dcGrandfather;
    if (!design) return previous;
    const next = update({ ...previous, ...design.newHireFormula });
    return { ...previous, dcGrandfather: { ...design, newHireFormula: pickFormula(next) } };
  });
  const handleChange = (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = event.target;
    if (!FORMULA_KEYS.includes(name)) return;
    const next = type === 'checkbox' ? (event.target as HTMLInputElement).checked : value;
    setFormData(previous => ({ ...previous, [name]: next }));
  };
  const inputProps = (name: string) => ({ name, value: formData[name as keyof FormData], onChange: handleChange });
  return { formData, setFormData, handleChange, inputProps };
}
