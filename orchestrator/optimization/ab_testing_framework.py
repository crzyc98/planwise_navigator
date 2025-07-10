"""
S050: A/B Testing Framework for Optimization Validation

Statistical validation framework for testing optimization recommendations
against baseline methods and validating synthetic vs real simulation correlation.
"""

from __future__ import annotations
import json
import uuid
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import ttest_ind, chi2_contingency, mannwhitneyu
import logging

from orchestrator.resources.duckdb_resource import DuckDBResource

logger = logging.getLogger(__name__)


class TestStatus(Enum):
    """A/B test status."""
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class TestVariant(Enum):
    """Test variant types."""
    CONTROL = "control"
    TREATMENT = "treatment"


@dataclass
class ABTestMetric:
    """A/B test metric definition."""
    name: str
    description: str
    metric_type: str  # 'continuous', 'binary', 'count'
    primary: bool = False
    expected_direction: str = 'increase'  # 'increase', 'decrease', 'neutral'
    minimum_detectable_effect: float = 0.05


@dataclass
class ABTestConfig:
    """A/B test configuration."""
    test_id: str
    test_name: str
    description: str
    control_parameters: Dict[str, float]
    treatment_parameters: Dict[str, float]
    success_metrics: List[ABTestMetric]
    sample_size_per_group: int
    test_duration_days: int
    significance_level: float = 0.05
    power: float = 0.8
    randomization_seed: Optional[int] = None


@dataclass
class ABTestResult:
    """Individual A/B test result for a metric."""
    metric_name: str
    control_mean: float
    treatment_mean: float
    effect_size: float
    effect_size_ci: Tuple[float, float]
    p_value: float
    significant: bool
    test_statistic: float
    control_n: int
    treatment_n: int
    statistical_power: float
    confidence_level: float


@dataclass
class ABTestAnalysis:
    """Complete A/B test analysis results."""
    test_id: str
    analysis_timestamp: str
    test_duration_actual: int
    sample_size_actual: Dict[str, int]
    metric_results: List[ABTestResult]
    overall_recommendation: str
    statistical_summary: Dict[str, Any]
    confidence_score: float
    business_impact: Dict[str, Any]


