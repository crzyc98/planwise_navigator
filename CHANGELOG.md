# Changelog

All notable changes to PlanAlign Engine will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Studio now asks for the census as-of date when you import a census, prefilled with December 31 of the census year read from hire dates. The date is saved with the file and moves with it when you switch censuses with Use as Census. A rolled-forward census gets December 31 of its bridge year. Rows marked inactive with no termination date now leave the workforce on this date instead of the inferred plan-year end. Censuses imported earlier keep today's inferred date.

### Fixed

- Workspace sync no longer stores or shares the remote's access token in the sync settings file, and checks the remote address before every push and pull.
- Calibration requests from Studio must name a workspace; file paths are no longer accepted by the API.
- Any imported file in a workspace can now be deleted from Studio's imported files list. Deleting used to depend on a creator label that Studio never set, so it only worked for files recorded under the default label.
- Files PlanAlign writes are now private to the account running it, and workspace exports and calibration scratch files are removed when they are no longer needed.
- Calibration, backtest and optimizer jobs now wait in the same server-wide queue as simulations so only one heavy job runs at a time by default, and starting too many queued jobs at once is refused with a clear message instead of overloading the machine. Parameter fits run no simulation, so they still start straight away.
- When `PLANALIGN_API_TOKEN` is set, Studio now shows a sign-in screen and asks for the token once, instead of having the token built into the page. Sessions last 12 hours (`PLANALIGN_API_SESSION_TTL_HOURS`). `VITE_PLANALIGN_API_TOKEN` is no longer used, and live run progress no longer accepts the token as a `?token=` URL parameter; scripts should send an `Authorization: Bearer` header.
- Studio now bundles its font locally instead of loading it from Google, so it works offline and behind a corporate firewall (#1189).
- The age band, tenure band, turnover, opt-out, deferral segment, and census analysis tools now give the same "Invalid census file path" answer for any location outside the workspaces folder, whether or not a file exists there.
- The interactive API documentation pages (`/api/docs`, `/api/redoc`) and schema (`/api/openapi.json`) now require the API token when `PLANALIGN_API_TOKEN` is set, and `/api/health` now returns fixed status messages instead of server file paths or raw error details (#1188).
- The API server now refuses to start if `PLANALIGN_API_TOKEN` is set to an empty, blank, or shorter-than-16-character value, and empty tokens can never pass authentication (#1187). Leaving the variable unset still works as before for local use.
- Removed unused internet connectivity checks that pointed at external sites (`httpbin.org`, `google.com`, `github.com`), keeping PlanAlign free of unexpected outbound HTTP calls (#1192).
- A scenario name or warning that contains text like `{{ body }}` now appears as written in the HTML and PDF scenario report, instead of being replaced with report content.
- The census path checks in Studio now give the same "Invalid census file path" answer for any location outside the workspaces folder, whether or not a file exists there.
- Importing a workspace archive is refused when it would unpack to more than 10 GB in total, 4 GB for one file, or 10,000 files, so a small crafted archive can no longer fill the disk. The limits can be changed with `PLANALIGN_API_IMPORT_MAX_UNPACKED_BYTES`, `PLANALIGN_API_IMPORT_MAX_MEMBER_BYTES` and `PLANALIGN_API_IMPORT_MAX_MEMBER_COUNT`.
- The optimizer and ensemble pages now only read and save files inside PlanAlign's own folders (the config folder, optimizer runs, ensembles and workspaces), and turn down any other location on the server.
- Studio now refuses a workspace or scenario link with a malformed name instead of reading or saving files outside that workspace, and a census upload to a workspace that does not exist is refused instead of creating an empty folder.
- A scenario can now set promotion raises to "deterministic", so every promoted employee gets exactly the configured raise with no random spread. This documented option was previously rejected as invalid.
- The compensation growth solver only reads a census stored inside the workspaces folder, and a census upload keeps its original file under a fixed name, so an unusual filename can no longer affect where it is saved.
- Studio now rejects a scenario or plan design id with unsupported characters, an unknown auto-enrollment scope or match template, or a census path outside the workspaces folder when you save or start a run, instead of failing partway through the run.
- Imported workspaces now only use data files stored inside the workspace, and archive imports reject entries with unsafe paths or links.
- The census tie-out no longer counts impossible employer match or core dollars in the census total (#1262). A census row whose match or core amount is negative, or above that person's gross pay, is left out of the "Employer match" or "Employer core" census value, and the row's message says how many rows were left out. These are the same rows Census Analysis flags as impossible. Tie-outs for censuses without such rows are unchanged.
- A census row marked inactive with no termination date no longer starts the simulation as a current employee (#1249). It gets the census plan-year end as an imputed termination date, so the starting headcount matches Census Analysis, and the run shows one warning with the number of rows and the date used. Censuses whose active flags and termination dates agree give the same results as before.
- Batch and CLI runs now use the seed's new-hire pay settings (25th–45th percentile and a 0.98–1.10 market multiplier by level) instead of falling back to the 50th percentile and 1.0 (#1196). Any scenario not named `default` was affected; Studio runs were not. Batch and CLI scenarios that leave `hire_pay_ratio` unset will see lower new-hire pay. The new-hire cost columns in `int_workforce_needs` also read the seed's multiplier now, so they are no longer about 9% too high (#1200).
- A run now stops before anything is built, with a clear message, when the census file has deferral rates that are not a number from 0 to 1, such as 6, 15 or `6%` entered as percentages (#1263). The message gives the number of rows and the expected form (0.06 for 6%). Before, a rate of 10 or more crashed the run partway through with a decimal cast error, and a rate between 1 and 10 ran with parts of the engine reading it differently. Censuses with such rates, including negative ones, no longer run until the file is fixed.
- Studio links on the Simulate page, the scenario's run page, the run health panel and the provenance report now stay in the current workspace (#1198). Before, they dropped the workspace from the address, so Studio reopened whichever workspace the browser last stored, which could be another client's when two tabs were open.
- A simulation run no longer fails when recording its provenance fails, for example on a full disk (#1197). The run finishes and the provenance report lists the capture as incomplete.
- When a year's event counts can't be read during a run, the provenance report now says the counts are unavailable instead of showing zero events for that year (#1199). The year's workforce reconciliation leaves hires and terminations blank instead of using zero.
- Moving quickly between scenarios no longer leaves the previous scenario's details and run history on the simulation detail page (#1201).
- Switching workspace on the NDT page now clears the scenarios and plan design picked in the previous workspace (#1202), so the page no longer shows a spurious "unable to load years" error.
- The census import wizard now says when saving the field mapping fails or the mapping suggestions can't load (#1203). Before, the spinner stopped with no message.
- Census import now reads `f` as no in yes/no columns, matching `t` for yes (#1250). Before, a column coded `t`/`f` was rejected on its `f` rows.

### Security

- Updated locked Python dependencies (`Pillow`, `WeasyPrint`, `GitPython`, `deepdiff`, `anyio`, `starlette`, `urllib3`, `certifi`, `brotli`, `py7zr`, `python-multipart`, `sqlparse`, and dev tooling) to patched versions, clearing open Dependabot advisories and retiring the resolved `sqlparse` and `black` audit exceptions (#1191).

## [3.6.0] - 2026-11-20

### Added

- Census Analysis now flags rows whose columns contradict each other (#1260): contributions above pay, negative contributions, a birth date on or after the hire date, a termination before the hire, dates after the census year, ages at hire under 14 or over 100, contributions well above the stated deferral rate or not matching the pre-tax/Roth/after-tax split, contributions above the IRS 402(g) limit with catch-up, and pay far above the rest of the file. Each flag shows a row count only.
- Simulation runs now warn when the census has impossible or implausible values (#1262), using the same row checks as Census Analysis. The run's Activity Feed and log show one warning naming the rules that flagged rows, with row counts only. Results do not change.
- The census import wizard now checks the whole file, not just the first 100 rows (#1261). The preview step lists each Census Analysis check that found problems, with impossible values shown apart from warnings, and the counts match Census Analysis after import. You can download the flagged rows as a CSV of row number and employee ID, with the checks each row failed. If the checks can't run, the preview step says why. None of these checks block the import. The old fixed compensation range ($1,000 to $10M) is gone; the shared checks for pay at or below zero and pay far above the rest of the file replace it.

### Fixed

- The minimum wage preview now rejects two steps in the same calendar year, as saving a scenario already did. Before, a direct API call could preview a schedule that could not be saved or run.

## [3.5.1] - 2026-11-19

### Fixed

- An ensemble job now removes its temporary work folder before it reports that it has finished (#1215). Before, a job could read as completed for a moment while the folder was still there.

## [3.5.0] - 2026-11-19

### Added

- The census can give each hourly person an hourly rate as `hourly_rate`, `hours_worked` (all paid hours in the census year) or `scheduled_hours_per_week`, for the coming minimum wage change (#1230). `hourly_rate` is preferred and wins when a row has more than one. Studio's census import maps the new columns and reports how many people have a rate, how many have none, and how many rates fall below $7.25 or above $500 an hour; those people stay in the census with no rate. A census roll-forward carries each rate, moved with pay. A census without these columns gives the same results as before.
- A scenario can schedule minimum wage steps under `compensation.minimum_wage`, each a new minimum hourly rate and an effective date, at most one per calendar year (#1229). On that date everyone on the census whose hourly rate is below the minimum gets a raise of the minimum divided by their rate, less one, recorded as a `minimum_wage` event that shows the old and new rate. Hours stay as they were, so pay rises in proportion; the floor applies after any merit raise, COLA or promotion on or before the date, sits outside the raise budget, and deferrals, match and core follow the higher pay from the date. A person's rate moves with their later raises, so nobody is raised twice. `fct_minimum_wage_steps` reports, per step, how many people were raised, how many census staff had no rate and were left alone, and the annual pay added. Simulated hires and acquired groups have no hourly rate and are not covered, so the effect fades as census staff turn over. A run rejects a minimum wage when no census row has a rate, and warns and skips a step dated outside its years. Scenarios without a minimum wage produce the same results as before.
- Studio can set a minimum wage increase in the compensation settings: a new hourly rate and effective date, with another step a year or more later if needed (#1231). The block is off when the scenario's census has no hourly rates and says which columns the sponsor needs to send. Before a run it estimates from the census how many people are below each new minimum, how many have no rate, and the annual pay added. Results show by year how many people were raised, the pay added, how many had no rate or were simulated hires, and an estimate of the added pay still on payroll at year end; employer contributions come from comparing with the same scenario without the minimum wage in Cost Comparison, which now says when only one side has one. Scenarios without a minimum wage look and run as before.
- Studio has a census file guide: Import Data → "What should the census include?" (also in the settings menu and Configure → Data Sources). It lists the five required columns and every optional column the import wizard maps, grouped by purpose, with its format, the header names Studio recognises and what Studio does when it is left out. It has a Download template button (a CSV with every column and one made-up row) and a Copy column list button for an email to a plan sponsor. The page reads the census column list from the API (`GET /api/census/schema`), so new columns appear without a Studio change.
- Each acquisition in `workforce.acquisitions` can set how the DC plan treats its members (#1227): `service_credit` (`prior_service`, the default, or `acquisition_date` to start service at zero), `plan_entry` (`acquisition_date`, the default, or `waiting_period` to apply the plan's normal waiting period from that date), and `starting_participation_rate` with `starting_deferral_rate` to start a set share of members deferring at that rate instead of going through auto-enrollment. Service credit acts through `current_tenure`, so it drives employer contribution eligibility, vesting and service-based match, core and points formulas. **Behaviour change for existing acquisitions:** with the settings unset, members now enter the plan on the acquisition date with their prior service, instead of waiting out eligibility as new entrants. Members also form their own cohort for opt-out and flat-rate enrollment draws, so contributions for everyone else match a run without the acquisition through the join year. Scenarios without acquisitions are unchanged.
- Each acquisition can override who its members are (#1228): `average_pay` (an amount) or `relative_pay` (pay relative to existing staff, e.g. 0.9 for 10% below), `average_age` and `average_service`. Pay is scaled by one factor so the group's spread is kept; age and service shift every member by whole years to the target, with age at least 18 and service between 0 and age minus 18. Unset, members mirror existing staff as before.
- Studio's Workforce Parameters page has an Acquisitions list (#1228). Each group takes a name, headcount and effective date, the three plan settings (service credit, plan entry, starting participation) and, under "Who they are", optional average pay (a percent of staff pay or an amount), age and service; by default a group mirrors existing staff. Studio says when a date falls outside the simulated years, a name repeats or a value is out of range, and keeps any setting it does not edit when saving. A preview lists who joins when, with an estimated annual pay from the census's average active pay. In results, acquired members are their own bar in the Event Distribution chart and their own Acquired step in the run report's workforce reconciliation, and a table splits pay and employer cost between acquired and existing staff by year. Comparisons say when only one scenario has acquisitions or a group's settings differ. Scenarios without acquisitions look the same as before.

## [3.4.0] - 2026-11-18

### Added

- A scenario can add acquired groups under `workforce.acquisitions`, each with an id, a headcount and an effective date (#1226). A run whose years do not include that date warns and leaves the group out. On that date the group joins on top of organic hiring, made to look like the sponsor's active staff (age, service, level, pay and hours), and never takes new-hire turnover. Members carry an `acquisition_id` in `fct_yearly_events` and `fct_workforce_snapshot`. Scenarios without acquisitions produce the same results as before. In this first version members get no termination, raise or promotion in the year they join, and their starting pay is copied from before that year's raises, so they trail continuing staff by one raise. They enter the plan as new entrants until #1227 adds the options, and Studio support is #1228.
- On the Scenario Diff page, each changed setting has a "Use in …" button on both sides that copies that one value into the other scenario's saved settings. Rerun that scenario to see the effect. Pay settings are saved in both forms Studio keeps (decimal and percent). Settings that can't be copied this way show no button: the census path, whole seed tables, and engine DC plan sections that Studio's DC plan settings override. Copy the DC plan row instead.

### Fixed

- The Scenario Diff page no longer lists the scenario name (`simulation.name`) as a changed setting.
- Comparisons no longer call two results like-for-like when they differ in the engine's voluntary enrollment rate, new-hire opt-out rate or deferral spread lift (`enrollment.auto_enrollment.*`). These now count as employee behaviour.
- Run changes show the maximum voluntary deferral and match cap in the right units (75%, not 0.75%).

### Changed

- The calibration page now opens on a short form: set employee growth and average pay growth, then Calibrate. It always solves raises and hire pay together, and holds the scenario's termination rates and new-hire ages as they are, showing them read-only. Scenario choice, other solve modes, age and termination edits, and search limits move to a collapsed Advanced settings section. Applying a result no longer copies one scenario's termination rates and new-hire ages onto every scenario unless you changed them under Advanced settings.

### Fixed

- Calibrating an older workspace with "Raises and hire pay together" no longer fails with a bare error ID. That mode needs one pay scale for staff and hires, which older workspaces keep off. Studio now warns about this in the calibration panel and offers to turn it on for the scenario, re-run the scenario, and calibrate in one step. The calibration service also explains which setting to turn on.

## [3.3.0] - 2026-11-16

### Added

- Cost Comparison can export the comparison report as PDF or PowerPoint for the scenarios and anchor on the page, and the Overview report button now offers the same two formats. If the server can't create a report because a component isn't installed, Studio says which one.
- The API can now compare a scenario's census with its first simulated year (`GET /api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/census-tie-out`). For active headcount, eligible count, participation, average deferral, total pay, employer match and employer core it gives both values under one definition, the difference, a tolerance that allows for the configured growth and raises, and whether the row ties, has a gap or isn't in the census, with a line on what to check. Total pay, employer match and employer core count everyone paid in the year, including people who left, so the census total is what the sponsor paid; headcount, eligible count and the rates count employees active at year end. It reads the census archived with the run, not the workspace's current file.
- Overview has a Census Tie-out panel for the selected scenario. It shows each metric's census-year and first-simulated-year values, the difference and whether it ties, with a line on what to check for each gap, and names the census file and years it used. You can mark one scenario per workspace as the current plan from the panel, and the Scenarios list shows a Current plan badge on it. On other scenarios the panel says gaps are expected if the scenario changes the plan design and shows no gap count.
- When the scenario marked as the current plan has census tie-out gaps, Run Health shows one line naming the rows that differ, linking to the Overview panel. A scenario report that includes the marked scenario, on its own or in a comparison, shows its tie-out table after the figures. Other scenarios show neither. Neither ever fails or blocks a run.
- Studio's API can now run a seed ensemble for a scenario: it estimates the run count, time and disk first, then queues the ensemble behind other simulations, reports progress per seed, and can cancel it. Each ensemble's results stay in the workspace, and a run where some seeds fail is reported as partial. `planalign simulate --seeds` also takes `--parallel` to cap how many seeds run at once.
- Cost Comparison shows how much each employer cost moves across simulation seeds when the compared scenarios have seed ensembles: P10–P90 beside each annual and total cost, and the range of the difference from the anchor, taken seed by seed (for example, "saves $40K–$80K"). An ensemble run before the scenario's settings changed shows no range, ensembles on different seeds or years aren't paired, and the page says why in each case.
- Studio's Ensembles page can now run an ensemble: pick a scenario and seed count, review the estimated time and disk, then follow its progress, cancel it, or open its results with one click. No terminal or file path needed; opening a database by path moved under Advanced.
- Cost Comparison can download its tables as a small Excel workbook (Summary). It has the figures the page shows for the current view (anchor, cohort, gross or net of forfeitures, match/core split), a by-year sheet, and a Notes sheet with the view settings and each scenario's run. Unavailable figures are blank cells with a note, never $0.
- Points-based core contributions can pay a flat rate until an employee reaches a minimum service, for example 1% until three years of service and the points table after that (#1222). It is off unless set, so existing scenarios produce the same results.

### Changed

- New Studio workspaces now model 2026–2030. Existing workspaces and scenarios keep their years, and the CLI's default config is unchanged.
- The scenario report (PDF, PowerPoint, HTML) now leads with each plan design in plain words and its employer cost against an anchor scenario, followed by cost by year, cost as % of capped pay, participation and average deferral, with cost definitions as notes and provenance in an appendix. Pick the anchor with `anchor=` on the report download or `planalign report --anchor`; a selected scenario without a usable result is listed as missing instead of dropped. Headcount and average pay are no longer in the report. A custom `--template-dir` template now fills only `{{ title }}`, `{{ body }}` and `{{ trace }}`; one written for the old `{{ rows }}`, `{{ charts }}`, `{{ provenance }}` or `{{ warnings }}` placeholders is rejected with an error instead of rendering without figures.
- The PowerPoint scenario report now uses real PowerPoint tables and an editable line chart (data opens in PowerPoint's chart editor) instead of text boxes and a picture, on 16:9 slides; long tables continue on a second slide. Figures match the PDF.

### Added

- Studio's comparison pages now say whether each scenario is like-for-like with the anchor, meaning only its plan design differs (#1178). When the census, seed, simulated years, engine version or build, model seed tables, or a workforce, pay or employee-behavior setting differs, the page names each difference with both values, so part of the cost difference isn't read as the plan change. When a result didn't record enough to check, it says it can't tell. Scenarios and Overview show which engine version each result ran on and mark an older one with a one-click rerun, and comparison exports record each scenario's engine version and verdict. Overview also lists what changed since a scenario's previous run, with both values, and comparison pages note a scenario whose assumptions or inputs changed since then.

### Fixed

- Configs now reject scenario and plan design ids that use characters other than letters, digits, spaces and `_ . : -` (up to 128 characters), and an auto-enrollment scope other than all eligible employees or new hires only (before, an unknown Studio scope silently auto-enrolled nobody). A Studio run's census must be inside the workspaces folder, and a census path can't contain a quote. The match template must be one of simple, tiered, stretch, safe harbor or QACA, the escalation effective date must be a real `MM-DD`, and age and tenure band labels can't contain a single quote. Existing scenarios use values that already pass, so their results don't change.
- Downloading or deleting an imported file now only touches files inside that workspace's `data/` folder. Files in a workspace imported from another machine's export can now be downloaded, because their stored paths are matched to the new workspace's copy.

### Security

- The API now rejects HTTP and WebSocket requests whose `Host` header isn't allowlisted (`localhost`, `127.0.0.1`, `::1` and the bind host by default). Set `PLANALIGN_API_ALLOWED_HOSTS` to serve the API under other names. Studio needs no change.

### Fixed

- Cost Comparison's net view with existing employees grandfathered now subtracts forfeiture offsets from the grandfathered cost each year, not the ungrandfathered cost. A net total whose gross total is unavailable, and an offset total with no measurable year, now read as unavailable instead of a dollar figure.

## [3.2.0] - 2026-11-12

### Changed

- New-hire ages must be at least 21 (#1040). Calibration's age editor, calibration requests and scenario configs reject younger ages, so no simulated hire is too young for a plan's minimum age. The defaults and Match Census already start at 22, so default results don't change. A plan's minimum age is likewise capped at 21. A saved scenario with a new-hire age under 21 must be updated before it runs: use Match Census, or edit the ages in Calibration and apply. Census employees are still taken as given, whatever their age; see the census file format guide.
- Nondiscrimination tests now say a $0-pay employee is a data problem to fix in the census or run (#1036). Every employee has pay, so these rows are still never dropped from ADP, ACP, 401(a)(4) or 415 testing.

### Added

- Studio's DC Plan Analytics now shows estimated pre-tax and Roth totals beneath employee deferrals, in both the single-scenario cards and the comparison table. They come from each run's assumed source split (85% pre-tax / 15% Roth by default, plus any required Roth catch-up the run modeled), so they are estimates, not payroll data.

### Fixed

- ACP and 401(a)(4) results now say when an employee's HCE status used current pay because prior-year pay was missing, as ADP already did (#1037). All three report how many employees were classified on observed prior-year pay versus current pay. Employee details no longer show current pay as prior-year pay: `prior_year_compensation` is empty for those employees, and a new `hce_pay_basis` field says which pay was used.

## [3.1.0] - 2026-11-10

### Added

- Studio's Data Import page now warns when the census is more than a year behind the start year, and offers to roll it forward (#1078). Rolling forward simulates the missing year once under the workspace's settings, waits behind any running simulation, then saves the bridge census, lists it in Imported Files and makes it the workspace census. The original census stays listed, so "Use as Census" switches back.

- `planalign census roll-forward` turns a census more than a year old into a bridge census (#1078). It simulates the missing year once under the given settings and saves the employees still active at year-end, with made-up hires flagged as `simulated_employee`. Pay is each person's year-end rate, under the same pay setting as the original census. Starting 2026 from a 2024 census rolled forward to 2025 matched a continuous 2025–2026 run's 2026 hires, terminations and headcount exactly, and its average pay to within 0.3%. Starting 2026 straight from the 2024 census had 17% fewer terminations. Runs now log a warning when the census is more than a year behind the start year.

### Removed

- Removed the Export Format choice from Batch Processing. Studio ignored it, and each run already writes its own Excel results.
- Deleted 238 YAML settings with no effect from setup, compensation, new_hire_compensation, raise_timing, plan_year, plan_eligibility, enrollment, employee_id_generation, optimization, orchestrator, multi_year, deferral_baseline, deferral_rates, corporate_network, and legacy ops. Stopped exporting 11 unread dbt variables and added guards for YAML consumers and exported-variable readers.

### Fixed

- Census staging no longer assumes a 2024 plan year when none is set (#1163). Studio never sets one, so a 2025 census showed its 2025 hires as not yet eligible at the start of the simulation. The plan year now defaults to the census year, and dates set in `setup` still win. On a 2025 study census, the start-of-simulation eligible count went from 3,284 to 4,084 of 4,124 active. Events, enrollment, pay and contributions were unchanged, and a 2024 census gives identical results. A bridge census from `planalign census roll-forward` no longer needs the dates moved.

- Batch Processing now has a Cancel button for each scenario that is waiting or running, and shows cancelled scenarios as Cancelled.

- Studio now runs simulations one at a time (#1086). Runs started while another is in progress wait as queued and can be cancelled before they start. Batches always run in sequence, and Batch Processing no longer shows an execution mode. A server can allow more at once with `PLANALIGN_API_MAX_CONCURRENT_SIMULATIONS`. After an API restart, scenarios left queued or running are marked failed instead of staying stuck.

- Contributions used the year-end deferral rate for the whole year. They now weight each rate by the days it was in effect, using the year's enrollment, escalation, match-response, enrollment-change and deferral-change events (#989). A September enrollee now contributes for about 4 months, not 12. A 07-01 escalation weights the old and new rates about 50/50. A participant enrolled in a prior year who opts out mid-year now contributes until the opt-out. Same-year enroll→opt-out windowing and deferral-change-only results are unchanged. Baseline impact (default config, 2025–2027): employee contributions −0.9%/−0.5%/−0.4% and employer match −0.3%/−0.2%/−0.2%, mostly from mid-year enrollees. With `deferral_auto_escalation.effective_day: "07-01"`: contributions −3.5%/−3.6%/−3.5% and match −0.8%/−1.7%/−1.6%. Event counts are unchanged.

- YAML match formulas were ignored (match always used the tiered default), and optimizer match levers had no effect. Match design now uses `dc_plan.match_tiers` everywhere. The YAML/CLI match-magnet ceiling is now 5%, which earns the full default match, instead of 6%.
- YAML `eligibility.waiting_period_days` was exported under names no model read, so it (and the optimizer's `eligibility.waiting_period_days` lever) had no effect. It now sets the plan eligibility waiting period; Studio's eligibility months still take precedence. The optimizer's `vesting_schedule` lever is removed because the simulation does not model vesting.

- Editing a legacy match eligibility rule in Studio no longer stores a new-hire service waiver. A later minimum-service edit now requires hire-year employees to meet service instead of keeping them match-eligible.
- Clearing the auto-enrollment hire-date cutoff in Studio no longer fails the run with an invalid `''::DATE`. A blank cutoff now uses the engine default (2020-01-01), the same way the escalation cutoff works.
- Studio saves promotion increases and ranges in the nested promotion settings, including 12.5% and 5%, and removes stale flat aliases when either is edited. Legacy flat defaults still defer to nested values.
- DC Plan participation charts no longer classify nonparticipants labeled "not auto enrolled" as automatically enrolled. Enrollment-method counts exclude unenrolled and nonparticipating rows; existing run results display correctly without rerunning simulations.

### Changed

- Average deferral, employer contribution, and total savings rates on Census Analysis and the DC Plan page now count employees who don't defer or receive a contribution as 0 (#1055). Census Analysis's average and median deferral, and the DC Plan average deferral (including scenario comparison), previously left them out, so default values are lower. A new "Exclude zeros from averages" checkbox on both pages restores contributors-only averages. On the DC Plan page it also divides each contribution rate by the pay of only the employees who received that contribution. The API exposes this as `exclude_zeros`. The headline employer cost rate is unchanged.
- DuckDB upgraded from 1.5.6 to 2.0.0. Simulation results are unchanged: the same config and seed produce identical events, snapshots and contribution amounts. Only some floating-point diagnostic columns differ, by less than 1e-14 relative. Environments must reinstall from the lock (`uv pip install -e ".[dev]"`).
- Opt-out age and income bands are configurable in YAML and Studio's advanced opt-out section. Cohort-normalized probabilities now target the configured rate, reducing the previous demographic bias (about 12–14% against a 9% target in observed runs). Realized rates vary with deterministic draws; clipping at 100% can lower the expected rate. Default runs can produce fewer opt-outs.
- Participant deferral behaviors are now **on by default** (#986): Easy Enroll offers preset 6%, 8% and 10% packages with automatic increases to 10%; self-directed enrollees can choose below the auto-enrollment default (10% at defaults up to 3%, 15% above 3%) or lower eligible starting rates toward the full-match rate. Participants can raise or lower their contribution rate each year (yearly chances of 8.5% up / 6.7% down (plus 1.5% stopping, so 8.2% lower their rate in total), the same whether or not they are in automatic increases, scaled by age, income and tenure), stop while remaining enrolled, and restart at a 40% annual probability (about two-thirds of stops restart, matching plan data). Participant-elected automatic-increase signup defaults to 1% outside Easy Enroll; the plan's default mode remains automatic. Existing nonparticipants' YoY age rates are proportionally retuned to about a 5% population-average conversion probability, retaining income and tenure gradients. The fitted increase multipliers and step sizes are unchanged; the periodic re-enrollment sweep remains off.
- Below-default starting-rate shares now scale by age and income, making younger and lower-paid self-directed enrollees more likely to choose below the default; effective shares are capped at 100%.
- Voluntary decreases now cut a share of the current rate, with higher-rate participants more likely to decrease.
- **Results change on upgrade.** Scenarios inheriting these defaults change enrollment channel mix, starting rates, yearly rate changes, employee contributions and employer match. In Studio's DC Plan settings, turn off **Offer Easy Enroll packages**, **Model employees changing their own contribution rate**, and **Also pull rates down to the full-match rate when it is below the auto-enrollment default**; set every **Choosing a rate below the auto-enrollment default** tier share to 0% and participant-elected automatic-increase signup to 0%. The equivalent YAML settings are `easy_enroll.enabled: false`, `deferral_rate_changes.enabled: false` (with `restart_probability: 0.0`), `enrollment.match_magnet.downward_enabled: false`, `enrollment.below_default.share_tiers: [{max_auto_enroll_default_rate: null, share: 0.0}]`, and `deferral_auto_escalation.participant_elected_signup_probability: 0.0`. To restore the previous YoY behavior, set `enrollment.year_over_year_conversion.base_rates_by_age` to `{young: 0.03, mid_career: 0.05, mature: 0.07, senior: 0.08}`; to disable conversion entirely, set its `enabled` to `false`. Keep escalation mode `automatic` to reproduce the previous mode. Explicitly saved settings continue to override defaults. Review fresh isolated results before adopting a new baseline; the 5% conversion target is a population-average probability, not an exact annual count or a guarantee that YoY wins over other enrollment channels.

- First-year match-responsive deferral increases can reach the full employer-match threshold even above the annual auto-escalation cap. Simultaneous escalation no longer clips that response; the existing IRS rate-equivalent limit remains. Reruns can produce higher employee contributions and employer matches. Studio now keeps the escalation cap inside the collapsible annual escalation settings.
- Studio match eligibility controls now show the requirements actually in effect for legacy configurations. Editing one requirement saves the complete displayed policy instead of silently activating other dormant eligibility settings; unchanged configurations retain their existing behavior. Configuration review describes the effective requirements directly.
- Studio Workforce Parameters and DC Plan now separate plan provisions from behavioral assumptions, preserve custom settings, preview suggestions, and review effective configuration before saving. Numeric fields support direct decimal entry and report unfinished or invalid edits without converting blanks to zero.
- dbt commands launched by the orchestrator now run with `DO_NOT_TRACK=1`, so they never send dbt Labs anonymous usage stats, even if the environment enables them. Simulation outputs are unchanged.
- Explicit `null` for `dc_plan.voluntary_enrollment_rate` or `dc_plan.new_hire_opt_out_rate` now selects demographic behavior even when a legacy enrollment block supplies a flat rate. An omitted key continues to inherit; an explicit zero remains zero. Review configurations containing both forms before rerunning a projection.

## [3.0.0] - 2026-10-14 "Plan Design & Evidence"

Consolidates development since the last tagged release, v2.2.0. Versions
2.3.0 and 2.4.0 were development milestones, not separate tagged releases.

### Upgrade notes and breaking changes

- **Enrollment configuration changed meaning.** An explicit
  `voluntary_enrollment_rate: 0.30` now targets 30% of eligible new hires;
  it previously multiplied demographic probabilities by 0.3. Review saved
  Studio scenarios, including those that stored the former default of 30%.
  Clear the field (or omit the YAML key) to use demographic probabilities,
  or set an intentional target fraction. Neither choice automatically
  reproduces the former multiplier behavior; recalibrate affected scenarios.
- **Deferral defaults affect projected costs.** The upward spread now defaults
  to 4 percentage points and the voluntary deferral cap to 15%. To retain the
  former spread and cap settings, set `deferral_spread_max_lift: 0` under
  `enrollment.auto_enrollment` and `max_deferral_rate: 0.10` under
  `enrollment.match_magnet`. These settings do not undo other simulation fixes
  or the enrollment-rate semantic change.
- **Python 3.12 or newer is required.** Refresh the environment using the
  checked-in dependency lock before upgrading an older installation.
- Preserve existing run archives and effective configurations as historical
  evidence. Validate upgrades in fresh, isolated scenario databases and review
  enrollment, deferral, and employer-cost differences before adopting new
  baselines. Identical seeds do not guarantee identical results across versions.

### Release highlights

- Plan-design optimization with Studio controls and candidate promotion;
  grandfathered designs, per-design parameters and formula families, age-banded
  and Social Security integrated core contributions.
- Census-history parameter fitting, backtest scorecards, seed ensembles, and
  Studio workflows for reviewing and applying fitted parameters.
- Evidence packs, cross-scenario explanations, event audit exploration, run
  provenance, retained successful results, and read-only compliance reporting.
- Net employer-cost comparisons, contribution breakdowns, DC plan trends,
  census analysis, dark mode, and Excel, Parquet, and Tableau comparison exports.
- Simulation and API reliability fixes covering scenario grain, eligibility,
  termination boundaries, contribution calculations, census input validation,
  dbt failure reporting, and database connection cleanup.


### Cost Comparison export to Excel and Tableau

**Added — Excel and Tableau buttons on the Cost Comparison page.** They export
every selected scenario's full `fct_workforce_snapshot` (all years, all
employees) with `scenario_name` and `scenario_id` columns, plus the cleaned
census (`stg_census_data`) and a metadata tab. Excel puts all scenarios on one
tab, or one tab per scenario when they would exceed Excel's 1,048,576-row
limit. Tableau (`.hyper`) has no row limit, keeps column types, and is much
faster on large workspaces (3 s vs ~6 min for 2.1M rows). The Studio scenario
ID replaces dbt's internal `scenario_id` ('default') in the export.

**Dependencies:** `tableauhyperapi==0.0.26479` (later releases dropped macOS
builds; not installed on Linux ARM, where Tableau export returns 501) and
`lxml` (faster openpyxl writes).


### Fit & Backtest in Studio (issue #588)

**Added — Run → Fit & Backtest page.** Analysts can now upload annual census
history, fit parameters, backtest them against held-out years, and apply an
accepted pack to a *new* scenario, all without the command line. Jobs run as
cancellable `planalign fit|backtest` subprocesses, persist per workspace
across restarts, and are pruned to the newest 20 finished jobs. Applying
requires reviewing the config diff and acknowledging thin cells, unfittable
groups, and a missing, WARN, or FAIL backtest. It is refused if the history,
the pack, or the source scenario changed after review.

**Added — `diagnostics.json` in every parameter pack**, plus `fit_report.md`
in backtest packs. Both are additive; pack fingerprints are unchanged.

**Changed — backtest simulations layer the pack over `--seeds-dir`** when one
is given, rather than always over `dbt/seeds`, so the held-out run uses the
same bands and priors the fit did. Runs without `--seeds-dir` are unchanged.


### New-hire enrollment rates and deferral spread (issue #652)

**Changed — `voluntary_enrollment_rate` now means what it says.** It was a multiplier on demographic enrollment probabilities, so setting it to 100% was a no-op that still produced roughly 58-73% enrollment. It is now the exact fraction of eligible new hires who voluntarily enroll in their hire year. Leaving it unset keeps the previous demographic behaviour, so scenarios that never set it reproduce exactly.

**Added — `new_hire_opt_out_rate`.** The exact fraction of auto-enrolled new hires who opt out. Unset keeps the demographic opt-out model. Continuing employees are unaffected by both settings and keep `opt_out_rates.target`.

**Fixed — new hires were drawn twice.** `int_voluntary_enrollment_decision` and `int_proactive_voluntary_enrollment` each decided independently against different hash seeds, then a deduplication priority picked a winner. Two draws at probability p yield 1-(1-p)^2, not p. The proactive path now stands down when a flat rate is set.

**Fixed — `proactive_voluntary` enrollment method.** The category was missing from the alias list in `int_enrollment_state_accumulator`, so those enrollments carried a NULL method and reached the correct reporting bucket only through a fallback.

**Added — upward deferral spread (`deferral_spread_max_lift`), on by default at 4 percentage points.** The demographic deferral table assigned every member of a cell the identical rate, which is never what a real population looks like. The table value now acts as a floor, with employees distributed above it (40/30/15/10/5 across +0 to +4 percentage points). **This raises average deferral rates by roughly 0.3 percentage points on any scenario that does not set the field, and therefore raises projected employer match cost.** That is intended: the previous averages were artificially low precisely because everyone sat on the floor. Set `deferral_spread_max_lift: 0` to disable it and reproduce the previous rates exactly.

**Changed — maximum voluntary deferral rate now defaults to 15%, raised from 10%.** Three demographic cells (mature/executive and senior/high at 12%, senior/executive at 15%) carry table values above the old cap and were being clamped down. **This moves results on its own, whether or not the spread is enabled**: 295 of 43,903 employee-years (0.67%) change on an otherwise unmodified scenario, raising the average deferral rate by 0.014 percentage points.

**Behaviour change for existing Studio scenarios.** The Studio form previously shipped a default of `30` in the voluntary field, so scenarios created with untouched defaults stored an explicit `0.30`. Under the old meaning that was a 0.3x multiplier (~17% enrolment); under the new meaning it is a flat 30%. Those scenarios will produce different results. The field default is now empty, matching the engine's own default of demographic behaviour. YAML- and CLI-driven scenarios that never set the key are unaffected.


### Ensembles and backtesting

- **Feature 133 — seed ensembles:** `planalign simulate --seeds N` now runs
  isolated seed worlds and writes auditable linear percentile bands with
  retained per-seed evidence, optional threshold-exceedance probabilities, and
  workbook distribution exports. Metrics with zero spread across all seeds (for
  example `active_headcount`, solved by the E077 growth solver) render as
  `deterministic` rather than as identical percentile columns.

  `--attribution` now averages across deterministic anchor seeds and reports
  paired-bootstrap confidence intervals, rankings, and workbook exports (#550).
  These are main-effect estimates, not a full variance decomposition; shares
  need not sum to one. See [the ensemble guide](docs/guides/seed_ensembles.md)
  for methodology and limitations. Enrollment and merit are labelled
  structurally not stochastic rather than 0%.

- **Feature 131 — backtest scorecards:** `planalign backtest` fits parameter
  packs on early census snapshots only, simulates held-out years across
  isolated seed runs, and emits deterministic Markdown/JSON scorecards with
  thresholds, seed spread, observability, and an auditable provenance chain.
  Predicted and actual are held to one definition on both sides: terminations
  count the experienced cohort, by-level headcount is band-derived from
  compensation, and employer-match cost is reported as not observable rather
  than inferred from an assumed formula. The harness self-test backtests
  history the simulator itself produced, so a residual error is attributable
  to the harness rather than to configuration divergence.

### Simulation state and retained results

- **Feature 122 — state pipeline redesign:** managed API/Studio attempts now use
  immutable run-specific databases and atomically retain the latest successful result
  while a new run is active. Scenario reads expose result/active run consistency
  headers, and Studio shows one global in-progress warning.
- Normalized the SQL/dbt event and workforce-state DAG: current-year events publish
  once, workforce state has one authoritative accumulator, benefit calculations use
  separated workforce/enrollment/deferral state, and the workforce snapshot is a
  composition. Removed the two redundant legacy state relations after exact parity.
- STATE_ACCUMULATION now uses one command per year with no state full-refresh. In the
  three-run 60,040-employee warm matrix, median peak RSS was 86.2% of baseline for the
  reference workload and 81.4% for Studio; exact public mart compatibility was
  preserved. The observed whole-run invocation total is evidence, not a fixed target.
- This feature targets the active SQL pipeline only; deprecated Polars compatibility
  remnants remain out of scope and Polars support was not restored.

## [2.2.0] - 2026-07-11 "Calibration"

_Consolidates all work since 2.1.0 (March–July 2026, ~258 commits), reconstructed from git history._

### Added

**Fast Compensation Calibration (Feature 105, #280)**
- `planalign calibrate <year-range>` — rebuilds only the compensation/workforce dbt subgraph per year; per-year avg comp and YoY growth are exact vs. a full simulation, ~3–5× faster
- Interactive re-tune loop (`--interactive`), COLA/merit overrides, isolated calibration databases by default
- Target-seeking auto-calibration against real production levers: workforce growth, COLA/merit, new-hire age distribution, per-level comp ranges via Match Census × scale
- Termination-rate tuning with Match Census; population and total-compensation growth in output
- Studio "Calibration" panel (`/calibrate`) reworked into guided steps, backed by `POST /api/calibration/run` (shared `CalibrationRunner` with the CLI); calibration runs as background jobs with polling (#380)

**Simulation Engine & DC Plan Modeling**
- **Feature 103** (#357): configurable new-hire DC-plan ineligibility — `eligibility.new_hire_ineligible_pct`, optional `eligibility_override` census column, and census-calibrated mode; resolved in the new `int_plan_eligibility_override` temporal accumulator and enforced across enrollment/contribution/match models. Defaults leave behavior byte-for-byte unchanged
- **Feature 102** (#328, #335): match-magnet dial exposed in Studio; fixed match-ceiling not driving deferral selection; `points_based` DMR corrected
- **Feature 101** (#307, #332): contributions and employer match prorated for same-year enroll→opt-out windows
- **Feature 099** (#317): tenure-graded multi-tier employer match formulas (`employer_match_status: 'tenure_graded'`)
- **Feature 093**: `scheduled_hours_per_week` census field with part-time eligibility hours handling
- **Feature 086**: DC plan eligibility audit trail with prerequisite chain enforcement
- **Feature 085**: opt-out rate configuration with census analysis
- Per-employee auto-escalation opt-out census flag (#316)

**Studio & Data Import**
- **Features 087–091**: census data import overhaul — CSV/Excel → Parquet wizard with schema-aware predictive field mapping, sheet re-selection, soft-validated field mappings (#350), and stg_census_data contract fixes
- **Feature 094**: live simulation run dashboard — structured telemetry protocol, milestone activity feed, live trend chart, WebSocket resync with REST snapshot fallback
- **Feature 088** (#291): per-run simulation log capture for analyst access
- Curated "Workforce Parameters" tab with advanced settings tucked away (#358); sidebar nav grouped into Setup/Run/Analyze
- Year selector on DC plan comparison summary and contribution mix (#322); deferral distribution toggle and year filter on analytics pages (#312, #315)

### Changed
- **Feature 092**: consolidated dbt invocations per stage for simulation performance; multi-threading and checkpointing disabled by default
- Runtime outputs consolidated under `var/` with run-artifact retention (#391)
- Python domain code moved from `config/` into the `planalign_core` package (#390)
- **Feature 104** (#365, #367): removed dead eligibility-events join in `fct_workforce_snapshot` (returned zero rows in every configuration); verified byte-identical output
- Lint debt driven to zero: ruff 387→0 (#331), mypy clean across all packages with pydantic plugin (#333), black formatting enforced via pre-commit hooks (#330)
- Docs: pruned ~430 stale epic/story/session docs (#392); documentation rewritten from the current codebase

### Fixed
- **Feature 108** (#419): purge stale prior-run state before each simulated year
- **Feature 107** (#418): preserve census enrollment state across simulation years
- **Feature 106** (#406): stop the simulation when a workflow stage reports failure
- Duplicate simulation starts rejected for queued scenarios (#417); cancel now stops the real subprocess across service instances (#416)
- `event_sequence` ordered chronologically with priority as same-day tiebreaker (#412)
- Year-cleanup deletes scoped to scenario and plan design (#410)
- Studio scenario seed overrides no longer leak into global dbt seeds (#413); per-scenario seeds persist across batch runs
- dbt correctness: merit raises no longer granted to already-terminated employees; zero-mean new-hire comp variance with seeded stable event RNGs; new-hire-termination contribution proration (#334); 414(s) testing compensation capped at IRS limit in ACP/401(a)(4) tests
- **Feature 095**: voluntary enrollees missing from snapshot participation/deferral/match
- WebSocket telemetry reliability (reconnect backoff, missed updates, stuck "running" states); failed/cancelled runs persist `run_metadata.json` and appear in run history
- Census handling: placeholder default no longer shadows workspace census; relative `census_parquet_path` resolved against workspace dir; wizard-generated census wired into workspace config
- Batch: failure exit codes propagate; unknown scenario names rejected
- `ExecutionMutex` acquired atomically (O_EXCL); `int_effective_parameters` built before hazard cache rebuild

### Security
- API authentication boundary and safe network defaults (#414): loopback bind by default, optional shared-token auth via `PLANALIGN_API_TOKEN` (constant-time comparison), wildcard-CORS-on-non-loopback rejected at startup
- Path traversal prevented in the artifact download route (#407)
- API defaults to multi-tenant DB resolution; legacy project-DB fallback gated behind a dev-mode flag (#409)
- New `SECURITY.md` documenting the deployment security model, hardening checklist, and vulnerability reporting

### Removed
- Orphaned auto-enrollment decision-matrix model chain (#319); 5 duplicate dbt models (v2 models renamed to canonical)
- Stale `dq_employee_contributions_validation` references (#408)
- Dead frontend mock telemetry service and unused dev helpers

---

## [2.1.0] - 2026-03-03 "Studio & Compliance"

### Added

**PlanAlign Studio (Web Interface)**
- **E081**: FastAPI backend + React/Vite frontend for scenario management, batch processing, and real-time simulation telemetry via WebSocket
- **E085**: DC Plan Contribution Analytics Dashboard with per-year metrics and export
- **E093**: Compensation analytics broken out by detailed status code
- **E104**: Scenario cost comparison page with multi-scenario charting
- **E013**: Employer cost ratio metrics (employer cost per $1 of employee comp) on comparison page
- **E014/E018**: Redesigned comparison page with sidebar layout, year-by-year breakdown tables, and variance rows
- **E015**: Copy-to-clipboard for comparison tables with Excel-compatible variance formatting
- **033**: Multi-year compensation matrix on Compare Cost page
- **046**: Tenure-based and points-based employer match contribution modes with gap/overlap validation
- **048**: DC plan metrics (participation rate, avg deferral, employer cost) in scenario comparison API
- **049**: Refactored ConfigStudio into modular section components
- **050**: NDT ACP (Actual Contribution Percentage) non-discrimination testing
- **051**: NDT 401(a)(4) general test and 415 annual additions limit test
- **052**: NDT ADP (Actual Deferral Percentage) nondiscrimination test with scenario comparison mode
- **053**: Core contribution tier validation and points-based contribution mode
- **055**: Structured census field validation warnings with tiered severity UI
- **056**: Row-level data quality warnings for census uploads
- **057**: DC plan comparison charts on scenario comparison page
- **059**: Deferral rate distribution comparison across scenarios
- **060**: Average/total compensation toggle with CAGR display on charts
- Unsaved changes tracking in ConfigStudio with beforeunload guard
- Automatic workspace repair on startup
- Delete database option in Advanced Settings tab
- Scenario reorder controls with anchor-first ordering and localStorage persistence
- SECURE 2.0 super catch-up contribution limits for ages 60-63

**Event Sourcing & Simulation Engine**
- **E001**: Centralized age/tenure band definitions in dbt seeds with `assign_age_band`/`assign_tenure_band` macros
- **E003**: Band configuration management UI in PlanAlign Studio
- **E004**: Event type abstraction layer (`EventGenerator`, `EventRegistry`) for extensible event generation
- **E005**: Unified `DatabasePathResolver` for API services (workspace, scenario, project-level databases)
- **E006**: Self-healing dbt initialization with automatic seed/dependency install
- **E007**: State accumulator contract with type-safe Pydantic validation
- **E008**: Hardened IRS 402(g) contribution limit enforcement
- **E010**: Service-based employer match contribution tiers
- **E025/E026**: Vesting analysis page + IRS 401(a)(17) compensation limit compliance
- **E058**: Match-responsive deferral adjustment events
- **E082**: Configurable new hire demographics (age/level distribution via seeds + UI) and promotion rate multiplier
- **E084**: Configurable DC Plan match formulas with editable tiers and graded core by service
- **039**: Per-scenario seed configuration with unified save and workspace fallback chain
- **040**: Vesting year selector on analysis page
- Level discount factor in termination hazard model (higher-level employees get lower termination rates)

**Infrastructure & Architecture**
- **E073**: Split 1,471-line config.py into 7 focused modules
- **E076**: Polars state accumulation pipeline with 1000x+ performance benchmarking
- **E083**: Workspace cloud synchronization via Git (`planalign sync` commands)
- **E011**: Auto-install sqlparse token limit fix on first import (with sitecustomize.py Windows fallback)
- **031**: Workspace export/import via 7z archives
- **034**: Extracted setup and validation concerns from PipelineOrchestrator
- **035**: Modularized config/events.py into domain-specific submodules
- **027**: Split large monolith files into focused packages
- Schema tests for hazard termination model (not_null, monotonicity)

### Changed
- Scenario comparison limit increased from 3 to 6 scenarios
- Tenure calculation now uses day-based precision instead of year-only subtraction
- Terminated employee tenure calculated to termination date (not year-end)
- Census compensation uses correct annualization logic
- Participation rate computed using active employees only per year
- Deferral rate IRS 402(g) cap simplified to guard on compensation > 0 upfront
- Dynamic band macros now use `run_query` to read from seed tables at compile time
- `age_multipliers` and `tenure_multipliers` are now required config fields
- Seed writes use atomic temp file + `os.replace()` to prevent partial files
- Windows compatibility: ProactorEventLoop, cross-platform subprocess, UTF-8 encoding

### Fixed
- **E009**: Service-based core contribution tier support
- **E022**: Hire-termination date ordering and type mismatches
- **E025**: Proportional minimum tenure for new hire terminations
- **E028**: O(n^2) scalar subqueries in fct_workforce_snapshot (performance regression)
- **E036**: Deferral rate escalation now generates events for eligible employees
- **E037/E043**: Census compensation annualization logic corrected
- **E041**: Consistent per-year participation rate
- **E044**: Salary range input UX and default scale factor
- **E047**: Tenure eligibility enforcement for employer contributions; Add Tier defaulting fix
- **E054**: Shared workspace context in DC Plan analytics page
- **E086**: Removed unused turnover parameters from UI
- **E087**: Analytics Dashboard export and storage path display
- **E088**: Removed hardcoded Impact Preview section from Config Studio
- **E089**: Census file upload persistence and metadata display
- **E090**: Census file upload now used in simulations
- **E091**: Use prorated_annual_compensation for analytics
- **E092**: DC Plan analytics page database fallback and case sensitivity
- **E094**: Analytics page remembers workspace and simulation after run
- **E095**: Wired eligibility_months UI field to dbt vars
- **E096**: Participation bug (event type mismatch in deferral accumulator) — 5 bugs fixed
- **E097**: Polars schema mismatch and year range cleanup
- **E098**: Extended seed data through 2035 to fix 2030 contribution bug
- **E099**: Copy scenario now includes all DC Plan and New Hire settings
- **E100**: Copy scenario now includes data sources (census file path)
- **E101**: UI auto-escalation settings now override legacy YAML config
- **E102**: Escalation delay years variable name mismatch; hire date cutoff clearing; Polars var passthrough
- **E103**: Analytics page dropdowns correctly select workspace/scenario from URL
- Auto-escalation hire date filter uses inclusive comparison (>=)
- DuckDB ORDER BY in UNION ALL subquery error
- Cast level_id to INTEGER in snapshot and state models
- Polars: empty parquet files for years with no events, workspace database path priority
- Studio: chart colors, legend ordering, TypeScript errors, stale data overwrite, workspace switching
- Event priority inconsistency, error handler fragility, SQL safety, and warning filter gaps
- Resolved 8 failing unit tests and 5 flaky/environment-specific tests

### Removed
- **E024**: Removed Polars pipeline — simplified to SQL-only mode (~4,400 LOC removed)
- Removed deprecated Streamlit dashboard
- Removed Makefile and Make references
- Removed 179 lines of redundant content from CLAUDE.md and README.md

---

## [2.0.0] - 2025-11-24 "PlanAlign Engine"

### BREAKING CHANGES
- **Project Renamed**: PlanWise Navigator → PlanAlign Engine
- **CLI Command Renamed**: `planwise` → `planalign`
- **Package Renamed**: `navigator_orchestrator` → `planalign_orchestrator`
- **Package Renamed**: `planwise_cli` → `planalign_cli`
- **dbt Project Name**: `planwise_navigator` → `planalign_engine`

### Migration Guide
1. Update all imports:
   - `from navigator_orchestrator` → `from planalign_orchestrator`
   - `from planwise_cli` → `from planalign_cli`
2. Update CLI commands:
   - `planwise simulate` → `planalign simulate`
   - `planwise batch` → `planalign batch`
   - `planwise status` → `planalign status`
3. Update dbt profiles to reference `planalign_engine` profile
4. Reinstall package: `uv pip install -e ".[dev]"`

---

## [1.0.0] - 2025-01-15 "Foundation"

### Added
- **E068**: Performance Optimization (2× improvement, 285s → 150s)
  - Multi-threaded dbt execution with configurable thread pools
  - Optimized incremental model strategies
  - Memory-efficient query patterns
  - 375× performance with Polars mode option

- **E069**: Batch Scenario Processing
  - Isolated database instances per scenario
  - Excel export with metadata (git SHA, seed, configuration)
  - Timestamped batch directories for reproducibility
  - Scenario comparison reports

- **E072**: Pipeline Modularization
  - 51% code reduction (2,478 → 1,220 lines)
  - 6 focused modules: WorkflowBuilder, StateManager, YearExecutor, EventGenerationExecutor, HookManager, DataCleanupManager
  - Extensible callback system for custom workflows
  - Improved testability and maintainability

- **E074**: Enhanced Error Handling
  - Context-rich exception hierarchy (NavigatorError, DatabaseError, PipelineError, etc.)
  - Pattern-based error recognition with ErrorCatalog
  - Correlation IDs for distributed tracing
  - Resolution hints for common issues
  - <5min bug diagnosis capability

- **E075**: Testing Infrastructure
  - 256 comprehensive tests (87 fast unit tests, integration suite)
  - Centralized fixture library (database, config, mock_dbt, workforce_data)
  - In-memory database fixtures for fast testing
  - 90%+ code coverage for core components
  - pytest markers for targeted test execution

- **E023**: Enrollment Architecture Fix
  - Temporal state accumulator pattern
  - `int_enrollment_state_accumulator` model
  - `int_deferral_rate_state_accumulator` model
  - Fixed circular dependencies in enrollment tracking
  - Validation model for enrollment architecture integrity

- **E078**: Cohort Pipeline Integration
  - Polars-based event factory (375× faster than dbt)
  - Multi-year termination fixes
  - Cohort-based workforce modeling
  - Hybrid SQL/Polars execution strategy

- **E080**: Validation Model to Test Conversion
  - Converted 30 validation SQL models to dbt tests
  - 90 passing data quality tests
  - Removed legacy validation code
  - Integrated with dbt build workflow
  - Improved CI/CD validation speed

- **PlanAlign CLI**: Rich-based terminal interface
  - `planalign simulate` - Multi-year simulation with progress tracking
  - `planalign batch` - Batch scenario processing
  - `planalign status` - Comprehensive system diagnostics
  - `planalign health` - Quick health check
  - `planalign checkpoints` - Checkpoint management
  - `planalign analyze` - Results analysis with terminal visualizations
  - `planalign validate` - Configuration validation

- **Versioning System**: Centralized version management
  - Semantic Versioning 2.0.0 compliance
  - Version displayed in CLI and status commands
  - Release metadata tracking

### Changed
- Database location standardized to `dbt/simulation.duckdb`
- dbt commands always run from `/dbt` directory
- Improved error messages with actionable resolution hints
- Enhanced logging with correlation IDs

### Fixed
- Enrollment event duplication across years
- Missing enrollment dates in temporal tracking
- Database lock conflicts with IDE connections
- Configuration validation edge cases
- Multi-year simulation state accumulation issues

### Technical Details
- Python 3.11+ required
- DuckDB 1.0.0 (columnar OLAP engine)
- dbt-core 1.8.8 with dbt-duckdb 1.8.1
- Pydantic v2 for configuration validation
- Rich + Typer for CLI interface
- pytest with comprehensive fixture library

---

## Version History

- **3.0.0** (2026-10-14): Plan Design & Evidence - Plan optimization, multi-design modeling, fitting and backtesting, ensembles, evidence and compliance reporting; enrollment semantics and deferral default changes
- **2.2.0** (2026-07-11): Calibration - Fast compensation calibration, new-hire eligibility modeling, tenure-graded match, census import wizard, API security hardening
- **2.1.0** (2026-03-03): Studio & Compliance - PlanAlign Studio, NDT testing, DC plan modeling, SQL-only mode, 60+ features/fixes
- **2.0.0** (2025-11-24): PlanAlign Engine - Project rename from PlanWise Navigator
- **1.0.0** (2025-01-15): Foundation - Initial production release with event sourcing, pipeline modularization, and comprehensive testing

---

## Links

- [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
- [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
- [PlanAlign Engine Documentation](./docs/)
- [Project Status](./CLAUDE.md#12-project-status)
