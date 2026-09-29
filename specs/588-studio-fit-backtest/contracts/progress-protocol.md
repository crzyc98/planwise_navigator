# Fit/Backtest Structured Progress Protocol (#588)

Progress events are emitted by `planalign fit` and `planalign backtest` only when the environment variable `PLANALIGN_FIT_PROGRESS=1` is set. Plain CLI output is byte-for-byte unchanged when it is unset.

## Line format

```
PLANALIGN_FIT_PROGRESS|{"v":1,"event":"<event>", ...fields}
```

- There is one line per event on stdout, flushed immediately.
- Consumers MUST ignore unknown events and unknown fields.

## Events

| event | fields | emitted by |
|---|---|---|
| `stage` | `stage` ∈ {`loading_history`, `fitting`, `writing_pack`, `scoring`} | fit + backtest |
| `seed_started` | `seed`, `index` (1-based), `total`, `years` (list of int) | backtest |
| `seed_completed` | `seed`, `index`, `total` | backtest |
| `simulation_failed` | `seed`, `year`, `message` | backtest, just before exiting with code 4 |
| `completed` | `pack_id`, `fingerprint`, `verdict?` | fit + backtest, after all artifacts are written |

## Studio mapping

- `stage` sets `JobProgress.stage`.
- `seed_started` sets `stage=simulating` and fills `seed`, `index` and `total`.
- `simulation_failed` populates `JobError.failed_seed` and `JobError.failed_year`.
