# Story S038-07: Enhanced CLI Interface

**Epic**: E038 - Navigator Orchestrator Refactoring & Modularization
**Story Points**: 2
**Priority**: Medium
**Status**: 🟠 In Progress
**Dependencies**: S038-01 (Core Infrastructure), S038-06 (Pipeline Orchestration)
**Assignee**: Development Team

---

## 🎯 **Goal**

Create a modern, user-friendly CLI interface that provides intuitive access to all orchestrator functionality with comprehensive help, validation, and progress reporting.

## 📋 **User Story**

As a **business analyst** using the PlanWise Navigator system,
I want **an intuitive command-line interface with clear options and helpful feedback**
So that **I can easily run simulations, check status, and get help without needing to understand implementation details**.

## 🛠 **Technical Tasks**

### **Task 1: Create Modern CLI Framework**
- Design CLI using `click` or `argparse` with subcommands
- Implement clear command structure with logical grouping
- Add comprehensive help text and examples
- Implement input validation with helpful error messages

### **Task 2: Command Implementation**
- Migrate existing CLI functionality from `run_multi_year.py`
- Add new commands for checkpoint management and status checking
- Implement configuration validation and dry-run capabilities
- Add interactive mode for guided simulation setup

### **Task 3: User Experience Enhancement**
- Add progress bars and status indicators for long-running operations
- Implement colored output for better readability
- Add confirmation prompts for destructive operations
- Create verbose and quiet modes for different use cases

## ✅ **Acceptance Criteria**

### **Functional Requirements**
- ✅ CLI provides access to all orchestrator functionality
- ✅ Clear subcommand structure with logical organization
- ✅ Comprehensive help text with usage examples
- ✅ Input validation with actionable error messages

### **Quality Requirements**
- ✅ 90%+ test coverage for CLI functionality
- ✅ Consistent user experience across all commands
- ✅ Fast command startup and response times
- ✅ Clear progress indication for long-running operations

### **Usability Requirements**
- ✅ Intuitive command names and argument structure
- ✅ Helpful error messages with suggested fixes
- ✅ Interactive mode for new users
- ✅ Both verbose and quiet output modes

## 🧪 **Testing Strategy**

### **Unit Tests**
```python
# test_cli.py
def test_cli_command_parsing_valid_arguments()
def test_cli_validation_invalid_configuration()
def test_cli_help_text_comprehensive()
def test_cli_interactive_mode_guided_setup()
def test_cli_progress_reporting_accuracy()
def test_cli_error_handling_user_friendly()
```

### **Integration Tests**
- Execute CLI commands against real simulation scenarios
- Test interactive mode with user input simulation
- Validate CLI integration with pipeline orchestrator
- Test CLI behavior with various configuration files

## 📊 **Definition of Done**

- [x] `cli.py` module created with modern CLI framework (argparse)
- [x] Core functionality accessible (run, validate, checkpoint)
- [ ] New commands for detailed status and interactive mode
- [ ] Unit tests achieve 90%+ coverage
- [ ] User experience validated with stakeholders
- [x] Documentation complete with command examples
- [x] Help text basic and accurate

### 🔧 Implementation Progress

- Added `navigator_orchestrator/cli.py` with subcommands:
  - `run`: start multi-year simulation; supports `--years`, `--resume`, `--dry-run`, `--threads`, `--fail-on-validation-error`
  - `validate`: check configuration parsing and provide tips
  - `checkpoint`: display last checkpoint info
- Added executable entry `navigator_orchestrator/__main__.py` to allow `python -m navigator_orchestrator ...`.
- Added tests in `tests/test_cli.py` covering config validation, dry-run execution, and checkpoint listing.

## 🔗 **Dependencies**

### **Upstream Dependencies**
- **S038-01**: Requires configuration and utilities modules
- **S038-06**: Uses pipeline orchestrator for command execution

