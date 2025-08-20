"""
Simple Setup Script for Optimization Storage
Creates a basic working version of the optimization storage system.
"""

import json
from datetime import datetime
from pathlib import Path

import duckdb


def setup_simple_optimization_storage():
    """Set up a simple version of the optimization storage."""

    db_path = "/Users/nicholasamaral/planwise_navigator/simulation.duckdb"

    print("🔧 Setting up simple optimization storage...")

    try:
        with duckdb.connect(db_path) as conn:
            # Create simple optimization results table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS optimization_results_unified (
                    run_id VARCHAR PRIMARY KEY,
                    scenario_id VARCHAR NOT NULL,
                    optimization_type VARCHAR NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    algorithm VARCHAR,
                    parameters VARCHAR,
                    results VARCHAR,
                    status VARCHAR DEFAULT 'completed',
                    runtime_seconds DOUBLE,
                    converged BOOLEAN,
                    objective_value DOUBLE
                )
            """
            )

            # Test the table
            conn.execute("SELECT COUNT(*) FROM optimization_results_unified").fetchone()
            print("✅ Created optimization_results_unified table")

            # Create a sample record
            sample_data = {
                "run_id": f'setup_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
                "scenario_id": "setup_test_scenario",
                "optimization_type": "advanced_scipy",
                "created_at": datetime.now(),
                "algorithm": "SLSQP",
                "parameters": json.dumps(
                    {"merit_rate_level_1": 0.045, "cola_rate": 0.025}
                ),
                "results": json.dumps(
                    {
                        "optimal_parameters": {
                            "merit_rate_level_1": 0.042,
                            "cola_rate": 0.023,
                        },
                        "objective_value": 0.234567,
                    }
                ),
                "status": "completed",
                "runtime_seconds": 12.5,
                "converged": True,
                "objective_value": 0.234567,
            }

            conn.execute(
                """
                INSERT INTO optimization_results_unified
                (run_id, scenario_id, optimization_type, created_at, algorithm,
                 parameters, results, status, runtime_seconds, converged, objective_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    sample_data["run_id"],
                    sample_data["scenario_id"],
                    sample_data["optimization_type"],
                    sample_data["created_at"],
                    sample_data["algorithm"],
                    sample_data["parameters"],
                    sample_data["results"],
                    sample_data["status"],
                    sample_data["runtime_seconds"],
                    sample_data["converged"],
                    sample_data["objective_value"],
                ],
            )

            print(f"✅ Created sample optimization record: {sample_data['run_id']}")

            # Verify we can read it back
            result = conn.execute(
                """
                SELECT run_id, scenario_id, optimization_type, status, converged
                FROM optimization_results_unified
                WHERE run_id = ?
            """,
                [sample_data["run_id"]],
            ).fetchone()

            if result:
                print(f"✅ Verified record: {result[1]} ({result[2]}) - {result[3]}")

            return True

    except Exception as e:
        print(f"❌ Setup failed: {e}")
        return False


def create_simple_functions():
    """Create simple save/load functions."""

    simple_functions_code = '''
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
'''

    # Write to a file
    output_file = Path(__file__).parent / "simple_optimization_storage.py"
    with open(output_file, "w") as f:
        f.write(simple_functions_code)

    print(f"✅ Created simple functions file: {output_file}")
    return str(output_file)


def main():
    """Main setup function."""
    print("🎯 Simple Optimization Storage Setup")
    print("=" * 40)

    success = True

    # Setup database table
    if setup_simple_optimization_storage():
        print("✅ Database setup successful")
    else:
        print("❌ Database setup failed")
        success = False

    # Create simple functions
    functions_file = create_simple_functions()
    if functions_file:
        print("✅ Simple functions created")
    else:
        print("❌ Functions creation failed")
        success = False

    if success:
        print("\n🎉 SIMPLE SETUP COMPLETE!")
        print("\n📖 Usage:")
        print("1. Import: from simple_optimization_storage import *")
        print("2. Save: simple_save_optimization_result(...)")
        print("3. Load: simple_load_optimization_results()")
        print("4. Summary: simple_get_optimization_summary()")
        print("\n📁 Database table: optimization_results_unified")
        print(f"📁 Functions file: {functions_file}")
    else:
        print("\n⚠️ Setup encountered issues")

    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
