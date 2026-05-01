# Feature Specification: Fix DC Plan Match UI for Tenure-Based and Points-Based Modes

**Feature Branch**: `083-fix-dc-match-ui`
**Created**: 2026-04-29
**Status**: Draft
**Input**: User description: "on the dc plan configure page when i have the match calculation mode as tenure-based (probably also effecting points based) can you change it to how the tiered or simple match works on the gui? where it is X% to X% deferrals XXX% match?  also, the XXX% match shoudl accept values greater than 100%, right now on the tenure and points based when i put 200% it makes it 2%"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deferral Range Shown Prominently in Tenure/Points Tiers (Priority: P1)

A plan designer configuring a tenure-based (or points-based) employer match wants each tier row to show the deferral range in the same readable format as deferral-based tiers: `X% to X% deferrals → XXX% match`. Currently the deferral cap is buried at the end of a cluttered row ("% match, max XX% def"), making it harder to read and inconsistent with the rest of the match configuration UI.

**Why this priority**: The inconsistency causes confusion when configuring complex plans. Aligning the display format across all match modes reduces cognitive load and misconfiguration risk.

**Independent Test**: Can be fully tested by opening the DC Plan configuration page, switching match calculation mode to "Tenure-Based", and verifying that each tier row renders with the deferral range prominently displayed in `X% to X% deferrals → XXX% match` format before and after saving.

**Acceptance Scenarios**:

1. **Given** the DC Plan Configure page with match mode set to "Tenure-Based", **When** the user views the Tenure Match Tiers section, **Then** each tier row displays its deferral range in the format `[min]% to [max]% deferrals → [matchRate]% match`, matching the visual layout used by deferral-based tiers.
2. **Given** the DC Plan Configure page with match mode set to "Points-Based", **When** the user views the Points Match Tiers section, **Then** each tier row displays its deferral range in the same `X% to X% deferrals → XXX% match` format.
3. **Given** a tenure or points tier with a deferral cap configured, **When** the user saves and reopens the scenario, **Then** the deferral range values are preserved and still displayed correctly.

---

### User Story 2 - Match Rate Accepts Values Greater Than 100% (Priority: P1)

A plan designer wants to configure an employer match rate above 100% (e.g., 200% match on the first 1% of deferrals — a common enhanced match design). When entering 200 into the match rate field on tenure-based or points-based tiers, the value is incorrectly stored or displayed as 2%, preventing valid plan designs from being configured.

**Why this priority**: This is a data-entry bug that silently corrupts match configurations. A 200% match is a legitimate and common plan design; the inability to enter it accurately blocks real use cases.

**Independent Test**: Can be fully tested by adding a tenure-based tier, typing `200` into the match rate field, saving the scenario, reopening it, and confirming the match rate displays as `200%` — not `2%` or any other normalized value.

**Acceptance Scenarios**:

1. **Given** a tenure-based tier editor, **When** the user enters `200` in the match rate field, **Then** the field displays `200` and the tier is saved with a 200% match rate.
2. **Given** a points-based tier editor, **When** the user enters `150` in the match rate field, **Then** the field displays `150` and the value is preserved after save/reload.
3. **Given** a match rate of 200% saved in a tenure tier, **When** the scenario is reopened, **Then** the match rate field shows `200`, not `2`.
4. **Given** a match rate field in tenure or points mode, **When** the user enters a value between 0 and 200 (inclusive), **Then** the value is accepted without truncation, normalization, or division.

---

### Edge Cases

- What happens when a tenure tier previously stored only a single deferral cap (no explicit minimum)? The deferral range minimum should default to 0% when displayed in the new format.
- What happens when a user enters a match rate of 0%? It should be accepted as a valid value (some tiers may intentionally have 0% match).
- What happens when the match rate exceeds 200%? The field should enforce a maximum of 200% — values beyond this are not standard plan designs.
- What happens to existing saved scenarios where a match rate was previously corrupted (stored as 0.02 instead of 200)? Those values remain as-is; no auto-migration is performed, and users must manually correct affected tiers.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The tenure-based match tier editor MUST display each tier's deferral range in the format `[deferralMin]% to [deferralMax]% deferrals → [matchRate]% match`, consistent with the deferral-based tier row format.
- **FR-002**: The points-based match tier editor MUST display each tier's deferral range using the same `X% to X% deferrals → XXX% match` format.
- **FR-003**: The tenure range (min/max years of service) for each tenure tier MUST remain visible and editable — the tier discriminator is years of service, not deferral range.
- **FR-004**: The points range (min/max points) for each points tier MUST remain visible and editable alongside the deferral range fields.
- **FR-005**: The match rate input field for tenure-based and points-based tiers MUST accept whole-number values from 0 to 200 without normalizing, dividing, or otherwise altering the entered value.
- **FR-006**: Match rate values entered as whole percentages (e.g., 200) MUST be stored and retrieved as the same whole-number value (200), not as a decimal fraction (0.02).
- **FR-007**: When a tenure or points tier only has a maximum deferral cap (no explicit minimum), the deferral range display MUST default the minimum to 0%.
- **FR-008**: All existing tier add/remove interactions MUST continue to function correctly after the layout change.
- **FR-009**: Tier gap and overlap validation warnings MUST continue to function for tenure years and points ranges after the UI redesign.

### Key Entities

- **Tenure Match Tier**: Defined by a years-of-service range (minYears, maxYears), a deferral range (minDeferralPct defaulting to 0, maxDeferralPct), and a match rate (whole-number percentage, 0–200).
- **Points Match Tier**: Defined by a points range (minPoints, maxPoints), a deferral range (minDeferralPct defaulting to 0, maxDeferralPct), and a match rate (whole-number percentage, 0–200).
- **Deferral Range**: The span of employee deferral percentages to which a given match rate applies, displayed as `[min]% to [max]% deferrals`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A plan designer can enter a match rate of 200% in a tenure-based or points-based tier and retrieve exactly 200% after saving and reopening the scenario — zero data loss or normalization errors.
- **SC-002**: The tier row layout in tenure-based and points-based modes is structurally consistent with deferral-based tier rows (deferral range first, match rate second), confirmed by side-by-side visual comparison.
- **SC-003**: All existing tenure-based and points-based plan configurations continue to load and display correctly after the UI change, with no regressions in tier add/remove, gap/overlap warnings, or save/reload behavior.
- **SC-004**: A user already familiar with the deferral-based tier format can configure a tenure-based match tier without needing to learn a different row layout — confirmed by consistent label ordering across all match modes.
