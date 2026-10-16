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

In **DC Plan**, **Plan provisions** contains **Eligibility and enrollment**, **Employer match**, **Employer core contribution**, and **Automatic contribution increases**. Enrollment behavior assumptions sit beside the relevant enrollment rules and are labeled separately. The remaining **Employee behavior assumptions** panels contain **Starting employee contribution rates** and **Response to the employer match**.

Open **Employer match**, enable **Employer Match Formula**, and select **Deferral-Based (match varies by deferral %)** under **Match Calculation Mode**. In **Match Tiers (editable)**, enter one tier from 0% to 4% with a 100% match rate. This represents “100% on the first 4%”: an employee contributing 4% reaches a formula maximum employer match of 4% of eligible compensation.

For a familiar tiered variant, use:

| Employee contribution interval | Employer match rate | Employer contribution at the interval maximum |
|---|---:|---:|
| 0% to 3% | 100% | 3% of eligible compensation |
| 3% to 5% | 50% | An additional 1% |

This is “100% on the first 3%, plus 50% on the next 2%.” The employee rate needed for the full match is **5%**; the formula maximum employer contribution is **4%**. Boundaries are cumulative: the second tier ends at 5%, not 2%. Use **+ Add Tier** for another interval. Template names describe starting formulas; they do not verify safe-harbor status or other plan requirements.

These examples assume eligible compensation and an employee meeting match eligibility. Applicable contribution limits and configured caps still apply. Check **Match eligibility** independently from **Core eligibility**: service, annual hours, the year-end employment requirement, terminated hire-year employees, and terminated experienced employees each matter. The three employment flags are independent; changing the year-end requirement does not change the exceptions. An allowed exception can qualify despite that requirement, while other service/hours rules still apply.

**Custom policy combination** identifies a retained combination of those flags. Review the displayed new-hire service waiver and any per-design scope notice. Global summaries are not universal rules for every assigned plan design. Other match modes, core schedules, integration settings, and inactive schedules remain saved when another mode is selected.

Match service, hours, and employment requirements apply directly; there is no
separate eligibility switch. Zero service or hours means no minimum for that
requirement. For older configurations, the editor shows the effective rule
(zero service, 1,000 hours, active at year-end, no termination exceptions),
rather than inactive detailed values. Editing a requirement saves the complete
displayed policy, so other inactive requirements cannot become active silently.
Opening or saving an unchanged configuration preserves its existing policy.
Previously saved detailed values remain in the underlying configuration for
inspection; review describes the effective requirements.

Finish by explaining the employee threshold, employer formula maximum, and the separate match/core eligibility rules.

## Task 3: change automatic enrollment, then disable it

In **Eligibility and enrollment**, **Automatic enrollment** groups the switch,
default deferral, opt-out delay, and employee opt-out assumptions. **Shared
enrollment rules** groups the waiting period, enrollment delay, scope, hire
cutoff, and **Voluntary enrollment assumptions**. Plan rules and employee behavior
assumptions are labeled within each group. Shared rules and voluntary assumptions
remain editable when automatic enrollment is off.

Enabled feature settings open by default. Collapse them manually if desired;
unrelated edits do not reopen them. Turning a feature off collapses its settings,
and turning it back on opens them. Enable checkboxes stay outside the collapsed
settings. Shared rules and contribution limits remain accessible because they
can affect other enabled features.

1. Set **Eligibility waiting period**. Each modeled month is 30 days: 3 months resolves to 90 days. An existing day-based setting can display a fractional month count, such as 1.5 months for 45 days; leaving it unchanged preserves the existing duration. Edits use whole modeled months.
2. Review **New-hire enrollment delay after eligibility**. The hire-year enrollment branch schedules from eligibility plus that delay; the continuing-employee branch uses January 15. Hire-year opt-outs add **Modeled opt-out delay**; the continuing-employee opt-out branch uses June 15. Voluntary enrollment before the automatic-enrollment deadline follows its separate decision timing.
3. Compare **Enrollment Scope** choices. **New Hires Only** uses **Hire Date Cutoff** in the first projection year, then current-year hires in later years. **All Eligible Employees** still respects the inclusive hire cutoff every year. Already enrolled employees are excluded from new enrollment decisions; plan eligibility still applies.

