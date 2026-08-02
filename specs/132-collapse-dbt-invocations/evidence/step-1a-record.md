# Step 1a — remove redundant start-year build

## Measurement

| Repetition | Commands | Wall (s) | Startup (s) | Execution (s) | Orchestration (s) |
|---:|---:|---:|---:|---:|---:|
| 1 | 19 | 99.890 | 62.998 | 18.152 | 18.740 |
| 2 | 19 | 99.738 | 64.117 | 18.398 | 17.223 |
| 3 | 19 | 99.789 | 64.566 | 18.380 | 16.843 |
| **Median** | **19** | **99.789** | **64.117** | **18.380** | **17.223** |

- Prior median: 103.576s
- Delta versus prior: **3.787s faster**
- Story 1 bar: 3.000s
- Parity: **PASS** — [step-1a-parity.md](step-1a-parity.md)
- Decision: **KEEP**

The deletion independently clears Story 1's corrected empirical bar. It also
removes a build whose result was immediately discarded by FOUNDATION's full
refresh, so the code path is simpler regardless of timing variance.
