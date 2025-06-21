### 13. Parallel-run playbook

```markdown
# filename: docs/parallel_run.md

# PlanWise Navigator Parallel Run Playbook

## Overview
This playbook guides the parallel run period where both legacy and new systems operate simultaneously.

## Timeline
- **Start Date**: TBD (after MVP completion)
- **Duration**: 3 months
- **Checkpoints**: Weekly validation meetings
- **Go/No-Go Decision**: Month 3, Week 2

## Phase 1: Shadow Mode (Month 1)

### Week 1-2: Initial Setup
- [ ] Deploy PlanWise Navigator in read-only mode
- [ ] Set up data sync from legacy system (daily batch)
- [ ] Configure monitoring and alerting
- [ ] Train pilot users (5-10 analysts)

### Week 3-4: Shadow Processing
- [ ] Run both systems with same inputs
- [ ] Compare outputs daily
- [ ] Document discrepancies
- [ ] No business decisions on new system

### Success Criteria
- Data sync completes < 1 hour
- 100% of legacy reports reproducible
- < 5% variance in key metrics

## Phase 2: Pilot Usage (Month 2)

### Week 1-2: Limited Production Use
- [ ] Enable write access for pilot users
- [ ] Run specific scenarios in new system
- [ ] Continue legacy for official reporting
- [ ] Daily reconciliation reports

### Week 3-4: Expanded Pilot
- [ ] Add 20-30 additional users
- [ ] Include one critical business process
- [ ] A/B test results with stakeholders
- [ ] Performance benchmarking

### Success Criteria
- User satisfaction > 4/5
- Performance meets SLAs
- Zero data loss incidents
- < 2% variance in projections

## Phase 3: Full Parallel Run (Month 3)

### Week 1-2: Complete Parallel Operation
- [ ] All users have access to both systems
- [ ] Run all scenarios in both systems
- [ ] Side-by-side comparison dashboards
- [ ] Gather comprehensive feedback

### Week 3: Go/No-Go Decision
- [ ] Executive review of metrics
- [ ] User acceptance survey
- [ ] Technical readiness assessment
- [ ] Risk assessment

### Week 4: Cutover or Extension
- [ ] If GO: Execute cutover plan
- [ ] If NO-GO: Extend parallel run
- [ ] Communication to all stakeholders

## Daily Reconciliation Checklist

| Check | Query | Tolerance | Action if Failed |
|-------|-------|-----------|------------------|
| Employee Count | `SELECT COUNT(*) FROM employees WHERE active_flag = true` | 0% | Investigate immediately |
| Total Compensation | `SELECT SUM(current_compensation) FROM workforce_snapshot` | 0.1% | Log discrepancy |
| Level Distribution | `SELECT level_id, COUNT(*) FROM employees GROUP BY level_id` | 0% | Review data mapping |
| Event Counts | `SELECT event_type, COUNT(*) FROM yearly_events GROUP BY event_type` | 2% | Analyze differences |
| Growth Rate | Calculate YoY headcount change | 0.5% | Review calculations |

## Monitoring Dashboard

```sql
-- Create reconciliation view
CREATE VIEW parallel_run_metrics AS
WITH legacy_metrics AS (
    SELECT 
        'legacy' as system,
        COUNT(*) as employee_count,
        SUM(salary) as total_comp,
        AVG(salary) as avg_comp
    FROM legacy.employees
    WHERE status = 'A'
),
new_metrics AS (
    SELECT 
        'planwise' as system,
        COUNT(*) as employee_count,
        SUM(current_compensation) as total_comp,
        AVG(current_compensation) as avg_comp
    FROM employees
    WHERE active_flag = true
)
SELECT 
    l.*,
    n.*,
    ABS(l.employee_count - n.employee_count) as count_diff,
    ABS(l.total_comp - n.total_comp) / l.total_comp * 100 as comp_diff_pct
FROM legacy_metrics l
CROSS JOIN new_metrics n;

## Rollback Procedures

### Immediate Rollback Triggers
1. Data corruption detected
2. >5% variance in critical metrics
3. Security breach
4. Performance degradation >50%

### Rollback Steps
1. **Hour 0**: Disable new system access
2. **Hour 1**: Restore legacy as primary
3. **Hour 2**: Preserve new system state for analysis
4. **Hour 4**: Root cause analysis begins
5. **Day 1**: Stakeholder communication
6. **Day 2**: Remediation plan

## Success Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Data Accuracy | >99.5% | TBD | ⏸️ |
| User Adoption | >80% | TBD | ⏸️ |
| Performance (p95) | <2s | TBD | ⏸️ |
| Uptime | >99.9% | TBD | ⏸️ |
| User Satisfaction | >4/5 | TBD | ⏸️ |

## Lessons Learned Log

| Date | Category | Learning | Action |
|------|----------|----------|--------|
| TBD | Data Quality | Example: Legacy nulls need handling | Update ETL |
| TBD | Performance | Example: Index needed on employee_id | Add index |
| TBD | Usability | Example: Users want Excel export | Add feature |

## Cutover Checklist

### Pre-Cutover (T-7 days)
- [ ] Final data reconciliation
- [ ] Performance testing at full load
- [ ] Backup procedures tested
- [ ] User training completed
- [ ] Runbooks updated

### Cutover Day (T-0)
- [ ] 06:00 - Legacy system backup
- [ ] 07:00 - Stop legacy batch jobs
- [ ] 08:00 - Final data sync
- [ ] 09:00 - Validation checks
- [ ] 10:00 - Switch DNS/routing
- [ ] 11:00 - User access enabled
- [ ] 12:00 - Monitoring engaged
- [ ] 17:00 - Day 1 assessment

### Post-Cutover (T+7 days)
- [ ] Daily health checks
- [ ] User feedback collection
- [ ] Performance optimization
- [ ] Legacy decommission planning
- [ ] Documentation updates