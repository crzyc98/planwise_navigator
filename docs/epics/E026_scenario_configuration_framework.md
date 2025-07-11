# Epic E026: Scenario Configuration Framework

## Epic Overview

### Summary
Build a high-performance scenario modeling framework with parallel processing that allows plan sponsors to define, compare, and analyze 10+ retirement plan design alternatives simultaneously through validated YAML configuration without code changes.

### Business Value
- Reduces plan design analysis time from weeks to hours
- Enables testing of 10+ scenarios vs traditional 2-3
- Saves $100K+ in actuarial consulting fees annually
- Improves decision quality with data-driven comparisons

### Success Criteria
- ✅ Support 10+ concurrent scenarios with isolated configurations and parallel processing
- ✅ YAML-based configuration with comprehensive Pydantic validation
- ✅ Real-time side-by-side comparison reports with interactive analytics
- ✅ Scenario execution completes in <2 minutes for 10-year projection using vectorized operations
- ✅ AI-powered scenario optimization recommendations
- ✅ Reproducible results with random seed control across all scenarios

---

## User Stories

### Story 1: Advanced Scenario Definition Framework (12 points)
**As a** benefits analyst
**I want** to define multiple plan scenarios in configuration files
**So that** I can test different designs without coding

**Acceptance Criteria:**
- Comprehensive YAML schema for complete plan design with Pydantic validation
- Advanced scenario inheritance (base + overrides) with multiple inheritance levels
- Real-time validation of configuration completeness with detailed error messages
- Support for 20+ named scenarios with efficient memory management
- Git-friendly format with conflict resolution support
- Template library with industry-standard plan designs
- Configuration versioning with rollback capabilities
- Parameter range validation with business rule constraints

### Story 2: High-Performance Scenario Execution Engine (20 points)
**As a** plan sponsor
**I want** to run multiple scenarios in parallel
**So that** I can quickly compare alternatives

**Acceptance Criteria:**
- ProcessPoolExecutor-based parallel execution for CPU-intensive scenarios
- Completely isolated simulation runs with UUID-based data partitioning
- Real-time progress tracking with WebSocket updates and ETA calculations
- Robust error handling with partial results and detailed failure diagnostics
- Resumable execution on failure with checkpoint/restart capabilities
- Dynamic resource allocation based on system capacity
- Scenario dependency management with execution ordering
- Memory-efficient execution with streaming results processing
- Performance monitoring with execution time analytics

### Story 3: Interactive Comparison Report Generator (12 points)
**As a** CFO
**I want** standardized comparison reports
**So that** I can make informed decisions

**Acceptance Criteria:**
- Interactive side-by-side metrics comparison with drill-down capabilities
- Dynamic multi-year cost projections with sensitivity sliders
- Comprehensive participation impact analysis with behavioral insights
- Detailed employee outcome comparisons with retirement readiness scoring
- AI-generated executive summary with data-driven recommendations
- Exportable reports in multiple formats (PDF, Excel, PowerPoint)
- Real-time scenario ranking with customizable weighting criteria
- Cost-benefit analysis with ROI calculations and break-even points

### Story 4: Advanced Sensitivity Analysis Tools (12 points)
**As a** risk manager
**I want** to understand scenario sensitivity
**So that** I can assess uncertainty and risk

**Acceptance Criteria:**
- Multi-parameter sensitivity testing with interaction effects
- High-performance Monte Carlo simulation with 10,000+ iterations
- Statistical confidence intervals on all key projections
- Comprehensive best/worst case analysis with stress testing
- Machine learning-based key driver identification with feature importance
- Tornado diagrams for parameter impact visualization
- Scenario robustness scoring with risk metrics
- What-if analysis with real-time parameter adjustment

### Story 5: Advanced Scenario Management UI (8 points)
**As a** benefits administrator
**I want** a user interface for scenario management
**So that** I can create and modify scenarios easily

