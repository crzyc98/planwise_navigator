# Story S038-02: dbt Command Orchestration

**Epic**: E038 - PlanAlign Orchestrator Refactoring & Modularization
**Story Points**: 3
**Priority**: High
**Status**: 🟠 In Progress
**Dependencies**: S038-01 (Core Infrastructure Setup)
**Assignee**: Development Team

---

## 🎯 **Goal**

Extract and enhance dbt command execution logic into a dedicated, robust module that provides clean interfaces for all dbt operations with improved error handling and progress reporting.

## 📋 **User Story**

As a **developer** working with dbt models in the simulation pipeline,
I want **a clean, reliable interface for executing dbt commands with enhanced error handling**
So that **I can easily run dbt operations with better visibility and recovery from failures**.

## 🛠 **Technical Tasks**

### **Task 1: Create `DbtRunner` Class**
- Design clean interface for dbt command execution
- Support for streaming output during long-running operations
- Command templating and validation
- Enhanced error classification and reporting

### **Task 2: Implement Command Orchestration**
- Migrate `run_dbt_command()` functionality with improvements
- Add retry logic for transient failures
- Support for parallel model execution
- Progress reporting and status updates

### **Task 3: Error Handling & Recovery**
- Classify different types of dbt errors (compilation, execution, data quality)
- Provide actionable error messages with suggested fixes
- Implement exponential backoff for retry logic
- Add detailed logging for debugging

## ✅ **Acceptance Criteria**

### **Functional Requirements**
- ✅ `DbtRunner` class provides clean interface for dbt operations
- ✅ Support for streaming output and progress reporting
- ✅ Retry logic for transient failures with exponential backoff
- ✅ Comprehensive error classification and reporting

### **Performance Requirements**
- ✅ No performance regression compared to existing implementation
- ✅ Support for parallel execution when appropriate
- ✅ Efficient handling of large model sets

### **Quality Requirements**
- ✅ 95%+ test coverage with comprehensive error scenario testing
- ✅ Clean separation between command building and execution
- ✅ Thread-safe implementation for concurrent usage

## 🧪 **Testing Strategy**

### **Unit Tests**
```python
# test_dbt_runner.py
def test_dbt_runner_successful_command_execution()
def test_dbt_runner_streaming_output_capture()
def test_retry_logic_transient_failures()
def test_error_classification_compilation_vs_execution()
def test_command_templating_variable_injection()
def test_parallel_model_execution()
```

### **Integration Tests**
- Execute real dbt commands against test project
- Validate streaming output with actual long-running models
- Test retry behavior with simulated network failures
- Verify error handling with intentionally broken models

## 📊 **Definition of Done**

- [x] `dbt_runner.py` module created with `DbtRunner` class
- [ ] All dbt command functionality migrated from existing code
- [x] Streaming output and progress reporting implemented
- [x] Retry logic with exponential backoff working
- [x] Comprehensive error handling and classification
- [ ] Unit and integration tests achieve 95%+ coverage
- [ ] Performance benchmarks show no regression
- [x] Documentation complete with usage examples

### 🔧 Implementation Progress

- Added `planalign_orchestrator/dbt_runner.py` implementing:
  - `DbtRunner` with streaming output, retry/backoff, and parallel model execution
  - Error classes and `classify_dbt_error`
  - `retry_with_backoff` helper
- Added tests in `tests/test_dbt_runner.py` for:
  - Successful execution (using `python` as stand-in)
  - Streaming output capture via callback
  - Retry/backoff on transient failures
  - Error classification logic
  - Command templating (`--vars` payload)
  - Parallel execution fan-out

## 📘 **Usage Examples**

```python
from planalign_orchestrator.dbt_runner import DbtRunner

runner = DbtRunner()  # working_dir='dbt', threads=4

# Run a selection with vars and simulation year
res = runner.execute_command(
    ["run", "--select", "int_*"],
    simulation_year=2026,
    dbt_vars={"cola_rate": 0.01},
)
assert res.success, res.stdout[-500:]

# Stream output and print each line as it arrives
res = runner.execute_command(["run"], stream_output=True, on_line=lambda l: print(f"> {l}"))

# Run multiple models in parallel
results = runner.run_models(["int_model_a", "int_model_b"], parallel=True)
assert all(r.success for r in results)
```