Each new-hire decision has its own **Rate source**: voluntary enrollment under
**Shared enrollment rules**, and opt-outs under **Automatic enrollment**:

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

## Acceptance record — analyst signoff received

### Guided analyst walkthrough, 2026-10-16 — signed off; coverage gaps retained

Nick, Lead Developer / VP of Analytics, explicitly signed off with “i signoff”
after the walkthrough fixes in PR #885 were merged. This approves the revised
configuration experience and the separately discussed match-response behavior.
Earlier pending-acceptance notes below describe the progression of the session;
this signoff supersedes requests for final analyst approval. It does not claim
that unobserved scenario repetitions, keyboard navigation, narrower layouts, or
independent compensation explanations were tested.

Participant: Nick, Lead Developer / VP of Analytics. Starting build: `fa4ca503`.
The session uses a copy of the synthetic fixture under
`var/epic862-acceptance/workspaces`, with the initial files retained separately.
Workspace: `23ee7591-735a-44d4-953e-6144539b3980`; available scenario:
`cd9f0164-2976-44fa-b0f4-d0ef3a2a0c31`. The fixture includes a scenario growth
override, a custom audit note, and an independent terminated-new-hire match
eligibility exception. These observations are participant reports, separate from
automated checks; no before/after timing improvement is claimed.

- **Task 1:** Nick reported 20 seconds and confirmed all seven requested values
  survived review/save/reload, with nothing confusing. He identified 2027, 2028,
  and 2029 as the projection years and described growth in terms of year-end
  active headcount CAGR. He had not examined pay-event output, so compensation
  behavior remains unverified. The facilitator explained the understanding
  questions before these responses; this is guided feedback, not an independent
  comprehension result. Role and timing are self-reported.
- **Task 2:** Nick reported 30 seconds before save was blocked by “This schedule
  contains custom row settings.” Completion and explanation acceptance remain
  pending. A regression reproduced the blocker when editing a two-tier match
  into one tier after YAML reordered object keys. The local fix compares object
  values independently of key order while retaining array order and protection
  for genuinely ambiguous custom metadata. Nick confirmed the fix helped and
  reached review, then reported that raw JSON tiers and internal template names
  were confusing. The local review now labels the employer match formula and
  template and describes tier percentages in plain language. Save/reload and
  acceptance of the revised review remain pending; no retry time was reported.
  Nick subsequently questioned the eligibility activation language and stated
  that service/hours requirements and the year-end employment checkbox should
  apply directly. The local editor now projects effective legacy requirements
  and saves the complete displayed policy when one of them is edited. Review
  describes actual requirements rather than presenting eligibility as off.
  This change still requires analyst acceptance.
  On entering a one-year match service requirement, Nick reported review rows
  showing six newly stored values and an eligibility Off → On transition. The
  local review now compares effective match requirements: unchanged inherited
  hours/employment rules are omitted, and the new-hire service exemption is
  described under indirect effects. Raw storage details remain in the complete
  configuration. Acceptance of this revised comparison is pending.
