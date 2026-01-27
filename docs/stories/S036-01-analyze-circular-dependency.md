# Story S036-01: Analyze and Document Circular Dependency

**Epic**: E036 - Deferral Rate State Accumulator Architecture
**Story Points**: 2
**Priority**: Critical
**Sprint**: Infrastructure Fix
**Owner**: Technical Architecture Team
**Status**: 🔵 Ready for Implementation
**Type**: Investigation

## Story

**As a** platform engineer
**I want** to analyze and document the complete circular dependency chain causing multi-year simulation failures
**So that** I can understand the root cause and design the correct solution architecture

## Business Context

The current `int_employee_contributions` model has a critical circular dependency with `fct_yearly_events` that prevents successful multi-year simulation execution. This investigation will map the complete dependency chain, analyze the impact on orchestration, and provide the foundation for implementing the state accumulator solution.

## Problem Statement

Current broken dependency chain:
1. `int_employee_contributions` tries to read `employee_deferral_rate` from `fct_yearly_events`
2. `fct_yearly_events` depends on `int_enrollment_events`
3. Orchestrator runs `int_employee_contributions` BEFORE `fct_yearly_events` is built
4. Result: Runtime error "referenced column employee_deferral_rate not found"

## Acceptance Criteria

### Analysis & Documentation
- [ ] **Complete dependency mapping** of all models affected by deferral rate dependencies
- [ ] **Document circular dependency chain** with visual diagram showing broken relationships
- [ ] **Produce verifiable DAG analysis** showing cycle path from `manifest.json` or `dbt ls` outputs
- [ ] **Analyze orchestration impact** on `run_multi_year.py` workflow execution
- [ ] **Identify all references** to `employee_deferral_rate` across the codebase with file:line citations
- [ ] **Compare with Epic E023 solution** to identify reusable patterns
- [ ] **Include orchestrator-managed `enrollment_registry`** as external dependency consideration

### Investigation Deliverables
- [ ] **Mermaid dependency diagrams** showing current broken state vs. target fixed state
- [ ] **DAG excerpt proof** explicitly showing cycle path and confirming target design removes any path `int_employee_contributions → fct_yearly_events → ... → int_employee_contributions`
- [ ] **Model impact assessment** listing all affected models and their dependencies
- [ ] **Orchestration analysis** documenting current execution order and issues with specific error messages
- [ ] **Reference audit** of all `employee_deferral_rate` usage patterns with grep/ripgrep output
- [ ] **Concrete artifacts** stored in `docs/epics/E036/diagrams/*.md` and `docs/epics/E036/impact_assessment.md`

## Technical Analysis Tasks

### Phase 1: Dependency Mapping
- [ ] **Generate DAG analysis** using `dbt ls --select int_employee_contributions+` (downstream) and `dbt ls --select @int_employee_contributions` (upstream)
- [ ] **Refresh dependency graph** with `dbt compile` before analysis
- [ ] **Extract manifest.json data** to enumerate all edges in the dependency chain
- [ ] **Map all model dependencies** involving deferral rate fields
- [ ] **Trace circular dependency path** from `int_employee_contributions` → `fct_yearly_events`
- [ ] **Identify upstream sources** of deferral rate data (enrollment events, escalation events, baseline)
- [ ] **Document downstream consumers** including `fct_employer_match_events` and `fct_payroll_ledger` if they read contributions

### Phase 2: Orchestration Impact Analysis
- [ ] **Analyze current `run_multi_year.py` execution order** and identify where it breaks
- [ ] **Document orchestration failure points** with specific error messages
- [ ] **Review multi-year state management** and identify propagation issues
- [ ] **Assess rollback scenarios** and data consistency requirements

### Phase 3: Reference Audit
- [ ] **Execute comprehensive search** for `employee_deferral_rate` with file:line citations using grep/ripgrep
- [ ] **Document field aliases** including `current_deferral_rate` and other variations
- [ ] **Identify direct dependencies** vs. transitive dependencies
- [ ] **Document data flow patterns** from sources to final consumption
- [ ] **Map field aliases and transformations** across model layers
- [ ] **Include minimal repro steps** with specific dbt commands and exact error text/context

### Phase 4: Solution Pattern Analysis
- [ ] **Review Epic E023** enrollment architecture fix for applicable patterns
- [ ] **Identify state accumulator requirements** based on dependency analysis
- [ ] **Document temporal state patterns** needed for deferral rate tracking
- [ ] **Define integration points** for new accumulator model

## Investigation Scope

### Non-Goals
- **No code changes** - this story only produces analysis artifacts to unblock S036-02
- **No orchestration modifications** - analysis only, implementation comes later

