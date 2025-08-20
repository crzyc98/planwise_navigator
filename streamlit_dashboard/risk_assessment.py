# filename: streamlit_dashboard/risk_assessment.py
"""
Comprehensive Risk Assessment System for Compensation Parameter Changes
Provides business impact scoring, risk analysis, and mitigation recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Literal, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


class RiskLevel(Enum):
    """Risk severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskCategory(Enum):
    """Risk assessment categories"""

    PARAMETER = "parameter"
    BUDGET = "budget"
    RETENTION = "retention"
    EQUITY = "equity"
    IMPLEMENTATION = "implementation"


@dataclass
class RiskFactor:
    """Individual risk factor assessment"""

    name: str
    category: RiskCategory
    score: float  # 0-100 scale
    level: RiskLevel
    description: str
    impact: str
    probability: float  # 0-1 scale
    mitigation: str
    business_context: str


@dataclass
class ParameterRisk:
    """Risk assessment for a specific parameter"""

    parameter_name: str
    job_level: int
    current_value: float
    proposed_value: float
    variance_from_baseline: float
    business_impact_weight: float
    risk_factors: List[RiskFactor] = field(default_factory=list)
    overall_score: float = 0.0
    overall_level: RiskLevel = RiskLevel.LOW


@dataclass
class ComprehensiveRiskAssessment:
    """Complete risk assessment for all parameter changes"""

    parameter_risks: List[ParameterRisk] = field(default_factory=list)
    aggregate_risks: List[RiskFactor] = field(default_factory=list)
    overall_score: float = 0.0
    overall_level: RiskLevel = RiskLevel.LOW
    recommendations: List[str] = field(default_factory=list)
    estimated_budget_impact: float = 0.0
    confidence_level: float = 0.0