- **Task 3:** Nick reported 60 seconds. His pasted review showed automatic
  enrollment changing On → Off, scope changing All eligible employees → New
  hires only, and voluntary enrollment changing 65% → 30%. The preexisting
  opt-out rate was 8%. Visual confirmation of the enrollment split and inactive
  controls remains pending. A simulation attempt failed because the walkthrough
  fixture pointed to `invariant_census.csv` where staging requires Parquet. This
  was a facilitator setup error, not evidence of an enrollment-control defect.
  The 150-row synthetic census was converted to workspace-local Parquet and the
  base census path corrected; the failed run archive was preserved.
  Replacement API run `7e2ae66f-b542-4b62-a167-80d4284ec0e6` completed successfully
  for 2027–2029. The scenario retains its explicit automatic-enrollment On
  override, so this run validates the census repair, not the workspace's Off
  setting or analyst understanding of inheritance.
  Nick then ran scenario `3c1d49fb-871b-43fd-8375-6378d0201f7e` with the scenario
  override also Off and reported a 20% Auto Enrolled chart slice. Read-only
  inspection confirmed the exported flag was false and the enrollment
  accumulator contained no automatic enrollments. Analytics incorrectly counted
  38 `not_participating - not auto enrolled` rows by matching the word `auto`.
  Method counts now require enrollment and exclude nonparticipating statuses.
  All 77 analytics/API tests passed, including three regressions. After restarting
  the isolated API, the same saved run returned 0 automatic, 110 voluntary, and
  46 census participants (71% voluntary / 29% census in the pie). No simulation
  data was changed or rerun for this reporting fix. Nick confirmed the refreshed
  chart looked good and showed Voluntary 71% / Census 29%, with no automatic slice.
  Nick then found it confusing that waiting period and enrollment delay remained
  editable with automatic enrollment off. The panel now separates automatic-only
  controls from shared enrollment rules and explicitly explains their voluntary
  enrollment use. This presentation change does not change engine mappings.
  At Nick's request, opt-out assumptions were then moved into Automatic
  enrollment and voluntary assumptions into Shared enrollment rules. The
  separate Enrollment and opt-outs panel was removed; behavior assumptions
  remain labeled distinctly from plan rules within the combined panel.
  Nick also requested enabled sections open by default, manual collapse, and
  automatic collapse when disabled. This behavior now applies to enrollment,
  match, core, escalation, and match-response settings; enabling checkboxes and
  shared voluntary enrollment limits remain accessible. Nick challenged the
  coupling between annual escalation and match response: an employee should be
  able to reach an 8% full-match threshold with a 6% annual escalation cap.
  Match response now uses the full-match threshold independently of that cap,
  retaining the existing IRS rate-equivalent limit. When both events occur,
  annual escalation cannot reduce the match-response rate. The escalation cap
  now collapses with annual escalation and is inactive when escalation is off.

  Three isolated two-year integration cases verified the 8% match / 6% escalation
  combination with escalation on, off, and explicit per-design parameters.
  Full-match responders reached 8% and retained it in year two; simultaneous
  escalation did not reduce their rates, and annual escalation events stayed
  within 6%. The existing first-year-only match-response regression also passed.
  Reproduce the focused behavioral checks with:
  `source .venv/bin/activate && pytest tests/test_studio_mapping_audit.py tests/integration/test_match_response_fact_integration.py -k match_response -q`.
  Frontend validation passed 329 tests, type checking, lint, and the production
  build (existing bundle-size and mixed-import warnings remain).

Scenario-override repetition, keyboard/navigation observations, narrow-layout
feedback, and remaining task-level effective-export verification remain pending.
Final analyst signoff has been received; these coverage gaps remain explicit.

Automated validation of the walkthrough fixes: 321 frontend tests, TypeScript,
ESLint, production build, and 149 targeted Python tests passed. The build retains
the existing bundle-size and mixed-import warnings. The opt-in
`test_production_displayed_match_eligibility` also passed three isolated
2025–2026 simulations: legacy and explicit displayed requirements produced the
same annual headcounts and match totals; a 10,000-hour requirement produced zero
match in both years. Workspace/scenario preview tests confirmed dormant legacy
values stay stored while the displayed policy governs export. Reproduce with
`PLANALIGN_MAPPING_AUDIT=1 pytest tests/test_studio_mapping_audit.py::test_production_displayed_match_eligibility -q`
from the repository root with the virtual environment active. This automated
evidence does not replace the remaining analyst tasks.

### Automated evidence, 2026-10-15

