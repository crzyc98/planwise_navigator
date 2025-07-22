# Smart Command Hook System for Claude Code

This directory contains a comprehensive solution to eliminate trial-and-error command execution in Claude Code. The system prevents common issues by validating environment setup, setting correct working directories, and handling virtual environment activation automatically.

## Problem Solved

**Before**: Claude Code would repeatedly try failing command patterns:
```bash
$ cd dbt && dbt run
bash: cd: dbt: No such file or directory

$ source venv/bin/activate && cd dbt && dbt run
bash: venv/bin/activate: No such file or directory

$ ./venv/bin/dbt run
bash: ./venv/bin/dbt: No such file or directory

$ /Users/nicholasamaral/planwise_navigator/venv/bin/python -m dbt run
# Finally works, but took 4 attempts
```

**After**: Single attempt with smart environment handling:
```bash
$ dbt run
✅ Command completed successfully (exit code: 0)
   Duration: 2.34s
```

## Components

### 1. Smart Environment Detection (`smart_environment.py`)
Intelligent project structure detection and validation:
- **Project Root Detection**: Finds project root by looking for indicator files (CLAUDE.md, definitions.py, dbt/)
- **Virtual Environment Validation**: Checks venv setup and Python executable paths
- **Tool Availability**: Validates that required tools (dbt, dagster, streamlit) are installed
- **Command Classification**: Categorizes commands by type to determine execution requirements

### 2. Smart Command Wrapper (`smart_command_wrapper.py`)
Execution engine that handles environment setup automatically:
- **Command Resolution**: Maps commands to correct executables in virtual environment
- **Working Directory Management**: Sets proper working directory based on command type
- **Environment Variables**: Configures DAGSTER_HOME and other required variables
- **Error Prevention**: Validates environment before execution to prevent failures

### 3. Claude Code Hook Script (`claude_code_hook.sh`)
Integration layer that intercepts bash commands:
- **Command Interception**: Catches problematic command patterns before execution
- **Pattern Detection**: Identifies common trial-and-error patterns and fixes them
- **Logging**: Records hook activity for debugging and monitoring
- **Graceful Fallback**: Allows non-intercepted commands to execute normally

### 4. Configuration System
Complete setup guide and example configurations:
- **Hook Configuration**: Example settings for Claude Code integration
- **Environment Setup**: Automated environment validation and setup instructions
- **Testing Suite**: Comprehensive tests for all components

## Quick Start

1. **Verify Installation**:
   ```bash
   python3 scripts/smart_environment.py --summary
   python3 scripts/smart_command_wrapper.py --validate
   ```

2. **Test Individual Commands**:
   ```bash
   # Test without execution
   python3 scripts/smart_command_wrapper.py --dry-run "dbt run"

   # Execute with smart wrapper
   python3 scripts/smart_command_wrapper.py "dbt run"
   ```

3. **Configure Claude Code Hooks** (see `hook_configuration_guide.md`):
   ```json
   {
     "hooks": {
       "before-tool-call-hook": [
         "/Users/nicholasamaral/planwise_navigator/scripts/claude_code_hook.sh \"$TOOL_CALL_PARAMETERS\""
       ]
     }
   }
   ```

4. **Run Test Suite**:
   ```bash
   python3 scripts/test_hook_system.py --verbose
   ```

## Files Overview

| File | Purpose | Usage |
|------|---------|-------|
| `smart_environment.py` | Environment detection and validation | Standalone or imported |
| `smart_command_wrapper.py` | Command execution with smart setup | CLI tool or Python module |
| `claude_code_hook.sh` | Claude Code integration hook script | Called by Claude Code hooks |
| `test_hook_system.py` | Comprehensive test suite | Validation and testing |
| `hook_configuration_guide.md` | Setup and configuration documentation | Reference guide |
| `.claude/settings.example.json` | Example Claude Code settings | Configuration template |

## Command Type Handling

The system automatically handles these command categories:

### dbt Commands
- **Working Directory**: Automatically switches to `dbt/` subdirectory
- **Virtual Environment**: Uses `venv/bin/dbt` executable
- **Examples**: `dbt run`, `dbt test`, `dbt compile`

### Dagster Commands
- **Working Directory**: Project root directory
- **Environment Variables**: Sets `DAGSTER_HOME`
- **Virtual Environment**: Uses `venv/bin/dagster` executable
- **Examples**: `dagster dev`, `dagster asset materialize`

### Streamlit Commands
- **Working Directory**: Project root directory
- **Virtual Environment**: Uses `venv/bin/streamlit` executable
- **Examples**: `streamlit run main.py`

### Python Scripts
- **Working Directory**: Project root directory
- **Virtual Environment**: Uses `venv/bin/python` executable
- **Examples**: `python script.py`, `pytest tests/`

### System Commands
- **No Interception**: Commands like `git`, `ls`, `cat` execute normally
- **Working Directory**: Current directory maintained

## Performance

- **Environment validation**: ~50ms (cached after first run)
- **Command resolution**: ~10ms overhead
- **Total overhead**: ~60ms per command
- **Benefit**: Eliminates multiple failed attempts (saves seconds per command)

## Monitoring and Debugging

### Log Files
- **Hook Activity**: `claude_code_hook.log`
- **Command History**: Includes timestamps, commands, and results

### Debugging Commands
```bash
# Check environment status
python3 scripts/smart_command_wrapper.py --validate --verbose

# Analyze command without execution
python3 scripts/smart_command_wrapper.py --dry-run "your-command"

# View recent hook activity
tail -f claude_code_hook.log

# Run comprehensive tests
python3 scripts/test_hook_system.py --verbose --integration-test
```

### Common Issues and Solutions

**Environment validation failed**:
```bash
python3 scripts/smart_command_wrapper.py --help-setup
```

**Hook not intercepting commands**:
- Check hook script permissions: `ls -la scripts/claude_code_hook.sh`
- Verify Claude Code settings: `cat .claude/settings.local.json`
- Check logs: `tail claude_code_hook.log`

**Virtual environment issues**:
```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Benefits

### For Claude Code Users
- ✅ **Zero trial-and-error**: Commands work on first attempt
- ✅ **Automatic setup**: No manual environment configuration needed
- ✅ **Clear error messages**: Helpful setup instructions when needed
- ✅ **Transparent operation**: See exactly what commands are executed

### For Project Teams
- ✅ **Consistent environment**: Same execution context for all team members
- ✅ **Reduced support burden**: Fewer environment-related issues
- ✅ **Better reproducibility**: Commands work the same way every time
- ✅ **Comprehensive logging**: Full audit trail of command execution

### For System Reliability
- ✅ **Prevents database locks**: Proper environment validation before execution
- ✅ **Handles path issues**: Automatic working directory management
- ✅ **Manages dependencies**: Virtual environment activation handled automatically
- ✅ **Graceful degradation**: Fallback to normal execution when appropriate

## Future Enhancements

Potential improvements for the hook system:

1. **Dynamic Configuration**: Load command mappings from config files
2. **Command Caching**: Cache resolved command paths for better performance
3. **Parallel Execution**: Support for parallel command execution
4. **Cloud Integration**: Extend for cloud-based development environments
5. **Advanced Pattern Matching**: More sophisticated command pattern detection

## Contributing

To extend the hook system:

1. **Add new command types**: Modify `command_mappings` in `smart_environment.py`
2. **Add interception patterns**: Update `should_intercept()` in `claude_code_hook.sh`
3. **Add tests**: Extend test cases in `test_hook_system.py`
4. **Update documentation**: Add examples to this README and configuration guide

The system is designed to be modular and extensible for different project types and development workflows.
