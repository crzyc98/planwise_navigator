# Environment Scripts - Setup and Deployment Utilities

## Purpose

The environment management scripts provide essential utilities for setting up, configuring, and maintaining the Fidelity PlanAlign Engine development and production environments. These scripts ensure consistent deployment, proper configuration, and reliable system operation.

## Architecture

The environment scripts implement standardized patterns for:
- **Development Environment Setup**: Local development configuration
- **Service Management**: Starting and stopping core services
- **Configuration Management**: Environment-specific settings
- **Deployment Automation**: Production deployment processes

## Key Environment Scripts

### 1. set_dagster_home.sh - Environment Configuration

**Purpose**: Configure system-wide DAGSTER_HOME environment variable for consistent pipeline execution.

```bash
#!/bin/bash
"""
Set DAGSTER_HOME environment variable system-wide for Fidelity PlanAlign Engine

This script configures the DAGSTER_HOME environment variable to prevent
temporary directory creation and ensure consistent pipeline execution.

Usage:
    ./scripts/set_dagster_home.sh
    ./scripts/set_dagster_home.sh --verify
"""

set -e  # Exit on any error

# Configuration
DAGSTER_HOME_PATH="$HOME/dagster_home_planwise"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to detect operating system
detect_os() {
    case "$(uname -s)" in
        Darwin*) echo "macos" ;;
        Linux*)  echo "linux" ;;
        CYGWIN*) echo "windows" ;;
        MINGW*)  echo "windows" ;;
        *) echo "unknown" ;;
    esac
}

# Function to set environment variable on macOS
set_macos_env() {
    log_info "Configuring DAGSTER_HOME for macOS using launchctl"

    # Set for current session
    export DAGSTER_HOME="$DAGSTER_HOME_PATH"

    # Set system-wide using launchctl
    launchctl setenv DAGSTER_HOME "$DAGSTER_HOME_PATH"

    # Add to shell profile for future sessions
    for profile in ~/.bash_profile ~/.zshrc ~/.bashrc; do
        if [[ -f "$profile" ]]; then
            log_info "Adding DAGSTER_HOME to $profile"

            # Remove any existing DAGSTER_HOME exports
            grep -v "export DAGSTER_HOME" "$profile" > "${profile}.tmp" 2>/dev/null || true
            mv "${profile}.tmp" "$profile" 2>/dev/null || true

            # Add new export
            echo "export DAGSTER_HOME=\"$DAGSTER_HOME_PATH\"" >> "$profile"
        fi
    done

    log_success "DAGSTER_HOME configured for macOS"
}

# Function to set environment variable on Linux
set_linux_env() {
    log_info "Configuring DAGSTER_HOME for Linux"

    # Set for current session
    export DAGSTER_HOME="$DAGSTER_HOME_PATH"

    # Add to system environment
    if [[ -w /etc/environment ]]; then
        # Remove existing entry
        sudo sed -i '/DAGSTER_HOME/d' /etc/environment 2>/dev/null || true
        # Add new entry
        echo "DAGSTER_HOME=\"$DAGSTER_HOME_PATH\"" | sudo tee -a /etc/environment > /dev/null
        log_info "Added DAGSTER_HOME to /etc/environment"
    fi

    # Add to user profiles
    for profile in ~/.bashrc ~/.bash_profile ~/.profile; do
        if [[ -f "$profile" ]] || [[ "$profile" == ~/.bashrc ]]; then
            # Create ~/.bashrc if it doesn't exist
            [[ ! -f ~/.bashrc ]] && touch ~/.bashrc

            log_info "Adding DAGSTER_HOME to $profile"

            # Remove any existing DAGSTER_HOME exports
            grep -v "export DAGSTER_HOME" "$profile" > "${profile}.tmp" 2>/dev/null || true
            mv "${profile}.tmp" "$profile" 2>/dev/null || true

            # Add new export
            echo "export DAGSTER_HOME=\"$DAGSTER_HOME_PATH\"" >> "$profile"
        fi
    done

    log_success "DAGSTER_HOME configured for Linux"
}

# Function to create DAGSTER_HOME directory
create_dagster_home() {
    log_info "Creating DAGSTER_HOME directory: $DAGSTER_HOME_PATH"

    # Create directory if it doesn't exist
    if [[ ! -d "$DAGSTER_HOME_PATH" ]]; then
        mkdir -p "$DAGSTER_HOME_PATH"
        log_success "Created DAGSTER_HOME directory"
    else
        log_info "DAGSTER_HOME directory already exists"
    fi

    # Create basic dagster.yaml if it doesn't exist
    local dagster_yaml="$DAGSTER_HOME_PATH/dagster.yaml"
    if [[ ! -f "$dagster_yaml" ]]; then
        log_info "Creating basic dagster.yaml configuration"

        cat > "$dagster_yaml" << EOF
# Fidelity PlanAlign Engine Dagster Configuration
# Generated by set_dagster_home.sh on $(date)

storage:
  filesystem:
    base_dir: "$DAGSTER_HOME_PATH/storage"

run_launcher:
  module: dagster.core.launcher
  class: DefaultRunLauncher

compute_logs:
  module: dagster.core.storage.local_compute_log_manager
  class: LocalComputeLogManager
  config:
    base_dir: "$DAGSTER_HOME_PATH/logs"

local_artifact_storage:
  module: dagster.core.storage.root
  class: LocalArtifactStorage
  config:
    base_dir: "$DAGSTER_HOME_PATH/storage"
EOF

        log_success "Created dagster.yaml configuration"
    fi

    # Set proper permissions
    chmod 755 "$DAGSTER_HOME_PATH"

    # Create subdirectories
    mkdir -p "$DAGSTER_HOME_PATH/storage"
    mkdir -p "$DAGSTER_HOME_PATH/logs"
    mkdir -p "$DAGSTER_HOME_PATH/history"
}

# Function to verify configuration
verify_configuration() {
    log_info "Verifying DAGSTER_HOME configuration"

    # Check if directory exists
    if [[ ! -d "$DAGSTER_HOME_PATH" ]]; then
        log_error "DAGSTER_HOME directory does not exist: $DAGSTER_HOME_PATH"
        return 1
    fi

    # Check environment variable in current session
    if [[ "$DAGSTER_HOME" == "$DAGSTER_HOME_PATH" ]]; then
        log_success "DAGSTER_HOME set correctly in current session: $DAGSTER_HOME"
    else
        log_warning "DAGSTER_HOME not set in current session. Current value: ${DAGSTER_HOME:-'(not set)'}"
    fi

    # Check system-wide setting (macOS)
    if [[ "$(detect_os)" == "macos" ]]; then
        local launchctl_value
        launchctl_value=$(launchctl getenv DAGSTER_HOME 2>/dev/null || echo "")
        if [[ "$launchctl_value" == "$DAGSTER_HOME_PATH" ]]; then
            log_success "DAGSTER_HOME set correctly system-wide (launchctl)"
        else
            log_warning "DAGSTER_HOME not set system-wide via launchctl"
        fi
    fi

    # Check configuration file
    if [[ -f "$DAGSTER_HOME_PATH/dagster.yaml" ]]; then
        log_success "Dagster configuration file exists"
    else
        log_warning "Dagster configuration file missing"
    fi

    # Test Dagster CLI access
    if command -v dagster >/dev/null 2>&1; then
        log_success "Dagster CLI is available"

        # Test dagster info command
        if dagster --help >/dev/null 2>&1; then
            log_success "Dagster CLI responds correctly"
        else
            log_warning "Dagster CLI not responding properly"
        fi
    else
        log_warning "Dagster CLI not found in PATH"
    fi
}

# Function to clean up temporary directories
cleanup_temp_directories() {
    log_info "Cleaning up temporary Dagster directories"

    # Find and remove temporary .tmp_dagster_home_* directories
    local temp_dirs
    temp_dirs=$(find "$PROJECT_ROOT" -maxdepth 1 -name ".tmp_dagster_home_*" -type d 2>/dev/null || true)

    if [[ -n "$temp_dirs" ]]; then
        log_info "Found temporary directories to clean:"
        echo "$temp_dirs"

        while IFS= read -r dir; do
            if [[ -n "$dir" ]]; then
                log_info "Removing: $dir"
                rm -rf "$dir"
            fi
        done <<< "$temp_dirs"

        log_success "Cleaned up temporary directories"
    else
        log_info "No temporary directories found"
    fi
}

# Main execution function
main() {
    local verify_only=false

    # Parse command line arguments
    for arg in "$@"; do
        case $arg in
            --verify|-v)
                verify_only=true
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [--verify] [--help]"
                echo ""
                echo "Set DAGSTER_HOME environment variable for Fidelity PlanAlign Engine"
                echo ""
                echo "Options:"
                echo "  --verify, -v    Only verify current configuration"
                echo "  --help, -h      Show this help message"
                exit 0
                ;;
            *)
                log_error "Unknown option: $arg"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done

    log_info "Setting up DAGSTER_HOME for Fidelity PlanAlign Engine"
    log_info "Target DAGSTER_HOME: $DAGSTER_HOME_PATH"
    log_info "Detected OS: $(detect_os)"

    if [[ "$verify_only" == true ]]; then
        verify_configuration
        exit $?
    fi

    # Create DAGSTER_HOME directory and configuration
    create_dagster_home

    # Set environment variable based on OS
    case "$(detect_os)" in
        macos)
            set_macos_env
            ;;
        linux)
            set_linux_env
            ;;
        windows)
            log_error "Windows setup not implemented yet"
            log_info "Please set DAGSTER_HOME manually to: $DAGSTER_HOME_PATH"
            exit 1
            ;;
        *)
            log_error "Unsupported operating system"
            exit 1
            ;;
    esac

    # Clean up any temporary directories
    cleanup_temp_directories

    # Verify the configuration
    echo ""
    verify_configuration

    echo ""
    log_success "DAGSTER_HOME configuration completed!"
    log_info "You may need to restart your terminal or run 'source ~/.bashrc' (or ~/.zshrc)"
    log_info "To verify the setup, run: $0 --verify"
}

# Execute main function with all arguments
main "$@"
```