**Acceptance Criteria:**
- Modern React-based web UI for scenario creation with drag-and-drop
- Comprehensive template library with industry-standard plan designs
- Real-time validation feedback with suggestion engine
- Advanced import/export capabilities with version control integration
- Smart scenario comparison selection with similarity analysis
- Collaborative editing with user permissions and approval workflows
- Visual configuration builder with plan design wizard
- Integration with external data sources for market benchmarking

---

## Technical Specifications

### Scenario Configuration Schema
```yaml
# Base scenario configuration
scenario_base:
  name: "Current Plan Design"
  description: "2024 baseline 401(k) plan"

  eligibility:
    minimum_age: 21
    minimum_service_months: 12
    entry_dates: ["quarterly"]
    hours_requirement: 1000

  enrollment:
    auto_enrollment:
      enabled: false

  contributions:
    employee:
      pre_tax_allowed: true
      roth_allowed: true
      catch_up_allowed: true
    employer:
      match_formula: "standard_tiered"
      safe_harbor: false

  vesting:
    schedule: "graded_2_to_6"

# Scenario with overrides
scenario_auto_enroll:
  name: "Auto-Enrollment 6%"
  base: "scenario_base"  # Inherit from base
  description: "Add auto-enrollment at 6% with escalation"

  # Override specific settings
  enrollment:
    auto_enrollment:
      enabled: true
      default_rate: 0.06
      annual_increase: 0.01
      maximum_rate: 0.10
      opt_out_window_days: 90

scenario_enhanced_match:
  name: "Enhanced Match Formula"
  base: "scenario_base"
  description: "Increase match to 100% on 4%, 50% on next 4%"

  contributions:
    employer:
      match_formula: "enhanced_tiered"
      match_details:
        tiers:
          - {min: 0.00, max: 0.04, rate: 1.00}
          - {min: 0.04, max: 0.08, rate: 0.50}
```