class OptimizationABTestFramework:
    """
    A/B testing framework for optimization validation.

    Features:
    - Statistical test design and power analysis
    - Randomized controlled experiments
    - Multiple metric tracking
    - Effect size estimation with confidence intervals
    - Business impact quantification
    - Automated recommendations
    """

    def __init__(self, duckdb_resource: DuckDBResource):
        self.duckdb_resource = duckdb_resource
        self._initialize_testing_tables()

    def _initialize_testing_tables(self):
        """Initialize DuckDB tables for A/B testing."""
        with self.duckdb_resource.get_connection() as conn:
            # A/B test configurations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_configs (
                    test_id VARCHAR PRIMARY KEY,
                    test_name VARCHAR,
                    description TEXT,
                    control_params_json VARCHAR,
                    treatment_params_json VARCHAR,
                    success_metrics_json VARCHAR,
                    sample_size_per_group INTEGER,
                    test_duration_days INTEGER,
                    significance_level DOUBLE,
                    power_level DOUBLE,
                    randomization_seed INTEGER,
                    status VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)

            # A/B test observations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_observations (
                    observation_id VARCHAR PRIMARY KEY,
                    test_id VARCHAR,
                    variant VARCHAR,
                    observation_timestamp TIMESTAMP,
                    entity_id VARCHAR,
                    metrics_json VARCHAR,
                    simulation_run_id VARCHAR,
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id)
                )
            """)

            # A/B test analysis results
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_analyses (
                    analysis_id VARCHAR PRIMARY KEY,
                    test_id VARCHAR,
                    analysis_timestamp TIMESTAMP,
                    test_duration_actual INTEGER,
                    sample_sizes_json VARCHAR,
                    metric_results_json VARCHAR,
                    overall_recommendation TEXT,
                    statistical_summary_json VARCHAR,
                    confidence_score DOUBLE,
                    business_impact_json VARCHAR,
                    FOREIGN KEY (test_id) REFERENCES ab_test_configs(test_id)
                )
            """)

            # Create indexes
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ab_test_status ON ab_test_configs(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ab_test_created ON ab_test_configs(created_at DESC)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ab_observations_test ON ab_test_observations(test_id, variant)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ab_analyses_test ON ab_test_analyses(test_id, analysis_timestamp DESC)")
            except:
                pass

    def design_ab_test(
        self,
        test_name: str,
        description: str,
        control_parameters: Dict[str, float],
        treatment_parameters: Dict[str, float],
        success_metrics: List[ABTestMetric],
        expected_effect_size: float = 0.05,
        significance_level: float = 0.05,
        power: float = 0.8
    ) -> ABTestConfig:
        """
        Design A/B test with statistical power analysis.

        Args:
            test_name: Human-readable test name
            description: Test description and hypothesis
            control_parameters: Control group parameters
            treatment_parameters: Treatment group parameters
            success_metrics: List of metrics to track
            expected_effect_size: Expected minimum detectable effect
            significance_level: Type I error rate (alpha)
            power: Statistical power (1 - beta)

        Returns:
            Complete A/B test configuration
        """
        test_id = f"ab_test_{uuid.uuid4().hex[:8]}"

        # Calculate required sample size
        sample_size = self._calculate_sample_size(
            expected_effect_size, significance_level, power
        )

        # Estimate test duration based on simulation throughput
        test_duration = self._estimate_test_duration(sample_size)

        config = ABTestConfig(
            test_id=test_id,
            test_name=test_name,
            description=description,
            control_parameters=control_parameters,
            treatment_parameters=treatment_parameters,
            success_metrics=success_metrics,
            sample_size_per_group=sample_size,
            test_duration_days=test_duration,
            significance_level=significance_level,
            power=power,
            randomization_seed=int(time.time())
        )

        # Store configuration
        self._store_test_config(config)

        logger.info(f"Designed A/B test {test_id}: {sample_size} samples per group, {test_duration} days")

        return config

    def start_ab_test(self, test_id: str) -> bool:
        """Start an A/B test."""
        with self.duckdb_resource.get_connection() as conn:
            # Update test status
            result = conn.execute("""
                UPDATE ab_test_configs
                SET status = 'active', started_at = CURRENT_TIMESTAMP
                WHERE test_id = ? AND status = 'draft'
            """, [test_id])

            if result.rowcount > 0:
                logger.info(f"Started A/B test {test_id}")
                return True
            else:
                logger.warning(f"Could not start A/B test {test_id} - check status")
                return False

    def record_observation(
        self,
        test_id: str,
        variant: TestVariant,
        entity_id: str,
        metrics: Dict[str, float],
        simulation_run_id: Optional[str] = None
    ) -> str:
        """Record an observation for the A/B test."""
        observation_id = f"obs_{uuid.uuid4().hex[:12]}"

        with self.duckdb_resource.get_connection() as conn:
            conn.execute("""
                INSERT INTO ab_test_observations (
                    observation_id, test_id, variant, observation_timestamp,
                    entity_id, metrics_json, simulation_run_id
                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """, [
                observation_id,
                test_id,
                variant.value,
                entity_id,
                json.dumps(metrics),
                simulation_run_id
            ])

        return observation_id

    def analyze_ab_test(
        self,
        test_id: str,
        interim_analysis: bool = False
    ) -> ABTestAnalysis:
        """
        Analyze A/B test results with comprehensive statistical testing.

        Args:
            test_id: A/B test identifier
            interim_analysis: Whether this is an interim analysis

        Returns:
            Complete statistical analysis results
        """
        logger.info(f"Analyzing A/B test {test_id}")

        # Get test configuration
        config = self._get_test_config(test_id)
        if not config:
            raise ValueError(f"Test {test_id} not found")

        # Get observations
        control_data, treatment_data = self._get_test_observations(test_id)

        if control_data.empty or treatment_data.empty:
            raise ValueError(f"Insufficient data for test {test_id}")

        # Calculate actual test duration
        test_duration = self._calculate_actual_duration(test_id)

        # Analyze each metric
        metric_results = []
        for metric in config.success_metrics:
            result = self._analyze_metric(
                metric, control_data, treatment_data, config.significance_level
            )
            metric_results.append(result)

        # Generate overall recommendation
        recommendation = self._generate_recommendation(metric_results, config)

        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(metric_results)

        # Calculate business impact
        business_impact = self._calculate_business_impact(metric_results, config)

        # Create statistical summary
        statistical_summary = self._create_statistical_summary(metric_results, config)

        analysis = ABTestAnalysis(
            test_id=test_id,
            analysis_timestamp=datetime.now().isoformat(),
            test_duration_actual=test_duration,
            sample_size_actual={
                "control": len(control_data),
                "treatment": len(treatment_data)
            },
            metric_results=metric_results,
            overall_recommendation=recommendation,
            statistical_summary=statistical_summary,
            confidence_score=confidence_score,
            business_impact=business_impact
        )

        # Store analysis results
        self._store_analysis_results(analysis)

        logger.info(f"A/B test analysis completed for {test_id}: {recommendation}")

        return analysis

    def _calculate_sample_size(
        self,
        effect_size: float,
        alpha: float,
        power: float
    ) -> int:
        """Calculate required sample size using power analysis."""
        # Use Cohen's formula for two-sample t-test
        z_alpha = stats.norm.ppf(1 - alpha / 2)
        z_beta = stats.norm.ppf(power)

        # Sample size per group
        n = 2 * ((z_alpha + z_beta) / effect_size) ** 2

        # Add 20% buffer for dropouts/invalid observations
        n_with_buffer = int(n * 1.2)

        # Minimum practical sample size
        return max(n_with_buffer, 30)

    def _estimate_test_duration(self, sample_size: int) -> int:
        """Estimate test duration based on sample size and simulation capacity."""
        # Assume we can generate ~100 observations per day
        daily_capacity = 100
        total_observations = sample_size * 2  # Both groups

        estimated_days = total_observations / daily_capacity

        # Add buffer and minimum duration
        return max(int(estimated_days * 1.5), 7)  # Minimum 1 week

    def _store_test_config(self, config: ABTestConfig):
        """Store A/B test configuration in database."""
        with self.duckdb_resource.get_connection() as conn:
            conn.execute("""
                INSERT INTO ab_test_configs (
                    test_id, test_name, description, control_params_json,
                    treatment_params_json, success_metrics_json, sample_size_per_group,
                    test_duration_days, significance_level, power_level,
                    randomization_seed, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft')
            """, [
                config.test_id,
                config.test_name,
                config.description,
                json.dumps(config.control_parameters),
                json.dumps(config.treatment_parameters),
                json.dumps([asdict(m) for m in config.success_metrics]),
                config.sample_size_per_group,
                config.test_duration_days,
                config.significance_level,
                config.power,
                config.randomization_seed
            ])

    def _get_test_config(self, test_id: str) -> Optional[ABTestConfig]:
        """Get test configuration from database."""
        with self.duckdb_resource.get_connection() as conn:
            result = conn.execute("""
                SELECT * FROM ab_test_configs WHERE test_id = ?
            """, [test_id]).fetchone()

            if not result:
                return None

            # Reconstruct config object
            success_metrics = [
                ABTestMetric(**m) for m in json.loads(result[5])
            ]

            return ABTestConfig(
                test_id=result[0],
                test_name=result[1],
                description=result[2],
                control_parameters=json.loads(result[3]),
                treatment_parameters=json.loads(result[4]),
                success_metrics=success_metrics,
                sample_size_per_group=result[6],
                test_duration_days=result[7],
                significance_level=result[8],
                power=result[9],
                randomization_seed=result[10]
            )

    def _get_test_observations(self, test_id: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Get control and treatment observations."""
        with self.duckdb_resource.get_connection() as conn:
            # Get all observations for this test
            observations_df = conn.execute("""
                SELECT variant, metrics_json, observation_timestamp
                FROM ab_test_observations
                WHERE test_id = ?
                ORDER BY observation_timestamp
            """, [test_id]).df()

        if observations_df.empty:
            return pd.DataFrame(), pd.DataFrame()

        # Parse metrics JSON
        observations_df['metrics'] = observations_df['metrics_json'].apply(json.loads)

        # Split by variant
        control_data = observations_df[observations_df['variant'] == 'control'].copy()
        treatment_data = observations_df[observations_df['variant'] == 'treatment'].copy()

        return control_data, treatment_data

    def _calculate_actual_duration(self, test_id: str) -> int:
        """Calculate actual test duration in days."""
        with self.duckdb_resource.get_connection() as conn:
            result = conn.execute("""
                SELECT
                    MIN(observation_timestamp) as start_time,
                    MAX(observation_timestamp) as end_time
                FROM ab_test_observations
                WHERE test_id = ?
            """, [test_id]).fetchone()

            if result[0] and result[1]:
                start_time = pd.to_datetime(result[0])
                end_time = pd.to_datetime(result[1])
                return (end_time - start_time).days
            else:
                return 0

    def _analyze_metric(
        self,
        metric: ABTestMetric,
        control_data: pd.DataFrame,
        treatment_data: pd.DataFrame,
        significance_level: float
    ) -> ABTestResult:
        """Analyze a single metric for the A/B test."""
        # Extract metric values
        control_values = [
            obs['metrics'].get(metric.name, 0)
            for _, obs in control_data.iterrows()
        ]
        treatment_values = [
            obs['metrics'].get(metric.name, 0)
            for _, obs in treatment_data.iterrows()
        ]

        control_values = np.array(control_values)
        treatment_values = np.array(treatment_values)

        # Choose appropriate statistical test
        if metric.metric_type == 'continuous':
            test_stat, p_value = self._continuous_metric_test(control_values, treatment_values)
        elif metric.metric_type == 'binary':
            test_stat, p_value = self._binary_metric_test(control_values, treatment_values)
        else:  # count
            test_stat, p_value = self._count_metric_test(control_values, treatment_values)

        # Calculate effect size
        control_mean = np.mean(control_values)
        treatment_mean = np.mean(treatment_values)
        effect_size = (treatment_mean - control_mean) / control_mean if control_mean != 0 else 0

        # Calculate confidence interval for effect size
        effect_size_ci = self._calculate_effect_size_ci(
            control_values, treatment_values, significance_level
        )

        # Calculate statistical power
        statistical_power = self._calculate_post_hoc_power(
            control_values, treatment_values, significance_level
        )

        return ABTestResult(
            metric_name=metric.name,
            control_mean=control_mean,
            treatment_mean=treatment_mean,
            effect_size=effect_size,
            effect_size_ci=effect_size_ci,
            p_value=p_value,
            significant=p_value < significance_level,
            test_statistic=test_stat,
            control_n=len(control_values),
            treatment_n=len(treatment_values),
            statistical_power=statistical_power,
            confidence_level=1 - significance_level
        )

    def _continuous_metric_test(
        self,
        control: np.ndarray,
        treatment: np.ndarray
    ) -> Tuple[float, float]:
        """Perform statistical test for continuous metric."""
        # Check normality assumption
        if len(control) > 8 and len(treatment) > 8:
            _, control_normal = stats.shapiro(control)
            _, treatment_normal = stats.shapiro(treatment)

            if control_normal > 0.05 and treatment_normal > 0.05:
                # Use t-test for normal data
                return ttest_ind(treatment, control, equal_var=False)

        # Use Mann-Whitney U test for non-normal data
        return mannwhitneyu(treatment, control, alternative='two-sided')

    def _binary_metric_test(
        self,
        control: np.ndarray,
        treatment: np.ndarray
    ) -> Tuple[float, float]:
        """Perform statistical test for binary metric."""
        # Create contingency table
        control_success = np.sum(control)
        control_failure = len(control) - control_success
        treatment_success = np.sum(treatment)
        treatment_failure = len(treatment) - treatment_success

        contingency = np.array([
            [control_success, control_failure],
            [treatment_success, treatment_failure]
        ])

        chi2, p_value, _, _ = chi2_contingency(contingency)
        return chi2, p_value

    def _count_metric_test(
        self,
        control: np.ndarray,
        treatment: np.ndarray
    ) -> Tuple[float, float]:
        """Perform statistical test for count metric."""
        # Use Poisson test or Mann-Whitney depending on distribution
        return mannwhitneyu(treatment, control, alternative='two-sided')

    def _calculate_effect_size_ci(
        self,
        control: np.ndarray,
        treatment: np.ndarray,
        alpha: float
    ) -> Tuple[float, float]:
        """Calculate confidence interval for effect size."""
        if len(control) == 0 or len(treatment) == 0:
            return (0.0, 0.0)

        # Bootstrap confidence interval
        n_bootstrap = 1000
        effect_sizes = []

        np.random.seed(42)  # For reproducibility

        for _ in range(n_bootstrap):
            # Bootstrap samples
            control_sample = np.random.choice(control, size=len(control), replace=True)
            treatment_sample = np.random.choice(treatment, size=len(treatment), replace=True)

            # Calculate effect size
            control_mean = np.mean(control_sample)
            treatment_mean = np.mean(treatment_sample)

            if control_mean != 0:
                effect_size = (treatment_mean - control_mean) / control_mean
                effect_sizes.append(effect_size)

        if effect_sizes:
            lower = np.percentile(effect_sizes, (alpha / 2) * 100)
            upper = np.percentile(effect_sizes, (1 - alpha / 2) * 100)
            return (lower, upper)
        else:
            return (0.0, 0.0)

    def _calculate_post_hoc_power(
        self,
        control: np.ndarray,
        treatment: np.ndarray,
        alpha: float
    ) -> float:
        """Calculate post-hoc statistical power."""
        if len(control) == 0 or len(treatment) == 0:
            return 0.0

        # Cohen's d (effect size)
        pooled_std = np.sqrt((np.var(control) + np.var(treatment)) / 2)
        if pooled_std == 0:
            return 0.0

        cohens_d = (np.mean(treatment) - np.mean(control)) / pooled_std

        # Power calculation using normal approximation
        n_per_group = min(len(control), len(treatment))
        z_alpha = stats.norm.ppf(1 - alpha / 2)
        z_beta = cohens_d * np.sqrt(n_per_group / 2) - z_alpha

        power = stats.norm.cdf(z_beta)
        return max(0.0, min(1.0, power))

    def _generate_recommendation(
        self,
        metric_results: List[ABTestResult],
        config: ABTestConfig
    ) -> str:
        """Generate overall recommendation based on metric results."""
        primary_metrics = [r for r in metric_results if any(m.name == r.metric_name and m.primary for m in config.success_metrics)]

        if not primary_metrics:
            primary_metrics = metric_results  # Use all metrics if no primary specified

        significant_positive = [r for r in primary_metrics if r.significant and r.effect_size > 0]
        significant_negative = [r for r in primary_metrics if r.significant and r.effect_size < 0]

        if len(significant_positive) > len(significant_negative):
            return "RECOMMEND TREATMENT: Statistically significant positive effects observed"
        elif len(significant_negative) > len(significant_positive):
            return "RECOMMEND CONTROL: Statistically significant negative effects observed"
        elif significant_positive or significant_negative:
            return "MIXED RESULTS: Significant effects in both directions - review individual metrics"
        else:
            return "NO SIGNIFICANT DIFFERENCE: Insufficient evidence to prefer either variant"

    def _calculate_confidence_score(self, metric_results: List[ABTestResult]) -> float:
        """Calculate overall confidence score for the test results."""
        if not metric_results:
            return 0.0

        # Factors: statistical power, sample size, consistency
        avg_power = np.mean([r.statistical_power for r in metric_results])
        min_sample_size = min([min(r.control_n, r.treatment_n) for r in metric_results])

        # Sample size factor (0-1)
        sample_factor = min(1.0, min_sample_size / 100)  # 100 as reasonable minimum

        # Consistency factor (how aligned are the effect directions)
        positive_effects = sum(1 for r in metric_results if r.effect_size > 0)
        negative_effects = sum(1 for r in metric_results if r.effect_size < 0)
        total_effects = len(metric_results)

        consistency = abs(positive_effects - negative_effects) / total_effects if total_effects > 0 else 0

        # Combined confidence score
        confidence = (avg_power * 0.4 + sample_factor * 0.3 + consistency * 0.3)
        return min(1.0, confidence)

    def _calculate_business_impact(
        self,
        metric_results: List[ABTestResult],
        config: ABTestConfig
    ) -> Dict[str, Any]:
        """Calculate business impact of the treatment."""
        impact = {
            "metric_impacts": {},
            "overall_impact_score": 0.0,
            "confidence_adjusted_impact": 0.0
        }

        total_impact = 0.0
        for result in metric_results:
            # Get expected direction for this metric
            metric_config = next(
                (m for m in config.success_metrics if m.name == result.metric_name),
                None
            )

            if metric_config:
                # Calculate directional impact
                expected_positive = metric_config.expected_direction in ['increase', 'neutral']
                actual_positive = result.effect_size > 0

                aligned = (expected_positive and actual_positive) or (not expected_positive and not actual_positive)

                impact_score = abs(result.effect_size) if aligned else -abs(result.effect_size)

                # Weight by significance and confidence
                weighted_impact = impact_score * (1.0 if result.significant else 0.5) * result.statistical_power

                impact["metric_impacts"][result.metric_name] = {
                    "effect_size": result.effect_size,
                    "aligned_with_expectation": aligned,
                    "weighted_impact": weighted_impact,
                    "statistical_significance": result.significant
                }

                total_impact += weighted_impact

        impact["overall_impact_score"] = total_impact / len(metric_results) if metric_results else 0.0

        # Confidence-adjusted impact
        confidence_score = self._calculate_confidence_score(metric_results)
        impact["confidence_adjusted_impact"] = impact["overall_impact_score"] * confidence_score

        return impact

    def _create_statistical_summary(
        self,
        metric_results: List[ABTestResult],
        config: ABTestConfig
    ) -> Dict[str, Any]:
        """Create statistical summary of the test."""
        return {
            "test_configuration": {
                "significance_level": config.significance_level,
                "planned_power": config.power,
                "planned_sample_size": config.sample_size_per_group,
                "planned_duration_days": config.test_duration_days
            },
            "observed_results": {
                "total_metrics": len(metric_results),
                "significant_metrics": sum(1 for r in metric_results if r.significant),
                "avg_effect_size": np.mean([r.effect_size for r in metric_results]),
                "avg_p_value": np.mean([r.p_value for r in metric_results]),
                "avg_statistical_power": np.mean([r.statistical_power for r in metric_results])
            },
            "quality_indicators": {
                "minimum_sample_size": min([min(r.control_n, r.treatment_n) for r in metric_results]) if metric_results else 0,
                "sample_size_balance": self._calculate_balance_score(metric_results),
                "effect_size_consistency": np.std([r.effect_size for r in metric_results]) if metric_results else 0
            }
        }

    def _calculate_balance_score(self, metric_results: List[ABTestResult]) -> float:
        """Calculate how balanced the sample sizes are."""
        if not metric_results:
            return 1.0

        balance_scores = []
        for result in metric_results:
            min_size = min(result.control_n, result.treatment_n)
            max_size = max(result.control_n, result.treatment_n)
            balance = min_size / max_size if max_size > 0 else 1.0
            balance_scores.append(balance)

        return np.mean(balance_scores)

    def _store_analysis_results(self, analysis: ABTestAnalysis):
        """Store A/B test analysis results in database."""
        analysis_id = f"analysis_{uuid.uuid4().hex[:8]}"

        with self.duckdb_resource.get_connection() as conn:
            conn.execute("""
                INSERT INTO ab_test_analyses (
                    analysis_id, test_id, analysis_timestamp, test_duration_actual,
                    sample_sizes_json, metric_results_json, overall_recommendation,
                    statistical_summary_json, confidence_score, business_impact_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                analysis_id,
                analysis.test_id,
                analysis.analysis_timestamp,
                analysis.test_duration_actual,
                json.dumps(analysis.sample_size_actual),
                json.dumps([asdict(r) for r in analysis.metric_results]),
                analysis.overall_recommendation,
                json.dumps(analysis.statistical_summary),
                analysis.confidence_score,
                json.dumps(analysis.business_impact)
            ])

    def get_active_tests(self) -> List[Dict[str, Any]]:
        """Get all active A/B tests."""
        with self.duckdb_resource.get_connection() as conn:
            return conn.execute("""
                SELECT test_id, test_name, description, started_at,
                       sample_size_per_group, test_duration_days
                FROM ab_test_configs
                WHERE status = 'active'
                ORDER BY started_at DESC
            """).df().to_dict('records')

    def get_test_progress(self, test_id: str) -> Dict[str, Any]:
        """Get progress information for an A/B test."""
        with self.duckdb_resource.get_connection() as conn:
            # Get test config
            config_result = conn.execute("""
                SELECT sample_size_per_group, test_duration_days, started_at
                FROM ab_test_configs
                WHERE test_id = ?
            """, [test_id]).fetchone()

            if not config_result:
                return {"error": "Test not found"}

            # Get current observations
            progress_result = conn.execute("""
                SELECT
                    variant,
                    COUNT(*) as observation_count,
                    MIN(observation_timestamp) as first_observation,
                    MAX(observation_timestamp) as last_observation
                FROM ab_test_observations
                WHERE test_id = ?
                GROUP BY variant
            """, [test_id]).df()

        target_size = config_result[0]
        target_duration = config_result[1]
        started_at = pd.to_datetime(config_result[2]) if config_result[2] else None

        progress = {
            "test_id": test_id,
            "target_sample_size": target_size,
            "target_duration_days": target_duration,
            "started_at": started_at.isoformat() if started_at else None,
            "sample_progress": {},
            "time_progress": 0.0
        }

        # Calculate sample progress
        for _, row in progress_result.iterrows():
            variant = row['variant']
            count = row['observation_count']
            progress["sample_progress"][variant] = {
                "current": count,
                "target": target_size,
                "completion_pct": (count / target_size) * 100 if target_size > 0 else 0
            }

        # Calculate time progress
        if started_at and not progress_result.empty:
            days_running = (datetime.now() - started_at).days
            progress["time_progress"] = (days_running / target_duration) * 100 if target_duration > 0 else 0

        return progress

    def complete_test(self, test_id: str) -> bool:
        """Mark an A/B test as completed."""
        with self.duckdb_resource.get_connection() as conn:
            result = conn.execute("""
                UPDATE ab_test_configs
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                WHERE test_id = ? AND status = 'active'
            """, [test_id])

            if result.rowcount > 0:
                logger.info(f"Completed A/B test {test_id}")
                return True
            else:
                logger.warning(f"Could not complete A/B test {test_id} - check status")
                return False