### 2. start_dagster.sh - Development Server Startup

**Purpose**: Start Dagster development server with proper configuration and error handling.

```bash
#!/bin/bash
"""
Start Dagster development server for Fidelity PlanAlign Engine

Usage:
    ./scripts/start_dagster.sh
    ./scripts/start_dagster.sh --port 3001
    ./scripts/start_dagster.sh --host 0.0.0.0 --port 3000
"""

set -e

# Configuration
DEFAULT_HOST="127.0.0.1"
DEFAULT_PORT="3000"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

# Parse command line arguments
HOST="$DEFAULT_HOST"
PORT="$DEFAULT_PORT"

while [[ $# -gt 0 ]]; do
    case $1 in
        --host|-h)
            HOST="$2"
            shift 2
            ;;
        --port|-p)
            PORT="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [--host HOST] [--port PORT]"
            echo ""
            echo "Start Dagster development server for Fidelity PlanAlign Engine"
            echo ""
            echo "Options:"
            echo "  --host, -h    Host to bind to (default: $DEFAULT_HOST)"
            echo "  --port, -p    Port to bind to (default: $DEFAULT_PORT)"
            echo "  --help        Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validation functions
check_dagster_home() {
    if [[ -z "$DAGSTER_HOME" ]]; then
        log_error "DAGSTER_HOME is not set"
        log_info "Run: ./scripts/set_dagster_home.sh"
        return 1
    fi

    if [[ ! -d "$DAGSTER_HOME" ]]; then
        log_error "DAGSTER_HOME directory does not exist: $DAGSTER_HOME"
        log_info "Run: ./scripts/set_dagster_home.sh"
        return 1
    fi

    log_success "DAGSTER_HOME configured: $DAGSTER_HOME"
}

check_dependencies() {
    log_info "Checking dependencies..."

    # Check if dagster is installed
    if ! command -v dagster &> /dev/null; then
        log_error "Dagster is not installed or not in PATH"
        log_info "Install with: pip install -r requirements.txt"
        return 1
    fi

    # Check if we're in the right directory
    if [[ ! -f "$PROJECT_ROOT/definitions.py" ]]; then
        log_error "definitions.py not found in project root"
        log_info "Make sure you're running this script from the Fidelity PlanAlign Engine root directory"
        return 1
    fi

    # Check if database exists
    if [[ ! -f "$PROJECT_ROOT/simulation.duckdb" ]]; then
        log_warning "simulation.duckdb not found - will be created on first run"
    fi

    log_success "Dependencies validated"
}

check_port_availability() {
    if command -v lsof &> /dev/null; then
        if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null; then
            log_error "Port $PORT is already in use"
            log_info "Use --port to specify a different port, or kill the process using port $PORT"
            return 1
        fi
    elif command -v netstat &> /dev/null; then
        if netstat -tulpn 2>/dev/null | grep ":$PORT " >/dev/null; then
            log_error "Port $PORT is already in use"
            return 1
        fi
    else
        log_warning "Cannot check port availability (lsof/netstat not found)"
    fi

    log_success "Port $PORT is available"
}

setup_environment() {
    log_info "Setting up environment..."

    # Change to project root
    cd "$PROJECT_ROOT"

    # Create necessary directories
    mkdir -p logs
    mkdir -p data

    # Set Python path
    export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

    log_success "Environment setup complete"
}

start_dagster_dev() {
    log_info "Starting Dagster development server..."
    log_info "Host: $HOST"
    log_info "Port: $PORT"
    log_info "Project: Fidelity PlanAlign Engine"

    echo ""
    log_success "🚀 Dagster will be available at: http://$HOST:$PORT"
    echo ""

    # Start Dagster dev server
    exec dagster dev \
        --host "$HOST" \
        --port "$PORT" \
        --working-directory "$PROJECT_ROOT"
}

# Cleanup function
cleanup() {
    log_info "Shutting down Dagster server..."
    # Dagster dev handles its own cleanup
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Main execution
main() {
    log_info "Starting Dagster development server for Fidelity PlanAlign Engine"

    # Run all checks
    check_dagster_home || exit 1
    check_dependencies || exit 1
    check_port_availability || exit 1

    # Setup and start
    setup_environment
    start_dagster_dev
}

main "$@"
```

