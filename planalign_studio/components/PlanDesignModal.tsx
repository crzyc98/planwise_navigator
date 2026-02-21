/**
 * E056: Read-only Plan Design Modal
 *
 * Displays the full DC plan configuration in a read-only modal,
 * accessible from the analysis page's "View Plan Design" button.
 * Reads directly from the raw anchorConfig API response.
 */

import React, { useEffect, useCallback } from 'react';
import { X, ShieldCheck, Zap, Settings, TrendingUp, Clock, CheckCircle, XCircle } from 'lucide-react';

interface PlanDesignModalProps {
  config: Record<string, any> | null;
  onClose: () => void;
}

// Read-only display field
const Field = ({ label, value, suffix }: { label: string; value: React.ReactNode; suffix?: string }) => (
  <div className="sm:col-span-3">
    <dt className="text-xs font-medium text-gray-500">{label}</dt>
    <dd className="mt-0.5 text-sm text-gray-900">
      {value}{suffix ? <span className="text-gray-500 ml-0.5">{suffix}</span> : null}
    </dd>
  </div>
);

const StatusBadge = ({ enabled }: { enabled: boolean }) => (
  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
    enabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
  }`}>
    {enabled ? <CheckCircle size={12} /> : <XCircle size={12} />}
    {enabled ? 'Enabled' : 'Disabled'}
  </span>
);

const SectionHeader = ({ icon: Icon, title, children }: { icon: React.ElementType; title: string; children?: React.ReactNode }) => (
  <div className="flex items-center justify-between border-b border-gray-200 pb-2 mb-4">
    <div className="flex items-center gap-2">
      <Icon size={16} className="text-gray-600" />
      <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
    </div>
    {children}
  </div>
);

// Convert decimal (0-1) to display percentage, handling values that might already be in percent
function toPercent(val: number | null | undefined, alreadyPercent = false): string {
  if (val == null) return '--';
  if (alreadyPercent) return `${val}`;
  // If value is <= 1, treat as decimal fraction
  if (val <= 1 && val >= 0) return `${(val * 100).toFixed(1)}`;
  return `${val.toFixed(1)}`;
}

function formatMatchMode(mode: string | undefined): string {
  switch (mode) {
    case 'deferral_based': return 'Deferral-Based';
    case 'graded_by_service': return 'Graded by Service';
    case 'tenure_based': return 'Tenure-Based';
    case 'points_based': return 'Points-Based';
    default: return mode || '--';
  }
}

function formatCoreType(status: string | undefined): string {
  switch (status) {
    case 'flat': return 'Flat Rate';
    case 'graded_by_service': return 'Graded by Service';
    case 'points_based': return 'Points-Based';
    default: return status || '--';
  }
}

function formatScope(scope: string | undefined): string {
  switch (scope) {
    case 'new_hires_only': return 'New Hires Only';
    case 'all_eligible': return 'All Eligible Employees';
    default: return scope || '--';
  }
}

export function PlanDesignModal({ config, onClose }: PlanDesignModalProps) {
  const dc = config?.dc_plan || {};

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  // Derive match tiers for display
  const matchMode = dc.match_status || 'deferral_based';
  const matchTiers: any[] = dc.match_tiers || [];
  const tenureMatchTiers: any[] = dc.tenure_match_tiers || [];
  const pointsMatchTiers: any[] = dc.points_match_tiers || [];

  // Derive core schedule for display
  const coreStatus = dc.core_status || 'flat';
  const coreGradedSchedule: any[] = dc.core_graded_schedule || [];
  const corePointsSchedule: any[] = dc.core_points_schedule || [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Plan Design Summary</h2>
            <p className="text-xs text-gray-500 mt-0.5">Read-only view of the DC plan configuration</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-200 rounded-lg transition-colors"
          >
            <X size={18} className="text-gray-500" />
          </button>
        </div>

        {/* Content */}
        <div className="overflow-y-auto flex-1 px-6 py-5 space-y-6">

          {/* Auto-Enrollment */}
          <section>
            <SectionHeader icon={Settings} title="Auto-Enrollment">
              <StatusBadge enabled={dc.auto_enroll ?? false} />
            </SectionHeader>
            <dl className="grid grid-cols-6 gap-x-4 gap-y-3">
              <Field label="Eligibility Period" value={dc.eligibility_months ?? '--'} suffix="months" />
              <Field label="Default Deferral Rate" value={dc.default_deferral_percent ?? '--'} suffix="%" />
              {dc.auto_enroll && (
                <>
                  <Field label="Enrollment Window" value={dc.auto_enroll_window_days ?? '--'} suffix="days" />
                  <Field label="Opt-Out Grace Period" value={dc.auto_enroll_opt_out_grace_period ?? '--'} suffix="days" />
                  <Field label="Enrollment Scope" value={formatScope(dc.auto_enroll_scope)} />
                  <Field label="Hire Date Cutoff" value={dc.auto_enroll_hire_date_cutoff || '--'} />
                </>
              )}
            </dl>
          </section>

          {/* Employer Match Formula */}
          <section>
            <SectionHeader icon={Zap} title="Employer Match Formula">
              <StatusBadge enabled={dc.match_enabled ?? false} />
            </SectionHeader>
            {dc.match_enabled !== false && (
              <div className="space-y-3">
                <dl className="grid grid-cols-6 gap-x-4 gap-y-3">
                  <Field label="Match Calculation Mode" value={formatMatchMode(matchMode)} />
                </dl>

                {/* Deferral-based tiers */}
                {matchMode === 'deferral_based' && matchTiers.length > 0 && (
                  <div className="bg-gray-50 rounded-lg border border-gray-200 p-3">
                    <p className="text-xs font-medium text-gray-700 mb-2">Match Tiers</p>
                    <div className="space-y-1">
                      {matchTiers.map((t: any, i: number) => (
                        <div key={i} className="flex items-center gap-2 text-xs text-gray-700">
                          <span className="text-gray-400 w-4">{i + 1}.</span>
                          <span>{toPercent(t.employee_min)}% to {toPercent(t.employee_max)}% deferrals</span>
                          <span className="text-gray-400">&rarr;</span>
                          <span className="font-medium">{toPercent(t.match_rate)}% match</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Tenure-based tiers */}
                {matchMode === 'tenure_based' && tenureMatchTiers.length > 0 && (
                  <div className="bg-gray-50 rounded-lg border border-gray-200 p-3">
                    <p className="text-xs font-medium text-gray-700 mb-2">Tenure Match Tiers</p>
                    <div className="space-y-1">
                      {tenureMatchTiers.map((t: any, i: number) => (
                        <div key={i} className="flex items-center gap-2 text-xs text-gray-700">
                          <span className="text-gray-400 w-4">{i + 1}.</span>
                          <span>{t.min_years} to {t.max_years ?? '\u221E'} yrs</span>
                          <span className="text-gray-400">&rarr;</span>
                          <span className="font-medium">{toPercent(t.match_rate)}% match, max {toPercent(t.max_deferral_pct)}% def</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Points-based tiers */}
                {matchMode === 'points_based' && pointsMatchTiers.length > 0 && (
                  <div className="bg-gray-50 rounded-lg border border-gray-200 p-3">
                    <p className="text-xs font-medium text-gray-700 mb-2">Points Match Tiers</p>
                    <p className="text-[10px] text-gray-500 mb-2">Points = FLOOR(age) + FLOOR(tenure)</p>
                    <div className="space-y-1">
                      {pointsMatchTiers.map((t: any, i: number) => (
                        <div key={i} className="flex items-center gap-2 text-xs text-gray-700">
                          <span className="text-gray-400 w-4">{i + 1}.</span>
                          <span>{t.min_points} to {t.max_points ?? '\u221E'} pts</span>
                          <span className="text-gray-400">&rarr;</span>
                          <span className="font-medium">{toPercent(t.match_rate)}% match, max {toPercent(t.max_deferral_pct)}% def</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>

          {/* Match Eligibility Requirements */}
          <section>
            <SectionHeader icon={Clock} title="Match Eligibility Requirements" />
            <dl className="grid grid-cols-6 gap-x-4 gap-y-3">
              <Field label="Min. Tenure" value={dc.match_min_tenure_years ?? 0} suffix="years" />
              <Field label="Min. Annual Hours" value={dc.match_min_hours_annual ?? 0} suffix="hours" />
              <div className="sm:col-span-6">
                <dt className="text-xs font-medium text-gray-500">Last Day Working Rule</dt>
                <dd className="mt-0.5 text-sm text-gray-900">
                  {dc.match_require_year_end_active
                    ? 'Enabled \u2014 only employees active at year-end receive match'
                    : 'Disabled \u2014 terminated employees may still receive match'}
                </dd>
              </div>
            </dl>
          </section>

          {/* Employer Core Contribution */}
          <section>
            <SectionHeader icon={ShieldCheck} title="Employer Core (Non-Elective) Contribution">
              <StatusBadge enabled={dc.core_enabled ?? false} />
            </SectionHeader>
            {dc.core_enabled && (
              <div className="space-y-3">
                <dl className="grid grid-cols-6 gap-x-4 gap-y-3">
                  <Field label="Contribution Type" value={formatCoreType(coreStatus)} />
                  {coreStatus === 'flat' && (
                    <Field label="Core Rate" value={dc.core_contribution_rate_percent ?? '--'} suffix="%" />
                  )}
                </dl>

                {/* Graded schedule */}
                {coreStatus === 'graded_by_service' && coreGradedSchedule.length > 0 && (
                  <div className="bg-gray-50 rounded-lg border border-gray-200 p-3">
                    <p className="text-xs font-medium text-gray-700 mb-2">Graded Core Schedule</p>
                    <div className="space-y-1">
                      {coreGradedSchedule.map((t: any, i: number) => (
                        <div key={i} className="flex items-center gap-2 text-xs text-gray-700">
                          <span className="text-gray-400 w-4">{i + 1}.</span>
                          <span>{t.service_years_min} to {t.service_years_max ?? '\u221E'} years</span>
                          <span className="text-gray-400">&rarr;</span>
                          <span className="font-medium">{toPercent(t.contribution_rate)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Points-based schedule */}
                {coreStatus === 'points_based' && corePointsSchedule.length > 0 && (
                  <div className="bg-gray-50 rounded-lg border border-gray-200 p-3">
                    <p className="text-xs font-medium text-gray-700 mb-2">Points Core Schedule</p>
                    <p className="text-[10px] text-gray-500 mb-2">Points = FLOOR(age) + FLOOR(tenure)</p>
                    <div className="space-y-1">
                      {corePointsSchedule.map((t: any, i: number) => (
                        <div key={i} className="flex items-center gap-2 text-xs text-gray-700">
                          <span className="text-gray-400 w-4">{i + 1}.</span>
                          <span>{t.min_points} to {t.max_points ?? '\u221E'} pts</span>
                          <span className="text-gray-400">&rarr;</span>
                          <span className="font-medium">{toPercent(t.contribution_rate)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Core eligibility */}
                <dl className="grid grid-cols-6 gap-x-4 gap-y-3">
                  <Field label="Min. Tenure" value={dc.core_min_tenure_years ?? 0} suffix="years" />
                  <Field label="Min. Annual Hours" value={dc.core_min_hours_annual ?? 0} suffix="hours" />
                  <div className="sm:col-span-6">
                    <dt className="text-xs font-medium text-gray-500">Last Day Working Rule</dt>
                    <dd className="mt-0.5 text-sm text-gray-900">
                      {dc.core_require_year_end_active
                        ? 'Enabled \u2014 only employees active at year-end receive core'
                        : 'Disabled \u2014 terminated employees may still receive core'}
                    </dd>
                  </div>
                </dl>
              </div>
            )}
          </section>

          {/* Auto-Escalation */}
          <section>
            <SectionHeader icon={TrendingUp} title="Auto-Escalation">
              <StatusBadge enabled={dc.auto_escalation ?? false} />
            </SectionHeader>
            {dc.auto_escalation && (
              <dl className="grid grid-cols-6 gap-x-4 gap-y-3">
                <Field label="Annual Increase" value={dc.escalation_rate_percent ?? '--'} suffix="%" />
                <Field label="Escalation Cap" value={dc.escalation_cap_percent ?? '--'} suffix="%" />
                <Field label="Effective Date" value={dc.escalation_effective_day || '--'} suffix="(MM-DD)" />
                <Field label="First Escalation Delay" value={dc.escalation_delay_years ?? '--'} suffix="years" />
                <Field label="Hire Date Cutoff" value={dc.escalation_hire_date_cutoff || '--'} />
              </dl>
            )}
          </section>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-200 bg-gray-50 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
