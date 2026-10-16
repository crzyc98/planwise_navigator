# Configure a projection in Studio

Use **Workforce Parameters** for projection years, headcount and pay assumptions, and **DC Plan** for retirement-plan provisions and employee behavior. The **Advanced** navigation retains **Simulation Settings**, **Data Sources**, **Compensation**, **New Hire Strategy**, **Workforce Segmentation**, **Workforce & Turnover**, and **Advanced Settings**.

The heading identifies the destination: **Base Configuration** edits workspace defaults; **Configure: …** edits the selected scenario's overrides. Confirm that destination before editing and again in **Review configuration**. An inherited scenario setting comes from its workspace or engine configuration; matching a familiar default value does not establish inheritance.

## Enter numeric assumptions

Select a numeric field to replace its value directly. Rates accept decimals, with the percent unit shown beside the entry; duration fields retain whole-number steppers. A blank required field is unfinished, not zero. Review, save, run, and section navigation require correcting unfinished or out-of-range entries first. Optional schedule endpoints may remain blank where the editor indicates an unbounded maximum (∞). Existing inherited values are preserved until edited.

## Task 1: set the projection and workforce assumptions

For a repeatable exercise, use a synthetic workspace with a synthetic census. Set:

| In Workforce Parameters | Example draft |
|---|---:|
| Projection period → First projection year | 2027 |
| Projection period → Last projection year | 2029 |
| Headcount and turnover → Annual headcount growth | 3% |
| Headcount and turnover → Experienced-employee turnover | 12% |
| Headcount and turnover → New-hire turnover assumption | 25% |
| Compensation growth → COLA / Inflation | 2% |
| Compensation growth → Merit Budget | 3.5% |

Both endpoint years are included, so this is a three-year projection. Headcount growth is a net target; hiring also replaces turnover. **New-hire turnover assumption** also affects surviving prior-year hires in later-year workforce planning. These inputs describe different populations and are not interchangeable.

Review **Current draft pay assumptions**. **Target compensation growth** is an optional solver goal, not a promised simulation result. **Promotion Budget** is retained for reference and does not constrain engine spending. Nested promotion overrides can supersede displayed promotion assumptions; check the resolved values in review.

Expand **New-hire assumptions** and **Advanced workforce assumptions** before reusing a saved scenario. Their summaries retain actual age profiles, pay ranges, promotion hazards, seed, and age/tenure bands. Some saved new-hire offer and level-distribution controls have no active engine mapping; their presence is not evidence that they affect results.

If using suggestions:

1. Choose **Suggest from census** for turnover, or **Calculate suggested settings** in **Compensation target helper**.
2. Inspect the source, counts, warnings, and current-versus-suggested values. Calculation alone does not change the draft.
3. Choose **Apply suggested rates** or **Apply suggested settings** to update the draft; choose **Cancel** to leave it unchanged. New-hire census previews use **Apply census suggestion**.
4. Recalculate if the preview says **Needs recalculation: inputs have changed.** Applying a suggestion still requires review and save.

Finish by explaining the projection years, each turnover population, the pay assumptions, and any inherited or inactive settings that remain.

## Task 2: enter and explain an employer match

In **DC Plan**, **Plan provisions** contains **Eligibility and automatic enrollment**, **Employer match**, **Employer core contribution**, and **Automatic contribution increases**. **Employee behavior assumptions** separately contains **Enrollment and opt-outs**, **Starting employee contribution rates**, and **Response to the employer match**.

Open **Employer match**, enable **Employer Match Formula**, and select **Deferral-Based (match varies by deferral %)** under **Match Calculation Mode**. In **Match Tiers (editable)**, enter one tier from 0% to 4% with a 100% match rate. This represents “100% on the first 4%”: an employee contributing 4% reaches a formula maximum employer match of 4% of eligible compensation.

For a familiar tiered variant, use:

| Employee contribution interval | Employer match rate | Employer contribution at the interval maximum |
|---|---:|---:|
| 0% to 3% | 100% | 3% of eligible compensation |
| 3% to 5% | 50% | An additional 1% |