### 3. start_dashboard.sh - Dashboard Deployment

**Purpose**: Launch Streamlit dashboard with proper configuration and environment setup.

```bash
#!/bin/bash
"""
Start Fidelity PlanAlign Engine Streamlit Dashboard

Usage:
    ./scripts/start_dashboard.sh
    ./scripts/start_dashboard.sh --port 8501
    ./scripts/start_dashboard.sh --dev
"""

set -e

# Configuration
DEFAULT_PORT="8501"
DEFAULT_HOST="localhost"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DASHBOARD_DIR="$PROJECT_ROOT/streamlit_app"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

# Parse arguments
PORT="$DEFAULT_PORT"
HOST="$DEFAULT_HOST"
DEV_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --port|-p)
            PORT="$2"
            shift 2
            ;;
        --host|-h)
            HOST="$2"
            shift 2
            ;;
        --dev|-d)
            DEV_MODE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Start Fidelity PlanAlign Engine Streamlit Dashboard"
            echo ""
            echo "Options:"
            echo "  --port, -p    Port to run on (default: $DEFAULT_PORT)"
            echo "  --host, -h    Host to bind to (default: $DEFAULT_HOST)"
            echo "  --dev, -d     Development mode with auto-reload"
            echo "  --help        Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

check_dependencies() {
    log_info "Checking dependencies..."

    # Check Streamlit
    if ! command -v streamlit &> /dev/null; then
        log_error "Streamlit not found"
        log_info "Install with: pip install streamlit"
        return 1
    fi

    # Check dashboard directory
    if [[ ! -d "$DASHBOARD_DIR" ]]; then
        log_error "Dashboard directory not found: $DASHBOARD_DIR"
        return 1
    fi

    # Check main dashboard file
    if [[ ! -f "$DASHBOARD_DIR/Dashboard.py" ]]; then
        log_error "Main dashboard file not found: $DASHBOARD_DIR/Dashboard.py"
        return 1
    fi

    # Check database
    if [[ ! -f "$PROJECT_ROOT/simulation.duckdb" ]]; then
        log_warning "simulation.duckdb not found - dashboard may have limited functionality"
    fi

    log_success "Dependencies validated"
}

setup_environment() {
    log_info "Setting up dashboard environment..."

    # Set environment variables
    export STREAMLIT_SERVER_PORT="$PORT"
    export STREAMLIT_SERVER_ADDRESS="$HOST"
    export STREAMLIT_SERVER_HEADLESS=true
    export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

    # Development mode settings
    if [[ "$DEV_MODE" == true ]]; then
        export STREAMLIT_SERVER_RUN_ON_SAVE=true
        export STREAMLIT_SERVER_FILE_WATCHER_TYPE="auto"
        log_info "Development mode enabled with auto-reload"
    fi

    # Set Python path
    export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

    # Change to dashboard directory
    cd "$DASHBOARD_DIR"

    log_success "Environment configured"
}

start_dashboard() {
    log_info "Starting Fidelity PlanAlign Engine Dashboard..."
    log_info "Host: $HOST"
    log_info "Port: $PORT"
    log_info "Mode: $(if [[ "$DEV_MODE" == true ]]; then echo "Development"; else echo "Production"; fi)"

    echo ""
    log_success "🎯 Dashboard will be available at: http://$HOST:$PORT"
    echo ""

    # Start Streamlit
    if [[ "$DEV_MODE" == true ]]; then
        exec streamlit run Dashboard.py \
            --server.address "$HOST" \
            --server.port "$PORT" \
            --server.runOnSave true \
            --server.fileWatcherType auto
    else
        exec streamlit run Dashboard.py \
            --server.address "$HOST" \
            --server.port "$PORT"
    fi
}

# Cleanup function
cleanup() {
    log_info "Shutting down dashboard..."
    exit 0
}

trap cleanup SIGINT SIGTERM

main() {
    log_info "Starting Fidelity PlanAlign Engine Dashboard"

    check_dependencies || exit 1
    setup_environment
    start_dashboard
}

main "$@"
```