class RiskAssessmentEngine:
    """Main engine for comprehensive risk assessment"""

    def __init__(self):
        self.baseline_parameters = {}
        self.workforce_metrics = {}
        self.market_benchmarks = {}
        self.historical_data = {}

        # Risk weight configurations
        self.risk_weights = {
            RiskCategory.PARAMETER: 0.25,
            RiskCategory.BUDGET: 0.30,
            RiskCategory.RETENTION: 0.25,
            RiskCategory.EQUITY: 0.15,
            RiskCategory.IMPLEMENTATION: 0.05,
        }

        # Business impact weights by job level
        self.job_level_weights = {
            1: 0.35,  # Largest population, high cumulative impact
            2: 0.30,  # Second largest population
            3: 0.20,  # Mid-level impact
            4: 0.10,  # Senior level, smaller population
            5: 0.05,  # Executive level, smallest population
        }

        # Market benchmark ranges (typical industry ranges)
        self.market_benchmarks = {
            "merit_base": {
                1: {"min": 0.025, "target": 0.04, "max": 0.055},
                2: {"min": 0.025, "target": 0.035, "max": 0.050},
                3: {"min": 0.020, "target": 0.030, "max": 0.045},
                4: {"min": 0.020, "target": 0.030, "max": 0.045},
                5: {"min": 0.015, "target": 0.025, "max": 0.040},
            },
            "cola_rate": {"all": {"min": 0.015, "target": 0.025, "max": 0.040}},
            "promotion_probability": {
                1: {"min": 0.08, "target": 0.12, "max": 0.18},
                2: {"min": 0.06, "target": 0.10, "max": 0.15},
                3: {"min": 0.04, "target": 0.08, "max": 0.12},
                4: {"min": 0.02, "target": 0.05, "max": 0.08},
                5: {"min": 0.01, "target": 0.03, "max": 0.05},
            },
            "new_hire_salary_adjustment": {
                "all": {"min": 1.05, "target": 1.10, "max": 1.20}
            },
        }

    def set_baseline_data(
        self, baseline_params: Dict, workforce_data: Optional[Dict] = None
    ):
        """Set baseline parameters and workforce data for risk assessment"""
        self.baseline_parameters = baseline_params
        if workforce_data:
            self.workforce_metrics = workforce_data

    def assess_parameter_risk(
        self, param_name: str, level: int, current_value: float, proposed_value: float
    ) -> ParameterRisk:
        """Assess risk for a single parameter change"""

        # Calculate variance from baseline
        variance = (
            abs(proposed_value - current_value) / current_value
            if current_value != 0
            else 1.0
        )

        # Get business impact weight
        business_weight = self.job_level_weights.get(level, 0.1)

        # Create parameter risk object
        param_risk = ParameterRisk(
            parameter_name=param_name,
            job_level=level,
            current_value=current_value,
            proposed_value=proposed_value,
            variance_from_baseline=variance,
            business_impact_weight=business_weight,
        )

        # Assess different risk factors
        param_risk.risk_factors.extend(
            [
                self._assess_magnitude_risk(
                    param_name, level, current_value, proposed_value, variance
                ),
                self._assess_market_alignment_risk(param_name, level, proposed_value),
                self._assess_competitive_risk(param_name, level, proposed_value),
                self._assess_budget_sensitivity_risk(
                    param_name, level, variance, business_weight
                ),
            ]
        )

        # Calculate overall parameter risk score
        param_risk.overall_score = np.mean([rf.score for rf in param_risk.risk_factors])
        param_risk.overall_level = self._score_to_level(param_risk.overall_score)

        return param_risk

    def _assess_magnitude_risk(
        self,
        param_name: str,
        level: int,
        current: float,
        proposed: float,
        variance: float,
    ) -> RiskFactor:
        """Assess risk based on magnitude of change"""

        # Calculate percentage change
        pct_change = abs((proposed - current) / current) * 100 if current != 0 else 100

        # Score based on magnitude
        if pct_change < 5:
            score = 10
            risk_level = RiskLevel.LOW
            description = f"Minor adjustment ({pct_change:.1f}% change)"
            impact = "Minimal operational disruption"
        elif pct_change < 15:
            score = 30
            risk_level = RiskLevel.LOW
            description = f"Moderate adjustment ({pct_change:.1f}% change)"
            impact = "Limited operational impact"
        elif pct_change < 30:
            score = 60
            risk_level = RiskLevel.MEDIUM
            description = f"Significant adjustment ({pct_change:.1f}% change)"
            impact = "Noticeable operational impact, requires communication"
        else:
            score = 85
            risk_level = RiskLevel.HIGH
            description = f"Major adjustment ({pct_change:.1f}% change)"
            impact = "Substantial operational impact, requires change management"

        return RiskFactor(
            name=f"Change Magnitude - {param_name} Level {level}",
            category=RiskCategory.PARAMETER,
            score=score,
            level=risk_level,
            description=description,
            impact=impact,
            probability=1.0,  # Magnitude risk is certain
            mitigation="Phase implementation over multiple periods if change is large",
            business_context=f"Level {level} represents ~{self.job_level_weights.get(level, 0.1)*100:.0f}% of workforce impact",
        )

    def _assess_market_alignment_risk(
        self, param_name: str, level: int, proposed: float
    ) -> RiskFactor:
        """Assess risk based on market benchmark alignment"""

        # Get market benchmarks
        if param_name in self.market_benchmarks:
            if level in self.market_benchmarks[param_name]:
                benchmark = self.market_benchmarks[param_name][level]
            else:
                benchmark = self.market_benchmarks[param_name].get(
                    "all", {"min": 0, "target": proposed, "max": float("inf")}
                )
        else:
            # No benchmark available
            return RiskFactor(
                name=f"Market Alignment - {param_name}",
                category=RiskCategory.RETENTION,
                score=20,
                level=RiskLevel.LOW,
                description="No market benchmark available",
                impact="Unknown competitive positioning",
                probability=0.3,
                mitigation="Establish market benchmarking for this parameter",
                business_context="Market data needed for informed decisions",
            )

        # Calculate market position
        min_val, target_val, max_val = (
            benchmark["min"],
            benchmark["target"],
            benchmark["max"],
        )

        if proposed < min_val:
            score = 80
            risk_level = RiskLevel.HIGH
            description = f"Below market minimum ({proposed:.1%} vs {min_val:.1%} min)"
            impact = "High retention risk, difficulty attracting talent"
            mitigation = "Consider increasing to at least market minimum"
        elif proposed < target_val:
            score = 40
            risk_level = RiskLevel.MEDIUM
            description = (
                f"Below market target ({proposed:.1%} vs {target_val:.1%} target)"
            )
            impact = "Moderate retention risk, competitive disadvantage"
            mitigation = "Monitor retention metrics closely"
        elif proposed <= max_val:
            score = 15
            risk_level = RiskLevel.LOW
            description = (
                f"Within market range ({proposed:.1%} vs {target_val:.1%} target)"
            )
            impact = "Competitive positioning maintained"
            mitigation = "Continue monitoring market trends"
        else:
            score = 60
            risk_level = RiskLevel.MEDIUM
            description = f"Above market maximum ({proposed:.1%} vs {max_val:.1%} max)"
            impact = "Potential budget inefficiency, unsustainable spending"
            mitigation = "Evaluate budget impact and long-term sustainability"

        return RiskFactor(
            name=f"Market Alignment - {param_name} Level {level}",
            category=RiskCategory.RETENTION,
            score=score,
            level=risk_level,
            description=description,
            impact=impact,
            probability=0.8,
            mitigation=mitigation,
            business_context=f"Market positioning affects talent acquisition and retention",
        )

    def _assess_competitive_risk(
        self, param_name: str, level: int, proposed: float
    ) -> RiskFactor:
        """Assess competitive positioning risk"""

        # This would typically use external market data
        # For now, we'll use heuristics based on parameter types

        if param_name == "merit_base":
            if proposed < 0.025:
                score = 75
                risk_level = RiskLevel.HIGH
                description = "Merit rate significantly below industry standards"
                impact = "High turnover risk, demotivation"
            elif proposed < 0.035:
                score = 45
                risk_level = RiskLevel.MEDIUM
                description = "Merit rate below competitive levels"
                impact = "Moderate retention risk"
            elif proposed > 0.06:
                score = 50
                risk_level = RiskLevel.MEDIUM
                description = "Merit rate above sustainable levels"
                impact = "Budget pressure, unrealistic expectations"
            else:
                score = 20
                risk_level = RiskLevel.LOW
                description = "Merit rate within competitive range"
                impact = "Balanced compensation approach"

        elif param_name == "cola_rate":
            if proposed < 0.015:
                score = 70
                risk_level = RiskLevel.HIGH
                description = "COLA below inflation expectations"
                impact = "Real wage decline, employee dissatisfaction"
            elif proposed > 0.05:
                score = 60
                risk_level = RiskLevel.MEDIUM
                description = "COLA significantly above inflation"
                impact = "Unsustainable budget growth"
            else:
                score = 25
                risk_level = RiskLevel.LOW
                description = "COLA aligned with economic conditions"
                impact = "Maintains purchasing power"

        else:
            # Default assessment
            score = 30
            risk_level = RiskLevel.LOW
            description = "Standard competitive assessment"
            impact = "Moderate competitive impact"

        return RiskFactor(
            name=f"Competitive Position - {param_name} Level {level}",
            category=RiskCategory.RETENTION,
            score=score,
            level=risk_level,
            description=description,
            impact=impact,
            probability=0.7,
            mitigation="Regular market benchmarking and talent retention analysis",
            business_context="Competitive positioning affects talent retention and acquisition costs",
        )

    def _assess_budget_sensitivity_risk(
        self, param_name: str, level: int, variance: float, business_weight: float
    ) -> RiskFactor:
        """Assess budget impact sensitivity risk"""

        # Calculate budget sensitivity score
        budget_impact = variance * business_weight * 100

        if budget_impact < 5:
            score = 15
            risk_level = RiskLevel.LOW
            description = "Low budget impact"
            impact = f"Estimated {budget_impact:.1f}% budget effect"
        elif budget_impact < 15:
            score = 40
            risk_level = RiskLevel.MEDIUM
            description = "Moderate budget impact"
            impact = f"Estimated {budget_impact:.1f}% budget effect"
        elif budget_impact < 30:
            score = 70
            risk_level = RiskLevel.HIGH
            description = "High budget impact"
            impact = f"Estimated {budget_impact:.1f}% budget effect"
        else:
            score = 90
            risk_level = RiskLevel.CRITICAL
            description = "Critical budget impact"
            impact = f"Estimated {budget_impact:.1f}% budget effect"

        return RiskFactor(
            name=f"Budget Sensitivity - {param_name} Level {level}",
            category=RiskCategory.BUDGET,
            score=score,
            level=risk_level,
            description=description,
            impact=impact,
            probability=0.9,
            mitigation="Detailed budget modeling and approval required",
            business_context=f"Level {level} workforce segment weight: {business_weight:.1%}",
        )

    def assess_equity_risk(self, all_parameter_changes: Dict) -> List[RiskFactor]:
        """Assess equity and fairness risks across all parameter changes"""
        equity_risks = []

        # Group parameters by type
        param_groups = {}
        for (param_name, level), (current, proposed) in all_parameter_changes.items():
            if param_name not in param_groups:
                param_groups[param_name] = {}
            param_groups[param_name][level] = {"current": current, "proposed": proposed}

        # Assess equity within each parameter type
        for param_name, level_data in param_groups.items():
            equity_risk = self._assess_parameter_equity(param_name, level_data)
            if equity_risk:
                equity_risks.append(equity_risk)

        return equity_risks

    def _assess_parameter_equity(
        self, param_name: str, level_data: Dict
    ) -> Optional[RiskFactor]:
        """Assess equity risk for a specific parameter across levels"""

        if len(level_data) < 2:
            return None

        # Calculate coefficient of variation for proposed values
        proposed_values = [data["proposed"] for data in level_data.values()]
        mean_val = np.mean(proposed_values)
        std_val = np.std(proposed_values)
        cv = std_val / mean_val if mean_val != 0 else 0

        # Calculate range ratio (max/min)
        max_val = max(proposed_values)
        min_val = min(proposed_values)
        range_ratio = max_val / min_val if min_val != 0 else float("inf")

        # Assess equity based on parameter type expectations
        if param_name == "merit_base":
            # Merit rates should generally decrease or stay similar at higher levels
            expected_trend = "decreasing"
            if cv > 0.3 or range_ratio > 2.0:
                score = 65
                risk_level = RiskLevel.MEDIUM
                description = "High variance in merit rates across levels"
                impact = "Potential fairness concerns and internal equity issues"
            else:
                score = 25
                risk_level = RiskLevel.LOW
                description = "Reasonable merit rate distribution"
                impact = "Equitable compensation approach"

        elif param_name == "cola_rate":
            # COLA should typically be uniform across levels
            if cv > 0.1:
                score = 80
                risk_level = RiskLevel.HIGH
                description = "Unequal COLA rates across levels"
                impact = "Significant equity concerns, potential legal risk"
            else:
                score = 15
                risk_level = RiskLevel.LOW
                description = "Uniform COLA application"
                impact = "Equitable treatment across levels"

        else:
            # Default equity assessment
            if cv > 0.4:
                score = 50
                risk_level = RiskLevel.MEDIUM
                description = f"High variability in {param_name}"
                impact = "Potential internal equity concerns"
            else:
                score = 20
                risk_level = RiskLevel.LOW
                description = f"Reasonable {param_name} distribution"
                impact = "Acceptable internal equity"

        return RiskFactor(
            name=f"Internal Equity - {param_name}",
            category=RiskCategory.EQUITY,
            score=score,
            level=risk_level,
            description=description,
            impact=impact,
            probability=0.6,
            mitigation="Review compensation philosophy and level differentiation strategy",
            business_context=f"CV: {cv:.2f}, Range ratio: {range_ratio:.2f}",
        )

    def assess_implementation_risk(
        self, parameter_changes: Dict, implementation_timeline: int = 90
    ) -> List[RiskFactor]:
        """Assess implementation and change management risks"""
        implementation_risks = []

        # Count number of simultaneous changes
        total_changes = len(parameter_changes)

        # Assess volume risk
        if total_changes > 10:
            volume_risk = RiskFactor(
                name="Change Volume",
                category=RiskCategory.IMPLEMENTATION,
                score=70,
                level=RiskLevel.HIGH,
                description=f"High number of simultaneous changes ({total_changes})",
                impact="Complex change management, communication challenges",
                probability=0.8,
                mitigation="Phase implementation or prioritize most critical changes",
                business_context="Multiple changes increase execution complexity",
            )
            implementation_risks.append(volume_risk)
        elif total_changes > 5:
            volume_risk = RiskFactor(
                name="Change Volume",
                category=RiskCategory.IMPLEMENTATION,
                score=40,
                level=RiskLevel.MEDIUM,
                description=f"Moderate number of simultaneous changes ({total_changes})",
                impact="Manageable change complexity",
                probability=0.5,
                mitigation="Clear communication plan and change timeline",
                business_context="Moderate change management requirements",
            )
            implementation_risks.append(volume_risk)

        # Assess timeline risk
        if implementation_timeline < 30:
            timeline_risk = RiskFactor(
                name="Implementation Timeline",
                category=RiskCategory.IMPLEMENTATION,
                score=85,
                level=RiskLevel.HIGH,
                description=f"Very short implementation timeline ({implementation_timeline} days)",
                impact="High execution risk, insufficient communication time",
                probability=0.9,
                mitigation="Extend timeline or reduce scope of changes",
                business_context="Rushed implementation increases failure risk",
            )
            implementation_risks.append(timeline_risk)
        elif implementation_timeline < 60:
            timeline_risk = RiskFactor(
                name="Implementation Timeline",
                category=RiskCategory.IMPLEMENTATION,
                score=50,
                level=RiskLevel.MEDIUM,
                description=f"Short implementation timeline ({implementation_timeline} days)",
                impact="Moderate execution risk",
                probability=0.6,
                mitigation="Detailed project plan and stakeholder communication",
                business_context="Compressed timeline requires careful management",
            )
            implementation_risks.append(timeline_risk)

        return implementation_risks

    def calculate_overall_risk_assessment(
        self, parameter_changes: Dict, implementation_timeline: int = 90
    ) -> ComprehensiveRiskAssessment:
        """Calculate comprehensive risk assessment for all proposed changes"""

        assessment = ComprehensiveRiskAssessment()

        # Assess individual parameter risks
        for (param_name, level), (current, proposed) in parameter_changes.items():
            param_risk = self.assess_parameter_risk(
                param_name, level, current, proposed
            )
            assessment.parameter_risks.append(param_risk)

        # Assess aggregate risks
        assessment.aggregate_risks.extend(self.assess_equity_risk(parameter_changes))
        assessment.aggregate_risks.extend(
            self.assess_implementation_risk(parameter_changes, implementation_timeline)
        )

        # Calculate overall scores
        all_risk_factors = []
        for param_risk in assessment.parameter_risks:
            all_risk_factors.extend(param_risk.risk_factors)
        all_risk_factors.extend(assessment.aggregate_risks)

        if all_risk_factors:
            # Weight risk scores by category
            weighted_score = 0
            total_weight = 0

            for risk_factor in all_risk_factors:
                weight = self.risk_weights.get(risk_factor.category, 0.1)
                weighted_score += risk_factor.score * weight * risk_factor.probability
                total_weight += weight * risk_factor.probability

            assessment.overall_score = (
                weighted_score / total_weight if total_weight > 0 else 0
            )
            assessment.overall_level = self._score_to_level(assessment.overall_score)

        # Generate recommendations
        assessment.recommendations = self._generate_risk_recommendations(assessment)

        # Estimate budget impact
        assessment.estimated_budget_impact = self._estimate_budget_impact(
            parameter_changes
        )

        # Calculate confidence level
        assessment.confidence_level = self._calculate_confidence_level(assessment)

        return assessment

    def _score_to_level(self, score: float) -> RiskLevel:
        """Convert numeric score to risk level"""
        if score < 25:
            return RiskLevel.LOW
        elif score < 50:
            return RiskLevel.MEDIUM
        elif score < 75:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL

    def _generate_risk_recommendations(
        self, assessment: ComprehensiveRiskAssessment
    ) -> List[str]:
        """Generate actionable risk mitigation recommendations"""
        recommendations = []

        # High-level recommendations based on overall risk
        if assessment.overall_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            recommendations.append(
                "🚨 Consider phased implementation to reduce overall risk exposure"
            )
            recommendations.append(
                "📋 Develop comprehensive change management and communication plan"
            )
            recommendations.append(
                "📊 Establish enhanced monitoring and feedback mechanisms"
            )

        # Category-specific recommendations
        category_counts = {}
        for risk in assessment.aggregate_risks + [
            rf for pr in assessment.parameter_risks for rf in pr.risk_factors
        ]:
            if risk.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                category_counts[risk.category] = (
                    category_counts.get(risk.category, 0) + 1
                )

        if category_counts.get(RiskCategory.BUDGET, 0) > 0:
            recommendations.append(
                "💰 Conduct detailed budget impact analysis before implementation"
            )

        if category_counts.get(RiskCategory.RETENTION, 0) > 0:
            recommendations.append(
                "👥 Monitor retention metrics closely during and after implementation"
            )

        if category_counts.get(RiskCategory.EQUITY, 0) > 0:
            recommendations.append(
                "⚖️ Review compensation philosophy and equity guidelines"
            )

        # Parameter-specific recommendations
        high_risk_params = [
            pr
            for pr in assessment.parameter_risks
            if pr.overall_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        ]
        if high_risk_params:
            recommendations.append(
                f"🎯 Focus attention on high-risk parameters: {', '.join([f'{p.parameter_name} L{p.job_level}' for p in high_risk_params])}"
            )

        return recommendations

    def _estimate_budget_impact(self, parameter_changes: Dict) -> float:
        """Estimate overall budget impact percentage"""
        total_impact = 0

        for (param_name, level), (current, proposed) in parameter_changes.items():
            if current != 0:
                change_pct = (proposed - current) / current
                weight = self.job_level_weights.get(level, 0.1)
                total_impact += abs(change_pct) * weight

        return total_impact * 100  # Convert to percentage

    def _calculate_confidence_level(
        self, assessment: ComprehensiveRiskAssessment
    ) -> float:
        """Calculate confidence level in the risk assessment"""
        # Higher confidence when we have more data points and lower variance
        data_completeness = min(len(assessment.parameter_risks) / 10, 1.0)  # Normalized

        # Lower confidence for very high or very low risk scores (extreme values)
        score_reliability = 1.0 - abs(assessment.overall_score - 50) / 50

        return (data_completeness + score_reliability) / 2