### **Downstream Dependencies**
- **S038-08** (Integration): Will validate CLI functionality

## 📝 **Implementation Notes**

### **CLI Structure Design**
```python
import click
from typing import Optional, List
from pathlib import Path

@click.group()
@click.version_option()
@click.option('--config', '-c',
              type=click.Path(exists=True),
              help='Path to configuration file')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.option('--quiet', '-q', is_flag=True, help='Suppress non-essential output')
@click.pass_context
def navigator_cli(ctx, config, verbose, quiet):
    """PlanWise Navigator Orchestrator CLI

    A comprehensive toolkit for workforce simulation and analysis.

    Examples:
        navigator run --years 2025-2027
        navigator status --year 2025
        navigator validate --config my_config.yaml
    """
    ctx.ensure_object(dict)
    ctx.obj['config_path'] = config
    ctx.obj['verbose'] = verbose
    ctx.obj['quiet'] = quiet

@navigator_cli.command()
@click.option('--start-year', type=int, help='Simulation start year')
@click.option('--end-year', type=int, help='Simulation end year')
@click.option('--years', help='Year range (e.g., 2025-2027)')
@click.option('--resume', is_flag=True, help='Resume from last checkpoint')
@click.option('--dry-run', is_flag=True, help='Validate configuration without running')
@click.pass_context
def run(ctx, start_year, end_year, years, resume, dry_run):
    """Run multi-year workforce simulation.

    Examples:
        navigator run --years 2025-2027
        navigator run --start-year 2025 --end-year 2027
        navigator run --resume  # Continue from last checkpoint
    """

    config_path = ctx.obj.get('config_path')
    verbose = ctx.obj.get('verbose', False)

    if years:
        start_year, end_year = parse_year_range(years)

    if dry_run:
        click.echo("🔍 Validating configuration...")
        validate_simulation_config(config_path, start_year, end_year)
        click.echo("✅ Configuration is valid")
        return

    orchestrator = setup_orchestrator(config_path, verbose)

    try:
        with click.progressbar(
            label='Running simulation',
            show_eta=True,
            show_percent=True
        ) as bar:
            result = orchestrator.execute_multi_year_simulation(
                start_year=start_year,
                end_year=end_year,
                resume_from_checkpoint=resume,
                progress_callback=lambda p: bar.update(p.stages_completed - bar.pos)
            )

        click.echo(f"✅ Simulation completed successfully")
        if verbose:
            display_simulation_summary(result)

    except Exception as e:
        click.echo(f"❌ Simulation failed: {e}", err=True)
        raise click.Abort()
```

### **Status and Monitoring Commands**
```python
@navigator_cli.command()
@click.option('--year', type=int, help='Check status for specific year')
@click.option('--all-years', is_flag=True, help='Show status for all years')
@click.option('--format', type=click.Choice(['table', 'json']),
              default='table', help='Output format')
@click.pass_context
def status(ctx, year, all_years, format):
    """Check simulation status and progress.

    Examples:
        navigator status --year 2025
        navigator status --all-years
        navigator status --format json
    """

    orchestrator = setup_orchestrator(ctx.obj.get('config_path'))

    if year:
        status_info = orchestrator.get_year_status(year)
        display_year_status(status_info, format)
    elif all_years:
        status_info = orchestrator.get_multi_year_status()
        display_multi_year_status(status_info, format)
    else:
        # Show general pipeline status
        status_info = orchestrator.get_pipeline_status()
        display_pipeline_status(status_info, format)

@navigator_cli.command()
@click.option('--list', 'list_checkpoints', is_flag=True,
              help='List available checkpoints')
@click.option('--year', type=int, help='Show checkpoint for specific year')
@click.option('--cleanup', is_flag=True, help='Remove old checkpoints')
@click.pass_context
def checkpoint(ctx, list_checkpoints, year, cleanup):
    """Manage simulation checkpoints.

    Examples:
        navigator checkpoint --list
        navigator checkpoint --year 2025
        navigator checkpoint --cleanup
    """

    orchestrator = setup_orchestrator(ctx.obj.get('config_path'))

    if list_checkpoints:
        checkpoints = orchestrator.list_checkpoints()
        display_checkpoints_table(checkpoints)
    elif year:
        checkpoint_info = orchestrator.get_checkpoint_info(year)
        display_checkpoint_details(checkpoint_info)
    elif cleanup:
        if click.confirm('Remove old checkpoints?'):
            removed_count = orchestrator.cleanup_old_checkpoints()
            click.echo(f"✅ Removed {removed_count} old checkpoints")
```

