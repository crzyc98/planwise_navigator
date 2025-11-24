# Auto-Optimize User Guide - Fidelity PlanAlign Engine

**Epic E012 Compensation Tuning System**
**Last Updated:** July 2025
**Target Audience:** Compensation Analysts, HR Professionals, Business Users

---

## Overview

The Auto-Optimize feature in Fidelity PlanAlign Engine's Compensation Tuning Interface enables analysts to automatically adjust compensation parameters to hit specific budget targets. This eliminates manual trial-and-error processes and reduces optimization time from hours to minutes.

### Key Benefits

- **Automated Parameter Tuning**: Intelligent adjustment of COLA, merit, and hiring parameters
- **Multi-Objective Optimization**: Simultaneously optimize for growth targets and budget constraints
- **Real-Time Progress Tracking**: Live visualization of convergence progress
- **Evidence-Based Results**: Comprehensive reporting with sensitivity analysis
- **Reproducible Outcomes**: Consistent results with configurable random seeds

---

## Getting Started

### Prerequisites

1. **Baseline Simulation**: Run at least one simulation to establish current state
2. **Parameter Understanding**: Familiarity with compensation parameter impacts
3. **Target Definition**: Clear growth rate or budget targets

### Access the Interface

1. Launch the Compensation Tuning Interface:
   ```bash
   streamlit run streamlit_dashboard/compensation_tuning.py
   ```

2. Navigate to the **"🤖 Auto-Optimize"** tab

### Basic Workflow

1. **Set Target**: Define your desired growth rate (typically 1-4%)
2. **Configure Settings**: Choose optimization strategy and simulation mode
3. **Run Optimization**: Start the automated process
4. **Review Results**: Analyze convergence and parameter changes
5. **Apply Results**: Use optimized parameters for production planning

---

## Interface Walkthrough

### Optimization Settings Panel

#### Core Parameters

- **Target Growth Rate (%)**: The compensation growth you want to achieve
  - *Range*: 0.0% - 10.0%
  - *Recommended*: 1.0% - 4.0% for realistic scenarios
  - *Example*: 2.5% for moderate growth targets

- **Max Iterations**: Maximum optimization attempts
  - *Range*: 1 - 20 iterations
  - *Recommended*: 8-12 for most scenarios
  - *Note*: More iterations = higher accuracy but longer runtime

- **Convergence Tolerance (%)**: How close to target constitutes success
  - *Range*: 0.01% - 1.0%
  - *Recommended*: 0.1% for balanced precision
  - *Example*: 0.05% for high-precision requirements

#### Optimization Strategies

**Conservative** (Recommended for Production)
- Small parameter adjustments (10% of gap per iteration)
- Lower risk of overshooting targets
- Slower convergence but more stable results
- Best for: Critical budget planning, risk-averse scenarios

**Balanced** (Default Recommendation)
- Moderate adjustments (30% of gap per iteration)
- Good balance of speed and stability
- Typical convergence in 5-8 iterations
- Best for: Standard planning scenarios, most use cases

**Aggressive** (Fast Prototyping)
- Large adjustments (50% of gap per iteration)
- Faster convergence but higher overshoot risk
- May require fine-tuning after initial convergence
- Best for: Rapid prototyping, initial exploration

### Advanced Settings

#### Algorithm Selection

Access via **"🔧 Advanced Optimization Settings"** expander:

- **SLSQP** (Default): Sequential Least Squares Programming
- **L-BFGS-B**: Limited-memory BFGS with bounds
- **TNC**: Truncated Newton Constrained
- **COBYLA**: Constrained Optimization by Linear Approximation

*See Algorithm Selection Guide for detailed comparison*

#### Simulation Mode

**🧪 Synthetic (Fast)** - *Recommended for Most Users*
- Uses mathematical approximations
- ~5-10 seconds per iteration
- Total optimization time: ~2-5 minutes
- Accuracy: ±0.1% typical variance from real simulation

**🔄 Real Simulation (Accurate)** - *For Maximum Precision*
- Full dbt model execution
- ~2-5 minutes per iteration
- Total optimization time: ~20-50 minutes
- Accuracy: Exact results matching production simulation

#### Progress Tracking

When enabled, provides real-time visualization:
- **Convergence Charts**: Growth rate progression toward target
- **Parameter Evolution**: How parameters change over iterations
- **Performance Metrics**: Timing and efficiency statistics
- **Constraint Monitoring**: Budget and feasibility constraint status

---

## Current State Analysis

Before optimization, the interface displays:

### Baseline Metrics
- **Current Growth**: Your existing parameter set's growth rate
- **Target Growth**: Your desired growth rate
- **Gap Analysis**: Difference and direction of required adjustment

### Optimization Readiness
- ✅ **Ready to Optimize**: Baseline exists and gap exceeds tolerance
- ⚠️ **Already at Target**: Current parameters meet requirements
- ❌ **Missing Baseline**: Need to run initial simulation first

---

## Running an Optimization

### Step-by-Step Process

1. **Review Current State**
   - Ensure baseline simulation results are loaded
   - Verify gap analysis shows meaningful difference from target

2. **Configure Parameters**
   - Set realistic target growth rate
   - Choose appropriate optimization strategy
   - Select simulation mode based on time/accuracy needs

3. **Start Optimization**
   - Click **"🚀 Start Auto-Optimization"**
   - Monitor progress in real-time (if enabled)
   - Wait for convergence or max iterations

4. **Review Results**
   - Check convergence status
   - Analyze final gap to target
   - Review parameter changes

### During Optimization

The interface shows:
- **Current Iteration**: Progress through max iterations
- **Live Growth Rate**: How each iteration affects growth
- **Parameter Adjustments**: What changes are being made
- **Convergence Status**: Whether target is achieved