This is “100% on the first 3%, plus 50% on the next 2%.” The employee rate needed for the full match is **5%**; the formula maximum employer contribution is **4%**. Boundaries are cumulative: the second tier ends at 5%, not 2%. Use **+ Add Tier** for another interval. Template names describe starting formulas; they do not verify safe-harbor status or other plan requirements.

These examples assume eligible compensation and an employee meeting match eligibility. Applicable contribution limits and configured caps still apply. Check **Match eligibility** independently from **Core eligibility**: service, annual hours, the year-end employment requirement, terminated hire-year employees, and terminated experienced employees each matter. The three employment flags are independent; changing the year-end requirement does not change the exceptions. An allowed exception can qualify despite that requirement, while other service/hours rules still apply.

**Custom policy combination** identifies a retained combination of those flags. Review the displayed new-hire service waiver and any per-design scope notice. Global summaries are not universal rules for every assigned plan design. Other match modes, core schedules, integration settings, and inactive schedules remain saved when another mode is selected.

Finish by explaining the employee threshold, employer formula maximum, and the separate match/core eligibility rules.

## Task 3: change automatic enrollment, then disable it

In **Eligibility and automatic enrollment**:

1. Set **Eligibility waiting period**. Each modeled month is 30 days: 3 months resolves to 90 days. An existing day-based setting can display a fractional month count, such as 1.5 months for 45 days; leaving it unchanged preserves the existing duration. Edits use whole modeled months.
2. Review **New-hire enrollment delay after eligibility**. The hire-year enrollment branch schedules from eligibility plus that delay; the continuing-employee branch uses January 15. Hire-year opt-outs add **Modeled opt-out delay**; the continuing-employee opt-out branch uses June 15. Voluntary enrollment before the automatic-enrollment deadline follows its separate decision timing.
3. Compare **Enrollment Scope** choices. **New Hires Only** uses **Hire Date Cutoff** in the first projection year, then current-year hires in later years. **All Eligible Employees** still respects the inclusive hire cutoff every year. Already enrolled employees are excluded from new enrollment decisions; plan eligibility still applies.

In **Enrollment and opt-outs**, each new-hire decision has its own **Rate source**:

| Choice | Meaning |
|---|---|
| Use inherited setting / Use inherited engine setting | Inherit the displayed source; this can be a specified rate or the demographic model. |
| Use demographic model | Explicitly clear an inherited flat rate for that decision. |
| Specify a percentage | Enter 0–100%; zero is an explicit 0%, not a blank or inheritance. |

Specified voluntary enrollment applies to eligible hires in their hire year. Continuing-employee enrollment uses demographic assumptions. A specified new-hire opt-out rate is the share of automatically enrolled new hires who opt out, not a share of the entire workforce.

For the exercise, specify 30% voluntary enrollment and 8% new-hire opt-outs. With automatic enrollment on, the illustrated split within enrollment scope is 30% voluntary, 64.4% automatically enrolled after opt-outs, and 5.6% opted out. This is an assumption preview, not a result guarantee or an enrollment count. The split is displayed only when both sources are specified percentages.

Turn off **Enable Auto-Enrollment**. The automatic-enrollment split disappears, and default deferral and opt-out settings become inactive. Their draft values are retained for re-enabling. Eligibility, voluntary enrollment, and shared scope/timing controls remain accessible because they still affect modeled enrollment. Toggling automatic enrollment or escalation does not introduce or reset a hire cutoff.

Distinguish the two employer-match behaviors: **New enrollees seeking the full match** affects voluntary enrollees; **First-year response by existing participants** affects active existing participants in the first projection year. **Max Voluntary Deferral** remains relevant with match seeking off. **Escalation Cap** can remain relevant to first-year participant response with annual escalation off.

**Max Upward Spread** and **Annual Increase** are percentage-point changes. Adding 1 percentage point to a 6% contribution produces 7%. **First Escalation Delay** uses enrollment years rather than elapsed enrollment anniversaries. Expand summaries showing clipping warnings before accepting a cap/spread combination.

## Review, save, and reload

Choose **Review changes** after editing, or **Review configuration** to inspect unchanged saved settings. In **Review configuration**:

- Confirm **Saving to scenario** or **Saving to workspace** and the destination name.
- Inspect **Changes**, **Indirect effects in engine settings**, and **Effective assumptions**. A displayed editor value can differ from a resolved engine value because of inheritance, precedence, or normalization.
- Inspect **Other active custom settings**, **Inactive saved settings**, and **Additional configured settings — mapping unverified**. A retained custom value is not automatically an active or validated modeling control.
- Use **Back to editing** for corrections. Review does not calculate or apply suggestions.
- Choose **Save configuration** only after reviewing the draft. **Save & Run** also opens review, whose final action is **Save configuration & Run**. Failed resolution or save must leave the draft available for correction.

Reload the same destination and reopen review. Confirm that edited values and intentional inheritance survived, while custom exception flags, inactive schedules, and unrelated settings were retained. Resolved configuration/export evidence verifies the inputs prepared for the engine; simulated outcomes require separate run evidence.

## Acceptance record — analyst signoff pending

### Automated evidence, 2026-10-15

The browser walkthrough used a disposable synthetic workspace under `var/epic862-browser`, separate from user workspaces. It exercised scenario headcount edits, tiered-match edits (3.5% and 4% maximum formula match at a 5% employee threshold), automatic enrollment off/on, explicit review/save, and reload. Saved YAML retained a custom unknown setting and an independent terminated-new-hire eligibility exception. A separate workspace-default edit from 2% to 2.5% growth survived review/save/reload without replacing the scenario's 3% override.

Desktop and 768-pixel layouts were inspected. The narrower layout stacks configuration navigation above the editor. Review Escape returns focus to its trigger; Shift-Tab and Tab wrap inside the dialog while skipping hidden details. These are targeted browser checks, not a complete accessibility audit or a measured analyst usability study.

The combined validation passed 232 frontend tests and 169 targeted Python tests, including the numeric-entry refinement. TypeScript, ESLint, Ruff, and the production frontend build were checked; the build retains its existing bundle-size and mixed-import warnings. Three isolated integration cases separately cover the nine-run mapping matrix and two-year enrollment modes; exact outcome evidence is in the field inventory. No shared development database was used.

Reproduce the automated checks with `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build` from `planalign_studio/`. From the repository root with the virtual environment active, run `pytest tests/api/test_configuration_preview.py tests/api/test_openapi_contract.py tests/api/test_route_auth_coverage.py tests/unit/orchestrator/test_config_export.py tests/test_config_export_match_magnet.py tests/unit/test_issue_669_studio_contract.py tests/test_studio_mapping_audit.py -m 'not integration' -q`. The inventory gives the separate opt-in isolated integration command.

This guide provides a repeatable task script. **Real analyst feedback and signoff are pending.** Automated component/API/browser checks do not establish analyst understanding. No before/after usability timing or baseline improvement is claimed here.

For each task, record participant role, build/SHA, workspace/scenario, initial custom settings, completion, errors, help requests, elapsed time, and explanation accuracy. Use synthetic data and repeat at 1280×800 and a narrower viewport, including keyboard-only navigation.

| Task | Real analyst completion | Errors / help / elapsed time | Explanation accuracy and feedback |
|---|---|---|---|
| 1. Projection, workforce, and pay assumptions | Pending | Not measured | Pending |
| 2. Simple and tiered match, thresholds, eligibility | Pending | Not measured | Pending |
| 3. Scope/rate changes and automatic enrollment off | Pending | Not measured | Pending |

- [ ] Repeat all tasks for workspace defaults and scenario overrides, including preexisting custom/inactive settings.
- [ ] Record final automated browser/API/component evidence separately from analyst observations.
- [ ] Verify review → save → reload values against effective exported engine settings.
- [ ] Confirm keyboard access and both viewport sizes; record any clipping or navigation failures.
- [ ] Obtain analyst feedback on terminology, rate-source choices, and collapsed summaries.
- [ ] Obtain real analyst acceptance and reconcile unresolved issues against the epic checklist.

Remaining boundaries: global summaries defer to per-design resolution; unsupported or unverified saved controls require the review disclosures; model estimates and formula templates are not compliance certification. Any engine mapping change needs its own evidence and, when behavioral, isolated simulation validation. Existing #840 and #856 investigations are not passing correctness baselines. See [the configuration field inventory](configuration_field_inventory.md) for the audited mappings and limitations.
