import type { DCPlanCohort, ReportFormat, ScenarioReportOptions } from '../services/api';

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

/** The Cost Comparison toggles that change its figures. */
export interface ReportViewBasis {
  cohort: DCPlanCohort;
  costView: 'gross' | 'net';
  grandfatherExisting: boolean;
}

export const REPORT_BASIS_NOTE = 'Report covers all employees, gross of forfeitures.';

/** The report is always all employees, gross, no grandfathering; says so when the page's view differs. */
export function reportBasisNote(view: ReportViewBasis): string | null {
  const matches = view.cohort === 'all' && view.costView === 'gross' && !view.grandfatherExisting;
  return matches ? null : REPORT_BASIS_NOTE;
}
