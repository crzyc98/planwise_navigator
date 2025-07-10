"""
S050: Configurable Merit Distribution System

Advanced merit distribution strategies with configurable patterns,
risk adjustments, and business rule integration for flexible compensation modeling.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
import pandas as pd
import yaml
from pathlib import Path
import logging

from orchestrator.resources.duckdb_resource import DuckDBResource

logger = logging.getLogger(__name__)


class DistributionStrategy(Enum):
    """Merit distribution strategy types."""
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    LOGARITHMIC = "logarithmic"
    FLAT = "flat"
    CUSTOM = "custom"
    PERFORMANCE_BASED = "performance_based"
    RISK_ADJUSTED = "risk_adjusted"
    MARKET_COMPETITIVE = "market_competitive"


class RiskFactor(Enum):
    """Risk adjustment factors."""
    FLIGHT_RISK = "flight_risk"
    PERFORMANCE_DECLINE = "performance_decline"
    MARKET_PRESSURE = "market_pressure"
    SUCCESSION_RISK = "succession_risk"
    SKILL_SCARCITY = "skill_scarcity"


@dataclass
class MeritDistributionConfig:
    """Configuration for merit distribution calculation."""
    strategy: DistributionStrategy
    base_merit_rate: float
    level_count: int = 5
    parameters: Dict[str, Any] = None
    risk_adjustments: Dict[RiskFactor, float] = None
    constraints: Dict[str, Any] = None
    custom_factors: Optional[List[float]] = None


@dataclass
class LevelMeritResult:
    """Merit rate result for a specific level."""
    level_id: int
    base_merit_rate: float
    risk_adjusted_rate: float
    final_merit_rate: float
    adjustment_factors: Dict[str, float]
    constraint_violations: List[str]


@dataclass
class MeritDistributionResult:
    """Complete merit distribution calculation result."""
    strategy_used: DistributionStrategy
    base_merit_rate: float
    level_results: List[LevelMeritResult]
    distribution_statistics: Dict[str, float]
    total_cost_impact: float
    compliance_status: Dict[str, Any]
    recommendations: List[str]


class MeritDistributionStrategy(ABC):
    """Abstract base class for merit distribution strategies."""

    def __init__(self, config: MeritDistributionConfig):
        self.config = config

    @abstractmethod
    def calculate_distribution(
        self,
        context: Dict[str, Any] = None
    ) -> List[float]:
        """Calculate merit rates for each level."""
        pass

    @abstractmethod
    def get_strategy_description(self) -> str:
        """Get human-readable description of the strategy."""
        pass

    def validate_distribution(self, rates: List[float]) -> List[str]:
        """Validate distribution against constraints."""
        violations = []

        if not rates:
            violations.append("No merit rates calculated")
            return violations

        # Check constraints from config
        if self.config.constraints:
            min_rate = self.config.constraints.get('min_rate', 0.0)
            max_rate = self.config.constraints.get('max_rate', 1.0)
            max_variance = self.config.constraints.get('max_variance_ratio', 0.5)

            # Check bounds
            for i, rate in enumerate(rates):
                if rate < min_rate:
                    violations.append(f"Level {i+1} rate {rate:.3f} below minimum {min_rate:.3f}")
                if rate > max_rate:
                    violations.append(f"Level {i+1} rate {rate:.3f} above maximum {max_rate:.3f}")

            # Check variance
            if len(rates) > 1:
                variance_ratio = np.std(rates) / np.mean(rates) if np.mean(rates) > 0 else 0
                if variance_ratio > max_variance:
                    violations.append(f"Variance ratio {variance_ratio:.3f} exceeds maximum {max_variance:.3f}")

        return violations


class LinearMeritDistribution(MeritDistributionStrategy):
    """Linear merit distribution strategy."""

    def calculate_distribution(self, context: Dict[str, Any] = None) -> List[float]:
        """Linear distribution: higher levels get proportionally higher rates."""
        base_rate = self.config.base_merit_rate
        level_count = self.config.level_count

        # Get linear slope from parameters
        slope = self.config.parameters.get('slope', 0.1) if self.config.parameters else 0.1

        rates = []
        for level in range(level_count):
            # Level 1 gets base rate, each subsequent level gets increment
            rate = base_rate + (level * slope * base_rate)
            rates.append(rate)

        return rates

    def get_strategy_description(self) -> str:
        slope = self.config.parameters.get('slope', 0.1) if self.config.parameters else 0.1
        return f"Linear distribution with {slope:.1%} increment per level"


class ExponentialMeritDistribution(MeritDistributionStrategy):
    """Exponential merit distribution strategy."""

    def calculate_distribution(self, context: Dict[str, Any] = None) -> List[float]:
        """Exponential distribution: steeper increases for higher levels."""
        base_rate = self.config.base_merit_rate
        level_count = self.config.level_count

        # Get exponential factor from parameters
        factor = self.config.parameters.get('growth_factor', 1.15) if self.config.parameters else 1.15

        rates = []
        for level in range(level_count):
            # Exponential growth
            rate = base_rate * (factor ** level)
            rates.append(rate)

        return rates

    def get_strategy_description(self) -> str:
        factor = self.config.parameters.get('growth_factor', 1.15) if self.config.parameters else 1.15
        return f"Exponential distribution with {factor:.2f}x growth factor"


class LogarithmicMeritDistribution(MeritDistributionStrategy):
    """Logarithmic merit distribution strategy."""

    def calculate_distribution(self, context: Dict[str, Any] = None) -> List[float]:
        """Logarithmic distribution: diminishing increases for higher levels."""
        base_rate = self.config.base_merit_rate
        level_count = self.config.level_count

        # Get logarithmic scaling from parameters
        scale = self.config.parameters.get('log_scale', 0.5) if self.config.parameters else 0.5

        rates = []
        for level in range(level_count):
            # Logarithmic scaling (level + 1 to avoid log(0))
            rate = base_rate * (1 + scale * np.log(level + 1))
            rates.append(rate)

        return rates

    def get_strategy_description(self) -> str:
        scale = self.config.parameters.get('log_scale', 0.5) if self.config.parameters else 0.5
        return f"Logarithmic distribution with {scale:.2f} scaling factor"


class FlatMeritDistribution(MeritDistributionStrategy):
    """Flat merit distribution strategy."""

    def calculate_distribution(self, context: Dict[str, Any] = None) -> List[float]:
        """Flat distribution: equal merit rates for all levels."""
        base_rate = self.config.base_merit_rate
        level_count = self.config.level_count

        return [base_rate] * level_count

    def get_strategy_description(self) -> str:
        return f"Flat distribution with {self.config.base_merit_rate:.1%} for all levels"


class PerformanceBasedMeritDistribution(MeritDistributionStrategy):
    """Performance-based merit distribution strategy."""

    def calculate_distribution(self, context: Dict[str, Any] = None) -> List[float]:
        """Distribution based on performance metrics by level."""
        base_rate = self.config.base_merit_rate
        level_count = self.config.level_count

        # Get performance multipliers from context or use defaults
        if context and 'performance_multipliers' in context:
            multipliers = context['performance_multipliers'][:level_count]
        else:
            # Default: assume higher levels have higher performance expectations
            multipliers = [1.0 + (level * 0.1) for level in range(level_count)]

        rates = []
        for level in range(level_count):
            multiplier = multipliers[level] if level < len(multipliers) else 1.0
            rate = base_rate * multiplier
            rates.append(rate)

        return rates

    def get_strategy_description(self) -> str:
        return "Performance-based distribution using performance multipliers"


class RiskAdjustedMeritDistribution(MeritDistributionStrategy):
    """Risk-adjusted merit distribution strategy."""

    def calculate_distribution(self, context: Dict[str, Any] = None) -> List[float]:
        """Distribution adjusted for various risk factors."""
        base_rate = self.config.base_merit_rate
        level_count = self.config.level_count

        # Start with linear distribution as base
        linear_rates = [base_rate * (1 + level * 0.05) for level in range(level_count)]

        # Apply risk adjustments if configured
        if self.config.risk_adjustments:
            risk_factors = self._calculate_risk_factors(context)

            for level in range(level_count):
                adjustment = self._calculate_level_risk_adjustment(level, risk_factors)
                linear_rates[level] *= (1 + adjustment)

        return linear_rates

    def _calculate_risk_factors(self, context: Dict[str, Any] = None) -> Dict[RiskFactor, float]:
        """Calculate risk factor scores."""
        risk_scores = {}

        for risk_factor, weight in self.config.risk_adjustments.items():
            if context and f"{risk_factor.value}_scores" in context:
                # Use actual risk scores from context
                scores = context[f"{risk_factor.value}_scores"]
                risk_scores[risk_factor] = np.mean(scores) * weight
            else:
                # Use default risk scoring
                default_score = self._get_default_risk_score(risk_factor)
                risk_scores[risk_factor] = default_score * weight

        return risk_scores

    def _get_default_risk_score(self, risk_factor: RiskFactor) -> float:
        """Get default risk score for a factor."""
        defaults = {
            RiskFactor.FLIGHT_RISK: 0.1,
            RiskFactor.PERFORMANCE_DECLINE: 0.05,
            RiskFactor.MARKET_PRESSURE: 0.15,
            RiskFactor.SUCCESSION_RISK: 0.08,
            RiskFactor.SKILL_SCARCITY: 0.12
        }
        return defaults.get(risk_factor, 0.0)

    def _calculate_level_risk_adjustment(
        self,
        level: int,
        risk_factors: Dict[RiskFactor, float]
    ) -> float:
        """Calculate risk adjustment for a specific level."""
        # Higher levels typically have higher risk exposure
        level_multiplier = 1.0 + (level * 0.1)

        total_adjustment = 0.0
        for risk_factor, score in risk_factors.items():
            # Different risk factors affect levels differently
            if risk_factor == RiskFactor.SUCCESSION_RISK:
                # Higher levels have more succession risk
                total_adjustment += score * level_multiplier
            elif risk_factor == RiskFactor.SKILL_SCARCITY:
                # Mid to high levels most affected
                if level >= 2:
                    total_adjustment += score * level_multiplier
            else:
                # General risk factors
                total_adjustment += score

        return total_adjustment

    def get_strategy_description(self) -> str:
        risk_types = [rf.value for rf in self.config.risk_adjustments.keys()] if self.config.risk_adjustments else []
        return f"Risk-adjusted distribution considering: {', '.join(risk_types)}"


class CustomMeritDistribution(MeritDistributionStrategy):
    """Custom merit distribution using user-defined factors."""

    def calculate_distribution(self, context: Dict[str, Any] = None) -> List[float]:
        """Custom distribution using provided factors."""
        base_rate = self.config.base_merit_rate

        if not self.config.custom_factors:
            raise ValueError("Custom factors must be provided for custom distribution")

        factors = self.config.custom_factors[:self.config.level_count]

        # Pad with 1.0 if insufficient factors provided
        while len(factors) < self.config.level_count:
            factors.append(1.0)

        rates = [base_rate * factor for factor in factors]
        return rates

    def get_strategy_description(self) -> str:
        factors = self.config.custom_factors[:5] if self.config.custom_factors else []
        return f"Custom distribution with factors: {factors}"


class ConfigurableMeritDistributionSystem:
    """
    Configurable merit distribution system supporting multiple strategies.

    Features:
    - Multiple distribution strategies
    - Risk adjustments
    - Business constraint integration
    - Cost impact analysis
    - Compliance checking
    - Historical pattern analysis
    """

    def __init__(self, duckdb_resource: DuckDBResource, config_path: Optional[Path] = None):
        self.duckdb_resource = duckdb_resource
        self.config_path = config_path
        self._strategies = self._initialize_strategies()
        self._initialize_tracking_tables()

    def _initialize_strategies(self) -> Dict[DistributionStrategy, type]:
        """Initialize available distribution strategies."""
        return {
            DistributionStrategy.LINEAR: LinearMeritDistribution,
            DistributionStrategy.EXPONENTIAL: ExponentialMeritDistribution,
            DistributionStrategy.LOGARITHMIC: LogarithmicMeritDistribution,
            DistributionStrategy.FLAT: FlatMeritDistribution,
            DistributionStrategy.PERFORMANCE_BASED: PerformanceBasedMeritDistribution,
            DistributionStrategy.RISK_ADJUSTED: RiskAdjustedMeritDistribution,
            DistributionStrategy.CUSTOM: CustomMeritDistribution
        }

    def _initialize_tracking_tables(self):
        """Initialize DuckDB tables for merit distribution tracking."""
        with self.duckdb_resource.get_connection() as conn:
            # Merit distribution configurations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS merit_distribution_configs (
                    config_id VARCHAR PRIMARY KEY,
                    config_name VARCHAR,
                    strategy VARCHAR,
                    base_merit_rate DOUBLE,
                    level_count INTEGER,
                    parameters_json VARCHAR,
                    risk_adjustments_json VARCHAR,
                    constraints_json VARCHAR,
                    custom_factors_json VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by VARCHAR
                )
            """)

            # Merit distribution results
            conn.execute("""
                CREATE TABLE IF NOT EXISTS merit_distribution_results (
                    result_id VARCHAR PRIMARY KEY,
                    config_id VARCHAR,
                    calculation_timestamp TIMESTAMP,
                    strategy_used VARCHAR,
                    base_merit_rate DOUBLE,
                    level_results_json VARCHAR,
                    distribution_stats_json VARCHAR,
                    total_cost_impact DOUBLE,
                    compliance_status_json VARCHAR,
                    context_json VARCHAR,
                    FOREIGN KEY (config_id) REFERENCES merit_distribution_configs(config_id)
                )
            """)

            # Create indexes
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_merit_config_strategy ON merit_distribution_configs(strategy)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_merit_results_timestamp ON merit_distribution_results(calculation_timestamp DESC)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_merit_results_config ON merit_distribution_results(config_id)")
            except:
                pass

    def calculate_merit_distribution(
        self,
        config: MeritDistributionConfig,
        context: Dict[str, Any] = None
    ) -> MeritDistributionResult:
        """
        Calculate merit distribution using specified strategy.

        Args:
            config: Merit distribution configuration
            context: Additional context data (workforce metrics, risk scores, etc.)

        Returns:
            Complete merit distribution calculation result
        """
        logger.info(f"Calculating merit distribution using {config.strategy.value} strategy")

        # Get strategy implementation
        strategy_class = self._strategies.get(config.strategy)
        if not strategy_class:
            raise ValueError(f"Unknown distribution strategy: {config.strategy}")

        strategy = strategy_class(config)

        # Calculate base distribution
        base_rates = strategy.calculate_distribution(context)

        # Apply risk adjustments
        level_results = []
        for level in range(len(base_rates)):
            base_rate = base_rates[level]

            # Calculate risk adjustments
            risk_adjusted_rate, adjustment_factors = self._apply_risk_adjustments(
                level, base_rate, config, context
            )

            # Apply final constraints and validation
            final_rate, violations = self._apply_constraints(
                level, risk_adjusted_rate, config
            )

            level_result = LevelMeritResult(
                level_id=level + 1,
                base_merit_rate=base_rate,
                risk_adjusted_rate=risk_adjusted_rate,
                final_merit_rate=final_rate,
                adjustment_factors=adjustment_factors,
                constraint_violations=violations
            )
            level_results.append(level_result)

        # Calculate distribution statistics
        final_rates = [r.final_merit_rate for r in level_results]
        distribution_stats = self._calculate_distribution_statistics(final_rates)

        # Calculate cost impact
        cost_impact = self._calculate_cost_impact(level_results, context)

        # Check compliance
        compliance_status = self._check_compliance(level_results, config)

        # Generate recommendations
        recommendations = self._generate_recommendations(level_results, config, context)

        result = MeritDistributionResult(
            strategy_used=config.strategy,
            base_merit_rate=config.base_merit_rate,
            level_results=level_results,
            distribution_statistics=distribution_stats,
            total_cost_impact=cost_impact,
            compliance_status=compliance_status,
            recommendations=recommendations
        )

        # Store results
        self._store_distribution_result(result, config, context)

        logger.info(f"Merit distribution calculated: {len(level_results)} levels, ${cost_impact:,.0f} impact")

        return result

    def _apply_risk_adjustments(
        self,
        level: int,
        base_rate: float,
        config: MeritDistributionConfig,
        context: Dict[str, Any] = None
    ) -> Tuple[float, Dict[str, float]]:
        """Apply risk adjustments to base merit rate."""
        adjusted_rate = base_rate
        adjustment_factors = {}

        if not config.risk_adjustments:
            return adjusted_rate, adjustment_factors

        for risk_factor, weight in config.risk_adjustments.items():
            # Get risk score for this level
            risk_score = self._get_risk_score(risk_factor, level, context)

            # Calculate adjustment
            adjustment = risk_score * weight
            adjustment_factors[risk_factor.value] = adjustment

            # Apply adjustment
            adjusted_rate *= (1 + adjustment)

        return adjusted_rate, adjustment_factors

    def _get_risk_score(
        self,
        risk_factor: RiskFactor,
        level: int,
        context: Dict[str, Any] = None
    ) -> float:
        """Get risk score for a specific factor and level."""
        if context and f"{risk_factor.value}_by_level" in context:
            level_scores = context[f"{risk_factor.value}_by_level"]
            return level_scores.get(str(level + 1), 0.0)

        # Default risk scoring based on level and factor type
        if risk_factor == RiskFactor.FLIGHT_RISK:
            # Higher levels typically have higher flight risk
            return 0.05 + (level * 0.02)
        elif risk_factor == RiskFactor.MARKET_PRESSURE:
            # Mid to senior levels most affected
            return 0.1 if level >= 2 else 0.05
        elif risk_factor == RiskFactor.SUCCESSION_RISK:
            # Senior levels have higher succession risk
            return 0.02 + (level * 0.03)
        elif risk_factor == RiskFactor.SKILL_SCARCITY:
            # Technical levels (2-4) most affected
            return 0.08 if 1 <= level <= 3 else 0.04
        else:
            return 0.05  # Default

    def _apply_constraints(
        self,
        level: int,
        rate: float,
        config: MeritDistributionConfig
    ) -> Tuple[float, List[str]]:
        """Apply constraints and return adjusted rate with violations."""
        violations = []
        adjusted_rate = rate

        if not config.constraints:
            return adjusted_rate, violations

        # Min/max rate constraints
        min_rate = config.constraints.get('min_rate', 0.0)
        max_rate = config.constraints.get('max_rate', 1.0)

        if rate < min_rate:
            violations.append(f"Rate {rate:.3f} below minimum {min_rate:.3f}")
            adjusted_rate = min_rate
        elif rate > max_rate:
            violations.append(f"Rate {rate:.3f} above maximum {max_rate:.3f}")
            adjusted_rate = max_rate

        # Level-specific constraints
        level_constraints = config.constraints.get('level_constraints', {})
        if str(level + 1) in level_constraints:
            level_min = level_constraints[str(level + 1)].get('min', min_rate)
            level_max = level_constraints[str(level + 1)].get('max', max_rate)

            if adjusted_rate < level_min:
                violations.append(f"Level {level + 1} rate below level minimum {level_min:.3f}")
                adjusted_rate = level_min
            elif adjusted_rate > level_max:
                violations.append(f"Level {level + 1} rate above level maximum {level_max:.3f}")
                adjusted_rate = level_max

        return adjusted_rate, violations

    def _calculate_distribution_statistics(self, rates: List[float]) -> Dict[str, float]:
        """Calculate statistical measures of the distribution."""
        if not rates:
            return {}

        rates_array = np.array(rates)

        return {
            "mean": float(np.mean(rates_array)),
            "median": float(np.median(rates_array)),
            "std_dev": float(np.std(rates_array)),
            "variance": float(np.var(rates_array)),
            "min": float(np.min(rates_array)),
            "max": float(np.max(rates_array)),
            "range": float(np.max(rates_array) - np.min(rates_array)),
            "coefficient_of_variation": float(np.std(rates_array) / np.mean(rates_array)) if np.mean(rates_array) > 0 else 0.0,
            "progression_slope": self._calculate_progression_slope(rates)
        }

    def _calculate_progression_slope(self, rates: List[float]) -> float:
        """Calculate the slope of merit rate progression across levels."""
        if len(rates) < 2:
            return 0.0

        levels = list(range(1, len(rates) + 1))
        return float(np.polyfit(levels, rates, 1)[0])

    def _calculate_cost_impact(
        self,
        level_results: List[LevelMeritResult],
        context: Dict[str, Any] = None
    ) -> float:
        """Calculate total cost impact of the merit distribution."""
        if not context:
            # Use default workforce assumptions
            context = {
                'workforce_size': 1000,
                'avg_salary': 75000,
                'level_distribution': [0.4, 0.3, 0.2, 0.07, 0.03]  # % by level
            }

        total_cost = 0.0
        workforce_size = context.get('workforce_size', 1000)
        avg_salary = context.get('avg_salary', 75000)
        level_distribution = context.get('level_distribution', [0.2] * 5)

        for i, result in enumerate(level_results):
            level_employees = workforce_size * level_distribution[i] if i < len(level_distribution) else 0
            level_avg_salary = context.get(f'level_{i+1}_avg_salary', avg_salary)

            level_cost = result.final_merit_rate * level_employees * level_avg_salary
            total_cost += level_cost

        return total_cost

    def _check_compliance(
        self,
        level_results: List[LevelMeritResult],
        config: MeritDistributionConfig
    ) -> Dict[str, Any]:
        """Check compliance with business rules and regulations."""
        compliance = {
            "overall_compliant": True,
            "violations": [],
            "warnings": [],
            "compliance_score": 0.0
        }

        # Check for constraint violations
        total_violations = 0
        for result in level_results:
            total_violations += len(result.constraint_violations)
            compliance["violations"].extend([
                f"Level {result.level_id}: {violation}"
                for violation in result.constraint_violations
            ])

        # Check progression logic
        rates = [r.final_merit_rate for r in level_results]
        if len(rates) > 1:
            # Check if progression makes business sense
            for i in range(len(rates) - 1):
                # For most strategies, higher levels should get equal or higher rates
                if rates[i] > rates[i + 1] and config.strategy not in [DistributionStrategy.FLAT]:
                    compliance["warnings"].append(
                        f"Level {i+1} rate ({rates[i]:.3f}) exceeds Level {i+2} rate ({rates[i+1]:.3f})"
                    )

        # Calculate compliance score
        compliance["overall_compliant"] = total_violations == 0
        compliance["compliance_score"] = max(0.0, 1.0 - (total_violations * 0.1))

        return compliance

    def _generate_recommendations(
        self,
        level_results: List[LevelMeritResult],
        config: MeritDistributionConfig,
        context: Dict[str, Any] = None
    ) -> List[str]:
        """Generate recommendations based on distribution analysis."""
        recommendations = []

        # Check for high variance
        rates = [r.final_merit_rate for r in level_results]
        if len(rates) > 1:
            cv = np.std(rates) / np.mean(rates) if np.mean(rates) > 0 else 0
            if cv > 0.3:
                recommendations.append(
                    f"High variability in merit rates (CV: {cv:.2f}) - consider smoothing distribution"
                )

        # Check for constraint violations
        violated_levels = [r for r in level_results if r.constraint_violations]
        if violated_levels:
            recommendations.append(
                f"{len(violated_levels)} levels have constraint violations - review parameters"
            )

        # Strategy-specific recommendations
        if config.strategy == DistributionStrategy.LINEAR:
            slope = np.polyfit(range(len(rates)), rates, 1)[0] if len(rates) > 1 else 0
            if abs(slope) < 0.002:
                recommendations.append("Linear progression is very flat - consider increasing slope parameter")

        elif config.strategy == DistributionStrategy.EXPONENTIAL:
            if max(rates) / min(rates) > 3:
                recommendations.append("Exponential distribution creates large gaps - consider reducing growth factor")

        # Cost impact recommendations
        if context:
            total_cost = self._calculate_cost_impact(level_results, context)
            budget_limit = context.get('budget_limit', float('inf'))

            if total_cost > budget_limit:
                recommendations.append(
                    f"Distribution exceeds budget by ${total_cost - budget_limit:,.0f} - consider reducing rates"
                )

        return recommendations

    def _store_distribution_result(
        self,
        result: MeritDistributionResult,
        config: MeritDistributionConfig,
        context: Dict[str, Any] = None
    ):
        """Store merit distribution result in database."""
        import uuid
        result_id = str(uuid.uuid4())

        with self.duckdb_resource.get_connection() as conn:
            conn.execute("""
                INSERT INTO merit_distribution_results (
                    result_id, config_id, calculation_timestamp, strategy_used,
                    base_merit_rate, level_results_json, distribution_stats_json,
                    total_cost_impact, compliance_status_json, context_json
                ) VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?)
            """, [
                result_id,
                "default_config",  # Could link to stored config
                result.strategy_used.value,
                result.base_merit_rate,
                json.dumps([asdict(r) for r in result.level_results], default=str),
                json.dumps(result.distribution_statistics),
                result.total_cost_impact,
                json.dumps(result.compliance_status),
                json.dumps(context or {})
            ])

    def get_strategy_comparison(
        self,
        base_merit_rate: float,
        strategies: List[DistributionStrategy] = None,
        context: Dict[str, Any] = None
    ) -> Dict[str, MeritDistributionResult]:
        """Compare multiple distribution strategies."""
        if strategies is None:
            strategies = [
                DistributionStrategy.LINEAR,
                DistributionStrategy.EXPONENTIAL,
                DistributionStrategy.FLAT,
                DistributionStrategy.RISK_ADJUSTED
            ]

        comparison_results = {}

        for strategy in strategies:
            try:
                config = MeritDistributionConfig(
                    strategy=strategy,
                    base_merit_rate=base_merit_rate,
                    level_count=5,
                    parameters={'slope': 0.1, 'growth_factor': 1.15, 'log_scale': 0.5},
                    risk_adjustments={
                        RiskFactor.FLIGHT_RISK: 0.1,
                        RiskFactor.MARKET_PRESSURE: 0.15
                    } if strategy == DistributionStrategy.RISK_ADJUSTED else None
                )

                result = self.calculate_merit_distribution(config, context)
                comparison_results[strategy.value] = result

            except Exception as e:
                logger.warning(f"Failed to calculate {strategy.value} distribution: {e}")

        return comparison_results

    def load_config_from_file(self, config_path: Path) -> MeritDistributionConfig:
        """Load merit distribution configuration from YAML file."""
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)

        # Parse strategy
        strategy = DistributionStrategy(config_data.get('strategy', 'linear'))

        # Parse risk adjustments
        risk_adjustments = {}
        if 'risk_adjustments' in config_data:
            for risk_name, weight in config_data['risk_adjustments'].items():
                try:
                    risk_factor = RiskFactor(risk_name)
                    risk_adjustments[risk_factor] = weight
                except ValueError:
                    logger.warning(f"Unknown risk factor: {risk_name}")

        return MeritDistributionConfig(
            strategy=strategy,
            base_merit_rate=config_data.get('base_merit_rate', 0.04),
            level_count=config_data.get('level_count', 5),
            parameters=config_data.get('parameters', {}),
            risk_adjustments=risk_adjustments if risk_adjustments else None,
            constraints=config_data.get('constraints', {}),
            custom_factors=config_data.get('custom_factors')
        )

    def get_historical_trends(self, days_back: int = 30) -> pd.DataFrame:
        """Get historical merit distribution trends."""
        with self.duckdb_resource.get_connection() as conn:
            return conn.execute("""
                SELECT
                    calculation_timestamp,
                    strategy_used,
                    base_merit_rate,
                    total_cost_impact,
                    JSON_EXTRACT(distribution_stats_json, '$.mean') as mean_rate,
                    JSON_EXTRACT(distribution_stats_json, '$.coefficient_of_variation') as cv,
                    JSON_EXTRACT(compliance_status_json, '$.compliance_score') as compliance_score
                FROM merit_distribution_results
                WHERE calculation_timestamp >= CURRENT_TIMESTAMP - INTERVAL ? DAY
                ORDER BY calculation_timestamp DESC
            """, [days_back]).df()


# Add missing import
import json