## 📘 **Usage Examples**

```bash
# Validate configuration
python -m navigator_orchestrator validate -c config/simulation_config.yaml

# Run a dry-run (echo dbt commands), verbose
python -m navigator_orchestrator run -c config/simulation_config.yaml --dry-run -v

# Run for a specific range and resume if checkpoints exist
python -m navigator_orchestrator run --years 2025-2027 --resume

# Show last checkpoint
python -m navigator_orchestrator checkpoint -c config/simulation_config.yaml
```

### **Validation and Configuration Commands**
```python
@navigator_cli.command()
@click.option('--config', type=click.Path(exists=True),
              help='Configuration file to validate')
@click.option('--schema', is_flag=True, help='Show configuration schema')
@click.option('--fix', is_flag=True, help='Attempt to fix common issues')
@click.pass_context
def validate(ctx, config, schema, fix):
    """Validate configuration and system setup.

    Examples:
        navigator validate
        navigator validate --config my_config.yaml
        navigator validate --schema
    """

    if schema:
        display_configuration_schema()
        return

    config_path = config or ctx.obj.get('config_path') or 'config/simulation_config.yaml'

    try:
        validation_results = validate_full_configuration(config_path)

        if validation_results.is_valid:
            click.echo("✅ Configuration is valid")
        else:
            click.echo("❌ Configuration validation failed:", err=True)
            for error in validation_results.errors:
                click.echo(f"   • {error}", err=True)

            if fix:
                if click.confirm('Attempt to fix issues automatically?'):
                    fix_results = auto_fix_configuration(config_path, validation_results)
                    display_fix_results(fix_results)

    except Exception as e:
        click.echo(f"❌ Validation error: {e}", err=True)
        raise click.Abort()

@navigator_cli.command()
@click.option('--interactive', '-i', is_flag=True, help='Interactive setup mode')
@click.option('--template', type=click.Choice(['basic', 'advanced', 'custom']),
              default='basic', help='Configuration template')
@click.argument('output_path', type=click.Path())
def init(interactive, template, output_path):
    """Initialize a new configuration file.

    Examples:
        navigator init config/my_simulation.yaml
        navigator init --interactive config/my_simulation.yaml
        navigator init --template advanced config/my_simulation.yaml
    """

    if interactive:
        config_data = interactive_config_setup()
    else:
        config_data = load_config_template(template)

    try:
        save_configuration(config_data, output_path)
        click.echo(f"✅ Configuration created: {output_path}")

        if click.confirm('Validate the new configuration?'):
            validate_full_configuration(output_path)

    except Exception as e:
        click.echo(f"❌ Failed to create configuration: {e}", err=True)
        raise click.Abort()
```

## 📘 **Command Reference**

- `run`
  - `--config, -c`: Path to YAML config (default `config/simulation_config.yaml`).
  - `--database`: Path to DuckDB file (default `simulation.duckdb`).
  - `--start-year` / `--end-year` or `--years 2025-2027`.
  - `--resume`: Resume from last checkpoint.
  - `--dry-run`: Use `echo` to simulate dbt calls.
  - `--threads N`: dbt threads for model runs.
  - `--fail-on-validation-error`: Stop on ERROR-level validation failures.
  - `-v, --verbose`: Print summary after completion.

