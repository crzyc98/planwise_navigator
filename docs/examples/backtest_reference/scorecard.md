# Backtest scorecard — pack

Fitted 2022–2024 · held out 2025 · seeds 42, 43, 44

## Year 2025

| Metric | Predicted | Actual | Absolute error | Percent error | Status |
|---|---:|---:|---:|---:|---|
| `compensation.average` | 127,711.6305 | 127,300.3893 | +411.2412 | +0.32% | **PASS** |
| `compensation.total` | 213,022,999.6600 | 212,846,250.9300 | +176,748.7300 | +0.08% | **PASS** |
| `flows.hires` | 241.0000 | 225.0000 | +16.0000 | +7.11% | **PASS** |
| `flows.promotions` | 97.0000 | 99.0000 | -2.0000 | -2.02% | **PASS** |
| `flows.terminations` | 143.0000 | 131.0000 | +12.0000 | +9.16% | **PASS** |
| `headcount.by_age_band.25-34` | 436.0000 | 342.0000 | +94.0000 | +27.49% | **FAIL** |
| `headcount.by_age_band.35-44` | 422.0000 | 433.0000 | -11.0000 | -2.54% | **WARN** |
| `headcount.by_age_band.45-54` | 399.0000 | 437.0000 | -38.0000 | -8.70% | **FAIL** |
| `headcount.by_age_band.55-64` | 366.0000 | 421.0000 | -55.0000 | -13.06% | **FAIL** |
| `headcount.by_age_band.65+` | 33.0000 | 34.0000 | -1.0000 | -2.94% | **WARN** |
| `headcount.by_age_band.< 25` | 11.0000 | 5.0000 | +6.0000 | +120.00% | **FAIL** |
| `headcount.by_level.1` | 503.0000 | 529.0000 | -26.0000 | -4.91% | **FAIL** |
| `headcount.by_level.2` | 560.0000 | 546.0000 | +14.0000 | +2.56% | **WARN** |
| `headcount.by_level.3` | 253.0000 | 266.0000 | -13.0000 | -4.89% | **FAIL** |
| `headcount.by_level.4` | 282.0000 | 260.0000 | +22.0000 | +8.46% | **FAIL** |
| `headcount.by_level.5` | 69.0000 | 71.0000 | -2.0000 | -2.82% | **WARN** |
| `headcount.by_tenure_band.10-19` | 483.0000 | 488.0000 | -5.0000 | -1.02% | **PASS** |
| `headcount.by_tenure_band.2-4` | 247.0000 | 252.0000 | -5.0000 | -1.98% | **PASS** |
| `headcount.by_tenure_band.20+` | 301.0000 | 305.0000 | -4.0000 | -1.31% | **PASS** |
| `headcount.by_tenure_band.5-9` | 255.0000 | 257.0000 | -2.0000 | -0.78% | **PASS** |
| `headcount.by_tenure_band.< 2` | 374.0000 | 370.0000 | +4.0000 | +1.08% | **PASS** |
| `headcount.total` | 1,668.0000 | 1,672.0000 | -4.0000 | -0.24% | **PASS** |
| `plan.average_deferral_rate` | 0.0467 | 0.0438 | +0.0028 | +6.42% | **WARN** |
| `plan.participation_rate` | 0.7908 | 0.6358 | +0.1550 | +24.38% | **FAIL** |

## Cumulative

