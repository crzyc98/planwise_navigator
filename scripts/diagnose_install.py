#!/usr/bin/env python
"""
Diagnostic script to check Fidelity PlanAlign Engine installation
Run this to diagnose import and installation issues
"""

import sys
import os
from pathlib import Path

print("=" * 80)
print("Fidelity PlanAlign Engine Installation Diagnostic")
print("=" * 80)
print()

# 1. Python version
print(f"✓ Python version: {sys.version}")
print(f"✓ Python executable: {sys.executable}")
print()

# 2. Current directory
print(f"✓ Current directory: {os.getcwd()}")
print()

# 3. Python path
print("✓ Python sys.path:")
for i, path in enumerate(sys.path, 1):
    print(f"   {i}. {path}")
print()

# 4. Check if we're in the right directory
repo_root = Path(__file__).parent.parent
print(f"✓ Repository root: {repo_root}")
print(f"✓ planalign_orchestrator exists: {(repo_root / 'planalign_orchestrator').exists()}")
print(f"✓ planalign_cli exists: {(repo_root / 'planalign_cli').exists()}")
print()

# 5. Try importing planalign_orchestrator
print("Testing imports...")
try:
    import planalign_orchestrator
    print(f"✅ planalign_orchestrator imported from: {planalign_orchestrator.__file__}")
except ImportError as e:
    print(f"❌ Cannot import planalign_orchestrator: {e}")
    print()
    print("FIX: Run 'pip install -e .' from the repository root")
    sys.exit(1)

# 6. Try importing all the modules used by orchestrator_wrapper
modules_to_test = [
    ("planalign_orchestrator.checkpoint_manager", "CheckpointManager"),
    ("planalign_orchestrator.config", "load_simulation_config"),
    ("planalign_orchestrator.dbt_runner", "DbtRunner"),
    ("planalign_orchestrator.pipeline_orchestrator", "PipelineOrchestrator"),
    ("planalign_orchestrator.recovery_orchestrator", "RecoveryOrchestrator"),
    ("planalign_orchestrator.registries", "RegistryManager"),
    ("planalign_orchestrator.scenario_batch_runner", "ScenarioBatchRunner"),
    ("planalign_orchestrator.utils", "DatabaseConnectionManager"),
    ("planalign_orchestrator.validation", "DataValidator"),
]

print()
failed_imports = []
for module_name, class_name in modules_to_test:
    try:
        module = __import__(module_name, fromlist=[class_name])
        getattr(module, class_name)
        print(f"✅ {module_name}.{class_name}")
    except ImportError as e:
        print(f"❌ {module_name}.{class_name}: {e}")
        failed_imports.append((module_name, class_name, str(e)))
    except AttributeError as e:
        print(f"⚠️  {module_name} imports but {class_name} not found: {e}")
        failed_imports.append((module_name, class_name, str(e)))

print()

# 7. Check planwise CLI
try:
    import planalign_cli
    print(f"✅ planalign_cli imported from: {planalign_cli.__file__}")
except ImportError as e:
    print(f"❌ Cannot import planalign_cli: {e}")
    failed_imports.append(("planalign_cli", "", str(e)))

print()

# 8. Check if planwise command is available
import shutil
planwise_path = shutil.which("planwise")
if planwise_path:
    print(f"✅ planwise command found at: {planwise_path}")
else:
    print("❌ planwise command not found in PATH")
    print("   FIX: Run 'pip install -e .' to install the CLI")

print()

# 9. Summary
if failed_imports:
    print("=" * 80)
    print("❌ INSTALLATION ISSUES FOUND")
    print("=" * 80)
    print()
    print("Failed imports:")
    for module, cls, error in failed_imports:
        print(f"  • {module}.{cls}")
        print(f"    Error: {error}")
    print()
    print("RECOMMENDED FIXES:")
    print("  1. Make sure you're in the virtual environment:")
    print("     source venv/bin/activate  # macOS/Linux")
    print("     .venv\\Scripts\\activate    # Windows")
    print()
    print("  2. Reinstall the package:")
    print("     pip install -e .")
    print()
    print("  3. If issues persist, try a fresh install:")
    print("     pip uninstall planwise-navigator")
    print("     pip install -e .")
    sys.exit(1)
else:
    print("=" * 80)
    print("✅ ALL CHECKS PASSED - Installation looks good!")
    print("=" * 80)
    print()
    print("You can now run:")
    print("  planwise --help")
    print("  planwise health")
    print("  planwise simulate 2025-2026")
    sys.exit(0)