- `validate`
  - `--config, -c`: Path to YAML config.
  - Prints parse status and tips for missing identifiers.

- `checkpoint`
  - `--config, -c`: Config path (for consistency).
  - `--database`: DuckDB file (for environment parity).
  - Displays last available checkpoint (year, stage, timestamp).

### Examples

```bash
python -m navigator_orchestrator validate -c config/simulation_config.yaml
python -m navigator_orchestrator run --years 2025-2027 --resume -v
python -m navigator_orchestrator run -c config/simulation_config.yaml --dry-run --threads 8
python -m navigator_orchestrator checkpoint -c config/simulation_config.yaml
```

### **Interactive Mode Implementation**
```python
def interactive_config_setup() -> Dict[str, Any]:
    """Guide user through interactive configuration setup."""

    click.echo("🚀 PlanWise Navigator Configuration Setup")
    click.echo("=" * 50)

    # Basic simulation settings
    scenario_id = click.prompt(
        'Scenario ID',
        default='default_scenario',
        help='Unique identifier for this simulation scenario'
    )

    plan_design_id = click.prompt(
        'Plan Design ID',
        default='standard_401k',
        help='Retirement plan design identifier'
    )

    start_year = click.prompt(
        'Simulation start year',
        type=int,
        default=2025
    )

    end_year = click.prompt(
        'Simulation end year',
        type=int,
        default=start_year + 2
    )

    # Advanced settings with defaults
    if click.confirm('Configure advanced settings?', default=False):
        target_growth_rate = click.prompt(
            'Target annual growth rate',
            type=float,
            default=0.03
        )

        termination_rate = click.prompt(
            'Base termination rate',
            type=float,
            default=0.12
        )

        new_hire_termination_rate = click.prompt(
            'New hire termination rate',
            type=float,
            default=0.25
        )
    else:
        target_growth_rate = 0.03
        termination_rate = 0.12
        new_hire_termination_rate = 0.25

    return {
        'scenario_id': scenario_id,
        'plan_design_id': plan_design_id,
        'simulation': {
            'start_year': start_year,
            'end_year': end_year,
            'random_seed': 42,
            'target_growth_rate': target_growth_rate
        },
        'termination_rates': {
            'base_rate': termination_rate,
            'new_hire_rate': new_hire_termination_rate
        }
    }
```

### **Output Formatting and Display**
```python
def display_simulation_summary(result: MultiYearSummary):
    """Display formatted simulation results."""

    click.echo("\n📊 SIMULATION SUMMARY")
    click.echo("=" * 50)

    click.echo(f"Years simulated: {result.start_year} - {result.end_year}")
    click.echo(f"Total workforce growth: {result.growth_analysis['total_growth_pct']:.1f}%")
    click.echo(f"CAGR: {result.growth_analysis['compound_annual_growth_rate']:.2f}%")

    # Workforce progression table
    click.echo("\n📈 Year-over-Year Progression:")
    headers = ['Year', 'Active Employees', 'Participation Rate']
    rows = []

    for breakdown in result.workforce_progression:
        rows.append([
            breakdown.year,
            f"{breakdown.active_employees:,}",
            f"{breakdown.participation_rate:.1%}"
        ])

    display_table(headers, rows)

def display_table(headers: List[str], rows: List[List[str]]):
    """Display formatted table using click.echo."""

    # Calculate column widths
    col_widths = [len(header) for header in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    # Print header
    header_row = " | ".join(h.ljust(w) for h, w in zip(headers, col_widths))
    click.echo(header_row)
    click.echo("-" * len(header_row))

    # Print data rows
    for row in rows:
        data_row = " | ".join(str(cell).ljust(w) for cell, w in zip(row, col_widths))
        click.echo(data_row)
```

---

**This story provides a modern, user-friendly CLI that makes the orchestrator accessible to business users while maintaining full functionality for developers.**
