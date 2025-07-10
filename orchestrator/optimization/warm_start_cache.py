"""
S050: Warm-Start Optimization Cache

Advanced caching system with historical success tracking and similarity-based
warm-start parameter recommendations for faster optimization convergence.
"""

from __future__ import annotations
import json
import math
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd
from scipy.spatial.distance import euclidean
from scipy.stats import pearsonr

from orchestrator.resources.duckdb_resource import DuckDBResource


@dataclass
class OptimizationHistoryEntry:
    """Historical optimization run entry for warm-start analysis."""
    run_id: str
    timestamp: datetime
    input_parameters: Dict[str, float]
    objectives: Dict[str, float]
    optimal_parameters: Dict[str, float]
    objective_value: float
    converged: bool
    function_evaluations: int
    runtime_seconds: float
    success_score: float
    parameter_hash: str
    similarity_features: Dict[str, float]


@dataclass
class WarmStartCandidate:
    """Warm-start parameter candidate with confidence metrics."""
    parameters: Dict[str, float]
    confidence_score: float
    historical_performance: Dict[str, Any]
    source_run_id: str
    similarity_metrics: Dict[str, float]
    expected_improvement: float


class WarmStartOptimizationCache:
    """
    Advanced warm-start cache with historical success tracking.

    Features:
    - Hybrid similarity matching (parameter distance + objective similarity)
    - Success pattern recognition
    - Performance prediction
    - Intelligent cache management
    """

    def __init__(self, duckdb_resource: DuckDBResource, cache_size_limit: int = 10000):
        self.duckdb_resource = duckdb_resource
        self.cache_size_limit = cache_size_limit
        self._initialize_cache_tables()

    def _initialize_cache_tables(self):
        """Initialize DuckDB tables for optimization history storage."""
        with self.duckdb_resource.get_connection() as conn:
            # Main optimization history table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS optimization_history (
                    run_id VARCHAR PRIMARY KEY,
                    timestamp TIMESTAMP,
                    input_params_json VARCHAR,
                    objectives_json VARCHAR,
                    optimal_params_json VARCHAR,
                    objective_value DOUBLE,
                    converged BOOLEAN,
                    function_evaluations INTEGER,
                    runtime_seconds DOUBLE,
                    success_score DOUBLE,
                    parameter_hash VARCHAR,
                    similarity_features_json VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Parameter similarity index for fast lookups
            conn.execute("""
                CREATE TABLE IF NOT EXISTS parameter_similarity_index (
                    run_id VARCHAR,
                    parameter_name VARCHAR,
                    normalized_value DOUBLE,
                    PRIMARY KEY (run_id, parameter_name),
                    FOREIGN KEY (run_id) REFERENCES optimization_history(run_id)
                )
            """)

            # Success pattern cache for common scenarios
            conn.execute("""
                CREATE TABLE IF NOT EXISTS success_patterns (
                    pattern_id VARCHAR PRIMARY KEY,
                    scenario_description VARCHAR,
                    parameter_ranges_json VARCHAR,
                    success_rate DOUBLE,
                    avg_convergence_time DOUBLE,
                    recommended_start_json VARCHAR,
                    sample_size INTEGER,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes for performance
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_opt_history_success ON optimization_history(success_score DESC)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_opt_history_timestamp ON optimization_history(timestamp DESC)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_param_similarity ON parameter_similarity_index(parameter_name, normalized_value)")
            except:
                pass  # Indexes may already exist

    def record_optimization_result(
        self,
        input_parameters: Dict[str, float],
        objectives: Dict[str, float],
        optimal_parameters: Dict[str, float],
        objective_value: float,
        converged: bool,
        function_evaluations: int,
        runtime_seconds: float
    ) -> str:
        """Record optimization result for future warm-start analysis."""
        run_id = str(uuid.uuid4())
        timestamp = datetime.now()

        # Calculate success score (0-1 scale)
        success_score = self._calculate_success_score(
            converged, objective_value, function_evaluations, runtime_seconds
        )

        # Generate parameter hash for deduplication
        parameter_hash = self._generate_parameter_hash(input_parameters, objectives)

        # Extract similarity features
        similarity_features = self._extract_similarity_features(input_parameters, objectives)

        # Store in database
        with self.duckdb_resource.get_connection() as conn:
            conn.execute("""
                INSERT INTO optimization_history (
                    run_id, timestamp, input_params_json, objectives_json,
                    optimal_params_json, objective_value, converged,
                    function_evaluations, runtime_seconds, success_score,
                    parameter_hash, similarity_features_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                run_id,
                timestamp,
                json.dumps(input_parameters),
                json.dumps(objectives),
                json.dumps(optimal_parameters),
                objective_value,
                converged,
                function_evaluations,
                runtime_seconds,
                success_score,
                parameter_hash,
                json.dumps(similarity_features)
            ])

            # Store normalized parameters for similarity search
            for param_name, value in input_parameters.items():
                normalized_value = self._normalize_parameter_value(param_name, value)
                conn.execute("""
                    INSERT INTO parameter_similarity_index (run_id, parameter_name, normalized_value)
                    VALUES (?, ?, ?)
                """, [run_id, param_name, normalized_value])

        # Update success patterns
        self._update_success_patterns()

        # Manage cache size
        self._manage_cache_size()

        return run_id

    def get_warm_start_candidates(
        self,
        current_parameters: Dict[str, float],
        objectives: Dict[str, float],
        n_candidates: int = 5,
        min_confidence: float = 0.3
    ) -> List[WarmStartCandidate]:
        """
        Get warm-start candidates based on historical success patterns.

        Uses hybrid similarity approach:
        - Parameter distance for direct similarity
        - Objective similarity for outcome-based matching
        - Success pattern recognition
        """
        candidates = []

        # Get historical data sorted by success score
        with self.duckdb_resource.get_connection() as conn:
            history_df = conn.execute("""
                SELECT * FROM optimization_history
                WHERE converged = true AND success_score > ?
                ORDER BY success_score DESC
                LIMIT 100
            """, [min_confidence]).df()

        if history_df.empty:
            return candidates

        # Calculate current parameter features
        current_features = self._extract_similarity_features(current_parameters, objectives)
        current_normalized = {
            name: self._normalize_parameter_value(name, value)
            for name, value in current_parameters.items()
        }

        # Find similar historical runs
        similarities = []
        for _, row in history_df.iterrows():
            historical_params = json.loads(row['input_params_json'])
            historical_objectives = json.loads(row['objectives_json'])
            historical_features = json.loads(row['similarity_features_json'])

            # Calculate similarity metrics
            param_similarity = self._calculate_parameter_similarity(
                current_normalized, historical_params
            )
            objective_similarity = self._calculate_objective_similarity(
                objectives, historical_objectives
            )
            feature_similarity = self._calculate_feature_similarity(
                current_features, historical_features
            )

            # Hybrid similarity score
            combined_similarity = (
                0.5 * param_similarity +
                0.3 * objective_similarity +
                0.2 * feature_similarity
            )

            similarities.append({
                'run_id': row['run_id'],
                'similarity_score': combined_similarity,
                'param_similarity': param_similarity,
                'objective_similarity': objective_similarity,
                'feature_similarity': feature_similarity,
                'success_score': row['success_score'],
                'runtime_seconds': row['runtime_seconds'],
                'function_evaluations': row['function_evaluations'],
                'optimal_params': json.loads(row['optimal_params_json']),
                'historical_params': historical_params
            })

        # Sort by similarity and select top candidates
        similarities.sort(key=lambda x: x['similarity_score'], reverse=True)

        for i, sim in enumerate(similarities[:n_candidates]):
            # Calculate confidence score
            confidence = self._calculate_confidence_score(sim)

            if confidence >= min_confidence:
                # Predict expected improvement
                expected_improvement = self._predict_improvement(sim, current_parameters)

                candidate = WarmStartCandidate(
                    parameters=sim['optimal_params'],
                    confidence_score=confidence,
                    historical_performance={
                        'success_score': sim['success_score'],
                        'runtime_seconds': sim['runtime_seconds'],
                        'function_evaluations': sim['function_evaluations']
                    },
                    source_run_id=sim['run_id'],
                    similarity_metrics={
                        'parameter_similarity': sim['param_similarity'],
                        'objective_similarity': sim['objective_similarity'],
                        'feature_similarity': sim['feature_similarity'],
                        'combined_similarity': sim['similarity_score']
                    },
                    expected_improvement=expected_improvement
                )
                candidates.append(candidate)

        return candidates

    def get_success_patterns(self) -> List[Dict[str, Any]]:
        """Get identified success patterns for optimization guidance."""
        with self.duckdb_resource.get_connection() as conn:
            patterns_df = conn.execute("""
                SELECT * FROM success_patterns
                ORDER BY success_rate DESC, sample_size DESC
            """).df()

        patterns = []
        for _, row in patterns_df.iterrows():
            patterns.append({
                'pattern_id': row['pattern_id'],
                'description': row['scenario_description'],
                'parameter_ranges': json.loads(row['parameter_ranges_json']),
                'success_rate': row['success_rate'],
                'avg_convergence_time': row['avg_convergence_time'],
                'recommended_start': json.loads(row['recommended_start_json']),
                'sample_size': row['sample_size']
            })

        return patterns

    def _calculate_success_score(
        self,
        converged: bool,
        objective_value: float,
        function_evaluations: int,
        runtime_seconds: float
    ) -> float:
        """Calculate normalized success score (0-1) for optimization run."""
        if not converged:
            return 0.0

        # Base score for convergence
        score = 0.5

        # Bonus for low objective value (normalized by typical range)
        if objective_value < 100:  # Adjust based on typical objective values
            score += 0.2

        # Bonus for efficiency (fewer evaluations)
        if function_evaluations < 50:
            score += 0.15
        elif function_evaluations < 100:
            score += 0.1

        # Bonus for speed (faster runtime)
        if runtime_seconds < 30:
            score += 0.15
        elif runtime_seconds < 60:
            score += 0.1

        return min(1.0, score)

    def _generate_parameter_hash(
        self,
        parameters: Dict[str, float],
        objectives: Dict[str, float]
    ) -> str:
        """Generate hash for parameter combination to detect duplicates."""
        import hashlib

        # Round parameters to avoid floating point precision issues
        rounded_params = {k: round(v, 6) for k, v in parameters.items()}
        rounded_objectives = {k: round(v, 6) for k, v in objectives.items()}

        combined = {**rounded_params, **rounded_objectives}
        content = json.dumps(combined, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()

    def _extract_similarity_features(
        self,
        parameters: Dict[str, float],
        objectives: Dict[str, float]
    ) -> Dict[str, float]:
        """Extract features for similarity comparison."""
        features = {}

        # Parameter statistics
        param_values = list(parameters.values())
        features['param_mean'] = np.mean(param_values)
        features['param_std'] = np.std(param_values)
        features['param_range'] = max(param_values) - min(param_values)

        # Objective weights
        total_weight = sum(objectives.values())
        if total_weight > 0:
            features['cost_weight'] = objectives.get('cost', 0) / total_weight
            features['equity_weight'] = objectives.get('equity', 0) / total_weight
            features['targets_weight'] = objectives.get('targets', 0) / total_weight

        # Parameter patterns
        if 'merit_rate_level_1' in parameters:
            merit_rates = [parameters.get(f'merit_rate_level_{i}', 0) for i in range(1, 6)]
            features['merit_progression'] = np.polyfit(range(5), merit_rates, 1)[0]  # Slope

        return features

    def _normalize_parameter_value(self, param_name: str, value: float) -> float:
        """Normalize parameter value to [0, 1] range for comparison."""
        # Define parameter ranges (should be configurable)
        param_ranges = {
            'merit_rate_level_1': (0.01, 0.10),
            'merit_rate_level_2': (0.01, 0.10),
            'merit_rate_level_3': (0.01, 0.10),
            'merit_rate_level_4': (0.01, 0.10),
            'merit_rate_level_5': (0.01, 0.10),
            'cola_rate': (0.0, 0.05),
            'new_hire_salary_adjustment': (1.0, 1.30),
            'promotion_probability_level_1': (0.0, 0.20),
            'promotion_probability_level_2': (0.0, 0.20),
            'promotion_probability_level_3': (0.0, 0.20),
            'promotion_probability_level_4': (0.0, 0.20),
            'promotion_raise_level_1': (0.05, 0.25),
            'promotion_raise_level_2': (0.05, 0.25),
            'promotion_raise_level_3': (0.05, 0.25),
            'promotion_raise_level_4': (0.05, 0.25)
        }

        if param_name in param_ranges:
            min_val, max_val = param_ranges[param_name]
            return (value - min_val) / (max_val - min_val) if max_val > min_val else 0.5
        else:
            # Default normalization for unknown parameters
            return min(1.0, max(0.0, value))

    def _calculate_parameter_similarity(
        self,
        params1: Dict[str, float],
        params2: Dict[str, float]
    ) -> float:
        """Calculate similarity between two parameter sets."""
        common_params = set(params1.keys()) & set(params2.keys())
        if not common_params:
            return 0.0

        # Calculate normalized parameter vectors
        vec1 = np.array([self._normalize_parameter_value(p, params1[p]) for p in common_params])
        vec2 = np.array([self._normalize_parameter_value(p, params2[p]) for p in common_params])

        # Use cosine similarity for scale-invariant comparison
        dot_product = np.dot(vec1, vec2)
        norms = np.linalg.norm(vec1) * np.linalg.norm(vec2)

        if norms == 0:
            return 1.0 if np.array_equal(vec1, vec2) else 0.0

        cosine_sim = dot_product / norms
        return max(0.0, cosine_sim)  # Ensure non-negative

    def _calculate_objective_similarity(
        self,
        obj1: Dict[str, float],
        obj2: Dict[str, float]
    ) -> float:
        """Calculate similarity between objective weight sets."""
        # Normalize objectives to sum to 1
        def normalize_objectives(obj):
            total = sum(obj.values())
            return {k: v / total for k, v in obj.items()} if total > 0 else obj

        norm_obj1 = normalize_objectives(obj1)
        norm_obj2 = normalize_objectives(obj2)

        common_objectives = set(norm_obj1.keys()) & set(norm_obj2.keys())
        if not common_objectives:
            return 0.0

        # Calculate weighted similarity
        total_similarity = 0.0
        for obj_name in common_objectives:
            weight1 = norm_obj1[obj_name]
            weight2 = norm_obj2[obj_name]
            # Use inverse absolute difference
            similarity = 1.0 - abs(weight1 - weight2)
            total_similarity += similarity

        return total_similarity / len(common_objectives)

    def _calculate_feature_similarity(
        self,
        features1: Dict[str, float],
        features2: Dict[str, float]
    ) -> float:
        """Calculate similarity between extracted features."""
        common_features = set(features1.keys()) & set(features2.keys())
        if not common_features:
            return 0.0

        similarities = []
        for feature_name in common_features:
            val1 = features1[feature_name]
            val2 = features2[feature_name]

            # Handle potential division by zero
            if val1 == 0 and val2 == 0:
                similarity = 1.0
            elif val1 == 0 or val2 == 0:
                similarity = 0.0
            else:
                # Use relative difference
                similarity = 1.0 - abs(val1 - val2) / max(abs(val1), abs(val2))

            similarities.append(similarity)

        return np.mean(similarities)

    def _calculate_confidence_score(self, similarity_data: Dict[str, Any]) -> float:
        """Calculate confidence score for warm-start candidate."""
        # Base confidence from similarity
        base_confidence = similarity_data['similarity_score']

        # Adjust based on historical success
        success_bonus = similarity_data['success_score'] * 0.3

        # Adjust based on efficiency
        runtime = similarity_data['runtime_seconds']
        evaluations = similarity_data['function_evaluations']

        efficiency_bonus = 0.0
        if runtime < 60 and evaluations < 100:
            efficiency_bonus = 0.2
        elif runtime < 120 and evaluations < 200:
            efficiency_bonus = 0.1

        confidence = base_confidence + success_bonus + efficiency_bonus
        return min(1.0, confidence)

    def _predict_improvement(
        self,
        similarity_data: Dict[str, Any],
        current_parameters: Dict[str, float]
    ) -> float:
        """Predict expected improvement from using this warm-start."""
        # Simple heuristic based on historical performance
        base_improvement = similarity_data['success_score'] * 0.4

        # Factor in similarity strength
        similarity_factor = similarity_data['similarity_score'] * 0.3

        # Factor in efficiency gains
        runtime = similarity_data['runtime_seconds']
        efficiency_factor = max(0.0, (120 - runtime) / 120) * 0.3

        return base_improvement + similarity_factor + efficiency_factor

    def _update_success_patterns(self):
        """Update success patterns based on recent optimization history."""
        # This would implement pattern recognition logic
        # For now, we'll implement a simple version that identifies
        # parameter ranges that lead to consistent success
        pass

    def _manage_cache_size(self):
        """Manage cache size by removing old/poor entries."""
        with self.duckdb_resource.get_connection() as conn:
            # Count current entries
            count = conn.execute("SELECT COUNT(*) FROM optimization_history").fetchone()[0]

            if count > self.cache_size_limit:
                # Remove oldest low-performing entries
                excess = count - self.cache_size_limit
                conn.execute("""
                    DELETE FROM optimization_history
                    WHERE run_id IN (
                        SELECT run_id FROM optimization_history
                        ORDER BY success_score ASC, timestamp ASC
                        LIMIT ?
                    )
                """, [excess])

    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        with self.duckdb_resource.get_connection() as conn:
            stats = conn.execute("""
                SELECT
                    COUNT(*) as total_entries,
                    AVG(success_score) as avg_success_score,
                    AVG(runtime_seconds) as avg_runtime,
                    COUNT(CASE WHEN converged THEN 1 END) as converged_count,
                    MIN(timestamp) as oldest_entry,
                    MAX(timestamp) as newest_entry
                FROM optimization_history
            """).fetchone()

            if stats[0] == 0:
                return {"total_entries": 0}

            return {
                "total_entries": stats[0],
                "avg_success_score": round(stats[1], 3),
                "avg_runtime_seconds": round(stats[2], 2),
                "convergence_rate": round(stats[3] / stats[0], 3),
                "oldest_entry": stats[4],
                "newest_entry": stats[5]
            }

    def clear_cache(self, older_than_days: Optional[int] = None):
        """Clear optimization cache."""
        with self.duckdb_resource.get_connection() as conn:
            if older_than_days:
                cutoff_date = datetime.now() - timedelta(days=older_than_days)
                conn.execute(
                    "DELETE FROM optimization_history WHERE timestamp < ?",
                    [cutoff_date]
                )
            else:
                conn.execute("DELETE FROM optimization_history")
                conn.execute("DELETE FROM parameter_similarity_index")
                conn.execute("DELETE FROM success_patterns")