## 🔗 **Dependencies**

### **Upstream Dependencies**
- **S038-01**: Requires `utils.py` for logging and timing utilities

### **Downstream Dependencies**
- **S038-06** (Pipeline Orchestration): Will use `DbtRunner` for model execution
- **All other stories**: Most modules will execute dbt commands through this interface

## 📝 **Implementation Notes**

### **DbtRunner Interface Design**
```python
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path

@dataclass
class DbtResult:
    success: bool
    stdout: str
    stderr: str
    execution_time: float
    return_code: int
    command: List[str]

class DbtRunner:
    def __init__(self, working_dir: Path = Path("dbt"), threads: int = 4):
        self.working_dir = working_dir
        self.threads = threads

    def execute_command(
        self,
        command_args: List[str],
        description: str = "Running dbt command",
        simulation_year: Optional[int] = None,
        dbt_vars: Optional[Dict[str, Any]] = None,
        stream_output: bool = True
    ) -> DbtResult:
        """Execute a dbt command with enhanced error handling."""

    def run_model(
        self,
        model_name: str,
        **kwargs
    ) -> DbtResult:
        """Run a specific dbt model with common options."""

    def run_models(
        self,
        models: List[str],
        parallel: bool = False,
        **kwargs
    ) -> List[DbtResult]:
        """Run multiple models with optional parallel execution."""
```

### **Error Classification Strategy**
```python
class DbtError(Exception):
    """Base exception for dbt-related errors."""

class DbtCompilationError(DbtError):
    """Error during dbt compilation phase."""

class DbtExecutionError(DbtError):
    """Error during dbt execution phase."""

class DbtDataQualityError(DbtError):
    """Error due to data quality test failures."""

def classify_dbt_error(stdout: str, stderr: str, return_code: int) -> DbtError:
    """Classify dbt error based on output and return code."""
    if "Compilation Error" in stderr:
        return DbtCompilationError("Model compilation failed")
    elif "Database Error" in stderr:
        return DbtExecutionError("Database execution failed")
    elif "test failed" in stdout.lower():
        return DbtDataQualityError("Data quality tests failed")
    else:
        return DbtError("Unknown dbt error occurred")
```

### **Retry Logic Implementation**
```python
import time
import random
from typing import Callable

def retry_with_backoff(
    func: Callable,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0
) -> Any:
    """Execute function with exponential backoff retry logic."""

    for attempt in range(max_attempts):
        try:
            return func()
        except (DbtExecutionError, ConnectionError) as e:
            if attempt == max_attempts - 1:
                raise e

            delay = min(base_delay * (backoff_factor ** attempt), max_delay)
            jitter = random.uniform(0, 0.1) * delay  # Add jitter
            time.sleep(delay + jitter)

            print(f"Attempt {attempt + 1} failed, retrying in {delay:.1f}s...")
```

### **Streaming Output Support**
```python
import subprocess
from typing import Generator

def execute_with_streaming(
    command: List[str],
    working_dir: Path
) -> Generator[str, None, DbtResult]:
    """Execute command with real-time output streaming."""

    process = subprocess.Popen(
        command,
        cwd=working_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    stdout_lines = []
    for line in iter(process.stdout.readline, ''):
        stdout_lines.append(line)
        yield line.rstrip()  # Stream to caller

    process.wait()

    return DbtResult(
        success=process.returncode == 0,
        stdout=''.join(stdout_lines),
        stderr="",  # Combined with stdout
        execution_time=0,  # Would be tracked separately
        return_code=process.returncode,
        command=command
    )
```

---

**This story provides a robust, maintainable foundation for all dbt operations in the orchestrator, with enhanced error handling and user experience improvements.**