### 4. install_venv.sh - Virtual Environment Setup

**Purpose**: Automated virtual environment creation and dependency installation.

```bash
#!/bin/bash
"""
Install and configure Python virtual environment for Fidelity PlanAlign Engine

Usage:
    ./scripts/install_venv.sh
    ./scripts/install_venv.sh --python python3.11
    ./scripts/install_venv.sh --force
"""

set -e

# Configuration
VENV_NAME="planwise_venv"
PYTHON_VERSION="python3"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REQUIREMENTS_FILE="$PROJECT_ROOT/requirements.txt"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

# Parse arguments
FORCE_RECREATE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --python)
            PYTHON_VERSION="$2"
            shift 2
            ;;
        --force|-f)
            FORCE_RECREATE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Install Python virtual environment for Fidelity PlanAlign Engine"
            echo ""
            echo "Options:"
            echo "  --python      Python version to use (default: python3)"
            echo "  --force, -f   Force recreate virtual environment"
            echo "  --help        Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

check_python() {
    log_info "Checking Python installation..."

    if ! command -v "$PYTHON_VERSION" &> /dev/null; then
        log_error "$PYTHON_VERSION not found"
        log_info "Please install Python 3.8+ and try again"
        return 1
    fi

    # Check Python version
    local python_version_output
    python_version_output=$("$PYTHON_VERSION" --version 2>&1)
    log_success "Found: $python_version_output"

    # Verify minimum version (3.8+)
    local version_check
    version_check=$("$PYTHON_VERSION" -c "import sys; print(sys.version_info >= (3, 8))")
    if [[ "$version_check" != "True" ]]; then
        log_error "Python 3.8+ required"
        return 1
    fi
}

create_virtual_environment() {
    local venv_path="$PROJECT_ROOT/$VENV_NAME"

    if [[ -d "$venv_path" ]] && [[ "$FORCE_RECREATE" == false ]]; then
        log_info "Virtual environment already exists: $venv_path"
        log_info "Use --force to recreate"
        return 0
    fi

    if [[ -d "$venv_path" ]] && [[ "$FORCE_RECREATE" == true ]]; then
        log_info "Removing existing virtual environment..."
        rm -rf "$venv_path"
    fi

    log_info "Creating virtual environment with $PYTHON_VERSION..."
    "$PYTHON_VERSION" -m venv "$venv_path"

    log_success "Virtual environment created: $venv_path"
}

install_dependencies() {
    local venv_path="$PROJECT_ROOT/$VENV_NAME"
    local activate_script="$venv_path/bin/activate"

    if [[ ! -f "$activate_script" ]]; then
        log_error "Virtual environment activation script not found"
        return 1
    fi

    log_info "Activating virtual environment..."
    # shellcheck source=/dev/null
    source "$activate_script"

    # Upgrade pip
    log_info "Upgrading pip..."
    pip install --upgrade pip

    # Install requirements
    if [[ -f "$REQUIREMENTS_FILE" ]]; then
        log_info "Installing dependencies from requirements.txt..."
        pip install -r "$REQUIREMENTS_FILE"
        log_success "Dependencies installed successfully"
    else
        log_warning "requirements.txt not found, installing minimal dependencies..."
        pip install dagster dagster-webserver dagster-dbt duckdb streamlit pandas plotly pydantic
    fi

    # Install development dependencies if in dev mode
    if [[ -f "$PROJECT_ROOT/requirements-dev.txt" ]]; then
        log_info "Installing development dependencies..."
        pip install -r "$PROJECT_ROOT/requirements-dev.txt"
    fi
}

create_activation_script() {
    local venv_path="$PROJECT_ROOT/$VENV_NAME"
    local script_path="$PROJECT_ROOT/activate.sh"

    log_info "Creating activation script..."

    cat > "$script_path" << EOF
#!/bin/bash
# Fidelity PlanAlign Engine Environment Activation
# Source this file to activate the virtual environment and set up paths

# Activate virtual environment
source "$venv_path/bin/activate"

# Set project root
export PLANWISE_ROOT="$PROJECT_ROOT"

# Set Python path
export PYTHONPATH="$PROJECT_ROOT:\$PYTHONPATH"

# Set DAGSTER_HOME if not already set
if [[ -z "\$DAGSTER_HOME" ]]; then
    export DAGSTER_HOME="\$HOME/dagster_home_planwise"
fi

echo "✅ Fidelity PlanAlign Engine environment activated"
echo "   Virtual environment: $VENV_NAME"
echo "   Project root: $PROJECT_ROOT"
echo "   DAGSTER_HOME: \$DAGSTER_HOME"
echo ""
echo "Available commands:"
echo "   dagster dev                    # Start Dagster development server"
echo "   streamlit run streamlit_app/Dashboard.py  # Start dashboard"
echo "   python scripts/run_simulation.py          # Run simulation"
EOF

    chmod +x "$script_path"
    log_success "Created activation script: $script_path"
}

verify_installation() {
    local venv_path="$PROJECT_ROOT/$VENV_NAME"
    local activate_script="$venv_path/bin/activate"

    log_info "Verifying installation..."

    # Activate environment for testing
    # shellcheck source=/dev/null
    source "$activate_script"

    # Test key imports
    local test_imports=(
        "dagster"
        "duckdb"
        "streamlit"
        "pandas"
        "plotly"
        "pydantic"
    )

    for package in "${test_imports[@]}"; do
        if python -c "import $package" 2>/dev/null; then
            log_success "$package: OK"
        else
            log_error "$package: FAILED"
            return 1
        fi
    done

    log_success "All dependencies verified"
}

main() {
    log_info "Setting up Fidelity PlanAlign Engine Python environment"

    cd "$PROJECT_ROOT"

    check_python || exit 1
    create_virtual_environment || exit 1
    install_dependencies || exit 1
    create_activation_script || exit 1
    verify_installation || exit 1

    echo ""
    log_success "🎉 Environment setup complete!"
    echo ""
    log_info "To activate the environment, run:"
    echo "   source activate.sh"
    echo ""
    log_info "Or manually activate with:"
    echo "   source $VENV_NAME/bin/activate"
}

main "$@"
```

