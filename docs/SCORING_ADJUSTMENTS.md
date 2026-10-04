# Indicator scoring, margin and temporal robustness

**Implementation version:** indicator scoring v0.3 / score adjustments v1.0  
**Scope:** 133 Virginia + 159 Georgia county equivalents  
**Normative configuration:** `configs/indicator_scoring.json` and `configs/score_adjustments.json`

This document describes the calculation that the live pipeline runs. The calculation is deliberately split so that indicator anchors, margin and county climate factors are prepared independently of Camille's eight dimension weights.

## Order of operations

```text
raw county indicators
  → indicator utilities U (0–100)
  → equal-weight base dimensions D (0–1)
  → three dimension-specific CMRA factors Aᴿ
  → adjusted dimensions Dᴿ (0–1)
  → Camille weights + configured interactions
  → suitability Sᴿ (0–100)
  → one weakest-link margin factor A_M
  → final score
```

The ordinary dimension columns consumed by the existing interaction and decision modules contain `Dᴿ`. The unadjusted values are retained as `base__<dimension>`. Therefore the existing downstream interfaces do not change.

## 1. Fixed-anchor piecewise normalization

For a higher-is-better indicator:

```text
U = 100 × clip((x − L) / (T − L), 0, 1)
```

For a lower-is-better indicator:

```text
U = 100 × clip((L − x) / (L − T), 0, 1)
```

`T` is the good/full-utility anchor, `L` is the bad/zero-utility boundary, and missing values remain missing. Labor force first applies `ln(1+x)` to the value and both anchors. Every result is written as `u__<metric_id>`.

| Dimension | Indicator | Direction | T | L |
|---|---|---:|---:|---:|
| Climate risk | Wildfire national percentile | lower | 0.20 | 0.90 |
| Climate risk | Inland-flood loss-rate national percentile | lower | 0.10 | 0.80 |
| Water | Baseline water stress | lower | 1 | 4 |
| Water | 2050 BAU water stress | lower | 1 | 4 |
| Land/ecology | Low-impervious land share | higher | 0.98 | 0.25 |
| Land/ecology | GAP 1/2 protected-land share | lower | 0 | 0.25 |
| Land/ecology | Wetland land share | lower | 0 | 0.40 |
| Fiber | Business fiber 100/20 availability | higher | 0.90 | 0.20 |
| Fiber | Business fiber 1000/100 availability | higher | 0.90 | 0.10 |
| Workforce/community | Labor force, log transformed | higher | 150,000 | 2,000 |
| Workforce/community | Social-vulnerability percentile | lower | 0.05 | 0.95 |
| Cooling climate | Historical CDD65 | lower | 700 | 2,200 |
| Cooling climate | Historical days above 90°F | lower | 5 | 75 |
| Transportation | Distance to Interstate, km | lower | 5 | 50 |
| Transportation | Distance to rail, km | lower | 1 | 20 |
| Energy/carbon | Industrial electricity price, USD/MWh | lower | 65 | 120 |
| Energy/carbon | SAIDI without major-event days | lower | 100 | 300 |
| Energy/carbon | Grid CO₂e intensity, kg/MWh | lower | 200 | 600 |

All eight base dimensions are arithmetic means of their member utilities, expressed on 0–1:

```text
D_ij = Σ α_jk U_ik / 100,  where Σ α_jk = 1
```

The current `α` values are equal within each dimension: 1/2 for two-indicator dimensions and 1/3 for Land/ecology and Energy/carbon. No weight is reallocated when a required indicator is missing.

## 2. Safety margin

For each selected indicator `k`, normalized headroom and its factor are:

```text
m_ik   = clip((U_ik − τ_k) / (100 − τ_k), 0, 1)
a_M,ik = 1 − λ_M(1 − m_ik)
```

The current configuration uses `τ_k = 0` and `λ_M = 0.20` for all 18 indicators. The county factor is the weakest selected factor:

```text
A_M,i = min_k(a_M,ik)
```

The 18 factors are never multiplied. Strong indicators cannot hide the weakest margin, and adding an indicator does not create an automatic compounding penalty. The audit table includes `margin_headroom__<metric>`, `margin_factor__<metric>`, `margin_adjustment`, and `margin_limiting_indicator`.

## 3. Indicator-derived hard-zero gate

A zero utility is a scoring boundary, not automatically physical infeasibility. The optional rule is:

