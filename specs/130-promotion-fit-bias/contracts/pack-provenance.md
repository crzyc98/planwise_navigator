# Contract: parameter-pack provenance

**Feature**: 130-promotion-fit-bias | Implements FR-009, FR-010, FR-017

The question this contract answers: months after a projection was run, can a reviewer holding only the run's `run_metadata` and the pack directory determine whether the promotion hazard behind it was fitted from the client's history or was a retained default? Today they cannot.

## 1. `manifest.json` — new fields

`PackManifest` (`pack.py:74`) gains two fields, both serialized by the existing `asdict` path:

```json
{
  "pack_id": "fit-2022-2024-20260801T142233Z",
  "fingerprint": "…",
  "promotion_basis": "estimated",
  "thresholds": { "level_coverage_threshold": 0.90 }
}
```

| Field | Type | Semantics |
|---|---|---|
| `promotion_basis` | `str` | `measured` \| `estimated` \| `not_fitted` |
| `thresholds` | `dict[str, float]` | **Non-default values only.** Empty dict when both thresholds are at their defaults, so a default run's manifest is unchanged in substance. |

`PackManifest.from_dict` already filters to known fields (`pack.py:102`), so **older packs load without migration** — the new fields take their dataclass defaults (`"measured"` and `{}`). Worth an explicit backward-compatibility test.

### Fingerprint interaction

The fingerprint covers the config fragment and every seed byte (`pack.py:14`) — not the manifest. Adding manifest fields therefore does **not** change any existing pack's fingerprint, and two fits differing only in basis still fingerprint differently because their fitted seed values differ. No special handling needed.

## 2. `param_pack` provenance block — new field

`apply.provenance_block` (`apply.py:69`) gains one key:

```python
{
    "pack_id": ...,
    "fingerprint": ...,
    "fit_date": ...,
    "source_digest": ...,
    "snapshot_years": [...],
    "promotion_basis": "not_fitted",   # NEW
}
```

This is the FR-010 mechanism. The block is stamped into the effective config, `SimulationConfig` retains unknown top-level keys, and `to_dbt_vars` ignores them — so it reaches `run_metadata` **without perturbing the config fingerprint** (`apply.py:70-75`). It is provenance, not a result-affecting input, which is exactly the property #458 designed the block around. Adding a field here is the cheapest possible satisfaction of FR-010: no schema migration, no new table, no change to config drift detection (Feature 109).

Thresholds are deliberately **not** propagated into the run block. They shaped the pack, and the pack's manifest records them; a run needs to know *what it got*, not how the fit was tuned. Anyone needing that detail follows `pack_id` to the manifest.

## 3. Seed files — unchanged shape

FR-003b and FR-009 together require that a pack's shape not depend on how promotion was resolved. All three bases emit the same three promotion seed files:

- `config_promotion_hazard_base.csv`
- `config_promotion_hazard_age_multipliers.csv`
- `config_promotion_hazard_tenure_multipliers.csv`

| Basis | Seed contents |
|---|---|
| `measured` | Fitted values (today's behavior) |
| `estimated` | Fitted values; levels that did not separate carry the prior, via the existing credibility path |
| `not_fitted` | Prior values throughout — a faithful copy of the current seeds |

The `not_fitted` case emits seeds that equal the priors rather than omitting the files. This is what makes FR-009 hold: `planalign simulate --params <pack>` builds its overlay project by file swap (`apply.py:107`), and a missing seed would break the overlay. A pack with a defaulted promotion hazard is a fully valid, runnable pack — it simply carries forward what was already configured.

## 4. Contract tests

1. A `measured` fit produces a manifest with `promotion_basis == "measured"` and `thresholds == {}`.
2. A `not_fitted` fit still emits all three promotion seed files, and their values equal the priors.
3. A pack from a `not_fitted` fit applies cleanly via `apply_pack` and yields an effective config whose `param_pack.promotion_basis` is `not_fitted`.
4. A manifest written before this feature (no `promotion_basis` key) loads through `from_dict` without error and defaults to `measured`.
5. Adding the manifest fields leaves the fingerprint of an otherwise-identical pack unchanged.
6. A fit run with a moved threshold records it in `manifest.thresholds`; a default run records an empty dict.
