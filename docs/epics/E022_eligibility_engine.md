# Epic E022: Eligibility Engine

## Epic Overview

### Summary
Build a simple, configurable eligibility determination engine that evaluates employee eligibility for DC plan participation based on days of service since hire date. This MVP focuses on the most common eligibility pattern: waiting period after hire.

### Business Value
- Automates complex eligibility calculations reducing manual HR work by 80%
- Ensures 100% compliance with plan document requirements
- Enables modeling of eligibility rule changes to assess participation impact

### Success Criteria
- ✅ Accurately determines eligibility for 100% of employees
- ✅ Supports all common eligibility rule patterns
- ✅ Processes daily eligibility updates for 100K employees in <30 seconds
- ✅ Generates clear audit trail for eligibility determinations
- ✅ Achieves <100ms response time for point-in-time eligibility queries
- ✅ Supports incremental processing with 95% cache hit rate for unchanged employees

### MVP Implementation Approach
This epic is being implemented in phases to deliver value quickly:

**MVP Phase (30 minutes - Ultra-Simplified)**
- Core eligibility calculator based on days since hire (S022-01)
- **Eligibility event generation** for newly eligible employees
- Integration with orchestrator_mvp framework via `orchestrator_mvp/run_multi_year.py`
- Configuration-driven waiting period (0-365+ days)

**Post-MVP Phase**
All advanced eligibility features have been moved to **Epic E026: Advanced Eligibility Features**. See `/docs/epics/E026_advanced_eligibility_features.md` for:
- Entry date processing (S022-03)
- Employee classification rules (S022-02)
- Age/hours-based requirements
- Complex service calculations
- Advanced classification rules

---

## User Stories

### MVP Stories (In Development)

#### Story S022-01: Core Eligibility Calculator (5 points) 🚧
**Status**: Ready for implementation
**As a** benefits administrator
**I want** automated eligibility determination based on days of service
**So that** employees are enrolled after the configured waiting period

**MVP Acceptance Criteria:**
- ✅ Process 100K employees in <30 seconds using SQL/dbt operations
- ✅ Evaluate service requirements in days since hire (0, 365, etc.)
- ✅ Configuration via dbt variables (eligibility_waiting_days)
- ✅ Generate ELIGIBILITY events for newly eligible employees
- ✅ Track eligibility status changes in event stream
- ✅ Support configuration via dbt variables
- ✅ Integration with orchestrator_mvp multi-year simulation framework

**Implementation**: See `/docs/stories/S022-01-core-eligibility-calculator.md`

---

## Related Epics

### Epic E026: Advanced Eligibility Features
All advanced eligibility features have been moved to Epic E026. See `/docs/epics/E026_advanced_eligibility_features.md` for:

- **Story S022-02**: Basic Employee Classification (5 points)
- **Story S022-03**: Entry Date Processing (4 points)
- **Story S026-01**: Age-Based Eligibility Requirements (6 points)
- **Story S026-02**: Hours-Based Eligibility (8 points)
- **Story S026-03**: Complex Service Computation (12 points)
- **Story S026-04**: Advanced Classification Rules (8 points)
- **Story S026-05**: Eligibility Change Tracking (8 points)

**Total Epic E026**: 51 story points, 5-6 weeks estimated duration

---

## Technical Specifications

### Eligibility Configuration (Centralized)
```yaml
# config/simulation_config.yaml
eligibility:
  waiting_period_days: 365  # 0 for immediate, 365 for 1 year, etc.
```

This integrates with the existing simulation configuration, allowing you to configure eligibility alongside other simulation parameters like growth rates and termination rates.

