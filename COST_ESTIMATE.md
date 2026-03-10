# Fidelity PlanAlign Engine - Development Cost Estimate

Analysis Date: March 6, 2026
Codebase Version: 1.0.0 ("Foundation") - Feature-complete MVP

---

## Codebase Metrics

| Category                        | Lines of Code | Files         |
| ------------------------------- | ------------- | ------------- |
| Python - Orchestrator           | 25,665        | ~45           |
| Python - API (FastAPI)          | 17,520        | ~30           |
| Python - CLI (Rich/Typer)       | 3,975         | ~10           |
| Python - Config/Events          | 2,713         | ~8            |
| Python - Scripts                | 6,411         | ~15           |
| Python - Tests                  | 26,282        | 70 files      |
| Python - Other                  | 1,269         | ~5            |
| SQL - dbt Models                | 26,539        | 144 models    |
| SQL - dbt Tests                 | 6,360         | 51 tests      |
| SQL - dbt Macros                | 3,317         | 34 macros     |
| SQL - Other                     | 152           | -             |
| TypeScript/React (Studio)       | 19,679        | 34 components |
| YAML Configuration              | 32,316        | -             |
| CSV Seeds                       | 30,149        | 20 files      |
| HTML/CSS                        | 1,644         | -             |
| Markdown Documentation          | 269,032       | -             |
| TOTAL Source Code               | ~173,842      |               |
| TOTAL (incl. docs/config/seeds) | ~473,023      |               |

### Complexity Factors

- Event-sourced architecture with immutable audit trails (UUID-stamped)
- DuckDB columnar OLAP engine with dbt transformation layer
- Temporal state accumulators (Year N-1 to Year N pattern)
- 11+ event types with Pydantic v2 validation
- Modular pipeline orchestrator (6 focused modules)
- FastAPI backend with WebSocket real-time telemetry
- React/Vite frontend with 34 components
- Hazard-based workforce modeling engines (termination, promotion, hiring, compensation)
- DC Plan engine (contributions, vesting, forfeiture, HCE/IRS compliance)
- Batch scenario processing with Excel export
- Git-based workspace cloud sync
- Checkpoint/recovery system
- Enhanced error diagnostics with correlation IDs

---

## Development Time Estimate

### Base Development Hours (by complexity tier)

| Component                               | Lines  | Productivity | Hours |
| --------------------------------------- | ------ | ------------ | ----- |
| Orchestrator (event sourcing, pipeline) | 25,665 | 20 lines/hr  | 1,283 |
| API (FastAPI, WebSocket, REST)          | 17,520 | 25 lines/hr  | 701   |
| CLI (Rich interface)                    | 3,975  | 30 lines/hr  | 133   |
| Config/Events (Pydantic v2)             | 2,713  | 25 lines/hr  | 109   |
| Scripts (benchmarks, analysis)          | 6,411  | 30 lines/hr  | 214   |
| Other Python                            | 1,269  | 30 lines/hr  | 42    |
| dbt Models (complex SQL, accumulators)  | 26,539 | 20 lines/hr  | 1,327 |
| dbt Tests + Macros                      | 9,677  | 25 lines/hr  | 387   |
| TypeScript/React (Studio UI)            | 19,679 | 25 lines/hr  | 787   |
| Python Tests (256+ tests)               | 26,282 | 30 lines/hr  | 876   |
| YAML/HTML/CSS (meaningful)              | ~6,600 | 40 lines/hr  | 165   |
| BASE CODING SUBTOTAL                    | -      | -            | 6,024 |

### Overhead Multipliers

| Factor                                              | Percentage | Hours |
| --------------------------------------------------- | ---------- | ----- |
| Architecture and Design                             | +18%       | 1,084 |
| Debugging and Troubleshooting                       | +28%       | 1,687 |
| Code Review and Refactoring                         | +12%       | 723   |
| Documentation (269K lines)                          | +12%       | 723   |
| Integration and Testing                             | +22%       | 1,325 |
| Learning Curve (DuckDB, dbt, event sourcing, ERISA) | +15%       | 904   |
| OVERHEAD SUBTOTAL                                   | +107%      | 6,446 |

