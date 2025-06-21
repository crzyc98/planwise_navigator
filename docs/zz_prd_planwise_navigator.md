# PlanWise Navigator - Product Requirements Document & Rebuild Plan

**Date**: 2025-06-21  
**Version**: 2.0 (Complete Rebuild)  
**Target Packages**: Latest stable versions from requirements.txt

---

## 1. Executive Summary

PlanWise Navigator is Fidelity's on-premises workforce simulation platform that models employee lifecycle events (hiring, promotions, raises, terminations) to project future workforce composition and costs. This document outlines the complete rebuild using modern data stack components.

### Key Objectives
- **Simulate** multi-year workforce scenarios with configurable parameters
- **Project** headcount, compensation costs, and organizational structure changes
- **Analyze** impact of policy changes (promotion rates, termination rates, hiring targets)
- **Deliver** interactive dashboards and reports for decision-making

---

## 2. System Architecture

### Technology Stack
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Data Storage  │    │  Transformation │    │  Orchestration  │
│                 │    │                 │    │                 │
│   DuckDB 1.0.0  │◄───┤   dbt 1.9.2     │◄───┤ Dagster 1.10.20 │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         ▲                       ▲                       ▲
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Reporting     │    │  Configuration  │    │   Validation    │
│                 │    │                 │    │                 │
│ Streamlit 1.46  │    │  YAML + Pydantic│    │  Asset Checks   │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Data Flow
```
Raw Census Data → Staging → Intermediate Models → Marts → Dashboards
     │              │            │                │         │
   Seeds         stg_*        int_*           fct_/dim_*  Streamlit
```

---

## 3. Core Domain Models

### 3.1 Employee Lifecycle Events
```yaml
Events:
  - HIRE: New employee joining organization
  - PROMOTION: Level advancement with compensation increase
  - MERIT_RAISE: Compensation increase without level change  
  - TERMINATION: Employee leaving (voluntary/involuntary)
```

### 3.2 Organizational Structure
```yaml
Levels:
  1: Entry Level
  2: Experienced 
  3: Senior
  4: Lead/Principal
  5: Executive
```

### 3.3 Hazard Tables (Risk Models)
- **Promotion Hazard**: Probability of promotion by age/tenure/level
- **Termination Hazard**: Probability of termination by age/tenure/level  
- **Merit Raise Hazard**: Probability of merit increase by performance factors

---

## 4. Functional Requirements

### 4.1 Simulation Engine
- **Multi-year simulation**: Project 1-10 years forward
- **Configurable parameters**: Growth rates, termination rates, promotion rates
- **Random seed control**: Reproducible results for testing
- **Event generation**: Probabilistic events based on hazard tables
- **Cumulative calculations**: Year-over-year workforce composition changes

### 4.2 Data Processing
- **Incremental updates**: Process only changed data between runs
- **Data validation**: Row counts, primary keys, distribution checks
- **Schema evolution**: Handle changes to input data structure
- **Performance optimization**: Column-store queries, partition pruning

### 4.3 Analytical Outputs
- **Workforce snapshots**: Headcount by level/age/tenure at each year-end
- **Event summaries**: Annual hiring, promotion, termination totals
- **Financial projections**: Total compensation costs by year
- **Cohort analysis**: Track employee groups over time

### 4.4 Reporting & Visualization
- **Interactive dashboards**: Drill-down capabilities, filters
- **Scenario comparison**: Side-by-side what-if analysis
- **Export capabilities**: PDF reports, CSV data downloads
- **Real-time updates**: Auto-refresh when simulation completes

---

## 5. Technical Requirements

### 5.1 Performance
- **Query response**: < 2s for dashboard queries
- **Simulation runtime**: < 5 minutes for 5-year, 10K employee simulation
- **Memory usage**: < 8GB RAM for typical workloads
- **Storage efficiency**: Columnar compression, partition pruning

### 5.2 Reliability
- **Data consistency**: ACID transactions, referential integrity
- **Error handling**: Graceful failures with actionable error messages
- **Monitoring**: Pipeline health checks, data quality alerts
- **Recovery**: Rollback capabilities, checkpoint/restart