def create_risk_dashboard(assessment: ComprehensiveRiskAssessment) -> go.Figure:
    """Create comprehensive risk dashboard visualization"""

    # Create subplots
    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Risk Score Distribution",
            "Risk by Category",
            "Parameter Risk Heatmap",
            "Risk Trends",
        ),
        specs=[
            [{"type": "bar"}, {"type": "pie"}],
            [{"type": "heatmap", "colspan": 2}, None],
        ],
        vertical_spacing=0.12,
    )

    # 1. Risk Score Distribution
    risk_levels = ["Low", "Medium", "High", "Critical"]
    risk_counts = [0, 0, 0, 0]

    for param_risk in assessment.parameter_risks:
        if param_risk.overall_level == RiskLevel.LOW:
            risk_counts[0] += 1
        elif param_risk.overall_level == RiskLevel.MEDIUM:
            risk_counts[1] += 1
        elif param_risk.overall_level == RiskLevel.HIGH:
            risk_counts[2] += 1
        else:
            risk_counts[3] += 1

    colors = ["#2E8B57", "#FFD700", "#FF8C00", "#DC143C"]

    fig.add_trace(
        go.Bar(
            x=risk_levels, y=risk_counts, marker_color=colors, name="Risk Distribution"
        ),
        row=1,
        col=1,
    )

    # 2. Risk by Category
    category_scores = {}
    category_counts = {}

    all_risks = assessment.aggregate_risks + [
        rf for pr in assessment.parameter_risks for rf in pr.risk_factors
    ]

    for risk in all_risks:
        cat = risk.category.value
        category_scores[cat] = category_scores.get(cat, 0) + risk.score
        category_counts[cat] = category_counts.get(cat, 0) + 1

    category_avg_scores = {
        cat: score / category_counts[cat] for cat, score in category_scores.items()
    }

    fig.add_trace(
        go.Pie(
            labels=list(category_avg_scores.keys()),
            values=list(category_avg_scores.values()),
            name="Category Risk",
        ),
        row=1,
        col=2,
    )

    # 3. Parameter Risk Heatmap
    param_names = []
    job_levels = []
    risk_scores = []

    for param_risk in assessment.parameter_risks:
        param_names.append(f"{param_risk.parameter_name}")
        job_levels.append(f"Level {param_risk.job_level}")
        risk_scores.append(param_risk.overall_score)

    if param_names:
        # Create matrix for heatmap
        unique_params = list(set(param_names))
        unique_levels = list(set(job_levels))

        z_matrix = []
        for param in unique_params:
            row = []
            for level in unique_levels:
                score = 0
                for i, (p, l) in enumerate(zip(param_names, job_levels)):
                    if p == param and l == level:
                        score = risk_scores[i]
                        break
                row.append(score)
            z_matrix.append(row)

        fig.add_trace(
            go.Heatmap(
                z=z_matrix,
                x=unique_levels,
                y=unique_params,
                colorscale="RdYlGn_r",
                name="Parameter Risk Heatmap",
            ),
            row=2,
            col=1,
        )

    fig.update_layout(
        height=800, showlegend=False, title_text="Risk Assessment Dashboard"
    )

    return fig


