# Streamlit Compensation Tuning Interface - User Guide

## Overview

The E012 Streamlit Compensation Tuning Interface provides analysts with a self-service tool to adjust compensation parameters and run simulations without requiring code changes or developer intervention.

## Features

### ✅ Completed (S046)

1. **Interactive Parameter Sliders**
   - COLA Rate adjustment (0-8%)
   - Merit rates by job level (0-10%)
   - New hire salary adjustment (100-150%)
   - Promotion probabilities by level
   - Promotion raise percentages

2. **Real-time Parameter Validation**
   - Automatic validation with warnings and errors
   - Budget impact warnings for high rates
   - Performance impact warnings for low rates
   - Invalid range error detection

3. **Dagster Pipeline Integration**
   - GraphQL API integration for asset materialization
   - Command-line fallback for offline use
   - Real-time simulation progress tracking
   - Automatic parameter file updates

4. **Advanced Results Visualization**
   - Before/after comparison charts
   - Year-over-year growth rate analysis
   - Average salary evolution tracking
   - Impact summary metrics
   - Target achievement analysis

5. **Professional User Experience**
   - Clean, intuitive interface design
   - Comprehensive user guidance
   - Performance tips and best practices
   - Export functionality for results

## Installation

### Dependencies
```bash
pip install streamlit pandas plotly duckdb pydantic requests
```

### Files Created
- `streamlit_dashboard/compensation_tuning.py` - Main interface
- `streamlit_dashboard/launch_compensation_tuning.py` - Launcher script
- `streamlit_dashboard/test_compensation_interface.py` - Test suite

## Usage

### Starting the Interface

**Option 1: Using the launcher script**
```bash
cd streamlit_dashboard
python launch_compensation_tuning.py
```

**Option 2: Direct Streamlit command**
```bash
cd streamlit_dashboard
streamlit run compensation_tuning.py
```

The interface will open in your browser at `http://localhost:8501`

### Workflow

1. **Review Current Parameters** (Parameter Overview tab)
   - View current compensation settings
   - See parameter changes vs baseline
   - Check validation status

2. **Adjust Parameters** (Sidebar controls)
   - Use sliders to modify COLA, merit, and promotion rates
   - See real-time validation feedback
   - Watch for warnings and errors

3. **Analyze Impact** (Impact Analysis tab)
   - Preview expected outcomes
   - Enable "Show Before/After" for comparisons
   - Review growth rate projections

4. **Run Simulation** (Run Simulation tab)
   - Save parameter changes
   - Trigger multi-year simulation
   - Monitor progress via Dagster UI

5. **Review Results** (Results tab)
   - Examine detailed year-by-year outcomes
   - Export results for further analysis
   - Compare against targets

## Key Features

### Parameter Controls
- **COLA Rate**: Universal cost-of-living adjustment
- **Merit Rates**: Performance-based increases by job level
- **New Hire Adjustment**: Salary multiplier for new hires
- **Promotion Probability**: Advancement rates by level
- **Promotion Raises**: Compensation increases for promoted employees

### Validation System
- **Budget Warnings**: Alerts for rates above 6-8%
- **Performance Warnings**: Alerts for rates below 2%
- **Range Errors**: Prevention of invalid parameter values
- **Conflict Detection**: Identification of incompatible settings

### Integration Features
- **Dagster GraphQL API**: Direct asset materialization
- **DuckDB Connection**: Real-time results loading
- **Parameter File Updates**: Automatic CSV synchronization
- **Multi-year Simulation**: Full workforce projection

### Visualization Capabilities
- **Growth Rate Charts**: Year-over-year compensation growth
- **Salary Evolution**: Average compensation trends
- **Before/After Comparison**: Impact of parameter changes
- **Target Achievement**: Progress toward compensation goals

## Technical Architecture

### Data Flow
1. Parameters loaded from `dbt/seeds/comp_levers.csv`
2. User adjustments captured via Streamlit widgets
3. Validation applied to parameter combinations
4. Changes written back to CSV files
5. Dagster pipeline triggered for simulation
6. Results loaded from DuckDB database
7. Visualization updated with new data

### Integration Points
- **dbt Models**: Parameter processing and validation
- **Dagster Assets**: Multi-year simulation orchestration
- **DuckDB Database**: Results storage and retrieval
- **Configuration Files**: YAML-based simulation settings

## Troubleshooting

### Common Issues

**Dagster Connection Failed**
- Ensure Dagster UI is running: `dagster dev`
- Check localhost:3000 accessibility
- Interface will fall back to command-line execution

**Parameter Loading Failed**
- Verify `dbt/seeds/comp_levers.csv` exists
- Check file permissions and format
- Ensure dbt models are up to date

**Simulation Results Not Loading**
- Confirm `simulation.duckdb` database exists
- Run a simulation to generate initial data
- Check database file permissions

**Validation Errors**
- Review parameter ranges and limits
- Check for conflicting settings
- Refer to validation messages for guidance

### Performance Optimization
- Simulations typically take 2-5 minutes
- Large parameter changes require longer processing
- Use validation to avoid unrealistic scenarios
- Monitor progress via Dagster UI

## Next Steps (Future Stories)

- **S045**: Dagster tuning loops with convergence detection
- **S047**: SciPy-based optimization engine
- **S048**: Governance and audit framework

## Support

For issues or questions:
1. Check the interface help section (ℹ️ How to Use This Interface)
2. Review validation messages and warnings
3. Consult Dagster UI logs for detailed error information
4. Reference this guide for workflow guidance

---

**Last Updated**: 2025-06-29
**Version**: S046 - Analyst Interface Complete
**Status**: Production Ready
