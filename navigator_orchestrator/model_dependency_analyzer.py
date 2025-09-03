#!/usr/bin/env python3
"""
Model Dependency Analysis System

Analyzes dbt model dependencies to determine safe parallelization opportunities
while preserving data integrity and execution order requirements.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple
from collections import defaultdict, deque

from .model_execution_types import ModelClassifier, ModelExecutionType, ModelClassification


@dataclass
class DependencyGraph:
    """Represents the dependency graph of dbt models."""
    nodes: Dict[str, Set[str]] = field(default_factory=dict)  # model -> dependencies
    reverse_nodes: Dict[str, Set[str]] = field(default_factory=dict)  # model -> dependents

    def add_dependency(self, model: str, dependency: str) -> None:
        """Add a dependency relationship."""
        if model not in self.nodes:
            self.nodes[model] = set()
        if dependency not in self.reverse_nodes:
            self.reverse_nodes[dependency] = set()

        self.nodes[model].add(dependency)
        self.reverse_nodes[dependency].add(model)

    def get_dependencies(self, model: str) -> Set[str]:
        """Get direct dependencies of a model."""
        return self.nodes.get(model, set())

    def get_dependents(self, model: str) -> Set[str]:
        """Get direct dependents of a model."""
        return self.reverse_nodes.get(model, set())

    def get_transitive_dependencies(self, model: str) -> Set[str]:
        """Get all transitive dependencies of a model."""
        visited = set()
        queue = deque([model])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            for dep in self.get_dependencies(current):
                if dep not in visited:
                    queue.append(dep)

        visited.remove(model)  # Remove self
        return visited

    def topological_sort(self, models: List[str]) -> List[str]:
        """Return topologically sorted list of models."""
        in_degree = defaultdict(int)

        # Calculate in-degrees
        for model in models:
            for dep in self.get_dependencies(model):
                if dep in models:
                    in_degree[model] += 1
            if model not in in_degree:
                in_degree[model] = 0

        # Process nodes with no dependencies
        queue = deque([model for model in models if in_degree[model] == 0])
        result = []

        while queue:
            current = queue.popleft()
            result.append(current)

            for dependent in self.get_dependents(current):
                if dependent in models:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        if len(result) != len(models):
            raise ValueError(f"Circular dependency detected in models: {set(models) - set(result)}")

        return result


@dataclass
class ParallelizationOpportunity:
    """Represents an opportunity for parallel execution."""
    parallel_models: List[str]
    execution_group: str
    estimated_speedup: float
    resource_requirements: Dict[str, Any]
    safety_level: str  # "high", "medium", "low"


class ModelDependencyAnalyzer:
    """Analyzes model dependencies to identify parallelization opportunities."""

    def __init__(self, dbt_project_dir: Path):
        self.dbt_project_dir = dbt_project_dir
        self.classifier = ModelClassifier()
        self.dependency_graph = DependencyGraph()
        self._manifest_cache: Optional[Dict[str, Any]] = None

    def analyze_dependencies(self, refresh_cache: bool = False) -> DependencyGraph:
        """Analyze dbt model dependencies using dbt's manifest."""
        if refresh_cache or self._manifest_cache is None:
            self._load_dbt_manifest()

        self._build_dependency_graph()
        self._enrich_classifications()

        return self.dependency_graph

    def _load_dbt_manifest(self) -> None:
        """Load dbt manifest.json to get dependency information."""
        manifest_path = self.dbt_project_dir / "target" / "manifest.json"

        if not manifest_path.exists():
            # Generate manifest if it doesn't exist
            try:
                subprocess.run(
                    ["dbt", "compile"],
                    cwd=self.dbt_project_dir,
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Failed to compile dbt project for manifest: {e}")

        try:
            with open(manifest_path, 'r') as f:
                self._manifest_cache = json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load dbt manifest: {e}")

    def _build_dependency_graph(self) -> None:
        """Build dependency graph from dbt manifest."""
        if not self._manifest_cache:
            raise RuntimeError("Manifest not loaded")

        nodes = self._manifest_cache.get("nodes", {})

        for node_id, node_info in nodes.items():
            if not node_id.startswith("model."):
                continue

            model_name = node_info.get("name", "")
            if not model_name:
                continue

            # Get dependencies from the node
            depends_on = node_info.get("depends_on", {})
            node_dependencies = depends_on.get("nodes", [])

            for dep_id in node_dependencies:
                if dep_id.startswith("model."):
                    dep_model_name = self._manifest_cache["nodes"][dep_id]["name"]
                    self.dependency_graph.add_dependency(model_name, dep_model_name)

    def _enrich_classifications(self) -> None:
        """Enrich model classifications with actual dependency information."""
        for model_name in self.dependency_graph.nodes.keys():
            classification = self.classifier.classify_model(model_name)
            classification.dependencies = self.dependency_graph.get_dependencies(model_name)

    def identify_parallelization_opportunities(
        self,
        stage_models: List[str],
        max_parallelism: int = 4
    ) -> List[ParallelizationOpportunity]:
        """Identify opportunities for parallel execution within a stage."""
        opportunities = []

        # Group models by their parallel safety
        parallel_safe_models = []
        conditional_models = []
        sequential_models = []

        for model in stage_models:
            classification = self.classifier.classify_model(model)
            if classification.execution_type == ModelExecutionType.PARALLEL_SAFE:
                parallel_safe_models.append(model)
            elif classification.execution_type == ModelExecutionType.CONDITIONAL:
                conditional_models.append(model)
            else:
                sequential_models.append(model)

        # Create opportunities for parallel-safe models
        if len(parallel_safe_models) > 1:
            # Group by parallel group if available
            parallel_groups = self.classifier.get_parallel_groups(parallel_safe_models)

            for group_name, group_models in parallel_groups.items():
                if len(group_models) > 1:
                    # Check for interdependencies within group
                    independent_models = self._find_independent_models(
                        group_models, max_parallelism
                    )

                    if len(independent_models) > 1:
                        opportunities.append(ParallelizationOpportunity(
                            parallel_models=independent_models,
                            execution_group=group_name,
                            estimated_speedup=min(len(independent_models) * 0.7, 3.0),
                            resource_requirements={
                                "memory_mb": len(independent_models) * 256,
                                "cpu_threads": min(len(independent_models), max_parallelism)
                            },
                            safety_level="high"
                        ))

            # Handle ungrouped parallel-safe models
            ungrouped = [m for m in parallel_safe_models
                        if not self.classifier.classify_model(m).parallel_group]
            if len(ungrouped) > 1:
                independent_models = self._find_independent_models(ungrouped, max_parallelism)
                if len(independent_models) > 1:
                    opportunities.append(ParallelizationOpportunity(
                        parallel_models=independent_models,
                        execution_group="independent_parallel",
                        estimated_speedup=min(len(independent_models) * 0.6, 2.5),
                        resource_requirements={
                            "memory_mb": len(independent_models) * 512,
                            "cpu_threads": min(len(independent_models), max_parallelism)
                        },
                        safety_level="high"
                    ))

        # Analyze conditional models for potential parallelization
        if len(conditional_models) > 1:
            safe_conditional = self._analyze_conditional_parallelization(conditional_models)
            if len(safe_conditional) > 1:
                opportunities.append(ParallelizationOpportunity(
                    parallel_models=safe_conditional,
                    execution_group="conditional_parallel",
                    estimated_speedup=min(len(safe_conditional) * 0.4, 2.0),
                    resource_requirements={
                        "memory_mb": len(safe_conditional) * 768,
                        "cpu_threads": min(len(safe_conditional), max_parallelism // 2)
                    },
                    safety_level="medium"
                ))

        return opportunities

    def _find_independent_models(
        self,
        models: List[str],
        max_parallel: int
    ) -> List[str]:
        """Find models that can run independently in parallel."""
        if len(models) <= 1:
            return models

        # Create dependency subgraph
        model_set = set(models)
        independent = []

        for model in models:
            # Check if this model depends on any other model in the set
            deps = self.dependency_graph.get_dependencies(model)
            internal_deps = deps.intersection(model_set)

            # Also check if any other model depends on this one
            dependents = self.dependency_graph.get_dependents(model)
            internal_dependents = dependents.intersection(model_set)

            if not internal_deps and not internal_dependents:
                independent.append(model)
            elif not internal_deps:  # Only has dependents, could be first in parallel group
                independent.append(model)

        # Limit to max_parallel to avoid resource exhaustion
        return independent[:max_parallel]

    def _analyze_conditional_parallelization(self, models: List[str]) -> List[str]:
        """Analyze conditional models for safe parallelization."""
        safe_models = []

        for model in models:
            classification = self.classifier.classify_model(model)

            # Use heuristics to determine safety
            if self._is_conditionally_safe(model, classification):
                safe_models.append(model)

        # Remove models with interdependencies
        return self._find_independent_models(safe_models, len(safe_models))

    def _is_conditionally_safe(self, model: str, classification: ModelClassification) -> bool:
        """Determine if a conditional model is safe for parallelization."""
        # Models that only read from staging/config tables are generally safe
        deps = self.dependency_graph.get_dependencies(model)

        unsafe_patterns = {
            "accumulator", "state", "snapshot", "previous_year",
            "fct_yearly_events", "fct_workforce_snapshot"
        }

        for dep in deps:
            if any(pattern in dep.lower() for pattern in unsafe_patterns):
                return False

        # Check if model name suggests independent operation
        safe_patterns = {
            "hazard", "calculation", "eligibility", "determination",
            "validation", "audit", "monitoring"
        }

        return any(pattern in model.lower() for pattern in safe_patterns)

    def create_execution_plan(
        self,
        stage_models: List[str],
        max_parallelism: int = 4,
        enable_conditional_parallelization: bool = False
    ) -> Dict[str, Any]:
        """Create a detailed execution plan for a stage."""
        opportunities = self.identify_parallelization_opportunities(
            stage_models, max_parallelism
        )

        # Filter opportunities by safety level if needed
        if not enable_conditional_parallelization:
            opportunities = [op for op in opportunities if op.safety_level == "high"]

        # Create execution phases
        remaining_models = set(stage_models)
        execution_phases = []

        # Add parallel phases
        for opportunity in opportunities:
            if all(model in remaining_models for model in opportunity.parallel_models):
                execution_phases.append({
                    "type": "parallel",
                    "models": opportunity.parallel_models,
                    "group": opportunity.execution_group,
                    "estimated_speedup": opportunity.estimated_speedup,
                    "safety_level": opportunity.safety_level,
                    "resource_requirements": opportunity.resource_requirements
                })

                for model in opportunity.parallel_models:
                    remaining_models.remove(model)

        # Add sequential phase for remaining models
        if remaining_models:
            # Sort remaining models topologically
            remaining_list = list(remaining_models)
            try:
                sorted_remaining = self.dependency_graph.topological_sort(remaining_list)
            except ValueError:
                # Fallback to original order if circular dependencies
                sorted_remaining = remaining_list

            execution_phases.append({
                "type": "sequential",
                "models": sorted_remaining,
                "reason": "Sequential execution required for data integrity"
            })

        return {
            "total_models": len(stage_models),
            "parallelizable_models": sum(
                len(op.parallel_models) for op in opportunities
            ),
            "estimated_total_speedup": max(
                [op.estimated_speedup for op in opportunities] + [1.0]
            ),
            "execution_phases": execution_phases,
            "resource_requirements": {
                "peak_memory_mb": max(
                    [op.resource_requirements.get("memory_mb", 0) for op in opportunities] + [256]
                ),
                "peak_cpu_threads": max(
                    [op.resource_requirements.get("cpu_threads", 1) for op in opportunities] + [1]
                )
            }
        }

    def validate_execution_safety(self, parallel_models: List[str]) -> Dict[str, Any]:
        """Validate that a set of models can safely execute in parallel."""
        issues = []
        warnings = []

        for i, model_a in enumerate(parallel_models):
            for model_b in parallel_models[i+1:]:
                if not self.classifier.can_run_in_parallel(model_a, model_b):
                    issues.append(f"Models {model_a} and {model_b} cannot run in parallel")

                # Check for dependency conflicts
                if model_a in self.dependency_graph.get_dependencies(model_b):
                    issues.append(f"{model_b} depends on {model_a}")
                if model_b in self.dependency_graph.get_dependencies(model_a):
                    issues.append(f"{model_a} depends on {model_b}")

        # Check for resource conflicts
        memory_intensive_count = sum(
            1 for model in parallel_models
            if self.classifier.classify_model(model).memory_intensive
        )

        if memory_intensive_count > 2:
            warnings.append(f"{memory_intensive_count} memory-intensive models may cause resource contention")

        return {
            "safe": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "safety_score": max(0, 100 - len(issues) * 25 - len(warnings) * 5)
        }

    def export_dependency_analysis(self) -> Dict[str, Any]:
        """Export comprehensive dependency analysis."""
        return {
            "dependency_graph": {
                "nodes": {model: list(deps) for model, deps in self.dependency_graph.nodes.items()},
                "reverse_nodes": {model: list(deps) for model, deps in self.dependency_graph.reverse_nodes.items()}
            },
            "model_classifications": self.classifier.export_classification_report(),
            "total_models": len(self.dependency_graph.nodes),
            "parallelization_summary": {
                "parallel_safe": len(self.classifier.get_parallel_safe_models(list(self.dependency_graph.nodes.keys()))),
                "sequential_required": len(self.classifier.get_sequential_models(list(self.dependency_graph.nodes.keys()))),
                "conditional": len([
                    m for m in self.dependency_graph.nodes.keys()
                    if self.classifier.classify_model(m).execution_type == ModelExecutionType.CONDITIONAL
                ])
            }
        }
