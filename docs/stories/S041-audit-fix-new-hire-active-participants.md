# Story S041: Audit and Fix New Hire Active Participant Issues

**Story ID**: S041
**Story Name**: Audit and Fix New Hire Active Participant Issues
**Epic**: E011 - Workforce Simulation Validation & Correction
**Story Points**: 8
**Priority**: Must Have
**Sprint**: 3
**Status**: Pending
**Assigned To**: Engineering Team
**Business Owner**: Analytics Team

## Problem Statement

Recent analysis of the workforce simulation has revealed critical data integrity issues with new hire active participants that require comprehensive audit and remediation. While the primary issue of missing `new_hire_active` records has been resolved in S035/S036, deeper participant tracking inconsistencies have been discovered that impact simulation accuracy and auditability.

### Current Issues Identified

1. **Participant Status Inconsistencies**: New hire participants may have incorrect status classifications across simulation years
2. **Data Integrity Gaps**: Potential orphaned records or missing participant linkages in the pipeline
3. **Retention Rate Misalignment**: New hire active participant retention may not align with configured parameters
4. **Audit Trail Gaps**: Incomplete participant transition tracking affects compliance and validation

### Impact Assessment

- **Simulation Accuracy**: Incorrect participant data affects workforce projection reliability
- **Compliance Risk**: Poor audit trails for participant changes impact regulatory requirements
- **Business Planning**: Unreliable new hire retention data affects strategic workforce planning
- **Data Quality**: Integrity issues undermine confidence in simulation outputs

## Business Value

### Primary Benefits
- **Accurate Workforce Planning**: Reliable new hire participant tracking enables precise headcount projections
- **Regulatory Compliance**: Complete audit trails for all participant status changes
- **Data Quality Assurance**: Comprehensive participant data integrity throughout simulation pipeline
- **Stakeholder Confidence**: Trusted participant metrics for strategic decision-making

### Success Metrics
- 100% participant data integrity (no orphaned records or missing linkages)
- New hire retention rates within ±2% of configured parameters
- Complete audit trail for all participant status transitions
- Zero data quality validation failures in participant tracking

## Technical Analysis

### Data Flow Investigation

#### 1. Participant Pipeline Components
```
census_raw → stg_census_data → int_baseline_workforce
↓
int_hiring_events → fct_yearly_events
↓
fct_workforce_snapshot → participant status classification
↓
Multi-year state propagation → int_workforce_previous_year
```

#### 2. Critical Validation Points
- **Hire Event Generation**: `int_hiring_events.sql` participant creation
- **Status Classification**: `fct_workforce_snapshot.sql` lines 392-421 participant categorization
- **Multi-Year Linkage**: `int_workforce_previous_year.sql` participant continuity
- **Event Tracking**: `fct_yearly_events.sql` participant transition recording

#### 3. Potential Root Causes
- **Status Override Logic**: Participant status may be incorrectly modified in pipeline
- **Record Deduplication**: Participant records may be lost during data merging
- **Date Logic Issues**: Hire date validation affecting participant classification
- **Multi-Year State**: Participant status not properly carried between simulation years

### Current Configuration Parameters

```yaml
workforce:
  new_hire_termination_rate: 0.25  # 25% of new hires terminate
  total_termination_rate: 0.12     # 12% annual termination
simulation:
  target_growth_rate: 0.03         # 3% annual growth
```

#### Expected Participant Math (2025)
- **Baseline Workforce**: ~95 participants
- **New Hires**: ~14 participants (replacement + growth)
- **New Hire Terminations**: ~4 participants (25% of new hires)
- **New Hire Actives**: ~10 participants (should retain active status)

## Acceptance Criteria

### Data Integrity Requirements
1. **Participant Linkage**: All new hire participants properly linked across simulation years
2. **Status Accuracy**: Employment status correctly reflects participant's actual state
3. **Record Completeness**: No orphaned or missing participant records in pipeline
4. **Transition Tracking**: All participant status changes properly recorded in event log

### Validation Requirements
1. **Retention Rate Alignment**: New hire active retention within ±2% of expected rates
2. **Audit Trail Completeness**: Full participant history reconstruction from events
3. **Data Quality Gates**: All participant validation tests pass without exceptions
4. **Multi-Year Consistency**: Participant data integrity maintained across all simulation years

### Performance Requirements
1. **Processing Efficiency**: Participant audit checks complete within acceptable timeframes
2. **Validation Speed**: Data integrity checks don't significantly impact simulation runtime
3. **Reporting Accuracy**: Participant metrics accurately calculated and displayed

## Technical Tasks

### Phase 1: Comprehensive Audit (2 days)
- [ ] **Participant Data Flow Analysis**
  - Trace new hire participants through entire simulation pipeline
  - Identify all points where participant status can be modified
  - Map participant record transformations across CTEs
  - Document current vs. expected participant counts by year

- [ ] **Data Integrity Assessment**
  - Check for orphaned participant records without proper linkage
  - Validate participant status consistency across all models
  - Identify missing participant classifications or incorrect statuses
  - Analyze participant record deduplication logic for data loss

- [ ] **Retention Rate Validation**
  - Calculate actual vs. expected new hire retention rates
  - Validate termination probability logic for new hire participants
  - Check participant status progression through simulation years
  - Assess cumulative participant counts for mathematical accuracy

### Phase 2: Issue Remediation (4 days)
- [ ] **Status Classification Fixes**
  - Correct participant employment status assignment logic
  - Fix detailed status code determination for new hire actives
  - Ensure participant status preservation through pipeline transformations
  - Add defensive programming for participant NULL value handling

