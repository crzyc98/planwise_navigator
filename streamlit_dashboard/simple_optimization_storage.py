
# Simple Optimization Storage Functions
import duckdb
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

def simple_save_optimization_result(
    scenario_id: str,
    optimization_type: str,
    algorithm: str,
    parameters: Dict[str, Any],
    results: Dict[str, Any],
    runtime_seconds: float = 0.0,
    converged: bool = True
) -> str:
    """Save optimization result to simple storage."""

    db_path = "/Users/nicholasamaral/planwise_navigator/simulation.duckdb"
    run_id = f"{optimization_type}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    try:
        with duckdb.connect(db_path) as conn:
            conn.execute("""
                INSERT INTO optimization_results_unified
                (run_id, scenario_id, optimization_type, created_at, algorithm,
                 parameters, results, status, runtime_seconds, converged, objective_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                run_id,
                scenario_id,
                optimization_type,
                datetime.now(),
                algorithm,
                json.dumps(parameters),
                json.dumps(results),
                'completed',
                runtime_seconds,
                converged,
                results.get('objective_value', 0.0)
            ])

        return run_id

    except Exception as e:
        print(f"Save failed: {e}")
        return ""

def simple_load_optimization_results(limit: int = 10) -> List[Dict[str, Any]]:
    """Load recent optimization results."""

    db_path = "/Users/nicholasamaral/planwise_navigator/simulation.duckdb"

    try:
        with duckdb.connect(db_path) as conn:
            rows = conn.execute("""
                SELECT run_id, scenario_id, optimization_type, created_at,
                       algorithm, parameters, results, status, runtime_seconds,
                       converged, objective_value
                FROM optimization_results_unified
                ORDER BY created_at DESC
                LIMIT ?
            """, [limit]).fetchall()

            results = []
            for row in rows:
                try:
                    parameters = json.loads(row[5]) if row[5] else {}
                    results_data = json.loads(row[6]) if row[6] else {}
                except:
                    parameters = {}
                    results_data = {}

                results.append({
                    'run_id': row[0],
                    'scenario_id': row[1],
                    'optimization_type': row[2],
                    'created_at': row[3],
                    'algorithm': row[4],
                    'parameters': parameters,
                    'results': results_data,
                    'status': row[7],
                    'runtime_seconds': row[8],
                    'converged': row[9],
                    'objective_value': row[10]
                })

            return results

    except Exception as e:
        print(f"Load failed: {e}")
        return []

def simple_get_optimization_summary() -> Dict[str, Any]:
    """Get a summary of optimization results."""

    db_path = "/Users/nicholasamaral/planwise_navigator/simulation.duckdb"

    try:
        with duckdb.connect(db_path) as conn:
            # Get summary stats
            summary = conn.execute("""
                SELECT
                    COUNT(*) as total_runs,
                    COUNT(CASE WHEN converged = true THEN 1 END) as converged_runs,
                    COUNT(CASE WHEN optimization_type = 'advanced_scipy' THEN 1 END) as advanced_runs,
                    COUNT(CASE WHEN optimization_type = 'compensation_tuning' THEN 1 END) as tuning_runs,
                    AVG(runtime_seconds) as avg_runtime,
                    MAX(created_at) as latest_run
                FROM optimization_results_unified
            """).fetchone()

            return {
                'total_runs': summary[0],
                'converged_runs': summary[1],
                'advanced_runs': summary[2],
                'tuning_runs': summary[3],
                'avg_runtime': summary[4],
                'latest_run': summary[5],
                'success_rate': summary[1] / summary[0] if summary[0] > 0 else 0
            }

    except Exception as e:
        print(f"Summary failed: {e}")
        return {}