| Metric | Predicted | Actual | Absolute error | Percent error | Status |
|---|---:|---:|---:|---:|---|
| `compensation.average` | 127,711.6305 | 127,300.3893 | +411.2412 | +0.32% | **PASS** |
| `compensation.total` | 213,022,999.6600 | 212,846,250.9300 | +176,748.7300 | +0.08% | **PASS** |
| `flows.hires` | 241.0000 | 225.0000 | +16.0000 | +7.11% | **PASS** |
| `flows.promotions` | 97.0000 | 99.0000 | -2.0000 | -2.02% | **PASS** |
| `flows.terminations` | 143.0000 | 131.0000 | +12.0000 | +9.16% | **PASS** |
| `headcount.by_age_band.25-34` | 436.0000 | 342.0000 | +94.0000 | +27.49% | **FAIL** |
| `headcount.by_age_band.35-44` | 422.0000 | 433.0000 | -11.0000 | -2.54% | **WARN** |
| `headcount.by_age_band.45-54` | 399.0000 | 437.0000 | -38.0000 | -8.70% | **FAIL** |
| `headcount.by_age_band.55-64` | 366.0000 | 421.0000 | -55.0000 | -13.06% | **FAIL** |
| `headcount.by_age_band.65+` | 33.0000 | 34.0000 | -1.0000 | -2.94% | **WARN** |
| `headcount.by_age_band.< 25` | 11.0000 | 5.0000 | +6.0000 | +120.00% | **FAIL** |
| `headcount.by_level.1` | 503.0000 | 529.0000 | -26.0000 | -4.91% | **FAIL** |
| `headcount.by_level.2` | 560.0000 | 546.0000 | +14.0000 | +2.56% | **WARN** |
| `headcount.by_level.3` | 253.0000 | 266.0000 | -13.0000 | -4.89% | **FAIL** |
| `headcount.by_level.4` | 282.0000 | 260.0000 | +22.0000 | +8.46% | **FAIL** |
| `headcount.by_level.5` | 69.0000 | 71.0000 | -2.0000 | -2.82% | **WARN** |
| `headcount.by_tenure_band.10-19` | 483.0000 | 488.0000 | -5.0000 | -1.02% | **PASS** |
| `headcount.by_tenure_band.2-4` | 247.0000 | 252.0000 | -5.0000 | -1.98% | **PASS** |
| `headcount.by_tenure_band.20+` | 301.0000 | 305.0000 | -4.0000 | -1.31% | **PASS** |
| `headcount.by_tenure_band.5-9` | 255.0000 | 257.0000 | -2.0000 | -0.78% | **PASS** |
| `headcount.by_tenure_band.< 2` | 374.0000 | 370.0000 | +4.0000 | +1.08% | **PASS** |
| `headcount.total` | 1,668.0000 | 1,672.0000 | -4.0000 | -0.24% | **PASS** |
| `plan.average_deferral_rate` | 0.0467 | 0.0438 | +0.0028 | +6.42% | **WARN** |
| `plan.participation_rate` | 0.7908 | 0.6358 | +0.1550 | +24.38% | **FAIL** |

## Not observable

- `plan.employer_match_cost` (2025): snapshots carry no employee_deferral_rate column, so deferral levels and employer match cannot be observed
- `plan.employer_match_cost` (cumulative): snapshots carry no employee_deferral_rate column, so deferral levels and employer match cannot be observed

## Seed spread

