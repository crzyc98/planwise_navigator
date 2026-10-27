# Design: Realistic participant deferral behavior (epic #986)

**Status:** Approved 2026-10-26 (D1–D9 decided, §9). Revised after an independent gpt-6-astra review of the claims against `main@a16e5321`.
**Issues:** #985 AIP mode · #984 self-chosen enrollment rates · #987 Easy Enroll · #983 ongoing rate changes · #988 Studio controls
**Created:** 2026-10-26

This document fixes the shared decisions every child issue builds on: the event shape, rate state, contribution timing, config names, and the calibration report. Nothing here is implemented yet. Decisions are marked **[D#]** and recorded in §9.

---

## 1. What exists today (verified)

| Concern | Where | Behavior |
|---|---|---|
| Rate state | `int_deferral_rate_state_accumulator` | One row per employee-year, holding the year-end rate. In order: opt-out (an `enrollment_change` at 0%) forces 0% and unenrolls. Otherwise match response **plus** escalation, capped by the escalation cap and the IRS limit (`:325–333`, `:443–451`). Otherwise a `COALESCE` of escalation > match response > new enrollment > carried forward > fallback. |
| Escalation | `int_deferral_rate_escalation_events` | Year 1 reads rates from enrollment events. Later years read the **prior-year accumulator** (`:160–185`). Adds the increment up to the cap, skips 0% rates (`:253`), and is bounded by termination (`:292–309`). Membership comes inline from the census: `NOT auto_escalation_opt_out`, with new hires in by default (`:194–224`). |
| Match response | `int_deferral_match_response_events` | Event type `deferral_match_response`, `event_category = 'match_response'`. First year only, dated **Jan 1**. |
| Enrollment | `int_enrollment_events` | Auto-enrollment, voluntary, proactive, and **year-over-year (YoY) conversion** for existing non-participants. YoY excludes anyone who ever opted out, recent hires and plan-ineligible employees. Its probability is the age rate × income multiplier × tenure multiplier (`:482–511`). Dedupe order is voluntary > proactive > YoY > auto (`:816–827`). The channel is already in `event_category`. |
| Contributions | `int_employee_contributions` | `earned comp × year-end rate`. The only exception is same-year enroll→opt-out, which uses the enrollment-window rate and base (`:200–210`). It already outputs `effective_annual_deferral_rate`, which **match** consumes (`int_employee_match_calculations.sql:~122`). A mid-year enrollment or a mid-year escalation is already applied to the whole employment period. That approximation predates this epic. |
| Event union | `int_current_year_events` → `fct_yearly_events` | `event_category` passes through (`:279`). Ordering uses `event_priority()`. **Events with null compensation are dropped** unless their type is on the allowlist in `macros/utils/data_quality_flag.sql:6` (`int_current_year_events.sql:301`). |
| Participation reporting | `fct_workforce_snapshot.sql:325–350` / `analytics_service.py:672–686` | The snapshot treats rate > 0 as participating. Studio analytics count `is_enrolled_flag`. |
| Config → dbt | Pydantic (`config/workforce.py`) → `to_dbt_vars` (`config/export.py`; Studio's `dc_plan` applied as overrides) → `dbt_var_validation.py` → `tests/test_dbt_var_coverage.py` (#510 guard) | The established path for every setting. |
| Studio | `components/config/DCPlanSection.tsx` | Already split into **Plan provisions** and **Employee behavior assumptions** (#869). |
| Polars mode | `export.py:1196` | Hard-coded to `sql`. Ignore the Polars branches and don't extend them. |

---

## 2. Event shape

### 2.1 New event type: `deferral_change`

One new type covers every rate change the participant chooses. The reason goes in `event_category`, which already reaches `fct_yearly_events` unchanged. **No change to the `fct_yearly_events` schema.**

| `event_category` | Meaning | Issue |
|---|---|---|
| `proactive_increase` | Participant raises their rate | #983 |
| `proactive_decrease` | Participant lowers their rate (floor 1%) | #983 |
| `aip_response_decrease` | Participant lowers their rate after an AIP notice | #983 |
| `stop` | Participant goes to 0% and stays enrolled **[D1]** | #983 |
| `restart` | Participant at 0% resumes contributing | #983 |

Wiring required, all part of PR 0a:
- `evt_deferral_change()` in `macros/constants.sql`. `event_priority` 8, after `deferral_escalation` (7), with later priorities shifted by one. The shift keeps existing relative order, so existing `event_sequence` values don't change.
- `EVENT_DEFERRAL_CHANGE` in `planalign_core/constants.py`.
- **Add `deferral_change` to the null-compensation allowlist** in `data_quality_flag.sql`. These are rate-only events, so without this they're silently dropped.
- Add it to the `event_type` `accepted_values` test (`marts/schema.yml:92`) and to the event lists in `tests/invariants/queries.py:200–203, 321–324`. Escalation-specific checks stay escalation-specific.
- A new ephemeral model, `int_deferral_change_events`, placed after escalation in `_get_event_generation_models`. **It's added to the `int_current_year_events` union through Jinja only when `deferral_rate_changes.enabled`.** When the feature is off, the union compiles exactly as today, so there's no type-coercion risk from an empty branch.
- Columns: `employee_deferral_rate` (the new rate), `prev_employee_deferral_rate` (the rate just before the change), and `effective_date`. `compensation_amount` is the current compensation where available. `event_details` is readable text.

**Why not reuse `enrollment_change`?** The accumulator and contributions treat `enrollment_change` at 0% as an opt-out, so a `stop` would be mistaken for one.

### 2.2 Enrollment channel

No new column. `enrollment` events already record the channel in `event_category`. Easy Enroll is decided **after** the existing dedupe, as a channel among the people who enroll on their own (voluntary, proactive or YoY winners). It replaces that event's rate with the package rate and sets `event_category = 'easy_enroll'`. The original channel goes into `event_details`. That means no new precedence slot. Easy Enroll is only available before auto-enrollment happens; auto-enrolled participants never use it. Among employees who enroll on their own, `channel_share_without_auto_enrollment` (0.45) applies to plans without auto-enrollment and `channel_share_with_auto_enrollment` (0.57) applies to plans with auto-enrollment. The remainder enroll proactively online, choosing their rate themselves.

### 2.3 Timing and ordering **[D2, D3]**

- **[D2] At most one `deferral_change` per participant per year.** The calibration data is a net 12-month change per person.
- **[D3] The `deferral_change` is the participant's last rate event of the year.** Its date is drawn uniformly within the window: from (1 + the latest of Jan 1, this year's escalation date, and the match-response date) to (the earlier of Dec 31 and the termination date). **If the window is empty, there's no change.** This covers, for example, a Dec 31 escalation or a termination before the window opens.
  - With the default 01-01 escalation, this is a uniform draw over the whole year.
  - A plan with a late escalation date gets its changes squeezed into the rest of the year. That's a documented v1 limitation.
- `aip_response_decrease` is drawn within `post_escalation_decrease_window_days` after this year's escalation date, using the same bounds.

### 2.4 Who is eligible

**Continuous participants:** enrolled as of Jan 1 and active.
- Year 2+: `is_enrolled_flag` in the prior-year accumulator.
- Year 1: census participants with an enrollment date before Jan 1 (`int_baseline_workforce`).

People who enroll this year become eligible next year.

---

## 3. Rate state

### 3.1 Accumulator

There are two new columns on `int_deferral_rate_state_accumulator`. `sync_all_columns` is already set.

| Column | Type | Purpose |
|---|---|---|
| `aip_participant` | BOOLEAN | AIP membership, carried forward (§4). |
| `last_nonzero_deferral_rate` | DECIMAL(5,4) | Lets a `restart` resume at the participant's prior rate. |

**Year-end rate:** the existing CASE stays exactly as it is, renamed `rate_before_voluntary_change`. A final step then applies:

```
current_deferral_rate =
  CASE WHEN opt_out                        THEN 0          -- existing precedence kept
       WHEN deferral_change this year      THEN dc.employee_deferral_rate
       ELSE rate_before_voluntary_change END
```

`deferral_change` events compute their starting rate from the same logic, so `dc.prev_employee_deferral_rate = rate_before_voluntary_change`, and a DQ test asserts it. A `stop` sets the rate to 0 and leaves `is_enrolled_flag` true **[D1]**.

### 3.2 Contribution timing **[D4]**

Weighting is done **in `int_employee_contributions`**, which already reads `fct_yearly_events` and owns the employment window. The accumulator doesn't do it.

```
weighted_rate = prev_rate × (days_before_change / days_employed)
              + new_rate  × (days_from_change   / days_employed)     -- DECIMAL(9,6), rounded only at output
```

- It **replaces only the ordinary branch** (`year_end_deferral_rate`). The same-year enroll→opt-out branch is untouched.
- Employees with no `deferral_change` keep the existing expression and types.
- **Match** consumes `effective_annual_deferral_rate` as today, so it applies tier caps to the weighted annual rate. That's an **annual true-up** approximation. It differs from per-pay-period matching when a change crosses a tier boundary. This is documented, and it's consistent with today's annual match calculation.
- **[D4] Scope:** only the new events are weighted. The existing full-year treatment of mid-year enrollment and non-01-01 escalation is filed as a separate issue, because fixing it changes baseline results for many configs.

### 3.3 Participation semantics for `stop` [D1]

A stopped participant is enrolled but not contributing:
- The snapshot adds a `participation_status_detail` value, `not_participating - stopped contributions`. Its `participation_status` stays `not_participating` (rate = 0).
- The Studio analytics enrollment counts (`is_enrolled_flag`) still include them. PR 3d documents that difference and adds a "contributing" metric if needed.
- Match earned before the stop is kept, through the weighted rate.

---

## 4. AIP membership (#985, #987)

`deferral_auto_escalation.enabled` stays the only on/off switch, exactly as today. When it's false, no one is in AIP. When it's true, `mode` decides who is in:

| Mode | Who is in AIP |
|---|---|
| `automatic` (default) | Today's rule exactly: `NOT census.auto_escalation_opt_out`, new hires in by default. |
| `participant_elected` | Participants whose stable per-employee draw (salt `-aip-elect-`, no year in it) falls below `participant_elected_signup_probability`, plus every Easy Enroll enrollee. |

**Implementation:** a macro, `aip_initial_membership(mode, ...)`, holds the rule above. The escalation model uses it in **year 1**. For year 2+, it reads the prior-year accumulator's `aip_participant`, combined with this year's new Easy Enroll enrollees and the rule for new hires. That mirrors how escalation already reads rates, so there's no same-year dependency cycle.

- The accumulator writes `aip_participant` using the same macro and carry-forward.
- An `aip_response_decrease` does **not** clear it **[D7]**. The participant stays in AIP, and next year's step can trigger another decrease. The calibration report makes repeat decreases visible.
- In `automatic` mode the macro's year-1 output equals today's inline expression, and the carry-forward reproduces it in later years. The census flag is static, so this can be checked in a test.
- `mode` has no `none` value, so `enabled` and `mode` can't conflict. An earlier draft had `mode: none` as an alias for `enabled: false`. That broke dump→edit→validate round trips, which the optimizer uses to toggle `enabled`.

**[D5]** AIP mode and the Easy Enroll offering are run-global in v1, not per-plan-design (#632), matching the magnet, spread and match response.

---

## 5. Existing non-participants (#984) **[D6]**

Reuse YoY conversion. Don't add a parallel draw, which would double-count. Changes:

1. Route YoY's rate choice through the same below-default and two-way magnet logic as proactive enrollment.
   The resolved below-default share is the total share across self-directed channels (proactive, voluntary, YoY), apart from downward match-ceiling snaps. With AE enabled and a positive share, non-choosers are floored at the AE default after grid + spread and before the magnet; deliberate below-default choosers bypass the magnet.
2. Phase 4 retunes the YoY age rates so the **population-average** annual conversion is about 5%. The income and tenure multipliers (0.7–1.3) stay, which keeps realistic gradients. The calibration report verifies the average. If you want 5% exactly for everyone, the alternative is to set the multipliers to 1.0.

---

## 6. Config

Every new setting follows the established path:
1. a Pydantic field;
2. a `to_dbt_vars` export;
3. a `dc_plan` override for Studio;
4. a type check in `dbt_var_validation`;
5. coverage in `test_dbt_var_coverage`;
6. a Studio control (#988).

Defaults below are the **Phase 0–3 values (off, results unchanged)**. Comments show the **Phase 4** defaults.

```yaml
deferral_auto_escalation:            # existing
  enabled: true                      # unchanged: the only on/off switch
  mode: automatic                    # automatic | participant_elected (used only when enabled)
  participant_elected_signup_probability: 0.0          # Phase 4: 0.01 [D8]

easy_enroll:                         # new, #987
  enabled: false                                # Phase 4: true
  # Share of employees who enroll on their own (before any auto-enrollment) who use
  # Easy Enroll instead of choosing a rate themselves; the remainder enroll proactively online.
  # Use the share for whether the plan has auto-enrollment. Easy Enroll is only available
  # before auto-enrollment happens; auto-enrolled participants never use it.
  # Without auto-enrollment: ~45% Easy Enroll / 55% proactive.
  # With auto-enrollment: ~20% Easy Enroll / 15% proactive / 65% auto-enrolled,
  # so 20/35 ≈ 0.57 of employees who enroll on their own use Easy Enroll.
  channel_share_without_auto_enrollment: 0.45
  channel_share_with_auto_enrollment: 0.57
  packages:
    - {rate: 0.06, share: 0.30}
    - {rate: 0.08, share: 0.50}
    - {rate: 0.10, share: 0.20}
  escalation_cap: 0.10

enrollment:
  match_magnet:                      # existing
    downward_enabled: false                     # Phase 4: true (shares snap_probability)
  below_default:                     # new, #984
    share_tiers:                                # Phase 4: [{max_auto_enroll_default_rate: 0.03, share: 0.10}, {max_auto_enroll_default_rate: null, share: 0.15}]
      - {max_auto_enroll_default_rate: null, share: 0.0}
    steps: [{pp: 1, weight: 0.50}, {pp: 2, weight: 0.30}, {pp: 3, weight: 0.20}]            # −1/−2/−3pp
  year_over_year_conversion: ...     # existing; Phase 4 retune to ~5% population average [D6]

deferral_rate_changes:               # new, #983
  enabled: false                                # Phase 4: true
  with_escalation:     {increase_probability: 0.085, decrease_probability: 0.082}  # 2026-10-27: one all-plans rate for both groups
  without_escalation: {increase_probability: 0.085, decrease_probability: 0.082}
  increase_steps: [{pp: 1, weight: 0.10}, {pp: 2, weight: 0.10}, {pp: 3, weight: 0.15}, {pp: 5, weight: 0.20}, {pp: 7, weight: 0.20}, {pp: 10, weight: 0.25}]  # fitted in PR 3e
  decrease_steps: [{pp: 1, weight: 0.10}, {pp: 2, weight: 0.15}, {pp: 3, weight: 0.15}, {pp: 5, weight: 0.20}, {pp: 8, weight: 0.20}, {pp: 12, weight: 0.20}]  # fitted in PR 3e
  post_escalation_decrease_window_days: 90
  post_escalation_decrease_leaves_escalation: false                  # [D7]: stay in AIP
  stop_probability: 0.015
  restart_probability: 0.0                             # Phase 4: 0.40 [D9, rechecked 2026-10-27]
```

- Validators enforce:
  - package and step weights each sum to 1;
  - shares and rates lie in `[0, 1]`;
  - `share_tiers` is ordered with exactly one open-ended tier;
  - steps are clamped to the 1% floor and to the plan and IRS max.
- **Participant-level rates:** `with_escalation` / `without_escalation` apply per participant using `aip_participant`. That turns the with-AIP and without-AIP plan estimates into participant-level rates, and handles partial membership (participant-elected AIP, Easy Enroll) without assuming a plan mix.
- Each draw has its own salt: `-deferral-change-`, `-deferral-change-step-`, `-deferral-change-timing-`, `-aip-elect-`, `-easy-enroll-channel-`, `-easy-enroll-package-`, `-below-default-`, `-below-default-step-`.
- `below_default.share_tiers` specifies the total below-default share, rather than adding to low demographic-grid rates. A resolved share of zero or disabled AE preserves existing behavior without a floor. Downward magnet snaps to a full-match ceiling below the AE default are allowed and reported separately.

---

## 7. Calibration report

`scripts/deferral_calibration_report.py` runs **on demand** against a finished run's database. It is **not** a pipeline model: the REPORTING stage is empty today, and a per-year model would add a dbt invocation to every year of every run. The script queries `fct_workforce_snapshot` and `fct_yearly_events` directly. For each simulation year after the first, it reports **continuous participants** (enrolled and active at both year-ends), split by:

- `same` / `increase` / `decrease`, from year-end rates;
- increases attributed to `proactive` (a `proactive_increase` or `restart` `deferral_change` that year), else `aip` (a `deferral_escalation` that year), else `other` (for example, match response);
- `to_zero` / `from_zero`;
- average increase, average decrease, and net change in pp.

Each split is reported overall and by reporting-only bands that match the calibration file. These don't touch the seeded simulation bands:
- age by decade, 20–29 through 70+;
- income: <$25k, $25k, $40k, $50k, $60k, $75k, $100k, $125k, $150k, $200k, $250k+;
- tenure: 1–2, 2–3, 3–4, 4–5, 5–10, then 5-year steps to 30+.

`--targets <csv>` takes an optional targets file kept under git-ignored `data/calibration/`, with columns `dimension,band,metric,value`, and prints the differences. CI never sees the targets. CI tests use a synthetic DuckDB fixture with hand-computed expectations.

---

## 8. Delivery

**What "unchanged" means:** `fct_yearly_events` and `fct_workforce_snapshot` business columns are equal, comparing full rows after sorting. Volatile metadata (`created_at`, which comes from `CURRENT_TIMESTAMP`) is excluded. Literal byte identity is impossible today. Every PR shows this with A/B multi-year `simulate` runs (same config and seed) in isolated DBs. It's never assumed.

| PR | Content | Unchanged when off? |
|---|---|---|
| **0a** | Config models and exports (§6) at their off defaults; validation; coverage; `dc_plan` mappings. `evt_deferral_change` and the priority shift. The DQ allowlist, accepted values and invariant lists. The `int_deferral_change_events` skeleton, unioned only when enabled. The on-demand calibration report script. | Yes |
| **0b** | The `aip_initial_membership` macro and the `aip_participant` / `last_nonzero_deferral_rate` columns. Escalation reads membership from them. The `rate_before_voluntary_change` refactor. Contributions weighting hook (no-op without events). | Yes |
| 1a | #985 AIP modes plus Studio controls | Yes (`automatic`) |
| 1b | #984 below-default branch, downward magnet, YoY rate logic plus Studio controls | Yes (off) |
| 2 | #987 Easy Enroll plus Studio controls | Yes (off) |
| 3a–e | #983: changes, AIP response, stop/restart with snapshot semantics, multipliers, calibration fit, plus Studio controls | Yes (off) |
| 4 | Switch to the Phase 4 defaults; CHANGELOG; Studio "on by default" copy | **No, intended** |

Every PR runs edge configs (AE `all_eligible_employees`, escalation off, match response off, each AIP mode, Dec-31 escalation), plus the fast suite and dbt schema tests.

---

## 9. Decisions (signed off 2026-10-26)

| # | Decision |
|---|---|
| D1 | `stop` keeps the participant **enrolled at 0%**. The snapshot shows "stopped contributions", and `restart` is a rate change. |
| D2 | At most one voluntary change per participant per year. |
| D3 | The voluntary change is the year's last rate event. Only plans with late escalation dates see compressed timing. |
| D4 | Only the new events are time-weighted. The existing mid-year enrollment and escalation approximation is filed separately. |
| D5 | AIP mode and the Easy Enroll offering are run-global in v1. |
| D6 | Existing non-participants reuse YoY conversion, retuned in Phase 4 to a ~5% population average with the income and tenure gradients kept. |
| D7 | An `aip_response_decrease` does **not** remove the participant from AIP (`post_escalation_decrease_leaves_escalation: false`). |
| D8 | The participant-elected AIP sign-up rate outside Easy Enroll defaults to **1%** in Phase 4. |
| D9 | `restart_probability` defaults to **5% a year** in Phase 4. Recheck it against the calibration report in 3e. **Rechecked 2026-10-27: 40%**, so about two-thirds of stops restart after turnover, in line with plan data. |

Still open, needed before PR 2: the #987 questions (which plans get Easy Enroll by default; whether auto-enrolled people can switch into a package; whether the 35% channel share is right).
