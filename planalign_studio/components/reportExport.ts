import type { ReportFormat, ScenarioReportOptions } from '../services/api';

/**
 * Maps the page's selection to a report request. The anchor is the path
 * scenario (falling back to the first selected one) and the rest go in
 * `compare`; the anchor is always sent explicitly.
 */
export function reportRequest(
  selectedIds: string[],
  anchorId: string,
  format: Exclude<ReportFormat, 'html'>,
): { scenarioId: string; options: ScenarioReportOptions } | null {
  if (selectedIds.length === 0) return null;
  const scenarioId = selectedIds.includes(anchorId) ? anchorId : selectedIds[0];
  return {
    scenarioId,
    options: {
      format,
      compare: selectedIds.filter(id => id !== scenarioId),
      anchor: scenarioId,
    },
  };
}
