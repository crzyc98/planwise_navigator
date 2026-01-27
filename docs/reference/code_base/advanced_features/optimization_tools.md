# Optimization Tools - Parameter Tuning and Analysis

## Purpose

The optimization tools provide advanced capabilities for fine-tuning Fidelity PlanAlign Engine simulation parameters, analyzing workforce dynamics patterns, and automatically optimizing model performance to achieve target outcomes with maximum efficiency.

## Architecture

The optimization framework implements sophisticated algorithms for:
- **Parameter Optimization**: Automated tuning of simulation parameters
- **Pattern Analysis**: Statistical analysis of workforce behavior patterns
- **Drift Detection**: Identification and correction of parameter drift
- **Performance Optimization**: Model efficiency and accuracy improvements

## Key Optimization Tools

### 1. auto_tune_hazard_tables.py - Automated Parameter Optimization

**Purpose**: Automatically optimize hazard table parameters to match historical workforce patterns and achieve target outcomes.

```python
#!/usr/bin/env python3
"""
Automated Hazard Table Optimization for Fidelity PlanAlign Engine

This tool uses statistical optimization algorithms to automatically tune
hazard table parameters based on historical data and target outcomes.

Usage:
    python scripts/auto_tune_hazard_tables.py --historical-data data/historical_workforce.csv
    python scripts/auto_tune_hazard_tables.py --target-growth 0.03 --target-turnover 0.12
    python scripts/auto_tune_hazard_tables.py --optimize-all --iterations 100
"""

import argparse
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from scipy.optimize import minimize, differential_evolution
from sklearn.metrics import mean_squared_error, mean_absolute_error
import logging
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from orchestrator.utils.database_utils import DatabaseManager
from orchestrator.utils.simulation_utils import SimulationValidator
from scripts.run_simulation import SimulationRunner

class HazardTableOptimizer:
    """Automated optimization of hazard table parameters"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.logger = self._setup_logging()
        self.db_manager = DatabaseManager()
        self.validator = SimulationValidator()

        # Optimization parameters
        self.optimization_history = []
        self.best_parameters = None
        self.best_score = float('inf')

        # Parameter bounds for optimization
        self.parameter_bounds = {
            'promotion_rates': {
                'level_1': (0.05, 0.30),  # 5-30% promotion rate from level 1
                'level_2': (0.03, 0.25),  # 3-25% promotion rate from level 2
                'level_3': (0.02, 0.20),  # 2-20% promotion rate from level 3
                'level_4': (0.01, 0.15),  # 1-15% promotion rate from level 4
            },
            'termination_rates': {
                'base_rate': (0.08, 0.25),        # 8-25% base termination rate
                'new_hire_multiplier': (1.5, 3.0), # 1.5-3x higher for new hires
                'age_multipliers': {
                    'young': (0.8, 1.5),   # Age < 30 multiplier
                    'mid': (0.7, 1.2),     # Age 30-50 multiplier
                    'senior': (0.9, 1.8),  # Age > 50 multiplier
                }
            },
            'merit_rates': {
                'base_rate': (0.02, 0.08),         # 2-8% base merit increase
                'performance_multipliers': {
                    'exceptional': (1.5, 3.0),     # Exceptional performance
                    'exceeds': (1.2, 2.0),         # Exceeds expectations
                    'meets': (0.8, 1.2),           # Meets expectations
                }
            }
        }

    def _setup_logging(self) -> logging.Logger:
        """Setup logging for optimization process"""
        log_level = logging.DEBUG if self.verbose else logging.INFO

        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(f'logs/hazard_optimization_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            ]
        )

        return logging.getLogger(__name__)

    def load_historical_data(self, file_path: str) -> pd.DataFrame:
        """Load historical workforce data for comparison"""
        try:
            self.logger.info(f"Loading historical data from {file_path}")

            if file_path.endswith('.csv'):
                data = pd.read_csv(file_path)
            elif file_path.endswith('.parquet'):
                data = pd.read_parquet(file_path)
            else:
                # Try loading from database
                query = """
                SELECT
                    year,
                    total_headcount,
                    growth_rate,
                    turnover_rate,
                    promotion_rate,
                    avg_tenure,
                    level_1_count,
                    level_2_count,
                    level_3_count,
                    level_4_count,
                    level_5_count
                FROM historical_workforce_summary
                ORDER BY year
                """
                data = self.db_manager.execute_query(query)

            # Validate required columns
            required_columns = ['year', 'total_headcount', 'growth_rate', 'turnover_rate']
            missing_columns = [col for col in required_columns if col not in data.columns]

            if missing_columns:
                raise ValueError(f"Missing required columns: {missing_columns}")

            self.logger.info(f"Loaded {len(data)} historical data points")
            return data

        except Exception as e:
            self.logger.error(f"Failed to load historical data: {str(e)}")
            raise

    def extract_current_parameters(self) -> Dict[str, Any]:
        """Extract current hazard table parameters from database"""
        try:
            self.logger.info("Extracting current hazard table parameters")

            # Load promotion hazard parameters
            promotion_query = """
            SELECT level_id, base_promotion_rate, age_multiplier, tenure_multiplier
            FROM config_promotion_hazard_base
            """
            promotion_data = self.db_manager.execute_query(promotion_query)

            # Load termination hazard parameters
            termination_query = """
            SELECT level_id, base_termination_rate, age_multiplier, tenure_multiplier
            FROM config_termination_hazard_base
            """
            termination_data = self.db_manager.execute_query(termination_query)

            # Load merit hazard parameters
            merit_query = """
            SELECT performance_rating, base_merit_rate, level_multiplier
            FROM config_raises_hazard
            """
            merit_data = self.db_manager.execute_query(merit_query)

            # Structure parameters
            current_params = {
                'promotion_rates': {
                    f'level_{row["level_id"]}': row['base_promotion_rate']
                    for _, row in promotion_data.iterrows()
                },
                'termination_rates': {
                    'base_rate': termination_data['base_termination_rate'].mean(),
                    'level_multipliers': {
                        f'level_{row["level_id"]}': row['age_multiplier']
                        for _, row in termination_data.iterrows()
                    }
                },
                'merit_rates': {
                    'performance_multipliers': {
                        row['performance_rating']: row['base_merit_rate']
                        for _, row in merit_data.iterrows()
                    }
                }
            }

            self.logger.info("Successfully extracted current parameters")
            return current_params

        except Exception as e:
            self.logger.error(f"Failed to extract parameters: {str(e)}")
            raise

    def parameters_to_vector(self, params: Dict[str, Any]) -> np.ndarray:
        """Convert parameter dictionary to optimization vector"""
        vector = []

        # Promotion rates
        for level in ['level_1', 'level_2', 'level_3', 'level_4']:
            vector.append(params['promotion_rates'].get(level, 0.15))

        # Termination rates
        vector.append(params['termination_rates']['base_rate'])
        vector.append(params['termination_rates'].get('new_hire_multiplier', 2.0))

        # Age multipliers for termination
        age_mults = params['termination_rates'].get('age_multipliers', {})
        vector.extend([
            age_mults.get('young', 1.0),
            age_mults.get('mid', 0.9),
            age_mults.get('senior', 1.2)
        ])

        # Merit rates
        vector.append(params['merit_rates']['base_rate'])

        # Performance multipliers for merit
        perf_mults = params['merit_rates'].get('performance_multipliers', {})
        vector.extend([
            perf_mults.get('exceptional', 2.0),
            perf_mults.get('exceeds', 1.5),
            perf_mults.get('meets', 1.0)
        ])

        return np.array(vector)

    def vector_to_parameters(self, vector: np.ndarray) -> Dict[str, Any]:
        """Convert optimization vector back to parameter dictionary"""
        params = {
            'promotion_rates': {
                'level_1': float(vector[0]),
                'level_2': float(vector[1]),
                'level_3': float(vector[2]),
                'level_4': float(vector[3]),
            },
            'termination_rates': {
                'base_rate': float(vector[4]),
                'new_hire_multiplier': float(vector[5]),
                'age_multipliers': {
                    'young': float(vector[6]),
                    'mid': float(vector[7]),
                    'senior': float(vector[8])
                }
            },
            'merit_rates': {
                'base_rate': float(vector[9]),
                'performance_multipliers': {
                    'exceptional': float(vector[10]),
                    'exceeds': float(vector[11]),
                    'meets': float(vector[12])
                }
            }
        }

        return params

    def get_optimization_bounds(self) -> List[Tuple[float, float]]:
        """Get parameter bounds for optimization"""
        bounds = []

        # Promotion rate bounds
        for level in ['level_1', 'level_2', 'level_3', 'level_4']:
            bounds.append(self.parameter_bounds['promotion_rates'][level])

        # Termination rate bounds
        bounds.append(self.parameter_bounds['termination_rates']['base_rate'])
        bounds.append(self.parameter_bounds['termination_rates']['new_hire_multiplier'])

        # Age multiplier bounds
        age_bounds = self.parameter_bounds['termination_rates']['age_multipliers']
        bounds.extend([
            age_bounds['young'],
            age_bounds['mid'],
            age_bounds['senior']
        ])

        # Merit rate bounds
        bounds.append(self.parameter_bounds['merit_rates']['base_rate'])

        # Performance multiplier bounds
        perf_bounds = self.parameter_bounds['merit_rates']['performance_multipliers']
        bounds.extend([
            perf_bounds['exceptional'],
            perf_bounds['exceeds'],
            perf_bounds['meets']
        ])

        return bounds

    def update_hazard_tables(self, params: Dict[str, Any]) -> None:
        """Update database hazard tables with new parameters"""
        try:
            self.logger.debug("Updating hazard tables with new parameters")

            # Update promotion hazard table
            for level_str, rate in params['promotion_rates'].items():
                level_id = int(level_str.split('_')[1])

                update_query = """
                UPDATE config_promotion_hazard_base
                SET base_promotion_rate = ?
                WHERE level_id = ?
                """
                self.db_manager.execute_query(update_query, [rate, level_id])

            # Update termination hazard table
            base_term_rate = params['termination_rates']['base_rate']

            update_query = """
            UPDATE config_termination_hazard_base
            SET base_termination_rate = ?
            """
            self.db_manager.execute_query(update_query, [base_term_rate])

            # Update merit hazard table
            base_merit_rate = params['merit_rates']['base_rate']

            for perf_rating, multiplier in params['merit_rates']['performance_multipliers'].items():
                update_query = """
                UPDATE config_raises_hazard
                SET base_merit_rate = ?
                WHERE performance_rating = ?
                """
                self.db_manager.execute_query(update_query, [base_merit_rate * multiplier, perf_rating])

            self.logger.debug("Hazard tables updated successfully")

        except Exception as e:
            self.logger.error(f"Failed to update hazard tables: {str(e)}")
            raise

    def run_simulation_with_parameters(self, params: Dict[str, Any]) -> Dict[str, float]:
        """Run simulation with given parameters and return key metrics"""
        try:
            # Update hazard tables
            self.update_hazard_tables(params)

            # Run simulation
            runner = SimulationRunner(
                config_path="config/optimization_config.yaml",
                verbose=False
            )

            result = runner.run_simulation("multi_year")

            if result['status'] != 'success':
                self.logger.warning(f"Simulation failed: {result.get('error', 'Unknown error')}")
                return {'error': True}

            # Extract key metrics
            summary = result.get('summary', {})

            metrics = {
                'final_headcount': summary.get('final_headcount', 0),
                'avg_growth_rate': summary.get('avg_growth_rate', 0),
                'avg_turnover_rate': summary.get('avg_turnover_rate', 0),
                'total_promotions': summary.get('total_events', {}).get('promotions', 0),
                'execution_time': result.get('execution_time', 0),
                'error': False
            }

            return metrics

        except Exception as e:
            self.logger.error(f"Simulation with parameters failed: {str(e)}")
            return {'error': True}

    def objective_function(self, vector: np.ndarray, historical_data: pd.DataFrame,
                          targets: Dict[str, float]) -> float:
        """Objective function for optimization (minimization)"""
        try:
            # Convert vector to parameters
            params = self.vector_to_parameters(vector)

            # Run simulation
            metrics = self.run_simulation_with_parameters(params)

            if metrics.get('error', False):
                return 1e6  # Large penalty for failed simulations

            # Calculate weighted score based on targets
            score = 0.0
            weights = {
                'growth_rate': 10.0,    # High weight for growth rate accuracy
                'turnover_rate': 8.0,   # High weight for turnover rate accuracy
                'headcount': 5.0,       # Medium weight for headcount accuracy
                'promotions': 3.0       # Lower weight for promotion volume
            }

            # Growth rate error
            if 'target_growth' in targets:
                growth_error = abs(metrics['avg_growth_rate'] - targets['target_growth'])
                score += weights['growth_rate'] * growth_error

            # Turnover rate error
            if 'target_turnover' in targets:
                turnover_error = abs(metrics['avg_turnover_rate'] - targets['target_turnover'])
                score += weights['turnover_rate'] * turnover_error

            # Historical data comparison if available
            if not historical_data.empty:
                hist_avg_growth = historical_data['growth_rate'].mean()
                hist_avg_turnover = historical_data['turnover_rate'].mean()

                score += weights['growth_rate'] * abs(metrics['avg_growth_rate'] - hist_avg_growth)
                score += weights['turnover_rate'] * abs(metrics['avg_turnover_rate'] - hist_avg_turnover)

            # Track optimization history
            self.optimization_history.append({
                'parameters': params,
                'metrics': metrics,
                'score': score,
                'iteration': len(self.optimization_history) + 1
            })

            # Update best parameters if this is the best score
            if score < self.best_score:
                self.best_score = score
                self.best_parameters = params.copy()
                self.logger.info(f"New best score: {score:.6f} (iteration {len(self.optimization_history)})")

            return score

        except Exception as e:
            self.logger.error(f"Objective function evaluation failed: {str(e)}")
            return 1e6  # Large penalty for errors

    def optimize_parameters(self, historical_data: pd.DataFrame,
                           targets: Dict[str, float],
                           method: str = 'differential_evolution',
                           max_iterations: int = 50) -> Dict[str, Any]:
        """Optimize hazard table parameters using specified algorithm"""

        self.logger.info(f"Starting parameter optimization with {method}")
        self.logger.info(f"Targets: {targets}")
        self.logger.info(f"Max iterations: {max_iterations}")

        # Get current parameters as starting point
        current_params = self.extract_current_parameters()
        initial_vector = self.parameters_to_vector(current_params)

        # Get parameter bounds
        bounds = self.get_optimization_bounds()

        self.logger.info(f"Optimizing {len(initial_vector)} parameters within bounds")

        # Run optimization
        start_time = datetime.now()

        if method == 'differential_evolution':
            result = differential_evolution(
                func=lambda x: self.objective_function(x, historical_data, targets),
                bounds=bounds,
                maxiter=max_iterations,
                popsize=15,
                atol=1e-6,
                seed=42,
                disp=self.verbose
            )
        elif method == 'minimize':
            result = minimize(
                fun=lambda x: self.objective_function(x, historical_data, targets),
                x0=initial_vector,
                bounds=bounds,
                method='L-BFGS-B',
                options={'maxiter': max_iterations}
            )
        else:
            raise ValueError(f"Unknown optimization method: {method}")

        optimization_time = (datetime.now() - start_time).total_seconds()

        # Extract results
        if result.success:
            optimal_params = self.vector_to_parameters(result.x)
            final_score = result.fun

            self.logger.info(f"Optimization completed successfully!")
            self.logger.info(f"Final score: {final_score:.6f}")
            self.logger.info(f"Optimization time: {optimization_time:.2f} seconds")
            self.logger.info(f"Function evaluations: {result.nfev}")

            return {
                'success': True,
                'optimal_parameters': optimal_params,
                'final_score': final_score,
                'optimization_time': optimization_time,
                'iterations': result.nfev,
                'convergence_message': result.message if hasattr(result, 'message') else 'Converged',
                'optimization_history': self.optimization_history
            }
        else:
            self.logger.error(f"Optimization failed: {result.message if hasattr(result, 'message') else 'Unknown error'}")

            return {
                'success': False,
                'error': result.message if hasattr(result, 'message') else 'Optimization failed',
                'optimization_time': optimization_time,
                'best_parameters': self.best_parameters,
                'best_score': self.best_score,
                'optimization_history': self.optimization_history
            }

    def save_optimization_results(self, results: Dict[str, Any], output_file: str = None) -> None:
        """Save optimization results to file"""
        if output_file is None:
            output_file = f"optimization_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        try:
            import json

            # Convert numpy types to Python types for JSON serialization
            serializable_results = self._make_json_serializable(results)

            with open(output_file, 'w') as f:
                json.dump(serializable_results, f, indent=2)

            self.logger.info(f"Optimization results saved to {output_file}")

        except Exception as e:
            self.logger.error(f"Failed to save results: {str(e)}")

    def _make_json_serializable(self, obj):
        """Convert numpy types and other non-serializable types to JSON-compatible types"""
        if isinstance(obj, dict):
            return {key: self._make_json_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._make_json_serializable(item) for item in obj]
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.float64, np.float32)):
            return float(obj)
        else:
            return obj

def main():
    """Main entry point for hazard table optimization"""
    parser = argparse.ArgumentParser(description='Optimize Fidelity PlanAlign Engine hazard table parameters')

    parser.add_argument(
        '--historical-data',
        type=str,
        help='Path to historical workforce data file'
    )

    parser.add_argument(
        '--target-growth',
        type=float,
        default=0.03,
        help='Target annual growth rate (default: 0.03)'
    )

    parser.add_argument(
        '--target-turnover',
        type=float,
        default=0.12,
        help='Target annual turnover rate (default: 0.12)'
    )

    parser.add_argument(
        '--method',
        type=str,
        choices=['differential_evolution', 'minimize'],
        default='differential_evolution',
        help='Optimization algorithm (default: differential_evolution)'
    )

    parser.add_argument(
        '--iterations',
        type=int,
        default=50,
        help='Maximum optimization iterations (default: 50)'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Output file for optimization results'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    try:
        # Initialize optimizer
        optimizer = HazardTableOptimizer(verbose=args.verbose)

        # Load historical data if provided
        historical_data = pd.DataFrame()
        if args.historical_data:
            historical_data = optimizer.load_historical_data(args.historical_data)

        # Set optimization targets
        targets = {
            'target_growth': args.target_growth,
            'target_turnover': args.target_turnover
        }

        # Run optimization
        results = optimizer.optimize_parameters(
            historical_data=historical_data,
            targets=targets,
            method=args.method,
            max_iterations=args.iterations
        )

        # Save results
        optimizer.save_optimization_results(results, args.output)

        # Display summary
        if results['success']:
            print(f"\n✅ Optimization completed successfully!")
            print(f"   Final score: {results['final_score']:.6f}")
            print(f"   Iterations: {results['iterations']}")
            print(f"   Time: {results['optimization_time']:.2f} seconds")

            if args.output:
                print(f"   Results saved to: {args.output}")
        else:
            print(f"\n❌ Optimization failed: {results.get('error', 'Unknown error')}")
            if results.get('best_parameters'):
                print(f"   Best score achieved: {results['best_score']:.6f}")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n⚠️  Optimization interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Optimization error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### 2. simple_drift_optimizer.py - Parameter Drift Detection

**Purpose**: Monitor and correct parameter drift in workforce simulation models over time.

**Key Features**:
- Statistical drift detection algorithms
- Automated parameter correction
- Trend analysis and forecasting
- Alert generation for significant drift

### 3. analyze_termination_patterns.py - Advanced Pattern Analysis

**Purpose**: Deep analysis of termination patterns to identify trends and optimize retention strategies.

**Key Features**:
- Cohort-based termination analysis
- Risk factor identification
- Predictive modeling for at-risk employees
- Retention strategy recommendations

## Supporting Analysis Tools

### Performance Analysis
- **model_performance_analyzer.py**: Analyze simulation model performance and accuracy
- **benchmark_simulation_speed.py**: Performance benchmarking and optimization
- **memory_usage_profiler.py**: Memory usage analysis and optimization

### Statistical Analysis
- **workforce_statistics_analyzer.py**: Statistical analysis of workforce patterns
- **correlation_analyzer.py**: Identify correlations between workforce variables
- **outlier_detection.py**: Detect and analyze workforce data outliers

## Optimization Algorithms

### Genetic Algorithm Implementation
```python
class GeneticOptimizer:
    """Genetic algorithm for parameter optimization"""

    def __init__(self, population_size=50, mutation_rate=0.1, crossover_rate=0.8):
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate

    def optimize(self, objective_function, bounds, generations=100):
        """Run genetic algorithm optimization"""
        # Implementation details...
        pass