### Assumptions
- `scenario_id` and `plan_design_id` must be present in all relevant models (E036's unified event model)
- `simulation_year` is passed via `--vars` parameter
- Current temporal grain question requires recommendation (year vs. month/payroll) based on actual contribution rate usage

### Files to Analyze
- `dbt/models/intermediate/events/int_employee_contributions.sql` (BROKEN - circular dependency)
- `dbt/models/marts/fct_yearly_events.sql` (DOWNSTREAM target causing circular issue)
- `dbt/models/intermediate/int_enrollment_events.sql` (SOURCE candidate for accumulator)
- `dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql` (SOURCE candidate - corrected path)
- `dbt/models/intermediate/int_baseline_workforce.sql` (BASELINE source)
- `run_multi_year.py` (ORCHESTRATION workflow)
- External: `enrollment_registry` table (orchestrator-managed external dependency)

### Search Patterns
- `employee_deferral_rate` field usage with file:line output
- `{{ ref('fct_yearly_events') }}` dependencies
- Deferral rate calculations and transformations
- State accumulation patterns from Epic E023
- All event sources influencing deferral rate: `int_enrollment_events`, `int_deferral_rate_escalation_events`, override/adhoc changes

### Tooling & Methodology
- **Dependency Analysis**: Use `target/manifest.json` and `dbt ls` commands
  - `dbt ls --select int_employee_contributions+` (downstream dependencies)
  - `dbt ls --select @int_employee_contributions` (upstream dependencies)
  - `dbt compile` to refresh graph before analysis
- **Code References**: Generate file:line citations for every `employee_deferral_rate` reference
- **Cycle Detection**: Produce adjacency list from `dbt ls` output showing current broken paths

## Expected Outcomes

### Documentation Artifacts
1. **Circular Dependency Diagram**
   - Visual representation of broken dependency chain
   - Target state architecture showing fix
   - Model execution order requirements

2. **Impact Assessment Report**
   - All affected models with dependency relationships
   - Orchestration failure analysis
   - Data consistency implications

3. **Reference Audit Results**
   - Complete list of `employee_deferral_rate` usage
   - Source-to-consumer data flow mapping
   - Transformation and aliasing patterns

4. **Solution Architecture Foundation**
   - State accumulator requirements specification
   - Integration points with existing models
   - Temporal state tracking needs
   - Temporal grain recommendation (year vs. month/payroll) with backing analysis

### Key Questions to Answer
- **Where exactly does the circular dependency occur?** (with DAG proof)
- **What are all the models that depend on deferral rate data?** (including downstream consumers)
- **How does the current orchestration order cause failures?** (with specific error messages)
- **What temporal grain is needed for deferral rate state tracking?** (with recommendation)
- **Can we reuse Epic E023 patterns directly?** (with specific pattern analysis)
- **How does enrollment_registry affect circularity analysis?** (external dependency impact)
- **What are all event sources that influence deferral rate?** (comprehensive enumeration)

## Dependencies

### Required Information
- Access to `dbt/models/` directory for dependency analysis
- `run_multi_year.py` orchestration workflow understanding
- Epic E023 documentation and implementation patterns
- Current error logs from failed multi-year simulations

### Story Dependencies
- **None** (foundational investigation story)

### Blocking for Other Stories
- **S036-02**: Design State Accumulator (needs dependency analysis)
- **S036-03**: Implement Temporal State Tracking (needs architecture foundation)
- **S036-04**: Refactor Employee Contributions (needs reference audit)

## Success Metrics

### Analysis Completeness
- [ ] **All circular dependencies identified** and mapped
- [ ] **Complete model impact assessment** with no missed dependencies
- [ ] **Orchestration failure points documented** with specific errors
- [ ] **Reference audit covers all usage patterns** of deferral rate fields

### Documentation Quality
- [ ] **Visual diagrams are clear** and accurately represent dependencies
- [ ] **Technical analysis is thorough** and provides implementation guidance
- [ ] **Solution foundation is solid** and ready for architecture design
- [ ] **Epic E023 patterns are properly analyzed** for reuse opportunities

## Definition of Done

- [ ] **Complete circular dependency chain documented** with Mermaid diagram pair (broken vs. target)
- [ ] **DAG excerpt provided** showing explicit cycle path and target design validation
- [ ] **All affected models identified** with impact assessment including downstream consumers
- [ ] **Orchestration failure analysis complete** with specific error documentation and repro steps
- [ ] **Reference audit complete** showing all `employee_deferral_rate` usage with file:line citations
- [ ] **Epic E023 pattern analysis complete** with reuse recommendations
- [ ] **Solution architecture foundation documented** for next story with temporal grain recommendation
- [ ] **Validated target design** ensures accumulator never reads from `fct_yearly_events` (only prior accumulator + `int_*` sources)
- [ ] **Simple adjacency list provided** from `dbt ls` output showing current broken graph
- [ ] **Analysis reviewed and approved** by technical architecture team

## Implementation Notes

### Investigation Methodology
1. **Start with the error** - trace from `int_employee_contributions` failure point
2. **Map dependencies upstream** - find all sources of deferral rate data
3. **Map dependencies downstream** - find all consumers of contribution calculations
4. **Analyze orchestration flow** - understand execution order and failure points
5. **Compare with E023 patterns** - identify reusable architecture components

### Documentation Standards
- Use clear visual diagrams with Mermaid syntax
- Provide specific file paths and line numbers for references
- Include error messages and failure scenarios
- Document both current broken state and target fixed state
- Reference Epic E023 patterns and lessons learned

## Notes

This investigation story is critical for ensuring the subsequent implementation stories have a solid foundation. The analysis will directly inform the design of the deferral rate state accumulator and help avoid recreating circular dependencies in the solution.