## Supporting Environment Scripts

### Docker Support (Future Enhancement)
- **docker-compose.yml**: Container orchestration
- **Dockerfile**: Container image definition
- **docker-entrypoint.sh**: Container startup script

### CI/CD Integration
- **deploy.sh**: Production deployment automation
- **test.sh**: Automated testing pipeline
- **build.sh**: Build and packaging scripts

## Usage Examples

### Environment Setup
```bash
# Initial setup
./scripts/install_venv.sh
./scripts/set_dagster_home.sh

# Activate environment
source activate.sh

# Start services
./scripts/start_dagster.sh
./scripts/start_dashboard.sh --dev
```

### Development Workflow
```bash
# Daily development startup
source activate.sh
./scripts/start_dagster.sh --port 3000 &
./scripts/start_dashboard.sh --port 8501 --dev &

# Run simulation
python scripts/run_simulation.py --quick-test
```

## Environment Variables

### Required Variables
```bash
DAGSTER_HOME="$HOME/dagster_home_planwise"
PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
PLANWISE_ROOT="$PROJECT_ROOT"
```

### Optional Variables
```bash
STREAMLIT_SERVER_PORT="8501"
STREAMLIT_SERVER_ADDRESS="localhost"
DUCKDB_PATH="simulation.duckdb"
```

## Dependencies

### System Dependencies
- Python 3.8+
- bash shell
- Standard Unix utilities (lsof, netstat, etc.)

### Python Dependencies
- Core packages from requirements.txt
- Development packages for enhanced functionality

## Related Files

### Configuration Files
- `requirements.txt` - Python dependencies
- `requirements-dev.txt` - Development dependencies
- `config/` - Application configuration files

### Infrastructure
- `definitions.py` - Dagster workspace
- `streamlit_app/` - Dashboard application
- Database and data directories

## Implementation Notes

### Best Practices
1. **Error Handling**: Comprehensive error checking and user feedback
2. **Cross-Platform**: Support for macOS, Linux, and Windows
3. **Idempotency**: Scripts can be run multiple times safely
4. **Validation**: Verify setup before proceeding
5. **Cleanup**: Proper cleanup on exit and error conditions

### Security Considerations
- Validate all input parameters
- Use secure file permissions
- Avoid exposing sensitive information
- Implement proper access controls

### Maintenance Guidelines
- Regular updates for dependency versions
- Platform-specific testing
- Documentation updates for new features
- Monitoring script performance and reliability
