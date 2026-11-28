import { useId, type ReactNode } from 'react';
import { NumericInput } from './NumericInput';
import type { AcquisitionPay, AcquisitionRow } from './types';
import {
  AVERAGE_AGE_RANGE, MAX_AVERAGE_PAY, MAX_AVERAGE_SERVICE, PERCENT_OF_STAFF_RANGE, describeOverrides,
} from './acquisitions';

const INPUT = 'block w-full rounded-md border border-border-strong p-2 shadow-sm focus:border-brand-green focus:ring-brand-green sm:text-sm';
const SELECT = 'mt-1 block w-full pl-3 pr-10 py-2 text-base border-border-strong focus:outline-none focus:ring-brand-green focus:border-brand-green sm:text-sm rounded-md border shadow-sm';

interface Choice<T extends string> { value: T; label: string; helper: string }

const SERVICE_CREDIT: Choice<AcquisitionRow['serviceCredit']>[] = [
  { value: 'prior_service', label: 'Keep service from the acquired company', helper: 'Their years there count for eligibility, vesting and service-based contributions.' },
  { value: 'acquisition_date', label: 'Start service on the acquisition date', helper: 'Service counts from zero on the acquisition date, as for a new hire.' },
];
const JOIN_YEAR_HOURS: Choice<AcquisitionRow['joinYearHoursCredit']>[] = [
  { value: 'none', label: 'Count hours from the acquisition date', helper: "Only hours worked after joining count toward the plan's hours requirement for match and core in the join year." },
  { value: 'full_year', label: 'Credit a full year of hours', helper: 'In the join year, members meet the match and core hours requirement; contributions still use their actual pay and deferrals.' },
];
const PLAN_ENTRY: Choice<AcquisitionRow['planEntry']>[] = [
  { value: 'acquisition_date', label: 'Enter the plan on the acquisition date', helper: 'Members can join the plan as soon as they arrive.' },
  { value: 'waiting_period', label: "Wait out the plan's waiting period", helper: "Members become eligible after the plan's usual waiting period, counted from the acquisition date." },
];
type Participation = 'auto' | 'set';
const PARTICIPATION: Choice<Participation>[] = [
  { value: 'auto', label: 'Auto-enroll like new hires', helper: "Members go through the plan's auto-enrollment and opt-out rules, like new hires." },
  { value: 'set', label: 'Already participating at a set rate', helper: 'Set the share already contributing when they enter the plan, and their average deferral rate.' },
];
const PAY: Choice<AcquisitionPay['kind']>[] = [
  { value: 'mirror', label: 'Same as existing staff', helper: 'Each member takes the pay of a sampled staff member.' },
  { value: 'relative', label: "Percent of existing staff's pay", helper: '100% matches staff; 90% is 10% below. Every member moves by the same factor, so the spread is kept.' },
  { value: 'amount', label: 'Set an average amount', helper: 'Every member is scaled by the same factor so the group averages this amount.' },
];

interface SelectProps<T extends string> {
  label: string;
  ariaLabel: string;
  value: T;
  choices: Choice<T>[];
  onChange: (value: T) => void;
  children?: ReactNode;
}