The browser walkthrough used a disposable synthetic workspace under `var/epic862-browser`, separate from user workspaces. It exercised scenario headcount edits, tiered-match edits (3.5% and 4% maximum formula match at a 5% employee threshold), automatic enrollment off/on, explicit review/save, and reload. Saved YAML retained a custom unknown setting and an independent terminated-new-hire eligibility exception. A separate workspace-default edit from 2% to 2.5% growth survived review/save/reload without replacing the scenario's 3% override.

Desktop and 768-pixel layouts were inspected. The narrower layout stacks configuration navigation above the editor. Review Escape returns focus to its trigger; Shift-Tab and Tab wrap inside the dialog while skipping hidden details. These are targeted browser checks, not a complete accessibility audit or a measured analyst usability study.

The combined validation passed 232 frontend tests and 169 targeted Python tests, including the numeric-entry refinement. TypeScript, ESLint, Ruff, and the production frontend build were checked; the build retains its existing bundle-size and mixed-import warnings. Three isolated integration cases separately cover the nine-run mapping matrix and two-year enrollment modes; exact outcome evidence is in the field inventory. No shared development database was used.

Reproduce the automated checks with `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build` from `planalign_studio/`. From the repository root with the virtual environment active, run `pytest tests/api/test_configuration_preview.py tests/api/test_openapi_contract.py tests/api/test_route_auth_coverage.py tests/unit/orchestrator/test_config_export.py tests/test_config_export_match_magnet.py tests/unit/test_issue_669_studio_contract.py tests/test_studio_mapping_audit.py -m 'not integration' -q`. The inventory gives the separate opt-in isolated integration command.

This guide provides a repeatable task script. **Final analyst signoff has been received; the coverage gaps above remain open.** Automated component/API/browser checks do not establish analyst understanding. No before/after usability timing or baseline improvement is claimed here.

For each task, record participant role, build/SHA, workspace/scenario, initial custom settings, completion, errors, help requests, elapsed time, and explanation accuracy. Use synthetic data and repeat at 1280×800 and a narrower viewport, including keyboard-only navigation.

| Task | Real analyst completion | Errors / help / elapsed time | Explanation accuracy and feedback |
|---|---|---|---|
| 1. Projection, workforce, and pay assumptions | Workspace review/save/reload confirmed | 20 seconds; no reported errors or confusing controls; understanding questions explained by facilitator | Years and growth explained; pay behavior not independently assessed |
| 2. Simple and tiered match, thresholds, eligibility | Match and eligibility review accepted; full task coverage pending | Initial attempt blocked at 30 seconds; custom-row detection and review/eligibility presentation corrected; retry time not measured | Nick accepted readable formulas and requirements and gave final signoff; tiered-entry repetition pending |
| 3. Scope/rate changes and automatic enrollment off | Workspace edits and scenario Off run verified; corrected result chart accepted | 60 seconds; facilitator census setup repaired; false auto-enrollment chart slice corrected | Nick confirmed Voluntary 71% / Census 29%; editor inactive-control observations and scope explanation pending |

- [ ] Repeat all tasks for workspace defaults and scenario overrides, including preexisting custom/inactive settings.
- [ ] Record final automated browser/API/component evidence separately from analyst observations.
- [ ] Verify review → save → reload values against effective exported engine settings.
- [ ] Confirm keyboard access and both viewport sizes; record any clipping or navigation failures.
- [ ] Obtain analyst feedback on terminology, rate-source choices, and collapsed summaries.
- [ ] Obtain real analyst acceptance and reconcile unresolved issues against the epic checklist.

Remaining boundaries: global summaries defer to per-design resolution; unsupported or unverified saved controls require the review disclosures; model estimates and formula templates are not compliance certification. Any engine mapping change needs its own evidence and, when behavioral, isolated simulation validation. Existing #840 and #856 investigations are not passing correctness baselines. See [the configuration field inventory](configuration_field_inventory.md) for the audited mappings and limitations.
