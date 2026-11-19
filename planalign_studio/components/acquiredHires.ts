/**
 * Event counts with acquired members (#1226) split out of "hire": hire becomes
 * organic hiring and "acquired" is added, only when a year has acquired members.
 * Counts are aligned by year index, like event_trends.
 */
export function splitAcquiredHires(
  eventTrends: Record<string, number[]>, acquiredHires: number[] | undefined,
): Record<string, number[]> {
  const acquired = acquiredHires ?? [];
  if (!acquired.some(count => count > 0)) return eventTrends;
  const hires = eventTrends.hire ?? [];
  const years = Math.max(hires.length, acquired.length);
  return {
    ...eventTrends,
    hire: Array.from({ length: years }, (_, i) => (hires[i] ?? 0) - (acquired[i] ?? 0)),
    acquired: Array.from({ length: years }, (_, i) => acquired[i] ?? 0),
  };
}
