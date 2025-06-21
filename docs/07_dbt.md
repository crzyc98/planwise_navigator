Here’s your table reformatted with improved Markdown for better readability and clarity, especially for documentation in tools like Obsidian, GitHub, or internal wikis:

⸻

📦 dbt Model Contracts

A detailed reference of all models used in the workforce simulation pipeline.

Model	Type	Description	Primary Key(s)	Tests	Depends On
stg_census_data	staging	Clean employee census data	employee_id	unique, not_null	seeds.bootstrap_census_data
stg_config_job_levels	staging	Job level configuration	level_id	unique, not_null, values_in([1–5])	seeds.config_job_levels
stg_config_promotion_hazard	staging	Promotion probability base rates	level_id	unique, not_null	seeds.config_promotion_hazard_base
stg_config_termination_hazard	staging	Termination probability base rates	level_id	unique, not_null	seeds.config_termination_hazard_base
int_baseline_workforce	intermediate	Starting workforce for simulation	employee_id	unique, not_null	stg_census_data
int_previous_year_workforce	intermediate	Prior year workforce state	employee_id, simulation_year	unique_combination	int_baseline_workforce, fct_yearly_events
int_hazard_promotion	intermediate	Calculated promotion probabilities	employee_id, simulation_year	unique_combination	stg_config_promotion_hazard
int_hazard_termination	intermediate	Calculated termination probabilities	employee_id, simulation_year	unique_combination	stg_config_termination_hazard
int_hiring_events	intermediate	Generated new hire events	event_id	unique, not_null	int_previous_year_workforce
int_promotion_events	intermediate	Generated promotion events	event_id	unique, not_null	int_hazard_promotion
int_termination_events	intermediate	Generated termination events	event_id	unique, not_null	int_hazard_termination
int_merit_events	intermediate	Generated merit raise events	event_id	unique, not_null	int_previous_year_workforce
fct_workforce_snapshot	mart	Year-end workforce state	employee_id, simulation_year	unique_combination	int_previous_year_workforce, fct_yearly_events
fct_yearly_events	mart	All events by year	event_id	unique, not_null	int_*_events
mart_workforce_summary	mart	High-level metrics by year	simulation_year	unique, not_null	fct_workforce_snapshot
mart_cohort_analysis	mart	Cohort progression tracking	cohort_year, simulation_year	unique_combination	fct_workforce_snapshot
mart_financial_impact	mart	Compensation cost projections	simulation_year, level_id	unique_combination	fct_workforce_snapshot

seeds.bootstrap_census_data
        │
        ▼
stg_census_data
        │
        ▼
int_baseline_workforce ─┬──────────────────────────────┐
                        ▼                              ▼
        int_previous_year_workforce         int_merit_events
                        │                              │
        ┌───────────────┴────────────┐     ┌────────────┘
        ▼                            ▼     ▼
int_hazard_promotion     int_hazard_termination
        │                            │
        ▼                            ▼
int_promotion_events     int_termination_events
        │                            │
        └────┬────────────┬──────────┘
             ▼            ▼
       fct_yearly_events  int_hiring_events
             │
             ▼
   fct_workforce_snapshot
             │
    ┌────────┴─────────┬────────────┬───────────────┐
    ▼                  ▼            ▼               ▼
mart_workforce_summary │  mart_cohort_analysis   mart_financial_impact
                       │
                       ▼
     stg_config_job_levels ─────────────┐
     stg_config_promotion_hazard ──────┘
     stg_config_termination_hazard ────┘