### 5.3 Usability
- **Configuration-driven**: YAML files for all parameters
- **Self-documenting**: Auto-generated data lineage, column descriptions
- **Version controlled**: All code, config, and documentation in Git
- **Local development**: Single-command environment setup

---

## 6. Implementation Plan

### Phase 1: Foundation (Week 1)
```yaml
Tasks:
  - Setup project structure and environment
  - Configure DuckDB connection and basic schemas
  - Implement core Pydantic configuration models
  - Create basic Dagster workspace with dbt integration
  - Setup testing framework (pytest + dbt tests)

Deliverables:
  - Working dev environment with dagster dev
  - Basic dbt project structure
  - Configuration validation
  - Initial CI/CD pipeline
```

### Phase 2: Data Layer (Week 2) 
```yaml
Tasks:
  - Implement staging models (stg_census_data, stg_config_*)
  - Create intermediate workforce models (int_baseline_workforce)
  - Build hazard table models (int_hazard_*)
  - Implement event generation models (int_*_events)

Deliverables:
  - All staging and intermediate dbt models
  - Comprehensive schema tests
  - Data lineage documentation
  - Performance benchmarks
```

### Phase 3: Simulation Engine (Week 3)
```yaml
Tasks:
  - Implement simulation orchestration in Dagster
  - Create year-over-year progression logic
  - Build fact tables (fct_workforce_snapshot, fct_yearly_events)
  - Add cumulative calculation validation
  - Implement multi-year pipeline

Deliverables:
  - Working single-year simulation
  - Multi-year simulation pipeline
  - Asset checks and validation
  - Performance optimization
```

### Phase 4: Analytics & Reporting (Week 4)
```yaml
Tasks:
  - Build analytical mart models (mart_cohort_analysis, mart_financial_impact)
  - Create Streamlit dashboard application
  - Implement scenario comparison features
  - Add export/reporting capabilities

Deliverables:
  - Interactive dashboard
  - Analytical reports
  - Export functionality  
  - User documentation
```

---

## 7. File Structure

```
planwise_navigator/
├── definitions.py                    # Dagster workspace entry
├── requirements.txt                  # Python dependencies
├── dbt_project.yml                   # dbt configuration
├── 
├── orchestrator/                     # Dagster pipeline code
│   ├── __init__.py
│   ├── simulation_pipeline.py       # Main simulation logic
│   ├── assets.py                     # Dagster asset definitions
│   └── ops.py                        # Dagster operations
│
├── dbt/                              # dbt project
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── models/
│   │   ├── staging/                  # Raw data staging
│   │   │   ├── stg_census_data.sql
│   │   │   └── schema.yml
│   │   ├── intermediate/             # Business logic models
│   │   │   ├── events/               # Event generation
│   │   │   ├── hazards/              # Risk models
│   │   │   └── workforce/            # Workforce progression
│   │   └── marts/                    # Analytical outputs
│   │       ├── fct_workforce_snapshot.sql
│   │       ├── fct_yearly_events.sql
│   │       └── schema.yml
│   ├── seeds/                        # Configuration data
│   │   ├── config_job_levels.csv
│   │   ├── config_promotion_hazard_base.csv
│   │   └── bootstrap_census_data.csv
│   └── macros/                       # Reusable SQL functions
│       └── simulation_helpers.sql
│
├── config/                           # Configuration management
│   ├── simulation_config.yaml        # Main simulation parameters
│   ├── test_config.yaml             # Test scenarios
│   └── multi_year_config.yaml       # Multi-year parameters
│
├── dashboards/                       # Streamlit applications
│   ├── app.py                        # Main dashboard
│   ├── pages/                        # Multi-page app
│   └── components/                   # Reusable components
│
├── scripts/                          # Utility scripts
│   ├── setup_environment.py         # Dev environment setup
│   ├── run_simulation.py            # CLI simulation runner
│   └── validate_data.py             # Data validation utilities
│
├── tests/                            # Python tests
│   ├── test_simulation.py           # Simulation logic tests
│   ├── test_config.py               # Configuration tests
│   └── fixtures/                     # Test data
│
└── docs/                             # Documentation
    ├── architecture.md               # System architecture
    ├── configuration.md              # Config reference
    └── api.md                        # API documentation
```

