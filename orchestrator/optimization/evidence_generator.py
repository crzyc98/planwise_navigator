"""
Evidence report generator for optimization results.

Generates comprehensive business impact reports with parameter recommendations.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import tempfile
import os

from .optimization_schemas import OptimizationResult
from .sensitivity_analysis import SensitivityAnalyzer

class EvidenceGenerator:
    """Auto-generate business impact evidence reports."""

    def __init__(self, optimization_result: OptimizationResult):
        self.result = optimization_result
        self.report_template = self._get_report_template()

    def generate_mdx_report(self, output_dir: Optional[str] = None) -> str:
        """
        Generate comprehensive MDX evidence report.

        Args:
            output_dir: Directory to save report (defaults to temp directory)

        Returns:
            Path to generated report file
        """

        # Use temp directory if not specified
        if output_dir is None:
            output_dir = tempfile.gettempdir()

        # Generate report content
        report_content = self._generate_report_content()

        # Create filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"optimization_evidence_{self.result.scenario_id}_{timestamp}.md"
        file_path = os.path.join(output_dir, filename)

        # Write report
        with open(file_path, 'w') as f:
            f.write(report_content)

        return file_path

    def _generate_report_content(self) -> str:
        """Generate the full report content."""

        # Report sections
        sections = [
            self._generate_header(),
            self._generate_executive_summary(),
            self._generate_optimization_details(),
            self._generate_parameter_analysis(),
            self._generate_business_impact(),
            self._generate_risk_assessment(),
            self._generate_recommendations(),
            self._generate_technical_appendix()
        ]

        return "\n\n".join(sections)

    def _generate_header(self) -> str:
        """Generate report header."""

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return f"""# Compensation Optimization Evidence Report

**Scenario:** {self.result.scenario_id}
**Generated:** {timestamp}
**Algorithm:** {self.result.algorithm_used}
**Status:** {'✅ Converged' if self.result.converged else '❌ Failed to Converge'}
**Quality Score:** {self.result.solution_quality_score:.2f}/1.0

---"""

    def _generate_executive_summary(self) -> str:
        """Generate executive summary."""

        cost_impact = self.result.estimated_cost_impact
        employee_impact = self.result.estimated_employee_impact

        return f"""## Executive Summary

The optimization engine successfully {'converged' if self.result.converged else 'attempted'} to find optimal compensation parameters for scenario `{self.result.scenario_id}`.

**Key Results:**
- **Total Cost Impact:** ${cost_impact.get('value', 0):,.0f} {cost_impact.get('unit', 'USD')}
- **Employees Affected:** {employee_impact.get('count', 0):,} ({employee_impact.get('percentage_of_workforce', 0)*100:.1f}% of workforce)
- **Risk Level:** {self.result.risk_assessment}
- **Function Evaluations:** {self.result.function_evaluations}
- **Runtime:** {self.result.runtime_seconds:.1f} seconds

**Convergence Status:** {'The optimization successfully converged to an optimal solution.' if self.result.converged else 'The optimization did not fully converge but found a feasible solution.'}"""

    def _generate_optimization_details(self) -> str:
        """Generate optimization technical details."""

        return f"""## Optimization Details

### Algorithm Performance
- **Method:** {self.result.algorithm_used}
- **Objective Value:** {self.result.objective_value:.6f}
- **Iterations:** {self.result.iterations}
- **Function Evaluations:** {self.result.function_evaluations}
- **Runtime:** {self.result.runtime_seconds:.2f} seconds
- **Converged:** {'Yes' if self.result.converged else 'No'}

### Constraint Violations
{self._format_constraint_violations()}"""

    def _generate_parameter_analysis(self) -> str:
        """Generate parameter analysis section."""

        params_table = self._format_parameters_table()

        return f"""## Optimal Parameters

The optimization identified the following optimal parameter values:

{params_table}

### Parameter Insights
{self._generate_parameter_insights()}"""

    def _generate_business_impact(self) -> str:
        """Generate business impact analysis."""

        cost_impact = self.result.estimated_cost_impact
        employee_impact = self.result.estimated_employee_impact

        return f"""## Business Impact Analysis

### Financial Impact
- **Total Compensation Cost:** ${cost_impact.get('value', 0):,.0f}
- **Confidence Level:** {cost_impact.get('confidence', 'medium').title()}

### Workforce Impact
- **Employees Affected:** {employee_impact.get('count', 0):,}
- **Workforce Percentage:** {employee_impact.get('percentage_of_workforce', 0)*100:.1f}%
- **Risk Level:** {employee_impact.get('risk_level', 'medium').title()}

### Implementation Considerations
{self._generate_implementation_notes()}"""

    def _generate_risk_assessment(self) -> str:
        """Generate risk assessment section."""

        risk_level = self.result.risk_assessment
        risk_color = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}

        return f"""## Risk Assessment

**Overall Risk Level:** {risk_color.get(risk_level, '⚪')} {risk_level}

### Risk Factors
{self._assess_risk_factors()}

### Mitigation Strategies
{self._suggest_mitigation_strategies()}"""

    def _generate_recommendations(self) -> str:
        """Generate recommendations section."""

        return f"""## Recommendations

### Implementation Recommendations
{self._generate_implementation_recommendations()}

### Monitoring Recommendations
{self._generate_monitoring_recommendations()}

### Future Optimization Opportunities
{self._identify_future_opportunities()}"""

    def _generate_technical_appendix(self) -> str:
        """Generate technical appendix."""

        return f"""## Technical Appendix