### Typical Progression

```
Iteration 1: Current Growth 1.2% → Gap: +0.8% (need to increase)
Iteration 2: Current Growth 1.8% → Gap: +0.2% (getting closer)
Iteration 3: Current Growth 2.05% → Gap: -0.05% (converged!)
```

---

## Understanding Results

### Success Indicators

**✅ Converged Successfully**
- Final gap within tolerance (e.g., ±0.1%)
- Parameters automatically saved and applied
- Ready for production use

**⚠️ Partial Convergence**
- Significant improvement but not within tolerance
- Consider increasing max iterations or tolerance
- Results may still be usable depending on requirements

**❌ Failed to Converge**
- Target may be unrealistic for parameter constraints
- Consider adjusting target or optimization settings
- Check for simulation errors or database issues

### Results Dashboard

**Optimization Summary**
- **Converged**: Yes/No status
- **Iterations Used**: How many attempts were needed
- **Final Growth**: Achieved growth rate
- **Final Gap**: Remaining difference from target

**Convergence Chart**
- Visual progression toward target
- Target line and tolerance bands
- Identifies convergence iteration

**Parameter Changes**
Shows before/after values for:
- COLA rates by job level
- Merit rates by job level
- New hire salary adjustments
- Promotion rates and raises

---

## Common Scenarios

### Scenario 1: Budget Increase (Need Higher Growth)
**Situation**: Current growth 1.5%, need 3.0%
**Approach**: Use Balanced strategy, 12 iterations, 0.1% tolerance
**Expected Result**: Increased COLA and merit rates, higher new hire adjustments

### Scenario 2: Budget Tightening (Need Lower Growth)
**Situation**: Current growth 4.2%, need 2.5%
**Approach**: Use Conservative strategy to avoid overcorrection
**Expected Result**: Reduced merit rates, lower new hire premiums

### Scenario 3: Fine-Tuning (Small Adjustment)
**Situation**: Current growth 2.8%, need 3.0%
**Approach**: Use Conservative with tight tolerance (0.05%)
**Expected Result**: Minor COLA or merit adjustments

### Scenario 4: Rapid Prototyping (Multiple Targets)
**Situation**: Testing different growth scenarios
**Approach**: Use Aggressive with Synthetic mode for speed
**Expected Result**: Quick convergence for multiple "what-if" analyses

---

## Best Practices

### Target Setting
- **Start Conservative**: Begin with achievable targets (1-3% growth)
- **Consider Context**: Factor in economic conditions and company policies
- **Validate Feasibility**: Ensure targets align with business constraints

### Strategy Selection
- **Production Runs**: Always use Conservative or Balanced
- **Exploration**: Aggressive acceptable for initial investigation
- **Critical Decisions**: Use Real Simulation mode for final validation

### Iteration Management
- **Start with 8-10 iterations** for most scenarios
- **Increase to 15-20** for difficult convergence cases
- **Monitor progress**: Stop early if oscillating without improvement

### Parameter Validation
- **Review Changes**: Ensure parameter modifications make business sense
- **Cross-Check Results**: Validate against historical data and benchmarks
- **Document Decisions**: Keep records of optimization rationale

---

## Troubleshooting

### Common Issues

**"Cannot optimize without baseline results"**
- Solution: Run a simulation in the "Run Simulation" tab first
- Verify: Check that simulation completed successfully

**"Already at target - no optimization needed"**
- Review: Current parameters may already be optimal
- Consider: Tightening tolerance if refinement needed

**"Optimization failed - database lock error"**
- Solution: Close IDE database connections (VS Code, etc.)
- Retry: Database connections prevent simultaneous access

**"Convergence oscillation"**
- Symptoms: Growth rate bounces around target without converging
- Solutions: Reduce optimization aggressiveness, increase tolerance, or use different algorithm

**"Target seems unreachable"**
- Check: Whether target growth rate is realistic
- Consider: Parameter bounds may prevent achieving extreme targets
- Review: Business constraints and policy limitations

### Performance Issues

**Slow Optimization (Real Simulation Mode)**
- Expected: 2-5 minutes per iteration is normal
- Options: Switch to Synthetic mode for faster results
- Alternative: Run overnight for high-precision requirements

**Memory or CPU Issues**
- Close: Other applications to free resources
- Monitor: System performance during optimization
- Consider: Running on more powerful hardware for large datasets

---

## Next Steps

After successful optimization:

1. **Review Results**: Check the "Results" tab for detailed analysis
2. **Validate Parameters**: Ensure changes align with business policies
3. **Document Changes**: Record optimization rationale and results
4. **Implement Gradually**: Consider phased rollout of significant changes
5. **Monitor Impact**: Track actual results against optimized projections

### Advanced Features

- **Evidence Reports**: Generate comprehensive analysis documentation
- **Sensitivity Analysis**: Understand parameter impact ranges
- **Multi-Scenario Testing**: Compare multiple optimization targets
- **Historical Validation**: Test parameters against past performance

---

## Related Documentation

- [Algorithm Selection Guide](algorithm_selection_guide.md)
- [Synthetic vs Real Mode Guide](synthetic_real_mode_guide.md)
- [Troubleshooting Guide](auto_optimize_troubleshooting.md)
- [Best Practices Guide](auto_optimize_best_practices.md)
- [Technical Integration Guide](auto_optimize_integration_guide.md)

---

## Support

For additional assistance:
- **Technical Issues**: See troubleshooting guide or contact development team
- **Business Questions**: Consult with compensation team leads
- **Feature Requests**: Submit through standard enhancement process

*This guide is part of the Fidelity PlanAlign Engine E012 Compensation Tuning System documentation suite.*
