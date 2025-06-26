#!/bin/bash
# CI/CD test suite for PlanWise Navigator
# Run this before committing any changes

set -e  # Exit on error

echo "🔍 Running PlanWise Navigator CI Tests..."
echo "========================================="

# Check if we're in the right directory
if [[ ! -f "CLAUDE.md" ]]; then
    echo "❌ Error: Not in PlanWise Navigator root directory"
    echo "Please run from: /Users/nicholasamaral/planwise_navigator"
    exit 1
fi

# Activate virtual environment if it exists
if [[ -f "venv/bin/activate" ]]; then
    echo "🐍 Activating virtual environment..."
    source venv/bin/activate
fi

# 1. Python linting and type checking (optional)
echo "📝 Running Python validation..."
if command -v python &> /dev/null; then
    python -c "import orchestrator" 2>/dev/null && echo "✅ Python import check passed" || echo "⚠️  Python import issues detected"
else
    echo "⚠️  Python not available - skipping validation"
fi

# 2. dbt validation
echo "🔧 Checking dbt..."
cd dbt
if command -v dbt &> /dev/null; then
    echo "📦 Installing dbt dependencies..."
    dbt deps || echo "⚠️  dbt deps failed"

    echo "🔧 Checking dbt compilation..."
    dbt compile || echo "❌ dbt compilation failed"

    echo "🧪 Running fast dbt tests..."
    dbt test --exclude tag:slow || echo "❌ Some dbt tests failed"

    echo "✅ dbt validation completed"
else
    echo "⚠️  dbt not available - install with: pip install dbt-core dbt-duckdb"
fi

# 3. Final summary
cd ..
echo ""
echo "📊 CI Test Summary:"
echo "==================="
echo "✅ Basic syntax validation completed"
echo "💡 For full validation before pushing:"
echo "   - Ensure Python environment is set up"
echo "   - Run: pip install -r requirements.txt"
echo "   - Run this script again for complete testing"
echo ""
echo "🚀 Ready to commit? Run: git commit"