### High-Performance Scenario Execution Framework
```python
import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import uuid
import pickle
from pathlib import Path
import logging
from copy import deepcopy

@dataclass
class ScenarioConfig:
    scenario_id: str
    name: str
    description: str
    base_scenario: Optional[str] = None
    eligibility: Dict[str, Any] = None
    enrollment: Dict[str, Any] = None
    contributions: Dict[str, Any] = None
    matching: Dict[str, Any] = None
    vesting: Dict[str, Any] = None
    random_seed: Optional[int] = None

@dataclass
class ScenarioResult:
    scenario_id: str
    scenario_name: str
    execution_time_seconds: float
    status: str  # 'completed', 'failed', 'running'
    error_message: Optional[str] = None
    yearly_metrics: List[Dict] = None
    summary_statistics: Dict[str, Any] = None
    employee_outcomes: Dict[str, Any] = None
    performance_metrics: Dict[str, Any] = None

class HighPerformanceScenarioRunner:
    def __init__(self, base_population_df: pd.DataFrame,
                 base_config: ScenarioConfig,
                 max_workers: Optional[int] = None):
        self.base_population_df = base_population_df
        self.base_config = base_config
        self.max_workers = max_workers or min(8, len(os.sched_getaffinity(0)))
        self.checkpoint_dir = Path("scenario_checkpoints")
        self.checkpoint_dir.mkdir(exist_ok=True)

    def run_scenarios_parallel(self, scenario_configs: Dict[str, ScenarioConfig],
                             projection_years: int = 10,
                             enable_checkpoints: bool = True) -> Dict[str, ScenarioResult]:
        """Execute multiple scenarios using process-based parallelism for maximum performance"""

        results = {}
        execution_start = datetime.now()

        # Prepare scenarios for execution
        execution_tasks = self._prepare_execution_tasks(
            scenario_configs, projection_years, enable_checkpoints
        )

        logger.info(f"Starting parallel execution of {len(execution_tasks)} scenarios with {self.max_workers} workers")

        # Use ProcessPoolExecutor for true parallelism (bypasses Python GIL)
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all scenarios for execution
            future_to_scenario = {
                executor.submit(
                    execute_scenario_isolated,
                    task['scenario_config'],
                    task['population_data'],
                    task['projection_years'],
                    task['checkpoint_path']
                ): task['scenario_id']
                for task in execution_tasks
            }

            # Process results as they complete
            completed_count = 0
            total_scenarios = len(execution_tasks)

            for future in as_completed(future_to_scenario):
                scenario_id = future_to_scenario[future]
                completed_count += 1

                try:
                    result = future.result(timeout=1800)  # 30 minute timeout per scenario
                    results[scenario_id] = result

                    logger.info(
                        f"Completed scenario {completed_count}/{total_scenarios}: {scenario_id} "
                        f"in {result.execution_time_seconds:.1f}s"
                    )

                except Exception as e:
                    error_result = ScenarioResult(
                        scenario_id=scenario_id,
                        scenario_name=scenario_configs[scenario_id].name,
                        execution_time_seconds=0.0,
                        status='failed',
                        error_message=str(e)
                    )
                    results[scenario_id] = error_result

                    logger.error(f"Failed scenario {scenario_id}: {e}")

        total_execution_time = (datetime.now() - execution_start).total_seconds()
        logger.info(f"Completed all scenarios in {total_execution_time:.1f}s")

        return results

    def _prepare_execution_tasks(self, scenario_configs: Dict[str, ScenarioConfig],
                               projection_years: int,
                               enable_checkpoints: bool) -> List[Dict]:
        """Prepare execution tasks with data isolation"""

        tasks = []

        for scenario_id, config in scenario_configs.items():
            # Create isolated copy of population data for this scenario
            population_data = self.base_population_df.copy()
            population_data['scenario_id'] = scenario_id

            # Resolve configuration inheritance
            resolved_config = self._resolve_config_inheritance(config)

            # Set up checkpoint path
            checkpoint_path = None
            if enable_checkpoints:
                checkpoint_path = self.checkpoint_dir / f"{scenario_id}_checkpoint.pkl"

            tasks.append({
                'scenario_id': scenario_id,
                'scenario_config': resolved_config,
                'population_data': population_data,
                'projection_years': projection_years,
                'checkpoint_path': checkpoint_path
            })

        return tasks

    def _resolve_config_inheritance(self, config: ScenarioConfig) -> ScenarioConfig:
        """Resolve configuration inheritance chain"""

        if not config.base_scenario:
            return config

        # Start with base configuration
        resolved_config = deepcopy(self.base_config)

        # Apply overrides from scenario config
        for field in ['eligibility', 'enrollment', 'contributions', 'matching', 'vesting']:
            if getattr(config, field) is not None:
                setattr(resolved_config, field, getattr(config, field))

        # Update metadata
        resolved_config.scenario_id = config.scenario_id
        resolved_config.name = config.name
        resolved_config.description = config.description
        resolved_config.random_seed = config.random_seed

        return resolved_config

    def generate_optimization_recommendations(self, results: Dict[str, ScenarioResult]) -> List[Dict]:
        """Generate AI-powered optimization recommendations based on scenario results"""

        recommendations = []

        # Analyze successful scenarios only
        successful_results = {k: v for k, v in results.items() if v.status == 'completed'}

        if len(successful_results) < 2:
            return recommendations

        # Find optimal scenarios by different criteria
        cost_optimal = min(successful_results.items(),
                          key=lambda x: x[1].summary_statistics.get('total_employer_cost', float('inf')))

        participation_optimal = max(successful_results.items(),
                                  key=lambda x: x[1].summary_statistics.get('avg_participation_rate', 0))

        # Generate cost-effectiveness recommendation
        if cost_optimal[0] != participation_optimal[0]:
            cost_diff = (participation_optimal[1].summary_statistics['total_employer_cost'] -
                        cost_optimal[1].summary_statistics['total_employer_cost'])
            participation_diff = (participation_optimal[1].summary_statistics['avg_participation_rate'] -
                                cost_optimal[1].summary_statistics['avg_participation_rate'])

            if cost_diff / participation_diff < 100000:  # Cost per participation point
                recommendations.append({
                    'priority': 'HIGH',
                    'category': 'participation_optimization',
                    'recommendation': f'Consider {participation_optimal[1].scenario_name}',
                    'rationale': f'Increases participation by {participation_diff:.1%} for only ${cost_diff:,.0f} additional cost',
                    'impact_score': 0.9
                })

        return recommendations

def execute_scenario_isolated(config: ScenarioConfig,
                            population_df: pd.DataFrame,
                            projection_years: int,
                            checkpoint_path: Optional[Path] = None) -> ScenarioResult:
    """Execute a single scenario in isolation (run in separate process)"""

    execution_start = datetime.now()
    scenario_start_time = execution_start

    try:
        # Check for existing checkpoint
        if checkpoint_path and checkpoint_path.exists():
            with open(checkpoint_path, 'rb') as f:
                checkpoint_data = pickle.load(f)
                if checkpoint_data['projection_years'] == projection_years:
                    logger.info(f"Resuming scenario {config.scenario_id} from checkpoint")
                    return checkpoint_data['result']

        # Set random seed for reproducibility
        if config.random_seed:
            np.random.seed(config.random_seed)

        # Initialize vectorized engines
        from .eligibility_engine import VectorizedEligibilityEngine
        from .enrollment_engine import VectorizedEnrollmentEngine
        from .contribution_calculator import VectorizedContributionCalculator
        from .match_engine import VectorizedMatchEngine

        eligibility_engine = VectorizedEligibilityEngine(config.eligibility)
        enrollment_engine = VectorizedEnrollmentEngine(config.enrollment, config.random_seed)
        contribution_calculator = VectorizedContributionCalculator(config.contributions)
        match_engine = VectorizedMatchEngine(config.matching)

        # Execute multi-year simulation using vectorized operations
        yearly_results = []
        current_population = population_df.copy()

        for year in range(projection_years):
            year_start = datetime.now()

            # Vectorized simulation for this year
            year_result = execute_simulation_year_vectorized(
                current_population,
                year,
                eligibility_engine,
                enrollment_engine,
                contribution_calculator,
                match_engine
            )

            yearly_results.append(year_result)

            # Age population for next year (vectorized)
            current_population = age_population_vectorized(current_population)

            year_time = (datetime.now() - year_start).total_seconds()
            logger.debug(f"Scenario {config.scenario_id} year {year+1} completed in {year_time:.1f}s")

        # Calculate summary statistics
        summary_stats = calculate_summary_statistics_vectorized(yearly_results)

        # Calculate employee outcomes
        employee_outcomes = calculate_employee_outcomes_vectorized(yearly_results, current_population)

        execution_time = (datetime.now() - execution_start).total_seconds()

        result = ScenarioResult(
            scenario_id=config.scenario_id,
            scenario_name=config.name,
            execution_time_seconds=execution_time,
            status='completed',
            yearly_metrics=yearly_results,
            summary_statistics=summary_stats,
            employee_outcomes=employee_outcomes,
            performance_metrics={
                'avg_year_time': execution_time / projection_years,
                'population_size': len(population_df),
                'total_events_generated': sum(yr.get('total_events', 0) for yr in yearly_results)
            }
        )

        # Save checkpoint
        if checkpoint_path:
            checkpoint_data = {
                'projection_years': projection_years,
                'result': result,
                'timestamp': datetime.now()
            }
            with open(checkpoint_path, 'wb') as f:
                pickle.dump(checkpoint_data, f)

        return result

    except Exception as e:
        execution_time = (datetime.now() - execution_start).total_seconds()

        return ScenarioResult(
            scenario_id=config.scenario_id,
            scenario_name=config.name,
            execution_time_seconds=execution_time,
            status='failed',
            error_message=str(e)
        )

def execute_simulation_year_vectorized(population_df: pd.DataFrame,
                                     year: int,
                                     eligibility_engine,
                                     enrollment_engine,
                                     contribution_calculator,
                                     match_engine) -> Dict:
    """Execute one simulation year using vectorized operations"""

    # Step 1: Determine eligibility (vectorized)
    population_df = eligibility_engine.determine_eligibility_batch(
        population_df, datetime.now().replace(year=2025+year)
    )

    # Step 2: Process enrollment (vectorized)
    eligible_employees = population_df[population_df['is_eligible'] == True]
    if len(eligible_employees) > 0:
        enrolled_df = enrollment_engine.simulate_enrollment_batch(
            eligible_employees, datetime.now().replace(year=2025+year)
        )
        population_df.update(enrolled_df)

    # Step 3: Calculate contributions (vectorized)
    enrolled_employees = population_df[population_df['enrolled'] == True]
    if len(enrolled_employees) > 0:
        contribution_df = contribution_calculator.calculate_contributions_batch(
            enrolled_employees, datetime.now().replace(year=2025+year)
        )
        population_df.update(contribution_df)

    # Step 4: Calculate employer match (vectorized)
    contributing_employees = population_df[population_df['total_contributions'] > 0]
    if len(contributing_employees) > 0:
        match_df = match_engine.calculate_match_batch(
            contributing_employees, 'standard_formula'
        )
        population_df.update(match_df)

    # Calculate year metrics
    year_metrics = {
        'year': year + 1,
        'total_eligible': len(population_df[population_df['is_eligible'] == True]),
        'total_enrolled': len(population_df[population_df['enrolled'] == True]),
        'participation_rate': len(population_df[population_df['enrolled'] == True]) / len(population_df) if len(population_df) > 0 else 0,
        'avg_deferral_rate': population_df[population_df['enrolled'] == True]['deferral_rate'].mean() if len(population_df[population_df['enrolled'] == True]) > 0 else 0,
        'total_employee_contributions': population_df['total_contributions'].sum(),
        'total_employer_match': population_df['employer_match'].sum(),
        'total_events': len(population_df)  # Simplified event counting
    }

    return year_metrics

def age_population_vectorized(population_df: pd.DataFrame) -> pd.DataFrame:
    """Age the population by one year using vectorized operations"""
    population_df = population_df.copy()
    population_df['age'] += 1
    population_df['tenure_months'] += 12
    population_df['service_years'] += 1
    return population_df

def calculate_summary_statistics_vectorized(yearly_results: List[Dict]) -> Dict:
    """Calculate summary statistics from yearly results"""

    results_df = pd.DataFrame(yearly_results)

    return {
        'avg_participation_rate': results_df['participation_rate'].mean(),
        'final_participation_rate': results_df['participation_rate'].iloc[-1],
        'avg_deferral_rate': results_df['avg_deferral_rate'].mean(),
        'total_employer_cost': results_df['total_employer_match'].sum(),
        'total_employee_contributions': results_df['total_employee_contributions'].sum(),
        'participation_growth': results_df['participation_rate'].iloc[-1] - results_df['participation_rate'].iloc[0] if len(results_df) > 1 else 0,
        'cost_per_participant': results_df['total_employer_match'].sum() / results_df['total_enrolled'].sum() if results_df['total_enrolled'].sum() > 0 else 0
    }

def calculate_employee_outcomes_vectorized(yearly_results: List[Dict],
                                         final_population: pd.DataFrame) -> Dict:
    """Calculate employee outcome metrics"""

    enrolled_employees = final_population[final_population['enrolled'] == True]

    if len(enrolled_employees) == 0:
        return {'avg_retirement_readiness_score': 0, 'employees_on_track': 0}

    # Simplified retirement readiness calculation
    readiness_scores = enrolled_employees['deferral_rate'] * 100  # Simplified scoring

    return {
        'avg_retirement_readiness_score': readiness_scores.mean(),
        'employees_on_track': len(enrolled_employees[readiness_scores >= 70]),  # 70+ considered on track
        'high_savers': len(enrolled_employees[enrolled_employees['deferral_rate'] >= 0.10]),
        'avg_account_balance': enrolled_employees['total_contributions'].sum() * 5  # Simplified growth assumption
    }
```