### Total Estimated Development Hours: ~12,470 hours

---

## Realistic Calendar Time (with Organizational Overhead)

| Company Type        | Efficiency | Coding Hrs/Week | Calendar Weeks | Calendar Time |
| ------------------- | ---------- | --------------- | -------------- | ------------- |
| Solo/Startup (lean) | 65%        | 26 hrs          | 480 weeks      | ~9.2 years    |
| Growth Company      | 55%        | 22 hrs          | 567 weeks      | ~10.9 years   |
| Enterprise          | 45%        | 18 hrs          | 693 weeks      | ~13.3 years   |
| Large Bureaucracy   | 35%        | 14 hrs          | 891 weeks      | ~17.1 years   |

These are single-developer estimates. A team of 3 senior engineers would reduce calendar time by ~60-65%.

Overhead Assumptions:

- Standups, team syncs, 1:1s, sprint ceremonies
- Code reviews (giving), Slack/email, ad-hoc meetings
- Context switching, admin/tooling overhead

---

## Market Rate Research

Based on 2025-2026 US market data:

| Rate Tier   | Hourly Rate | Basis                                                                       |
| ----------- | ----------- | --------------------------------------------------------------------------- |
| Low-end     | $75/hr      | Remote, mid-market generalist Python/data                                   |
| Average     | $110/hr     | US-based senior Python + data engineering                                   |
| High-end    | $165/hr     | SF/NYC, event sourcing + financial domain specialist                        |
| Recommended | $125/hr     | Specialized stack (DuckDB, dbt, Pydantic, FastAPI, React, ERISA compliance) |

Rationale: This project requires niche expertise across event sourcing architecture, workforce simulation modeling, DuckDB/dbt data pipelines, ERISA compliance, and full-stack web development - a rare combination that commands premium rates.

---

## Total Engineering Cost Estimate

| Scenario    | Hourly Rate | Total Hours | Total Cost |
| ----------- | ----------- | ----------- | ---------- |
| Low-end     | $75         | 12,470      | $935,250   |
| Average     | $110        | 12,470      | $1,371,700 |
| High-end    | $165        | 12,470      | $2,057,550 |
| Recommended | $125        | 12,470      | $1,558,750 |

---

## Full Team Cost (All Roles)

| Company Stage  | Team Multiplier | Engineering Cost | Full Team Cost |
| -------------- | --------------- | ---------------- | -------------- |
| Solo/Founder   | 1.0x            | $1,558,750       | $1,558,750     |
| Lean Startup   | 1.45x           | $1,558,750       | $2,260,188     |
| Growth Company | 2.2x            | $1,558,750       | $3,429,250     |
| Enterprise     | 2.65x           | $1,558,750       | $4,130,688     |

### Role Breakdown (Growth Company)

| Role                   | Hours             | Rate    | Cost       |
| ---------------------- | ----------------- | ------- | ---------- |
| Engineering            | 12,470 hrs        | $125/hr | $1,558,750 |
| Product Management     | 3,741 hrs (0.30x) | $150/hr | $561,150   |
| UX/UI Design           | 3,118 hrs (0.25x) | $125/hr | $389,688   |
| Engineering Management | 1,871 hrs (0.15x) | $175/hr | $327,369   |
| QA/Testing             | 2,494 hrs (0.20x) | $100/hr | $249,400   |
| Project Management     | 1,247 hrs (0.10x) | $125/hr | $155,875   |
| Technical Writing      | 624 hrs (0.05x)   | $100/hr | $62,350    |
| DevOps/Platform        | 1,871 hrs (0.15x) | $150/hr | $280,575   |
| TOTAL                  | 27,436 hrs        | -       | $3,585,157 |

---

## Grand Total Summary

