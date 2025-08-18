## Streamlined Batch Scenario Runner Plan

### 1. **Enhanced Scenario Definition with Inheritance & Composition**

**Structure:**
- `batch_scenarios/templates/` - Reusable base configurations
  - `base_config.yaml` - Default simulation settings
  - `standard_match.yaml` - Common match formulas
  - `demographics_profiles.yaml` - Typical workforce patterns

- `batch_scenarios/scenarios/` - Actual scenario definitions
  - Each scenario YAML specifies:
    - Which template(s) to inherit from
    - Specific overrides (only what changes)
    - Metadata (name, description, tags)

**Key Features:**
- Multiple inheritance (can extend multiple templates)
- Deep merge for nested configuration
- Override only what changes (DRY principle)
- Support for both full replacement and partial patches

### 2. **Batch Running**

**Execution Flow:**
1. **Discovery** - Find all scenario files in `batch_scenarios/scenarios/`
2. **Resolution** - Merge templates with overrides to create full configs
3. **Execution** - Run each scenario sequentially or in parallel
4. **Collection** - Gather results and metrics from each run

**Output Structure:**
```
batch_outputs/
├── [timestamp]_batch_run/
│   ├── baseline/
│   ├── s1_aip_new_hires/
│   ├── s2_aip_all/
│   └── run_summary.json
```

**Features:**
- Simple CLI: `python run_batch.py` or `python run_batch.py --scenarios s1,s2`
- Progress tracking with status updates
- Error handling (continue on failure, log issues)
- Run summary with timing and success/failure status

### 3. **Batch Export**

**Per-Scenario Exports:**
Each scenario gets its own folder with:
- `simulation_{scenario_name}.duckdb` - Full database
- `workforce_snapshot_{scenario_name}.xlsx` - Period-by-period metrics
- `yearly_events_{scenario_name}.xlsx` - Annual summaries
- `contributions_{scenario_name}.xlsx` - Detailed contribution data

**Comparison Export:**
Single `comparison_report.xlsx` with multiple sheets:
- **Summary Sheet** - One row per scenario, key metrics as columns
  - Total participants (by year)
  - Total contributions
  - Employer match costs
  - Participation rates
  - Average deferral rates

- **Trends Sheet** - Time series comparisons
  - Year-over-year growth rates
  - Side-by-side metric evolution

- **Delta Sheet** - Changes from baseline
  - Absolute and percentage differences
  - Ranked by impact

**Export Features:**
- Consistent naming convention for easy import into other tools
- All exports include scenario metadata (config used, run timestamp)
- Excel formatting for readability (headers, number formats, conditional formatting for variances)

### Implementation Priority:
1. Start with scenario inheritance system (biggest quality-of-life improvement)
2. Add basic batch runner (sequential execution is fine initially)
3. Implement exports with comparison report
4. Optimize with parallel execution if needed

This keeps the scope focused on the core value: easily defining scenario variants, running them in batch, and getting comparable outputs for decision-making.