### Comparison Report Generation
```python
def generate_comparison_report(scenario_results, output_format='html'):
    """Generate comparative analysis report across scenarios"""

    report = {
        'executive_summary': {},
        'detailed_comparisons': {},
        'recommendations': []
    }

    # Extract key metrics for comparison
    for scenario_name, results in scenario_results.items():
        if 'error' not in results:
            summary = results['summary_statistics']

            report['executive_summary'][scenario_name] = {
                'total_employer_cost': summary['total_employer_contributions'],
                'avg_participation_rate': summary['avg_participation_rate'],
                'avg_deferral_rate': summary['avg_deferral_rate'],
                'cost_per_participant': summary['cost_per_participant'],
                'employee_savings_improvement': summary['savings_improvement']
            }

    # Rank scenarios by different criteria
    rankings = {
        'lowest_cost': sorted(scenarios, key=lambda x: x['total_employer_cost']),
        'highest_participation': sorted(scenarios, key=lambda x: x['avg_participation_rate'], reverse=True),
        'best_employee_outcome': sorted(scenarios, key=lambda x: x['employee_savings_improvement'], reverse=True)
    }

    # Generate recommendations
    if 'auto_enrollment' in scenario_results:
        ae_cost = report['executive_summary']['auto_enrollment']['total_employer_cost']
        base_cost = report['executive_summary']['baseline']['total_employer_cost']
        cost_increase = (ae_cost - base_cost) / base_cost

        if cost_increase < 0.10:  # Less than 10% cost increase
            report['recommendations'].append({
                'priority': 'HIGH',
                'recommendation': 'Implement auto-enrollment at 6%',
                'rationale': f'Increases participation with only {cost_increase:.1%} cost increase',
                'impact': 'High positive impact on retirement readiness'
            })

    return report
```