def display_risk_indicators(assessment: ComprehensiveRiskAssessment):
    """Display risk indicators and warnings in Streamlit UI"""

    # Overall risk status
    risk_color_map = {
        RiskLevel.LOW: "🟢",
        RiskLevel.MEDIUM: "🟡",
        RiskLevel.HIGH: "🟠",
        RiskLevel.CRITICAL: "🔴",
    }

    st.markdown(
        f"""
    <div style="background-color: #f0f2f6; padding: 1rem; border-radius: 0.5rem; margin: 1rem 0;">
        <h3>{risk_color_map[assessment.overall_level]} Overall Risk Level: {assessment.overall_level.value.upper()}</h3>
        <p><strong>Risk Score:</strong> {assessment.overall_score:.1f}/100</p>
        <p><strong>Confidence Level:</strong> {assessment.confidence_level:.1%}</p>
        <p><strong>Estimated Budget Impact:</strong> {assessment.estimated_budget_impact:.1f}%</p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # Critical risks warning
    critical_risks = [
        risk
        for param_risk in assessment.parameter_risks
        for risk in param_risk.risk_factors
        if risk.level == RiskLevel.CRITICAL
    ]
    critical_risks.extend(
        [
            risk
            for risk in assessment.aggregate_risks
            if risk.level == RiskLevel.CRITICAL
        ]
    )

    if critical_risks:
        st.error("🚨 Critical Risks Detected!")
        for risk in critical_risks:
            st.error(f"**{risk.name}**: {risk.description} - {risk.impact}")

    # High risks warning
    high_risks = [
        risk
        for param_risk in assessment.parameter_risks
        for risk in param_risk.risk_factors
        if risk.level == RiskLevel.HIGH
    ]
    high_risks.extend(
        [risk for risk in assessment.aggregate_risks if risk.level == RiskLevel.HIGH]
    )

    if high_risks:
        st.warning("⚠️ High Risks Identified:")
        for risk in high_risks:
            st.warning(f"**{risk.name}**: {risk.description}")

    # Recommendations
    if assessment.recommendations:
        st.info("💡 Risk Mitigation Recommendations:")
        for rec in assessment.recommendations:
            st.info(f"• {rec}")
