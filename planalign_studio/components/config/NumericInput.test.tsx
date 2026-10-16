import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { numericError, NumericInput, type NumericInputProps } from './NumericInput';

vi.mock('react', async original => ({
  ...await original<typeof import('react')>(),
  useState: (value: unknown) => [value, vi.fn()],
  useEffect: vi.fn(), useId: () => 'numeric-error', useRef: () => ({ current: null }),
}));

function input(props: NumericInputProps = {}) {
  const tree = NumericInput({ value: 3.5, ...props });
  return tree.props.children[0] as React.ReactElement<React.InputHTMLAttributes<HTMLInputElement>>;
}

describe('numeric configuration entry', () => {
  it('uses direct decimal entry without stepping or rounding percentages', () => {
    const field = input({ step: 5 });
    expect(field.props.type).toBe('text');
    expect(field.props.inputMode).toBe('decimal');
    expect(numericError('3.125', { min: 0, max: 100 })).toBe('');
  });

  it('keeps whole-number duration stepping separate from rate entry', () => {
    expect(input({ value: 30, integer: true, showStepper: true }).props.step).toBe(1);
    expect(numericError('1.5', { integer: true })).toBe('Enter a whole number.');
    expect(input({ value: 1.5, integer: true, showStepper: true }).props.step).toBe('any');
  });

  it.each(['', '-', '.', '1,5', 'NaN', 'Infinity', '1e3', '101'])('retains unfinished or invalid %s locally instead of coercing to zero', value => {
    const changed = vi.fn();
    const validity = vi.fn();
    input({ onChange: changed, max: 100 }).props.onChange!({ currentTarget: { value, setCustomValidity: validity } } as unknown as React.ChangeEvent<HTMLInputElement>);
    expect(changed).not.toHaveBeenCalled();
    expect(validity).toHaveBeenCalledWith(expect.any(String));
    expect(validity.mock.calls[0][0]).not.toBe('');
  });

  it('commits explicit zero and clears the error without clamping', () => {
    const changed = vi.fn();
    const validity = vi.fn();
    const event = { currentTarget: { value: '0', setCustomValidity: validity } } as unknown as React.ChangeEvent<HTMLInputElement>;
    input({ onChange: changed, min: 0 }).props.onChange!(event);
    expect(changed).toHaveBeenCalledWith(event);
    expect(validity).toHaveBeenCalledWith('');
    expect(numericError('-1', { min: 0 })).toBe('Enter 0 or more.');
  });

  it('allows clearing an optional unbounded schedule endpoint', () => {
    const changed = vi.fn();
    input({ placeholder: '∞', onChange: changed }).props.onChange!({ currentTarget: { value: '', setCustomValidity: vi.fn() } } as unknown as React.ChangeEvent<HTMLInputElement>);
    expect(changed).toHaveBeenCalledOnce();
  });

  it('selects existing contents on focus', () => {
    const select = vi.fn();
    input().props.onFocus!({ currentTarget: { select } } as unknown as React.FocusEvent<HTMLInputElement>);
    expect(select).toHaveBeenCalledOnce();
  });
});