function ChoiceSelect<T extends string>({ label, ariaLabel, value, choices, onChange, children }: SelectProps<T>) {
  const id = useId();
  const selected = choices.find(choice => choice.value === value) ?? choices[0];
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-ink-muted">{label}</label>
      <select id={id} aria-label={ariaLabel} value={value} onChange={event => onChange(event.target.value as T)} className={SELECT}>
        {choices.map(choice => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
      </select>
      <p className="mt-1 text-xs text-ink-muted">{selected.helper}</p>
      {children}
    </div>
  );
}

interface NumberProps {
  label: string;
  ariaLabel: string;
  value: number | null;
  onChange: (value: number | null) => void;
  min: number;
  max: number;
  suffix?: string;
  placeholder?: string;
  helper?: string;
}

/** An optional number; clearing it sets null. */
function OptionalNumber({ label, ariaLabel, value, onChange, min, max, suffix, placeholder, helper }: NumberProps) {
  return (
    <label className="block text-sm font-medium text-ink-muted">{label}
      <span className="mt-1 flex items-center gap-2">
        <NumericInput aria-label={ariaLabel} value={value ?? ''} allowEmpty min={min} max={max} placeholder={placeholder}
          onChange={event => onChange(event.target.value.trim() ? Number(event.target.value) : null)} className={INPUT} />
        {suffix && <span className="text-sm text-ink-muted">{suffix}</span>}
      </span>
      {helper && <span className="mt-1 block text-xs font-normal text-ink-muted">{helper}</span>}
    </label>
  );
}

interface FieldsProps {
  row: AcquisitionRow;
  index: number;
  onChange: (changes: Partial<AcquisitionRow>) => void;
}

/** How the plan treats the group (#1227). */
export function AcquisitionPlanFields({ row, index, onChange }: FieldsProps) {
  const name = `Acquisition ${index + 1}`;
  const participation: Participation = row.startingParticipationPct === null && row.startingDeferralPct === null ? 'auto' : 'set';
  const setParticipation = (value: Participation) => onChange(value === 'auto'
    ? { startingParticipationPct: null, startingDeferralPct: null }
    : { startingParticipationPct: row.startingParticipationPct ?? 50, startingDeferralPct: row.startingDeferralPct ?? 6 });
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <ChoiceSelect label="Service credit" ariaLabel={`${name} service credit`} value={row.serviceCredit} choices={SERVICE_CREDIT} onChange={serviceCredit => onChange({ serviceCredit })} />
      <ChoiceSelect label="Join-year hours" ariaLabel={`${name} join-year hours`} value={row.joinYearHoursCredit} choices={JOIN_YEAR_HOURS} onChange={joinYearHoursCredit => onChange({ joinYearHoursCredit })} />
      <ChoiceSelect label="Plan entry" ariaLabel={`${name} plan entry`} value={row.planEntry} choices={PLAN_ENTRY} onChange={planEntry => onChange({ planEntry })} />
      <ChoiceSelect label="Starting participation" ariaLabel={`${name} starting participation`} value={participation} choices={PARTICIPATION} onChange={setParticipation}>
        {participation === 'set' && (
          <div className="mt-2 grid grid-cols-2 gap-2">
            <OptionalNumber label="Participating" ariaLabel={`${name} share participating`} value={row.startingParticipationPct} min={0} max={100} suffix="%"
              onChange={startingParticipationPct => onChange({ startingParticipationPct })} />
            <OptionalNumber label="Average deferral" ariaLabel={`${name} average deferral rate`} value={row.startingDeferralPct} min={0} max={100} suffix="%"
              onChange={startingDeferralPct => onChange({ startingDeferralPct })} />
          </div>
        )}
      </ChoiceSelect>
    </div>
  );
}

function payChange(kind: AcquisitionPay['kind'], current: AcquisitionPay): AcquisitionPay {
  if (kind === current.kind) return current;
  if (kind === 'relative') return { kind, percentOfStaff: 100 };
  if (kind === 'amount') return { kind, averagePay: 0 };
  return { kind };
}

/** Who the group is (#1228): mirrors existing staff unless overridden. Collapsed by default. */
export function AcquisitionOverrideFields({ row, index, onChange }: FieldsProps) {
  const name = `Acquisition ${index + 1}`;
  const { pay } = row;
  return (
    <details className="rounded-md border border-border p-3">
      <summary className="cursor-pointer text-sm text-ink marker:text-ink-muted">
        <span className="font-medium">Who they are: </span>{describeOverrides(row)}
        <span className="block text-xs text-ink-muted">By default members are sampled from your active staff, so their pay, age and service match. Override any of them here.</span>
      </summary>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <ChoiceSelect label="Average pay" ariaLabel={`${name} pay`} value={pay.kind} choices={PAY} onChange={kind => onChange({ pay: payChange(kind, pay) })}>
          {pay.kind === 'relative' && (
            <div className="mt-2">
              <OptionalNumber label="Percent of staff pay" ariaLabel={`${name} percent of staff pay`} value={Number.isFinite(pay.percentOfStaff) ? pay.percentOfStaff : null}
                min={PERCENT_OF_STAFF_RANGE.min} max={PERCENT_OF_STAFF_RANGE.max} suffix="%"
                onChange={value => onChange({ pay: { kind: 'relative', percentOfStaff: value ?? Number.NaN } })} />
            </div>
          )}
          {pay.kind === 'amount' && (
            <div className="mt-2">
              <OptionalNumber label="Average annual pay ($)" ariaLabel={`${name} average annual pay`} value={pay.averagePay || null} min={0} max={MAX_AVERAGE_PAY}
                onChange={value => onChange({ pay: { kind: 'amount', averagePay: value ?? 0 } })} />
            </div>
          )}
        </ChoiceSelect>
        <OptionalNumber label="Average age" ariaLabel={`${name} average age`} value={row.averageAge} min={AVERAGE_AGE_RANGE.min} max={AVERAGE_AGE_RANGE.max}
          placeholder="Same as staff" helper="Leave blank to match staff. Everyone moves by the same years, never below 18."
          onChange={averageAge => onChange({ averageAge })} />
        <OptionalNumber label="Average service (years)" ariaLabel={`${name} average service`} value={row.averageService} min={0} max={MAX_AVERAGE_SERVICE}
          placeholder="Same as staff"
          helper={row.serviceCredit === 'acquisition_date'
            ? 'Service credit starts on the acquisition date, so the plan counts zero service whatever you set here.'
            : 'Leave blank to match staff. Kept between 0 and age minus 18.'}
          onChange={averageService => onChange({ averageService })} />
      </div>
    </details>
  );
}
