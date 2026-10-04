# Dimension Weights (`dc_locator.dimension_weights`)

Step ③a of the pipeline. It turns **four customer inputs** into the **8 dimension weights** used by the decision matrix. The weights start from an AHP base that reflects the team's judgment; the customer's choices then raise or lower specific dimensions.

```
w0 = AHP priority vector of the team's 8 × 8 pairwise comparisons
w_k = w0_k · M_k / Σ_l (w0_l · M_l)        M_k = product of the multipliers the customer's choices put on dimension k
→ within-state mode: energy & carbon set to 0, renormalize
→ cap: no dimension above 0.40; excess shared pro rata
```

## Run it

Requires Python 3.10+ and numpy (`pip install -r requirements.txt`). Run from the repository root.

```bash
# Default customer (balanced, nothing specified)
PYTHONPATH=src python3 -m dc_locator.dimension_weights

# Evaporative cooling, sustainability first
PYTHONPATH=src python3 -m dc_locator.dimension_weights --cooling_type evaporative --priority sustainability

# Full JSON (weights, AHP diagnostics, multiplier trace)
PYTHONPATH=src python3 -m dc_locator.dimension_weights --latency_sensitivity high --json

# Tests for this module
PYTHONPATH=src python3 -m unittest tests.dimension_weights.test_weights -v
```

Expected output, default customer (within-state mode):

| Dimension | AHP base (8 dims) | Within-state weight |
|---|---|---|
| Water | 0.237 | **0.313** |
| Climate risk | 0.137 | **0.182** |
| Fiber connectivity | 0.130 | **0.172** |
| Land & ecology | 0.080 | **0.106** |
| Cooling climate | 0.070 | **0.093** |
| Workforce & community | 0.060 | **0.079** |
| Transportation | 0.041 | **0.054** |
| Energy & carbon | 0.245 | **0** (state-level data, identical within a state) |

AHP check: λ_max = 8.080, CR = 0.008 (< 0.10), eigenvector and geometric-mean weights agree within 0.001.

With evaporative cooling and sustainability first, water would rise to 0.515. It is capped at **0.40**, and the excess goes to the other dimensions in proportion to their weights.

## The four customer inputs

All four are optional; the defaults reproduce the base weights.

| Input | Options (default in bold) | Effect |
|---|---|---|
| `cooling_type` | evaporative / air_economizer / liquid_closed_loop / **unknown** | Evaporative: water ×1.5. Air: water ×0.6, cooling ×1.5. Liquid closed loop: water ×0.5, cooling ×0.5 |
| `latency_sensitivity` | low / **normal** / high | Fiber ×0.6 / ×1 / ×1.6 |
| `reliability_requirement` | **standard** / high | High (Tier IV or 30+ year life): climate risk ×1.5 |
| `priority` | **balanced** / sustainability / operations | Sustainability: water, cooling, land (and energy, cross-state) ×2. Operations: fiber, workforce, transport ×2 |

Why each multiplier exists: evaporative cooling consumes water, so local water stress matters more; air-side economizers depend on outside temperature; closed-loop liquid cooling needs little water and tolerates heat; latency-sensitive workloads (inference, edge, finance) depend on network quality; a longer or more critical life accumulates more climate exposure.

## Method and sources

| Step | Method | Source |
|---|---|---|
| Base weights | Principal eigenvector of the 8 × 8 pairwise comparison matrix (Saaty 1–9 scale) | Saaty (1980), *The Analytic Hierarchy Process* |
| Consistency | CR = CI / RI, CI = (λ_max − n)/(n − 1), RI(8) = 1.41; reject CR ≥ 0.10 | Saaty (1980) |
| Cross-check | Row geometric mean; warn if it differs from the eigenvector by > 0.01 | Crawford & Williams (1985) |
| Several team members | Element-wise geometric mean of individual matrices (AIJ), then the same steps | Forman & Peniwati (1998) |
| Customer adjustment | Multiply and renormalize. Equivalent to multiplying each AHP ratio w_k/w_l by M_k/M_l, so the result stays a ratio-scale weight vector | — |

Citations are from memory; verify volume and page numbers before using them in the report.

## Configuration

`configs/dimension_weights.json` holds everything that is a judgment, so it can change without touching the code:

- `ahp.respondents`: each team member's 28 pairwise judgments, `[row_dimension, column_dimension, value]`. The file currently holds one draft respondent; add the others after the team session.
- `customer_inputs`: options, defaults and multipliers.
- `within_state_excluded`: dimensions set to 0 when ranking counties inside one state.
- `max_dimension_weight`: the cap (0.40).

## Output

`compute_dimension_weights(customer_inputs, mode)` returns:

| Field | Meaning | Use in report / slides |
|---|---|---|
| `weights` | Final 8 weights (sum to 1). Passed to the decision matrix as `dimension_weights` | Weight bar chart per customer profile |
| `reference_weights` | Weights for a default customer in the same mode | Baseline for comparison |
| `change_from_reference` | Final minus reference, per dimension | "Choosing evaporative cooling moves 9 points of weight to water" |
| `multiplier_trace` | Every multiplier applied: input, choice, dimension, factor | Explains each change |
| `capped_dimensions` | Dimensions held at the 0.40 cap | — |
| `ahp` | Base weights, geometric-mean weights, λ_max, CI, CR, per-respondent CR, warnings | Methodology slide: consistency check |

## Design choices (talking points for the report)

1. **Value judgment versus customer need.** "How much does water matter relative to fiber" is a team judgment, captured once with AHP and checked for consistency. "What does this project need" comes from the customer and only scales the judgment; it does not replace it.
2. **Simple inputs.** Customers never weigh 8 dimensions. They answer four multiple-choice questions about their project, and each answer maps to a documented, physically motivated multiplier.
3. **Ratio-scale consistency.** Multiplicative adjustment preserves the meaning of AHP weights as ratios of importance.
4. **No single dimension dominates.** The 0.40 cap stops combined inputs (for example evaporative cooling plus sustainability first) from turning the ranking into a single-criterion sort.
5. **State-level data handled explicitly.** Within one state, energy & carbon is identical for every county, so it gets weight 0 for county ranking and is used only for the cross-state comparison.
6. **Fully traceable.** Every final weight can be explained by the AHP base and the list of multipliers applied.

## Limitations

- The AHP matrix is a single-respondent draft; the team session will replace it.
- Multiplier sizes (×1.5, ×0.6, ×2) are assumptions; step ③b tests how sensitive the ranking is to them (SMAA).
- Interactions between dimensions (redundancy, synergy) are not modelled here. They are handled in steps ③c/③d and in the Choquet scoring of the decision matrix.
