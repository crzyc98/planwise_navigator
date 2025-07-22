# Smart Command Hook System Configuration Guide

This guide explains how to set up the smart command hook system to eliminate trial-and-error command execution in Claude Code.

## Overview

The smart hook system prevents common command execution issues by:

1. **Environment Validation**: Checking project structure and prerequisites before execution
2. **Automatic Path Setup**: Setting correct working directories for dbt, dagster, etc.
3. **Virtual Environment Management**: Automatically activating venv when needed
4. **Clear Error Messages**: Providing setup instructions when environment is invalid
5. **Intelligent Command Classification**: Routing commands to proper execution contexts

## Components

### 1. Smart Environment Detection (`smart_environment.py`)
- Detects project root by looking for key indicator files
- Validates virtual environment setup
- Checks for required tools (dbt, dagster, streamlit)
- Provides setup instructions for missing components

### 2. Smart Command Wrapper (`smart_command_wrapper.py`)
- Classifies commands by type (dbt, dagster, streamlit, python, system)
- Sets up proper execution context (working directory, environment variables)
- Handles virtual environment activation
- Can be used standalone or as part of hook system

### 3. Claude Code Hook Script (`claude_code_hook.sh`)
- Intercepts bash commands before execution
- Uses smart wrapper for commands that need special handling
- Provides warnings for problematic patterns
- Blocks execution if environment validation fails

## Installation and Setup

### Step 1: Verify Components

Ensure all components are in place and executable:

```bash
# Check that files exist and are executable
ls -la scripts/smart_environment.py
ls -la scripts/smart_command_wrapper.py
ls -la scripts/claude_code_hook.sh

# Test environment detection
python3 scripts/smart_environment.py --summary

# Test command wrapper
python3 scripts/smart_command_wrapper.py --validate
```

### Step 2: Configure Claude Code Hooks

Add the hook configuration to your Claude Code settings. Create or modify `.claude/settings.local.json`:

```json
{
  "hooks": {
    "user-prompt-submit-hook": [
      "echo 'Starting command execution...' >> /Users/nicholasamaral/planwise_navigator/claude_code_hook.log"
    ],
    "before-tool-call-hook": [
      "/Users/nicholasamaral/planwise_navigator/scripts/claude_code_hook.sh \"${TOOL_CALL_PARAMETERS}\""
    ]
  },
  "permissions": {
    "allow": [
      "Bash(*)"
    ]
  }
}
```

### Step 3: Configure Environment Variables (Optional)

Set environment variables to customize hook behavior:

```bash
# Enable verbose logging
export CLAUDE_HOOK_VERBOSE=true

# Set custom project root (if needed)
export CLAUDE_HOOK_PROJECT_ROOT="/path/to/your/project"
```

### Step 4: Test the Hook System

Test with commands that commonly cause issues:

```bash
# These should now work automatically:
dbt run
dagster dev
streamlit run main.py
cd dbt && dbt run  # This pattern often fails without hooks
```

## Hook Configuration Options

### Basic Hook Setup

Minimal configuration to intercept bash commands:

```json
{
  "hooks": {
    "before-tool-call-hook": [
      "/Users/nicholasamaral/planwise_navigator/scripts/claude_code_hook.sh \"$BASH_COMMAND\""
    ]
  }
}
```

### Advanced Hook Setup

Complete configuration with logging and multiple hook points:

```json
{
  "hooks": {
    "user-prompt-submit-hook": [
      "echo '[Hook] User prompt submitted' >> /Users/nicholasamaral/planwise_navigator/claude_code_hook.log"
    ],
    "before-tool-call-hook": [
      "echo '[Hook] Before tool call: $TOOL_NAME' >> /Users/nicholasamaral/planwise_navigator/claude_code_hook.log",
      "/Users/nicholasamaral/planwise_navigator/scripts/claude_code_hook.sh \"$TOOL_CALL_PARAMETERS\""
    ],
    "after-tool-call-hook": [
      "echo '[Hook] After tool call completed' >> /Users/nicholasamaral/planwise_navigator/claude_code_hook.log"
    ]
  },
  "permissions": {
    "allow": [
      "Bash(*)",
      "Task(*)",
      "Read(*)",
      "Write(*)"
    ]
  }
}
```

## Command Interception Rules

The hook system intercepts commands matching these patterns:

### Always Intercepted
- `dbt *` - dbt commands need proper working directory
- `dagster *` - dagster commands need environment setup
- `streamlit *` - streamlit commands need venv activation
- `python *.py` - Python scripts need venv and path setup
- `pytest *` - Test commands need venv activation

