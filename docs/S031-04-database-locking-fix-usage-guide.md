# S031-04 Database Locking Fix - Usage Guide

**Quick Reference**: How to use the fixed optimized multi-year simulation script without database locking issues.

## ✅ The Fix

The database locking issue has been resolved by replacing parallel process execution with dbt's built-in threading. This eliminates "Conflicting lock is held" errors while maintaining performance improvements.

## 🚀 Basic Usage

### Default (Recommended)
Uses safe threading mode - no configuration needed:
```bash
python scripts/run_optimized_multi_year_simulation.py --years 2024 2025 2026
```

### Debug Mode
Force sequential execution for troubleshooting:
```bash
python scripts/run_optimized_multi_year_simulation.py --years 2024 2025 --force-sequential
```

### Custom Threading
Adjust thread count for your system:
```bash
python scripts/run_optimized_multi_year_simulation.py --years 2024 2025 --threads 8
```

## 🧪 Test the Fix

Validate that database locking is resolved:
```bash
# Test both modes with performance comparison
python scripts/test_database_locking_fix.py

# Test only sequential mode
python scripts/test_database_locking_fix.py --force-sequential

# Test only threaded mode with custom thread count
python scripts/test_database_locking_fix.py --threads 8 --no-compare
```

## 🔧 Key Flags

| Flag | Purpose | Default |
|------|---------|---------|
| `--force-sequential` | Force sequential execution (debugging) | False |
| `--threads N` | Number of dbt threads to use | 4 |
| `--enable-coordination` | Enable S031-04 coordination optimizations | True |
| `--no-coordination` | Disable coordination optimizations | False |

## 📊 Expected Performance

- **Threaded Mode**: ~65% overhead reduction (S031-04 target)
- **Sequential Mode**: Reliable fallback, slightly slower but guaranteed to work
- **No more database locks**: Both modes prevent "Conflicting lock is held" errors

## ⚠️ Troubleshooting

### If you still see database locking errors:
1. Use `--force-sequential` to ensure it works in sequential mode
2. Check if other tools (VS Code, database viewers) have open connections
3. Ensure you're using the latest version with the fix

### If performance is slower than expected:
1. Try increasing threads: `--threads 8`
2. Check system resources (CPU, memory)
3. Compare with baseline using the test script

## 🎯 S031-04 Coordination Components

The fix maintains all coordination optimizations:
- ✅ CrossYearCostAttributor (UUID-stamped cost attribution)
- ✅ IntelligentCacheManager (multi-tier caching)
- ✅ CoordinationOptimizer (65% overhead reduction)
- ✅ ResourceOptimizer (memory and I/O optimization)

## 📝 Example Workflows

### Development
```bash
# Test the fix first
python scripts/test_database_locking_fix.py

# Run simulation with coordination
python scripts/run_optimized_multi_year_simulation.py --years 2024 2025
```

### Production
```bash
# Full optimization with higher thread count
python scripts/run_optimized_multi_year_simulation.py \
  --years 2024 2025 2026 2027 \
  --enable-all-optimizations \
  --threads 8
```

### Debugging
```bash
# Safe sequential mode
python scripts/run_optimized_multi_year_simulation.py \
  --years 2024 2025 \
  --force-sequential \
  --verbose
```

---

**Status**: S031-04 Database Locking Fix Complete (MVP)
**Last Updated**: 2025-08-01
**Contact**: See S031-04 story documentation for technical details
