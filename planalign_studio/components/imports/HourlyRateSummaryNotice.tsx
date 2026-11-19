import React from 'react';
import { Clock } from 'lucide-react';
import { CensusHourlyRateSummary } from '../../services/api';

const PRECEDENCE = ['hourly_rate', 'hours_worked', 'scheduled_hours_per_week'];

/** "1 person has" / "3 people have": the count with a matching noun and verb. */
const peopleHave = (count: number) =>
  `${count.toLocaleString()} ${count === 1 ? 'person has' : 'people have'}`;

const dollars = (value: number) =>
  `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** Import report on census hourly rates, used by a minimum wage change (#1230). */
export default function HourlyRateSummaryNotice({ summary }: { summary?: CensusHourlyRateSummary | null }) {
  if (!summary) return null;
  const sources = PRECEDENCE.filter((column) => (summary.by_source[column] ?? 0) > 0);
  return (
    <div className="flex items-start gap-3 text-left text-sm text-ink-muted bg-surface-subtle border border-border rounded-lg p-3">
      <Clock size={16} className="shrink-0 mt-0.5 text-ink-subtle" />
      <div className="space-y-1">
        <div className="font-medium text-ink">Hourly rates</div>
        <div>
          {peopleHave(summary.with_rate)} an hourly rate
          {sources.length > 0 && (
            <> ({sources.map((column) => `${summary.by_source[column].toLocaleString()} from ${column}`).join(', ')})</>
          )}
          . {peopleHave(summary.blank)} none and {summary.blank === 1 ? 'is' : 'are'} treated as not hourly.
        </div>
        {summary.out_of_bounds > 0 && (
          <div className="text-warning-ink">
            {peopleHave(summary.out_of_bounds)} a rate below {dollars(summary.minimum_rate)} or
            above {dollars(summary.maximum_rate)} an hour. They stay in the census with no rate,
            so a minimum wage change won't touch them. Check their pay and hours.
          </div>
        )}
        {summary.multiple_columns > 0 && (
          <div>
            {peopleHave(summary.multiple_columns)} more than one hourly column. The rate comes
            from hourly_rate first, then hours_worked, then scheduled_hours_per_week.
          </div>
        )}
        {summary.columns_present.includes('hours_worked') && (
          <div className="text-xs text-ink-subtle">
            hourly_rate is preferred: pay divided by all hours worked overstates the base rate for
            people paid overtime premium or bonuses.
          </div>
        )}
      </div>
    </div>
  );
}
