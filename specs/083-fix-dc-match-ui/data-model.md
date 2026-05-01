# Data Model: Fix DC Plan Match UI for Tenure-Based and Points-Based Modes

## No schema changes required

All changes in this feature are purely in the frontend display layer. The backend API and data storage are unaffected.

---

## Existing Entities (relevant to this feature)

### TenureMatchTier (`types.ts`)

| Field         | Type           | Description                                              |
|---------------|----------------|----------------------------------------------------------|
| minYears      | number         | Minimum years of service for this tier (inclusive)       |
| maxYears      | number \| null | Maximum years of service (exclusive); null = no upper bound |
| matchRate     | number         | Employer match percentage (0–200, whole number in UI)    |
| maxDeferralPct| number         | Maximum employee deferral % matched (0–100, whole number)|

**No new fields added.** The deferral range minimum is implicitly 0%.

### PointsMatchTier (`types.ts`)

| Field         | Type           | Description                                              |
|---------------|----------------|----------------------------------------------------------|
| minPoints     | number         | Minimum age+tenure points for this tier (inclusive)      |
| maxPoints     | number \| null | Maximum points (exclusive); null = no upper bound        |
| matchRate     | number         | Employer match percentage (0–200, whole number in UI)    |
| maxDeferralPct| number         | Maximum employee deferral % matched (0–100, whole number)|

---

## Serialization Contract (unchanged)

The frontend stores `matchRate` as a whole-number percentage (0–200). The API stores `match_rate` as a decimal fraction (0.0–2.0).

| Direction     | Conversion                         | Location              |
|---------------|------------------------------------|-----------------------|
| Load (API→UI) | `matchRate = match_rate * 100`     | ConfigContext.tsx     |
| Save (UI→API) | `match_rate = matchRate / 100`     | buildConfigPayload.ts |

The save direction (`buildConfigPayload.ts`) is already correct. Only the load direction in `ConfigContext.tsx` needs to be fixed.