- `compensation.average` (2025): 127,215.2145–127,776.8587; actual inside
- `compensation.average` (cumulative): 127,215.2145–127,776.8587; actual inside
- `compensation.total` (2025): 212,194,977.8400–213,131,800.3200; actual inside
- `compensation.total` (cumulative): 212,194,977.8400–213,131,800.3200; actual inside
- `flows.hires` (2025): 241.0000–241.0000; actual outside by -16.0000
- `flows.hires` (cumulative): 241.0000–241.0000; actual outside by -16.0000
- `flows.promotions` (2025): 89.0000–111.0000; actual inside
- `flows.promotions` (cumulative): 89.0000–111.0000; actual inside
- `flows.terminations` (2025): 143.0000–143.0000; actual outside by -12.0000
- `flows.terminations` (cumulative): 143.0000–143.0000; actual outside by -12.0000
- `headcount.by_age_band.25-34` (2025): 420.0000–438.0000; actual outside by -78.0000
- `headcount.by_age_band.25-34` (cumulative): 420.0000–438.0000; actual outside by -78.0000
- `headcount.by_age_band.35-44` (2025): 419.0000–441.0000; actual inside
- `headcount.by_age_band.35-44` (cumulative): 419.0000–441.0000; actual inside
- `headcount.by_age_band.45-54` (2025): 395.0000–404.0000; actual outside by +33.0000
- `headcount.by_age_band.45-54` (cumulative): 395.0000–404.0000; actual outside by +33.0000
- `headcount.by_age_band.55-64` (2025): 361.0000–371.0000; actual outside by +50.0000
- `headcount.by_age_band.55-64` (cumulative): 361.0000–371.0000; actual outside by +50.0000
- `headcount.by_age_band.65+` (2025): 32.0000–36.0000; actual inside
- `headcount.by_age_band.65+` (cumulative): 32.0000–36.0000; actual inside
- `headcount.by_age_band.< 25` (2025): 9.0000–11.0000; actual outside by -4.0000
- `headcount.by_age_band.< 25` (cumulative): 9.0000–11.0000; actual outside by -4.0000
- `headcount.by_level.1` (2025): 491.0000–510.0000; actual outside by +19.0000
- `headcount.by_level.1` (cumulative): 491.0000–510.0000; actual outside by +19.0000
- `headcount.by_level.2` (2025): 551.0000–574.0000; actual outside by -5.0000
- `headcount.by_level.2` (cumulative): 551.0000–574.0000; actual outside by -5.0000
- `headcount.by_level.3` (2025): 251.0000–258.0000; actual outside by +8.0000
- `headcount.by_level.3` (cumulative): 251.0000–258.0000; actual outside by +8.0000
- `headcount.by_level.4` (2025): 280.0000–284.0000; actual outside by -20.0000
- `headcount.by_level.4` (cumulative): 280.0000–284.0000; actual outside by -20.0000
- `headcount.by_level.5` (2025): 68.0000–70.0000; actual outside by +1.0000
- `headcount.by_level.5` (cumulative): 68.0000–70.0000; actual outside by +1.0000
- `headcount.by_tenure_band.10-19` (2025): 482.0000–492.0000; actual inside
- `headcount.by_tenure_band.10-19` (cumulative): 482.0000–492.0000; actual inside
- `headcount.by_tenure_band.2-4` (2025): 246.0000–258.0000; actual inside
- `headcount.by_tenure_band.2-4` (cumulative): 246.0000–258.0000; actual inside
- `headcount.by_tenure_band.20+` (2025): 301.0000–304.0000; actual outside by +1.0000
- `headcount.by_tenure_band.20+` (cumulative): 301.0000–304.0000; actual outside by +1.0000
- `headcount.by_tenure_band.5-9` (2025): 254.0000–260.0000; actual inside
- `headcount.by_tenure_band.5-9` (cumulative): 254.0000–260.0000; actual inside
- `headcount.by_tenure_band.< 2` (2025): 372.0000–375.0000; actual outside by -2.0000
- `headcount.by_tenure_band.< 2` (cumulative): 372.0000–375.0000; actual outside by -2.0000
- `headcount.total` (2025): 1,668.0000–1,668.0000; actual outside by +4.0000
- `headcount.total` (cumulative): 1,668.0000–1,668.0000; actual outside by +4.0000
- `plan.average_deferral_rate` (2025): 0.0463–0.0470; actual outside by -0.0025
- `plan.average_deferral_rate` (cumulative): 0.0463–0.0470; actual outside by -0.0025
- `plan.participation_rate` (2025): 0.7860–0.7938; actual outside by -0.1502
- `plan.participation_rate` (cumulative): 0.7860–0.7938; actual outside by -0.1502

**Verdict: FAIL** — 22 pass, 10 warn, 16 fail, 2 not observable

Thresholds (warn/fail): headcount 2.0%/4.0%; compensation 3.0%/6.0%; flows 10.0%/20.0%; plan 5.0%/10.0%.
Overrides: none.

Scorecard fingerprint: `09aca6156b73e2f9cf2523695006476a0e4bcb7658e2df18af2e6d9cef28c353`