| Metric                 | Solo     | Lean Startup | Growth Co | Enterprise |
| ---------------------- | -------- | ------------ | --------- | ---------- |
| Calendar Time (1 dev)  | ~9.2 yrs | ~10.9 yrs    | ~13.3 yrs | ~17.1 yrs  |
| Calendar Time (3 devs) | ~3.3 yrs | ~3.9 yrs     | ~4.8 yrs  | ~6.1 yrs   |
| Total Human Hours      | 12,470   | 18,082       | 27,434    | 33,046     |
| Total Cost             | $1.56M   | $2.26M       | $3.43M    | $4.13M     |

---

## Claude ROI Analysis

### Project Timeline

- First commit: June 21, 2025
- Latest commit: March 6, 2026
- Total calendar time: 258 days (~8.5 months)
- Total commits: 597
- Unique active days: 117

### Claude Active Hours Estimate

| Day Activity Level    | Days     | Avg Hours/Day | Subtotal   |
| --------------------- | -------- | ------------- | ---------- |
| Light (1-5 commits)   | ~60      | 2.0 hrs       | 120 hrs    |
| Medium (6-10 commits) | ~35      | 3.0 hrs       | 105 hrs    |
| Heavy (11-15 commits) | ~15      | 4.0 hrs       | 60 hrs     |
| Intense (16+ commits) | ~7       | 5.0 hrs       | 35 hrs     |
| TOTAL                 | 117 days | -             | ~320 hours |

Method: Git commit clustering by day with density-based session duration heuristics.

### Value per Claude Hour

| Value Basis                    | Total Value | Claude Hours | Per Claude Hour |
| ------------------------------ | ----------- | ------------ | --------------- |
| Engineering only (recommended) | $1,558,750  | 320 hrs      | $4,871/hr       |
| Full team (Growth Co)          | $3,429,250  | 320 hrs      | $10,716/hr      |
| Full team (Enterprise)         | $4,130,688  | 320 hrs      | $12,908/hr      |

### Speed vs. Human Developer

- Estimated human hours for same work: 12,470 hours
- Claude active hours: ~320 hours
- Speed multiplier: ~39x (Claude was 39x faster)

### Cost Comparison

- Human developer cost (at $125/hr avg): $1,558,750
- Estimated Claude cost (~8.5 months subscription): ~$1,700 (Pro plan)
- Net savings: ~$1,557,050
- ROI: ~916x (every $1 spent on Claude produced ~$916 of value)

---

## The Headline

> Claude worked for approximately 320 hours over 8.5 months and produced the equivalent of $1.56M in professional engineering value - roughly $4,871 per Claude hour. At a subscription cost of ~$1,700, that is a 916x return on investment.

---

## Assumptions

1. Rates based on US market averages (2025-2026 data)
2. Productivity rates reflect senior developer (5+ years) with domain expertise
3. Includes complete MVP implementation across 12+ production epics
4. Does not include: marketing, legal/compliance, office/equipment, cloud hosting, ongoing maintenance
5. Claude hours estimated from git commit density; actual may vary +/-20%
6. YAML/CSV lines discounted heavily (configuration data, not logic)
7. 269K lines of markdown documentation included in overhead estimate but not base coding hours

---

## Sources

- [Senior Full Stack Developer Salary - Glassdoor 2026](https://www.glassdoor.com/Salaries/senior-full-stack-developer-salary-SRCH_KO0,27.htm)
- [Senior Full Stack Developer Salary - ZipRecruiter](https://www.ziprecruiter.com/Salaries/Senior-Full-Stack-Developer-Salary)
- [Python Developer Hourly Rates 2026 - Arc](https://arc.dev/freelance-developer-rates/python)
- [Senior Python Developer Salary - ZipRecruiter](https://www.ziprecruiter.com/Salaries/Senior-Python-Developer-Salary)
- [Python Developer Hourly Rates 2026 - Aalpha](https://www.aalpha.net/articles/python-developer-hourly-rates/)
- [Data Engineer Hourly Rates - ContractRates](https://www.contractrates.fyi/Data-Engineer/hourly-rates)
- [dbt Developer Salary - ZipRecruiter](https://www.ziprecruiter.com/Salaries/Dbt-Developer-Salary)
- [Full Stack Developer Hourly Rate 2026 - Arc](https://arc.dev/freelance-developer-rates/full-stack)