```text
F_norm,i = 0 if any explicitly listed gate indicator has U_ik = 0
```

The shipped configuration intentionally has no approved hard-zero indicators and reports `normalization_gate_status = not_configured`. To activate the rule, set `hard_zero_gate.enabled` to `true` and list only team-approved non-negotiable indicators. A failed configured gate is excluded and unranked; a missing gate input is incomplete.

## 4. Dimension-specific temporal robustness

Source: the repository-local `data/raw/cmra_2025_va_ga_robustness_inputs.csv` extract of CMRA 2025 county climate projections. The stored table compares RCP8.5 mid-century with the historical mean across the joint 292-county VA+GA scope.

For heat, dry spells and heavy precipitation:

```text
Δ_ir = max(0, future_ir − historic_ir)

p_ir = 0                                      if Δ_ir = 0
p_ir = (average_rank(Δ_ir) − 1) / (292 − 1)  if Δ_ir > 0

Aᴿ_ir = 1 − 0.20 p_ir
```

Ties use average ranks. Improvements are not rewarded; only deterioration is penalized. The one-to-one mapping is:

| CMRA downside change | Target dimension | Operation |
|---|---|---|
| Increase in days above 90°F | Cooling climate | `Dᴿ_cooling = D_cooling × Aᴿ_heat` |
| Increase in consecutive dry days | Water | `Dᴿ_water = D_water × Aᴿ_dry` |
| Increase in days with ≥2 inches precipitation | Climate risk | `Dᴿ_climate = D_climate × Aᴿ_rain` |

Every other dimension has `Aᴿ = 1` and `Dᴿ = D`. The three factors are not combined into a global factor and no dimension receives more than one factor.

`data/processed/county_robustness_va_ga.csv` stores, by FIPS, the historic value, future value, downside change, percentile and final factor for all three directions. It is version-locked so a change in Camille's weights does not cause percentile recalculation. `scripts/build_robustness_factors.py` is the reproducible builder and defaults to the repository-local CMRA extract; rerun it only if the source, scenario, comparison geography or penalty coefficient changes.

The two original processed reference workbooks are also stored inside the repository:

- `data/processed/virginia_georgia_normalized_margin_v0.3.xlsx`
- `data/processed/va_ga_dimension_specific_robustness_v02.xlsx`

All configuration paths are relative to the repository. No workflow step depends on a user home directory or a parent folder outside this project.

## 5. Suitability and final score

The pipeline preserves the existing selectable decision model.

With weighted sum:

```text
Sᴿ_i = 100 Σ φ_j Dᴿ_ij
```

With the default 2-additive Choquet model:

```text
Sᴿ_i = 100 [Σ φ_j Dᴿ_ij − 1/2 Σ_(j<l) I_jl |Dᴿ_ij − Dᴿ_il|]
```

Camille's `φ` values enter only here. The final scoring adjustment is:

```text
Final_i = Sᴿ_i × A_M,i
```

If an explicitly configured normalization gate fails, the final score is zero and the county is excluded. The existing decision module's independent feasibility gates retain their original behavior. Because they are disabled in the default county-screening CLI, those runs remain in the existing `conditional` ranking pool; the adjustment layer does not pretend that unevaluated project evidence has passed.

## 6. Audit outputs

Each pipeline run writes:

- `ranking.csv`: final score, suitability before margin, margin factor, limiting indicator, base dimensions, adjusted dimensions and all eight robustness factors;
- `scored_counties_audit.csv`: all 18 `raw__*` values and `u__*` piecewise results, every indicator headroom/factor, base dimensions, CMRA historic/future/change/percentile values and adjusted dimensions;
- `decision_output.json`: final ranking plus contribution decomposition and adjustment metadata;
- `indicator_scoring.json`: exact directions, transformations, upper/lower anchors and within-dimension aggregation used;
- `score_adjustments.json`: exact adjustment configuration used;
- `weights.json` and `interactions.json`: unchanged downstream model inputs.

Use `--no-adjustments` only as a diagnostic comparison. It leaves the existing scoring/decision modules usable without the new layer.

## 7. Validation contract

The automated tests verify endpoints and interpolation of the piecewise functions, all 18 configured indicators, equal within-dimension aggregation, weakest-link margin behavior, explicit-only hard gates, full 292-county factor coverage, the one-factor/one-dimension mapping, final-score multiplication, and the unchanged diagnostic path with adjustments disabled.