---

## Performance Requirements

| Metric | Requirement | Implementation Strategy |
|--------|-------------|------------------------|
| Scenario Execution | <2 minutes for 10-year, 100K employee projection | ProcessPoolExecutor with vectorized simulation engines |
| Parallel Scenarios | 10+ concurrent scenarios with linear scaling | Process-based parallelism with isolated memory spaces |
| Configuration Validation | <1 second for complex YAML validation | Pydantic with pre-compiled schemas and caching |
| Report Generation | <30 seconds for interactive comparison reports | Optimized data aggregation with lazy loading |
| Memory Usage | <12GB total for 10 concurrent scenarios | Efficient data structures with checkpoint/restart |

## Dependencies
- E021-E025: All core DC plan components must be complete
- Pydantic for YAML validation and configuration management
- Plotly/Dash for interactive report generation
- ProcessPoolExecutor for high-performance parallel processing
- React/TypeScript for advanced UI components
- Redis for scenario execution state management
- Machine learning libraries for optimization recommendations
- WebSocket support for real-time progress updates

## Risks
- **Risk**: Configuration complexity overwhelming users
- **Mitigation**: Provide templates and validation
- **Risk**: Performance with many concurrent scenarios
- **Mitigation**: Implement queueing and resource limits

## Estimated Effort
**Total Story Points**: 64 points
**Estimated Duration**: 4-5 sprints

---

## Definition of Done
- [ ] YAML configuration schema finalized
- [ ] Scenario inheritance working correctly
- [ ] Parallel execution performing well
- [ ] Comparison reports generating accurately
- [ ] Sensitivity analysis tools complete
- [ ] UI for scenario management functional
- [ ] Performance targets met
- [ ] User documentation and templates created