```

### Bayesian Optimization
```python
class BayesianOptimizer:
    """Bayesian optimization with Gaussian processes"""

    def __init__(self, acquisition_function='expected_improvement'):
        self.acquisition_function = acquisition_function

    def optimize(self, objective_function, bounds, n_calls=50):
        """Run Bayesian optimization"""
        # Implementation details...
        pass
```

## Configuration and Usage

### Optimization Configuration
```yaml
# config/optimization_config.yaml
optimization:
  algorithm: 'differential_evolution'
  max_iterations: 100
  population_size: 30
  tolerance: 1e-6

targets:
  growth_rate: 0.03
  turnover_rate: 0.12
  promotion_rate: 0.15

constraints:
  max_parameter_change: 0.5  # Maximum 50% parameter change
  min_simulation_years: 3
  validation_threshold: 0.95
```

### Usage Examples
```bash
# Basic optimization
python scripts/auto_tune_hazard_tables.py --target-growth 0.03 --target-turnover 0.12

# With historical data
python scripts/auto_tune_hazard_tables.py --historical-data data/workforce_history.csv --iterations 100

# Drift analysis
python scripts/simple_drift_optimizer.py --baseline-date 2023-01-01 --current-date 2024-01-01

# Pattern analysis
python scripts/analyze_termination_patterns.py --cohort-analysis --risk-modeling
```

## Dependencies

### External Libraries
- `scipy` - Optimization algorithms
- `scikit-learn` - Machine learning and statistics
- `numpy` - Numerical computing
- `pandas` - Data manipulation

### Internal Dependencies
- Simulation execution framework
- Database utilities
- Configuration management
- Validation framework

## Related Files

### Core Infrastructure
- `scripts/run_simulation.py` - Simulation execution
- `orchestrator/utils/simulation_utils.py` - Simulation utilities
- Database models and configuration files

### Analysis Components
- Statistical analysis utilities
- Data visualization tools
- Report generation systems

## Implementation Notes

### Best Practices
1. **Convergence Criteria**: Implement robust convergence detection
2. **Parameter Bounds**: Enforce realistic parameter constraints
3. **Validation**: Validate optimized parameters against business rules
4. **Documentation**: Track optimization history and rationale

### Performance Considerations
- Use parallel execution for population-based algorithms
- Implement early stopping for convergence
- Cache expensive simulation runs
- Use efficient numerical libraries

### Quality Assurance
- Validate optimization results against historical data
- Implement cross-validation for parameter stability
- Monitor optimization convergence and stability
- Provide confidence intervals for optimized parameters
