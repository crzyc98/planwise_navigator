#!/bin/bash
# Clear Python cache to resolve import errors
# Run this after pulling new code or when you get "No module named" errors

echo "🧹 Clearing Python cache..."

# Remove all __pycache__ directories
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# Remove all .pyc files
find . -name "*.pyc" -delete 2>/dev/null

# Remove all .pyo files
find . -name "*.pyo" -delete 2>/dev/null

# Remove pytest cache
rm -rf .pytest_cache 2>/dev/null

# Remove mypy cache
rm -rf .mypy_cache 2>/dev/null

# Remove ruff cache
rm -rf .ruff_cache 2>/dev/null

echo "✅ Python cache cleared successfully!"
echo ""
echo "💡 Next steps:"
echo "   1. Reinstall the package: pip install -e ."
echo "   2. Test the CLI: planwise --help"
echo "   3. Run a simulation: planwise simulate 2025-2026"