- [ ] **Record Linkage Improvements**
  - Fix participant record deduplication to prevent data loss
  - Ensure proper participant linking across simulation years
  - Validate participant ID consistency throughout pipeline
  - Correct multi-year participant state propagation logic

- [ ] **Event Tracking Enhancements**
  - Ensure all participant status changes generate appropriate events
  - Add missing participant transition event types if needed
  - Validate participant event chronological ordering
  - Fix participant event metadata (timestamps, reasons, etc.)

### Phase 3: Validation & Testing (2 days)
- [ ] **Comprehensive Test Suite**
  - Create participant-specific data quality tests
  - Add retention rate validation tests with tolerance ranges
  - Implement participant audit trail completeness tests
  - Create multi-year participant consistency validation

- [ ] **Integration Testing**
  - Run end-to-end simulation with participant validation enabled
  - Test participant data integrity across all simulation years
  - Validate participant metrics in dashboard outputs
  - Ensure no regressions in existing functionality

## Validation Criteria

### Data Quality Checks
```sql
-- Participant Status Consistency
SELECT COUNT(*) as inconsistent_participants
FROM fct_workforce_snapshot
WHERE employment_status IS NULL
   OR detailed_status_code NOT IN ('continuous_active', 'new_hire_active', 'experienced_termination', 'new_hire_termination');

-- Participant Linkage Validation
SELECT simulation_year, COUNT(DISTINCT employee_id) as unique_participants
FROM fct_workforce_snapshot
WHERE detailed_status_code IN ('new_hire_active', 'new_hire_termination')
GROUP BY simulation_year;

-- Retention Rate Validation
SELECT
  simulation_year,
  COUNT(CASE WHEN detailed_status_code = 'new_hire_active' THEN 1 END) as active_new_hires,
  COUNT(CASE WHEN detailed_status_code = 'new_hire_termination' THEN 1 END) as terminated_new_hires,
  ROUND(COUNT(CASE WHEN detailed_status_code = 'new_hire_termination' THEN 1 END) * 100.0 /
        (COUNT(CASE WHEN detailed_status_code = 'new_hire_active' THEN 1 END) +
         COUNT(CASE WHEN detailed_status_code = 'new_hire_termination' THEN 1 END)), 2) as termination_rate_pct
FROM fct_workforce_snapshot
WHERE detailed_status_code IN ('new_hire_active', 'new_hire_termination')
GROUP BY simulation_year;
```

### Success Metrics
- **Data Integrity**: 0 inconsistent participant records
- **Retention Accuracy**: Termination rate within 23-27% range (25% ±2%)
- **Audit Completeness**: 100% participant transitions tracked in event log
- **Multi-Year Consistency**: Participant counts balance across all simulation years

## Dependencies

### Technical Dependencies
- **Upstream**: Requires working `int_hiring_events.sql` (completed in S035/S036)
- **Upstream**: Requires fixed `fct_workforce_snapshot.sql` status logic (completed in S036)
- **Parallel**: May inform S037 growth calculation validation
- **Downstream**: Impacts S039 comprehensive validation test development

### Business Dependencies
- **Configuration**: Validated participant parameters in `simulation_config.yaml`
- **Data Quality**: Clean baseline participant data from census sources
- **Stakeholder**: Analytics team validation of participant tracking requirements

## Risks & Mitigation

### Technical Risks
1. **Complex Participant Logic**: Multiple interconnected systems affect participant tracking
   - **Mitigation**: Systematic audit approach, comprehensive testing at each stage

2. **Performance Impact**: Additional validation may slow simulation processing
   - **Mitigation**: Optimize validation queries, implement efficient indexing strategies

3. **Data Migration**: Fixing participant issues may require historical data regeneration
   - **Mitigation**: Plan staged rollout, maintain backup of current state

### Business Risks
1. **Simulation Downtime**: Participant fixes may require simulation pipeline restart
   - **Mitigation**: Develop in separate branch, coordinate with stakeholders for maintenance window

2. **Historical Accuracy**: Previous participant projections may need recalculation
   - **Mitigation**: Document changes clearly, provide migration path for historical data

## Timeline

**Sprint 3 Schedule**:
- **Days 1-2**: Comprehensive participant audit and analysis
- **Days 3-6**: Issue remediation and fixes implementation
- **Days 7-8**: Validation testing and integration verification

**Milestone Checkpoints**:
- Day 2: Audit findings documented, remediation plan finalized
- Day 6: All participant fixes implemented and unit tested
- Day 8: Integration testing complete, validation metrics green

## Definition of Done

### Technical Completion
- [ ] All participant data integrity issues identified and resolved
- [ ] Participant retention rates align with configured parameters (±2% tolerance)
- [ ] Complete audit trail for all participant status transitions
- [ ] Comprehensive participant validation test suite implemented
- [ ] No regressions in existing simulation functionality

### Quality Assurance
- [ ] All participant validation tests pass
- [ ] Data quality checks show 0 integrity issues
- [ ] Multi-year simulation produces consistent participant metrics
- [ ] Performance benchmarks maintained or improved

### Documentation & Knowledge Transfer
- [ ] Participant audit findings documented with remediation actions
- [ ] Updated participant validation procedures in CLAUDE.md
- [ ] Technical documentation for participant tracking improvements
- [ ] Validation test documentation for future maintenance

---

**Story Owner**: Engineering Team
**Stakeholder Approval**: Analytics Team
**Technical Review**: Required before implementation
**Business Impact**: High - Critical for workforce planning accuracy
