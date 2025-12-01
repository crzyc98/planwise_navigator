"""Template service for pre-configured scenario templates."""

from typing import List, Optional

from ..models.templates import Template


class TemplateService:
    """Service for managing pre-configured scenario templates."""

    # Built-in templates
    BUILT_IN_TEMPLATES = [
        Template(
            id="baseline",
            name="Baseline (Conservative)",
            description="Standard configuration with moderate growth and turnover. "
            "Good starting point for most organizations.",
            category="general",
            config={
                "simulation": {
                    "target_growth_rate": 0.03,
                },
                "workforce": {
                    "total_termination_rate": 0.12,
                    "new_hire_termination_rate": 0.25,
                },
                "compensation": {
                    "merit_budget_percent": 3.5,
                    "cola_rate_percent": 2.0,
                },
                "dc_plan": {
                    "auto_enroll": True,
                    "match_percent": 50,
                    "match_limit_percent": 6,
                },
            },
        ),
        Template(
            id="high_growth",
            name="High Growth",
            description="Aggressive hiring plan with competitive compensation. "
            "Suitable for fast-growing organizations or expansion scenarios.",
            category="growth",
            config={
                "simulation": {
                    "target_growth_rate": 0.08,
                },
                "workforce": {
                    "total_termination_rate": 0.10,
                    "new_hire_termination_rate": 0.20,
                },
                "compensation": {
                    "merit_budget_percent": 4.5,
                    "cola_rate_percent": 2.5,
                },
                "dc_plan": {
                    "auto_enroll": True,
                    "match_percent": 100,
                    "match_limit_percent": 6,
                },
            },
        ),
        Template(
            id="cost_optimization",
            name="Cost Optimization",
            description="Focus on cost control with moderate benefits. "
            "For organizations prioritizing expense management.",
            category="cost",
            config={
                "simulation": {
                    "target_growth_rate": 0.01,
                },
                "workforce": {
                    "total_termination_rate": 0.15,
                },
                "compensation": {
                    "merit_budget_percent": 2.5,
                    "cola_rate_percent": 1.5,
                },
                "dc_plan": {
                    "auto_enroll": False,
                    "match_percent": 25,
                    "match_limit_percent": 4,
                },
            },
        ),
        Template(
            id="retention_focus",
            name="Retention Focus",
            description="Enhanced benefits and compensation to reduce turnover. "
            "Ideal for organizations with high attrition concerns.",
            category="retention",
            config={
                "simulation": {
                    "target_growth_rate": 0.02,
                },
                "workforce": {
                    "total_termination_rate": 0.08,
                    "new_hire_termination_rate": 0.15,
                },
                "compensation": {
                    "merit_budget_percent": 4.0,
                    "cola_rate_percent": 2.5,
                },
                "dc_plan": {
                    "auto_enroll": True,
                    "auto_escalation": True,
                    "match_percent": 100,
                    "match_limit_percent": 8,
                },
            },
        ),
        Template(
            id="tech_startup",
            name="Tech Startup",
            description="High growth with equity-like benefits structure. "
            "Matches typical Silicon Valley compensation patterns.",
            category="growth",
            config={
                "simulation": {
                    "target_growth_rate": 0.15,
                },
                "workforce": {
                    "total_termination_rate": 0.18,
                    "new_hire_termination_rate": 0.30,
                },
                "compensation": {
                    "merit_budget_percent": 5.0,
                    "cola_rate_percent": 3.0,
                },
                "dc_plan": {
                    "auto_enroll": True,
                    "match_percent": 50,
                    "match_limit_percent": 6,
                },
            },
        ),
        Template(
            id="mature_enterprise",
            name="Mature Enterprise",
            description="Stable workforce with generous benefits. "
            "Typical of established Fortune 500 companies.",
            category="general",
            config={
                "simulation": {
                    "target_growth_rate": 0.02,
                },
                "workforce": {
                    "total_termination_rate": 0.10,
                    "new_hire_termination_rate": 0.18,
                },
                "compensation": {
                    "merit_budget_percent": 3.0,
                    "cola_rate_percent": 2.0,
                },
                "dc_plan": {
                    "auto_enroll": True,
                    "auto_escalation": True,
                    "match_percent": 100,
                    "match_limit_percent": 6,
                    "vesting_schedule": "immediate",
                },
            },
        ),
    ]

    def list_templates(self) -> List[Template]:
        """List all available templates."""
        return self.BUILT_IN_TEMPLATES

    def get_template(self, template_id: str) -> Optional[Template]:
        """Get a specific template by ID."""
        for template in self.BUILT_IN_TEMPLATES:
            if template.id == template_id:
                return template
        return None

    def get_templates_by_category(self, category: str) -> List[Template]:
        """Get all templates in a specific category."""
        return [t for t in self.BUILT_IN_TEMPLATES if t.category == category]