### Optimization Configuration
- **Scenario ID:** {self.result.scenario_id}
- **Schema Version:** {self.result.schema_version}
- **Algorithm:** {self.result.algorithm_used}
- **Quality Score:** {self.result.solution_quality_score:.3f}

### Performance Metrics
- **Total Evaluations:** {self.result.function_evaluations}
- **Runtime:** {self.result.runtime_seconds:.2f}s
- **Iterations:** {self.result.iterations}

---

*This report was automatically generated by PlanWise Navigator Optimization Engine v1.0.0*"""

    def _format_constraint_violations(self) -> str:
        """Format constraint violations for display."""

        if not self.result.constraint_violations:
            return "✅ **No constraint violations detected**"

        violations_list = []
        for constraint, violation in self.result.constraint_violations.items():
            violations_list.append(f"- **{constraint}:** {violation:.6f}")

        return "⚠️ **Constraint violations detected:**\n" + "\n".join(violations_list)

    def _format_parameters_table(self) -> str:
        """Format optimal parameters as markdown table."""

        table_rows = ["| Parameter | Value | Unit | Description |", "|-----------|-------|------|-------------|"]

        # Import parameter schema for descriptions
        from .optimization_schemas import PARAMETER_SCHEMA

        for param_name, value in self.result.optimal_parameters.items():
            schema_info = PARAMETER_SCHEMA.get(param_name, {})
            unit = schema_info.get("unit", "")
            description = schema_info.get("description", param_name)

            if unit == "percentage":
                formatted_value = f"{value*100:.2f}%"
            else:
                formatted_value = f"{value:.4f}"

            table_rows.append(f"| {param_name} | {formatted_value} | {unit} | {description} |")

        return "\n".join(table_rows)

    def _generate_parameter_insights(self) -> str:
        """Generate insights about optimal parameters."""

        insights = []

        # Analyze parameter ranges
        from .optimization_schemas import PARAMETER_SCHEMA

        high_params = []
        low_params = []

        for param_name, value in self.result.optimal_parameters.items():
            if param_name in PARAMETER_SCHEMA:
                bounds = PARAMETER_SCHEMA[param_name]["range"]
                param_range = bounds[1] - bounds[0]
                relative_position = (value - bounds[0]) / param_range

                if relative_position > 0.8:
                    high_params.append(param_name)
                elif relative_position < 0.2:
                    low_params.append(param_name)

        if high_params:
            insights.append(f"**High-end parameters:** {', '.join(high_params)} - consider if these values align with organizational policy")

        if low_params:
            insights.append(f"**Conservative parameters:** {', '.join(low_params)} - may indicate cost optimization focus")

        return "\n".join(insights) if insights else "Parameters are within normal ranges."

    def _generate_implementation_notes(self) -> str:
        """Generate implementation considerations."""

        notes = [
            "- Review optimal parameters with compensation committee before implementation",
            "- Consider phased rollout to minimize workforce disruption",
            "- Monitor employee satisfaction metrics during implementation",
            "- Validate budget impact against annual planning targets"
        ]

        if self.result.risk_assessment == "HIGH":
            notes.insert(0, "⚠️ **High risk scenario - additional approval recommended**")

        return "\n".join(notes)

    def _assess_risk_factors(self) -> str:
        """Assess and list risk factors."""

        risk_factors = []

        if not self.result.converged:
            risk_factors.append("- Optimization did not fully converge")

        if self.result.constraint_violations:
            risk_factors.append("- Constraint violations present")

        if self.result.solution_quality_score < 0.7:
            risk_factors.append("- Below-average solution quality")

        if self.result.function_evaluations > 300:
            risk_factors.append("- High computational complexity")

        return "\n".join(risk_factors) if risk_factors else "- No significant risk factors identified"

    def _suggest_mitigation_strategies(self) -> str:
        """Suggest risk mitigation strategies."""

        strategies = [
            "- Implement gradual parameter changes over multiple periods",
            "- Monitor key workforce metrics during rollout",
            "- Maintain rollback capability for quick parameter reversion",
            "- Regular optimization reruns to validate parameter stability"
        ]

        return "\n".join(strategies)

    def _generate_implementation_recommendations(self) -> str:
        """Generate implementation recommendations."""

        recommendations = [
            "1. **Validation Phase:** Run simulation with optimal parameters on historical data",
            "2. **Approval Process:** Submit parameters for compensation committee review",
            "3. **Phased Rollout:** Implement changes gradually over 2-3 pay periods",
            "4. **Monitoring Setup:** Establish KPI dashboards for impact tracking"
        ]

        return "\n".join(recommendations)

    def _generate_monitoring_recommendations(self) -> str:
        """Generate monitoring recommendations."""

        monitoring = [
            "- **Weekly:** Track total compensation costs vs. budget",
            "- **Monthly:** Analyze employee satisfaction and retention metrics",
            "- **Quarterly:** Review parameter effectiveness and rerun optimization",
            "- **Annually:** Comprehensive compensation strategy assessment"
        ]

        return "\n".join(monitoring)

    def _identify_future_opportunities(self) -> str:
        """Identify future optimization opportunities."""

        opportunities = [
            "- Multi-year optimization incorporating career progression",
            "- Integration with performance management systems",
            "- Real-time parameter adjustment based on business metrics",
            "- Advanced constraint modeling for regulatory compliance"
        ]

        return "\n".join(opportunities)

    def _get_report_template(self) -> str:
        """Get the report template structure."""
        # This could be expanded to use external templates
        return "default_mdx_template"
