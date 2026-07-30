# Contract: Age-Banded Core Configuration and Presentation

## Accepted plan-design configuration

### Direct YAML

```yaml
employer_core_contribution:
  status: age_banded
  contribution_rate: 0.03 # flat fallback
  age_schedule:
    - min_age: 0
      max_age: 30
      contribution_rate: 0.03
    - min_age: 30
      max_age: null
      contribution_rate: 0.06
```

### Studio/workspace configuration

```yaml
dc_plan:
  core_status: age_banded
  core_age_schedule:
    - min_age: 0
      max_age: 30
      contribution_rate: 0.03
    - min_age: 30
      max_age: null
      contribution_rate: 0.06
```

Both forms use decimal `contribution_rate` values. Invalid nonempty schedules fail at configuration load: gaps, overlaps, a first tier above zero, negative rates, `min_age >= max_age`, or an unbounded tier before the final tier.

## Execution configuration contract

The exported transient execution value is:

```yaml
employer_core_status: age_banded
employer_core_age_schedule:
  - min_age: 0
    max_age: 30
    rate: 3.0
  - min_age: 30
    max_age: null
    rate: 6.0
```

`rate` is percentage-valued only at this execution boundary. An empty schedule is omitted or empty and uses `employer_core_contribution_rate` as the fallback.

## Studio presentation contract

- The core-mode selector includes **Age-Banded**.
- The tier editor shows minimum age, optional maximum age, and percentage rate, plus `[min, max)` guidance and validation feedback.
- Plan Design Summary displays **Age-Banded** and every configured age interval/rate.
- Scenario Cost Comparison describes the employer core design as age-banded rather than flat.
- The 401(a)(4) display uses generic nondiscrimination-review wording for any risk/caveat flag, including the age-banded caveat. It does not represent a legal qualification conclusion.

## Compatibility contract

`flat`, `graded_by_service`, and `points_based` retain their existing configuration fields, calculation behavior, audit-rate behavior, and user-facing labels.