### Simple Eligibility Implementation
```python
def process_eligibility_for_year(simulation_year: int, config) -> List[Dict]:
    """Simple eligibility processing - just days since hire"""
    eligibility_engine = EligibilityEngine(config)
    return eligibility_engine.generate_eligibility_events(simulation_year)

class EligibilityEngine:
    def __init__(self, config):
        self.config = config
        self.waiting_period_days = config.eligibility.waiting_period_days

    def generate_eligibility_events(self, simulation_year: int) -> List[Dict]:
        """Generate ELIGIBILITY events for newly eligible employees"""

        # Find employees who became eligible this year based on waiting period
        query = f"""
        WITH current_eligibility AS (
            SELECT
                employee_id,
                DATEDIFF('day', employee_hire_date, DATE('{simulation_year}-01-01')) as days_since_hire,
                DATEDIFF('day', employee_hire_date, DATE('{simulation_year}-01-01')) >= {self.waiting_period_days} as is_eligible
            FROM int_baseline_workforce
            WHERE employment_status = 'active'
        ),
        previous_eligibility AS (
            SELECT
                employee_id,
                DATEDIFF('day', employee_hire_date, DATE('{simulation_year - 1}-01-01')) >= {self.waiting_period_days} as was_eligible
            FROM int_baseline_workforce
            WHERE employment_status = 'active'
        )
        SELECT
            c.employee_id,
            c.days_since_hire,
            COALESCE(p.was_eligible, false) as was_previously_eligible
        FROM current_eligibility c
        LEFT JOIN previous_eligibility p ON c.employee_id = p.employee_id
        WHERE c.is_eligible = true
        AND COALESCE(p.was_eligible, false) = false
        """

        newly_eligible_df = self.duckdb_conn.execute(query).df()

        events = []
        for _, row in newly_eligible_df.iterrows():
            event = {
                "event_type": "ELIGIBILITY",
                "employee_id": row['employee_id'],
                "simulation_year": simulation_year,
                "event_date": f"{simulation_year}-01-01",
                "event_payload": {
                    "eligibility_type": "plan_participation",
                    "previous_status": "ineligible",
                    "new_status": "eligible",
                    "days_since_hire": int(row['days_since_hire']),
                    "waiting_period_days": self.waiting_period_days
                }
            }
            events.append(event)

        return events

# Integration with Dagster asset
@asset
def eligibility_events(context: AssetExecutionContext,
                      simulation_config,
                      int_baseline_workforce) -> pd.DataFrame:
    """Generate eligibility events using centralized configuration"""

    current_year = simulation_config['simulation']['start_year']
    eligibility_engine = EligibilityEngine(simulation_config)

    events = eligibility_engine.generate_eligibility_events(current_year)

    if events:
        return pd.DataFrame(events)
    else:
        return pd.DataFrame()  # Empty DataFrame if no new eligibility events
```

---

## Performance Requirements (MVP)

| Metric | Requirement | Implementation Strategy |
|--------|-------------|------------------------|
| Daily Processing | <30 seconds for 100K employees | Simple SQL/dbt operations |
| Event Generation | <5 seconds for newly eligible employees | Lightweight ELIGIBILITY event creation |
| Memory Usage | <1GB for 100K employee dataset | Minimal data requirements (just hire_date) |

**Note**: Advanced performance requirements moved to Epic E026

## Dependencies
- Employee hire date data from workforce simulation
- Event storage infrastructure (fct_yearly_events)
- dbt for SQL-based processing
- DuckDB for analytical queries

## Risks
- **Risk**: Performance with daily eligibility checks for 100K+ employees
- **Mitigation**: Simple SQL-based implementation with minimal complexity

**Note**: Complex risks moved to Epic E026

## Estimated Effort

### MVP Phase
**Total Story Points**: 5 points (S022-01: 5)
**Estimated Duration**: 30 minutes

### Post-MVP Phase (Epic E026)
**Total Story Points**: 51 points (moved to Epic E026)
**Estimated Duration**: 5-6 weeks (see Epic E026)

### Total Epic E022 (MVP Only)
**Total Story Points**: 5 points (S022-01 only)
**Estimated Duration**: 30 minutes

**Note**: Advanced features moved to Epic E026 (51 additional points)

---

## Definition of Done

### MVP Phase
- [ ] Core eligibility calculator processes 100K employees in <30 seconds using SQL/dbt
- [ ] Days-based service eligibility working (configurable waiting period)
- [ ] **Eligibility event generation** for newly eligible employees
- [ ] Integration with orchestrator_mvp via `orchestrator_mvp/run_multi_year.py` complete
- [ ] 95% test coverage for MVP features

### Epic E026 Integration
- [ ] Epic E022 MVP completed and tested
- [ ] Epic E026 stories prioritized and planned
- [ ] Integration path defined between simple and advanced eligibility
- [ ] Documentation references Epic E026 for advanced features