### Conditionally Intercepted
- Commands with `venv/bin/` paths - replaced with smart activation
- `cd ... && dbt ...` patterns - replaced with proper execution context
- `source venv/bin/activate` - handled automatically

### Never Intercepted
- Simple system commands: `ls`, `cat`, `echo`, `git`
- Commands already using absolute paths correctly

## Troubleshooting

### Hook Not Working

1. **Check hook script permissions**:
   ```bash
   ls -la scripts/claude_code_hook.sh
   # Should show: -rwxr-xr-x (executable)
   ```

2. **Check hook configuration**:
   ```bash
   cat .claude/settings.local.json | grep -A 5 hooks
   ```

3. **Check hook logs**:
   ```bash
   tail -f claude_code_hook.log
   ```

### Environment Validation Failures

1. **Check environment status**:
   ```bash
   python3 scripts/smart_command_wrapper.py --validate --verbose
   ```

2. **Get setup instructions**:
   ```bash
   python3 scripts/smart_command_wrapper.py --help-setup
   ```

3. **Test specific command**:
   ```bash
   python3 scripts/smart_command_wrapper.py --dry-run "dbt run"
   ```

### Common Issues and Fixes

#### Issue: "Virtual environment not found"
**Fix**:
```bash
cd /Users/nicholasamaral/planwise_navigator
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Issue: "dbt directory not found"
**Fix**: Check that you're in the correct project directory with a `dbt/` subdirectory

#### Issue: "Command not found in venv"
**Fix**:
```bash
source venv/bin/activate
pip install dbt-core dbt-duckdb dagster streamlit
```

#### Issue: Hook logs show "Not in PlanWise Navigator project directory"
**Fix**: Ensure Claude Code is running from the project root directory

## Manual Usage (Without Hooks)

You can use the smart command wrapper manually:

```bash
# Direct execution
python3 scripts/smart_command_wrapper.py "dbt run"

# With verbose output
python3 scripts/smart_command_wrapper.py "dagster dev" --verbose

# Dry run to see what would be executed
python3 scripts/smart_command_wrapper.py "streamlit run main.py" --dry-run

# Environment validation
python3 scripts/smart_command_wrapper.py --validate
```

## Benefits

### Before Hook System
```bash
# Trial-and-error pattern (what Claude Code used to do):
$ cd dbt && dbt run
bash: cd: dbt: No such file or directory

$ source venv/bin/activate && cd dbt && dbt run
bash: venv/bin/activate: No such file or directory

$ ./venv/bin/dbt run
bash: ./venv/bin/dbt: No such file or directory

$ /Users/nicholasamaral/planwise_navigator/venv/bin/python -m dbt run
# Finally works, but took 4 attempts
```

### After Hook System
```bash
# Single attempt, works immediately:
$ dbt run
✅ Command completed successfully (exit code: 0)
   Duration: 2.34s

# Hook automatically:
# 1. Detected command type: dbt
# 2. Set working directory: /Users/nicholasamaral/planwise_navigator/dbt
# 3. Activated virtual environment
# 4. Set environment variables
# 5. Executed: /Users/nicholasamaral/planwise_navigator/venv/bin/dbt run
```

## Customization

### Adding New Command Patterns

Edit `smart_environment.py` to add new command mappings:

```python
self.command_mappings = {
    CommandType.CUSTOM: {
        "commands": ["my-custom-tool"],
        "working_dir": "project_root",
        "requires_venv": True,
        "environment_vars": {"CUSTOM_VAR": "value"}
    }
}
```

### Modifying Interception Rules

Edit `claude_code_hook.sh` to change which commands are intercepted:

```bash
# Add new patterns to intercept_patterns array
intercept_patterns=(
    "^dbt "
    "^my-tool "  # Add your pattern here
    "^custom-command "
)
```

## Security Considerations

- Hook scripts run with your user permissions
- Validate all paths and commands before execution
- Consider using restricted permissions in `.claude/settings.local.json`
- Monitor hook logs for unexpected behavior

## Performance Impact

- Environment validation adds ~50-100ms per command
- Smart wrapper execution adds ~10-20ms overhead
- Benefits far outweigh costs by eliminating failed command attempts

## Support and Maintenance

- Hook logs: `claude_code_hook.log`
- Environment status: `python3 scripts/smart_command_wrapper.py --validate`
- Component testing: Run the test suite in the next section