---

## 8. Key Configuration Schema

```yaml
# config/simulation_config.yaml
simulation:
  start_year: 2025
  end_year: 2029
  random_seed: 42
  
workforce:
  target_growth_rate: 0.03           # 3% annual growth
  total_termination_rate: 0.12       # 12% annual turnover
  new_hire_termination_rate: 0.25    # 25% first-year turnover
  
promotion:
  base_rate: 0.15                    # 15% eligible for promotion
  level_caps:                        # Maximum promotions per level
    1: 0.20                          # 20% of L1 can promote to L2
    2: 0.15                          # 15% of L2 can promote to L3
    3: 0.10                          # 10% of L3 can promote to L4
    4: 0.05                          # 5% of L4 can promote to L5

compensation:
  cola_rate: 0.025                   # 2.5% cost of living adjustment
  merit_budget: 0.04                 # 4% of payroll for merit raises
  promotion_increase: 0.15           # 15% increase on promotion
```

---

## 9. Critical Success Factors

### 9.1 Data Quality
- **Validation Rules**: Every model must have schema tests
- **Monitoring**: Asset checks for data drift and anomalies
- **Documentation**: Every column documented with business context

### 9.2 Performance
- **Incremental Processing**: Only process changed/new data
- **Columnar Optimization**: Leverage DuckDB's analytical strengths
- **Memory Management**: Stream large datasets, avoid loading all in memory

### 9.3 Maintainability
- **Configuration-Driven**: No hardcoded business rules
- **Type Safety**: Pydantic models for all configuration
- **Testing**: High test coverage with realistic scenarios

---

## 10. Implementation Guidelines for Claude Code

### 10.1 Development Approach
1. **Start Simple**: Build working MVP first, then add complexity
2. **Test Early**: Write tests as you build, not after
3. **Document Everything**: Code comments, dbt docs, README files
4. **Follow Conventions**: Use established patterns from CLAUDE.md

### 10.2 Common Pitfalls to Avoid
- **Cumulative Logic Errors**: Always calculate from baseline + all events to date
- **Context Mismatches**: Use correct Dagster context types (Asset vs Op)
- **DuckDB Relation Issues**: Handle schema changes gracefully
- **Memory Leaks**: Close connections and clean up resources

### 10.3 Testing Strategy
```yaml
Unit Tests:
  - Configuration validation
  - Business logic functions
  - Data transformation utilities

Integration Tests:
  - dbt model compilation and execution
  - Dagster pipeline execution
  - Database connectivity

End-to-End Tests:
  - Full simulation scenarios
  - Dashboard functionality
  - Export capabilities
```

---

## 11. Success Metrics

### 11.1 Technical Metrics
- **Build Time**: < 30 seconds for clean build
- **Test Coverage**: > 90% for Python code, 100% for dbt models
- **Query Performance**: < 2s for dashboard queries
- **Pipeline Reliability**: > 99% success rate

### 11.2 Business Metrics
- **Simulation Accuracy**: < 5% variance from historical data
- **User Adoption**: 80% of analysts using for planning
- **Decision Speed**: 50% reduction in workforce planning cycles
- **Scenario Coverage**: Support for > 20 different policy scenarios

---

## 12. Next Steps

1. **Environment Setup**: Create fresh virtual environment with requirements.txt
2. **Project Structure**: Create directory structure and initialize repositories
3. **Foundation**: Implement basic Dagster + dbt integration
4. **Incremental Development**: Build and test one component at a time
5. **Validation**: Test with real data scenarios throughout development

---

**Remember**: This rebuild is an opportunity to implement best practices from the start. Focus on clean architecture, comprehensive testing, and clear documentation. The goal is a maintainable system that can evolve with changing business needs.