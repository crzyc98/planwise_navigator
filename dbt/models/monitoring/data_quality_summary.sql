{{ config(
    materialized='table',
    tags=['data_quality', 'monitoring', 'summary_dashboard']
) }}

-- Executive summary of data quality metrics for promotion compensation integrity
-- Provides high-level KPIs for data quality monitoring dashboard

WITH promotion_quality_metrics AS (
    SELECT 
        simulation_year,
        COUNT(*) as total_promotions,
        
        -- Data quality status breakdown
        COUNT(CASE WHEN data_quality_status = 'CRITICAL_VIOLATION' THEN 1 END) as critical_violations,
        COUNT(CASE WHEN data_quality_status = 'MAJOR_VIOLATION' THEN 1 END) as major_violations,
        COUNT(CASE WHEN data_quality_status = 'MINOR_VIOLATION' THEN 1 END) as minor_violations,
        COUNT(CASE WHEN data_quality_status = 'WARNING' THEN 1 END) as warnings,
        COUNT(CASE WHEN data_quality_status = 'PASS' THEN 1 END) as passed,
        
        -- Merit propagation analysis
        COUNT(CASE WHEN merit_propagation_status = 'MERIT_NOT_PROPAGATED' THEN 1 END) as merit_not_propagated,
        COUNT(CASE WHEN merit_propagation_status = 'MERIT_PROPERLY_PROPAGATED' THEN 1 END) as merit_properly_propagated,
        COUNT(CASE WHEN merit_propagation_status = 'NO_MERIT_EVENT' THEN 1 END) as no_merit_event,
        
        -- Financial impact
        SUM(estimated_underpayment_amount) as total_estimated_underpayment,
        AVG(compensation_gap) as avg_compensation_gap,
        AVG(gap_percentage) as avg_gap_percentage,
        
        -- Compensation ranges
        MIN(compensation_gap) as min_compensation_gap,
        MAX(compensation_gap) as max_compensation_gap,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY compensation_gap) as median_compensation_gap,
        
        -- Promotion increase analysis
        AVG(promotion_increase_percentage) as avg_promotion_increase_pct,
        MIN(promotion_increase_percentage) as min_promotion_increase_pct,
        MAX(promotion_increase_percentage) as max_promotion_increase_pct
        
    FROM {{ ref('data_quality_promotion_compensation') }}
    GROUP BY simulation_year
),

overall_metrics AS (
    SELECT 
        'ALL_YEARS' as simulation_year,
        SUM(total_promotions) as total_promotions,
        
        -- Aggregate violations
        SUM(critical_violations) as critical_violations,
        SUM(major_violations) as major_violations,
        SUM(minor_violations) as minor_violations,
        SUM(warnings) as warnings,
        SUM(passed) as passed,
        
        -- Merit propagation totals
        SUM(merit_not_propagated) as merit_not_propagated,
        SUM(merit_properly_propagated) as merit_properly_propagated,
        SUM(no_merit_event) as no_merit_event,
        
        -- Financial totals
        SUM(total_estimated_underpayment) as total_estimated_underpayment,
        AVG(avg_compensation_gap) as avg_compensation_gap,
        AVG(avg_gap_percentage) as avg_gap_percentage,
        
        -- Range analysis
        MIN(min_compensation_gap) as min_compensation_gap,
        MAX(max_compensation_gap) as max_compensation_gap,
        AVG(median_compensation_gap) as median_compensation_gap,
        
        -- Promotion increase analysis
        AVG(avg_promotion_increase_pct) as avg_promotion_increase_pct,
        MIN(min_promotion_increase_pct) as min_promotion_increase_pct,
        MAX(max_promotion_increase_pct) as max_promotion_increase_pct
        
    FROM promotion_quality_metrics
),

combined_metrics AS (
    SELECT * FROM promotion_quality_metrics
    UNION ALL
    SELECT * FROM overall_metrics
)

SELECT 
    simulation_year,
    total_promotions,
    
    -- Data quality percentages
    ROUND(critical_violations * 100.0 / NULLIF(total_promotions, 0), 2) as critical_violation_rate,
    ROUND(major_violations * 100.0 / NULLIF(total_promotions, 0), 2) as major_violation_rate,
    ROUND((critical_violations + major_violations) * 100.0 / NULLIF(total_promotions, 0), 2) as total_violation_rate,
    ROUND(passed * 100.0 / NULLIF(total_promotions, 0), 2) as pass_rate,
    
    -- Absolute counts
    critical_violations,
    major_violations,
    minor_violations,
    warnings,
    passed,
    
    -- Merit propagation metrics
    merit_not_propagated,
    merit_properly_propagated,
    no_merit_event,
    ROUND(merit_not_propagated * 100.0 / NULLIF(merit_not_propagated + merit_properly_propagated, 0), 2) as merit_failure_rate,
    
    -- Financial impact
    ROUND(total_estimated_underpayment, 2) as total_estimated_underpayment,
    ROUND(avg_compensation_gap, 2) as avg_compensation_gap,
    ROUND(avg_gap_percentage, 2) as avg_gap_percentage,
    
    -- Compensation gap distribution
    ROUND(min_compensation_gap, 2) as min_compensation_gap,
    ROUND(max_compensation_gap, 2) as max_compensation_gap,
    ROUND(median_compensation_gap, 2) as median_compensation_gap,
    
    -- Promotion increase analysis
    ROUND(avg_promotion_increase_pct, 2) as avg_promotion_increase_pct,
    ROUND(min_promotion_increase_pct, 2) as min_promotion_increase_pct,
    ROUND(max_promotion_increase_pct, 2) as max_promotion_increase_pct,
    
    -- Data quality score (0-100)
    ROUND(
        (passed * 100.0 + warnings * 75.0 + minor_violations * 50.0 + major_violations * 25.0 + critical_violations * 0.0) 
        / NULLIF(total_promotions, 0), 2
    ) as data_quality_score,
    
    -- Trend indicators (only for year-specific records)
    CASE 
        WHEN simulation_year != 'ALL_YEARS' THEN
            LAG(total_promotions) OVER (ORDER BY simulation_year) 
        ELSE NULL 
    END as previous_year_promotions,
    
    CASE 
        WHEN simulation_year != 'ALL_YEARS' THEN
            LAG(critical_violations + major_violations) OVER (ORDER BY simulation_year)
        ELSE NULL 
    END as previous_year_violations,
    
    -- Compliance status
    CASE 
        WHEN critical_violations = 0 AND major_violations = 0 THEN 'COMPLIANT'
        WHEN critical_violations = 0 AND major_violations < total_promotions * 0.05 THEN 'MINOR_ISSUES'
        WHEN critical_violations < total_promotions * 0.01 AND major_violations < total_promotions * 0.10 THEN 'MODERATE_ISSUES'
        ELSE 'CRITICAL_ISSUES'
    END as compliance_status,
    
    -- Risk level
    CASE 
        WHEN total_estimated_underpayment > 1000000 THEN 'HIGH_RISK'
        WHEN total_estimated_underpayment > 100000 THEN 'MEDIUM_RISK' 
        WHEN total_estimated_underpayment > 10000 THEN 'LOW_RISK'
        ELSE 'MINIMAL_RISK'
    END as financial_risk_level,
    
    -- Timestamp
    CURRENT_TIMESTAMP as summary_generated_at,
    '{{ var("simulation_year", "unknown") }}' as report_run_year

FROM combined_metrics
ORDER BY 
    CASE WHEN simulation_year = 'ALL_YEARS' THEN 1 ELSE 0 END,
    CAST(simulation_year AS VARCHAR)