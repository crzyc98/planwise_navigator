import { useConfigContext } from './ConfigContext';
import type { Template } from '../../services/api';

interface TemplateModalProps {
  templates: Template[];
  onClose: () => void;
}

export function TemplateModal({ templates, onClose }: TemplateModalProps) {
  const { setFormData } = useConfigContext();

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">
        <div className="p-6 border-b border-gray-200 flex-shrink-0">
          <h2 className="text-xl font-bold text-gray-900">Load Configuration Template</h2>
          <p className="text-sm text-gray-500 mt-1">Select a template to pre-fill configuration values</p>
        </div>
        <div className="p-6 overflow-y-auto flex-1 space-y-3">
          {templates.map(template => (
            <button
              key={template.id}
              onClick={() => {
                const cfg = template.config;
                setFormData(prev => ({
                  ...prev,
                  // Simulation
                  targetGrowthRate: cfg.simulation?.target_growth_rate != null
                    ? cfg.simulation.target_growth_rate * 100
                    : prev.targetGrowthRate,
                  // Workforce
                  totalTerminationRate: cfg.workforce?.total_termination_rate != null
                    ? cfg.workforce.total_termination_rate * 100
                    : prev.totalTerminationRate,
                  newHireTerminationRate: cfg.workforce?.new_hire_termination_rate != null
                    ? cfg.workforce.new_hire_termination_rate * 100
                    : prev.newHireTerminationRate,
                  // Compensation
                  meritBudget: cfg.compensation?.merit_budget_percent ?? prev.meritBudget,
                  colaRate: cfg.compensation?.cola_rate_percent ?? prev.colaRate,
                  // DC Plan (E084 Phase B: custom tiers)
                  dcAutoEnroll: cfg.dc_plan?.auto_enroll ?? prev.dcAutoEnroll,
                  dcMatchTemplate: cfg.dc_plan?.match_template || prev.dcMatchTemplate,
                  dcMatchTiers: cfg.dc_plan?.match_tiers
                    ? cfg.dc_plan.match_tiers.map((t: any) => ({
                        deferralMin: (t.employee_min ?? 0) * 100,
                        deferralMax: (t.employee_max ?? 0) * 100,
                        matchRate: (t.match_rate ?? 0) * 100,
                      }))
                    : prev.dcMatchTiers,
                  // E046: Tenure/Points match mode
                  dcMatchMode: cfg.dc_plan?.match_status || prev.dcMatchMode,
                  dcTenureMatchTiers: cfg.dc_plan?.tenure_match_tiers?.length
                    ? cfg.dc_plan.tenure_match_tiers.map((t: any) => ({
                        minYears: t.min_years ?? 0,
                        maxYears: t.max_years ?? null,
                        matchRate: (t.match_rate ?? 0) * 100,
                        maxDeferralPct: (t.max_deferral_pct ?? 0) * 100,
                      }))
                    : prev.dcTenureMatchTiers,
                  dcPointsMatchTiers: cfg.dc_plan?.points_match_tiers?.length
                    ? cfg.dc_plan.points_match_tiers.map((t: any) => ({
                        minPoints: t.min_points ?? 0,
                        maxPoints: t.max_points ?? null,
                        matchRate: (t.match_rate ?? 0) * 100,
                        maxDeferralPct: (t.max_deferral_pct ?? 0) * 100,
                      }))
                    : prev.dcPointsMatchTiers,
                  dcAutoEscalation: cfg.dc_plan?.auto_escalation ?? prev.dcAutoEscalation,
                }));
                onClose();
              }}
              className="w-full text-left p-4 border border-gray-200 rounded-lg hover:border-fidelity-green hover:bg-green-50 transition-colors"
            >
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="font-semibold text-gray-900">{template.name}</h3>
                  <p className="text-sm text-gray-500 mt-1">{template.description}</p>
                </div>
                <span className="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-600 rounded capitalize">
                  {template.category}
                </span>
              </div>
            </button>
          ))}
        </div>
        <div className="p-4 border-t border-gray-200 bg-gray-50 flex-shrink-0 rounded-b-xl">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 hover:bg-gray-200 rounded-lg transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
