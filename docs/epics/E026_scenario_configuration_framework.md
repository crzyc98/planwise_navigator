# Epic E026: Scenario Configuration Framework

## Epic Overview

### Summary
Build a comprehensive scenario modeling framework that allows plan sponsors to define, compare, and analyze multiple retirement plan design alternatives through YAML configuration without code changes.

### Business Value
- Reduces plan design analysis time from weeks to hours
- Enables testing of 10+ scenarios vs traditional 2-3
- Saves $100K+ in actuarial consulting fees annually
- Improves decision quality with data-driven comparisons

### Success Criteria
- ✅ Support 10+ concurrent scenarios with distinct configurations
- ✅ YAML-based configuration with validation
- ✅ Side-by-side comparison reports generated automatically
- ✅ Scenario execution completes in <5 minutes for 10-year projection

---

## User Stories

### Story 1: Scenario Definition Framework (8 points)
**As a** benefits analyst
**I want** to define multiple plan scenarios in configuration files
**So that** I can test different designs without coding

**Acceptance Criteria:**
- YAML schema for complete plan design
- Scenario inheritance (base + overrides)
- Validation of configuration completeness
- Support for 10+ named scenarios
- Version control friendly format

### Story 2: Scenario Execution Engine (13 points)
**As a** plan sponsor
**I want** to run multiple scenarios in parallel
**So that** I can quickly compare alternatives

**Acceptance Criteria:**
- Parallel execution of scenarios
- Isolated simulation runs (no interference)
- Progress tracking and status updates
- Error handling with partial results
- Resumable execution on failure

### Story 3: Comparison Report Generator (8 points)
**As a** CFO
**I want** standardized comparison reports
**So that** I can make informed decisions

**Acceptance Criteria:**
- Side-by-side metrics comparison
- Multi-year cost projections
- Participation impact analysis
- Employee outcome comparisons
- Executive summary with recommendations

### Story 4: Sensitivity Analysis Tools (8 points)
**As a** risk manager
**I want** to understand scenario sensitivity
**So that** I can assess uncertainty and risk

**Acceptance Criteria:**
- Parameter sensitivity testing
- Monte Carlo simulation support
- Confidence intervals on projections
- Best/worst case analysis
- Key driver identification

### Story 5: Scenario Management UI (5 points)
**As a** benefits administrator
**I want** a user interface for scenario management
**So that** I can create and modify scenarios easily

**Acceptance Criteria:**
- Web UI for scenario creation
- Template library for common designs
- Validation feedback in real-time
- Import/export capabilities
- Scenario comparison selection

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

### Scenario Execution Framework
```python
class ScenarioRunner:
    def __init__(self, base_population, simulation_config):
        self.base_population = base_population
        self.simulation_config = simulation_config
        self.results = {}

    def run_scenarios(self, scenario_configs, years=10):
        """Execute multiple scenarios in parallel"""
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}

            for scenario_name, config in scenario_configs.items():
                # Submit scenario for execution
                future = executor.submit(
                    self._run_single_scenario,
                    scenario_name,
                    config,
                    years
                )
                futures[future] = scenario_name

            # Collect results as they complete
            for future in as_completed(futures):
                scenario_name = futures[future]
                try:
                    result = future.result()
                    self.results[scenario_name] = result
                    logger.info(f"Completed scenario: {scenario_name}")
                except Exception as e:
                    logger.error(f"Failed scenario {scenario_name}: {e}")
                    self.results[scenario_name] = {"error": str(e)}

        return self.results

    def _run_single_scenario(self, name, config, years):
        """Run a single scenario simulation"""
        # Apply configuration overrides
        plan_config = self._merge_configs(self.base_config, config)

        # Initialize simulation components
        eligibility_engine = EligibilityEngine(plan_config.eligibility)
        enrollment_engine = EnrollmentEngine(plan_config.enrollment)
        contribution_calculator = ContributionCalculator(plan_config.contributions)
        match_engine = MatchEngine(plan_config.contributions.employer)

        # Run multi-year simulation
        results = {
            'yearly_metrics': [],
            'summary_statistics': {},
            'employee_outcomes': {}
        }

        population = deepcopy(self.base_population)

        for year in range(years):
            year_results = self._simulate_year(
                population,
                year,
                eligibility_engine,
                enrollment_engine,
                contribution_calculator,
                match_engine
            )
            results['yearly_metrics'].append(year_results)

            # Age population for next year
            population = self._age_population(population)

        # Calculate summary statistics
        results['summary_statistics'] = self._calculate_summary(results['yearly_metrics'])

        return results
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

## Dependencies
- E021-E025: All core DC plan components must be complete
- YAML parsing and validation library
- Report generation framework (HTML/PDF)
- Parallel processing infrastructure

## Risks
- **Risk**: Configuration complexity overwhelming users
- **Mitigation**: Provide templates and validation
- **Risk**: Performance with many concurrent scenarios
- **Mitigation**: Implement queueing and resource limits

## Estimated Effort
**Total Story Points**: 42 points
**Estimated Duration**: 3 sprints

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
