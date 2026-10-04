# Indicator scoring and score adjustments

This package owns everything below Camille's dimension weights:

```text
raw values → utilities U (0–100) → base dimensions D (0–1)
           → indicator margin A_M + dimension robustness Dᴿ
```

The complete formulas, all 18 anchors and the audit contract are in repository-relative path `docs/SCORING_ADJUSTMENTS.md`.

## Configuration

- `configs/indicator_scoring.json`: 18 indicator directions, transforms, good anchors `T`, bad boundaries `L`, and equal within-dimension weights.
- `configs/score_adjustments.json`: margin parameters, explicit hard-zero indicator list, robustness-to-dimension mapping and the precomputed factor-table path.
- `data/processed/county_robustness_va_ga.csv`: version-locked CMRA historical/future/downside/percentile/factor values for all 292 county equivalents.

No function in this package receives the eight dimension weights. This ensures a customer-weight change cannot change normalization, margin, or temporal-risk percentiles.

## Public functions

- `score_counties(table)`: identifiers, 8 base dimensions, 18 `u__*` utilities and context views.
- `apply_pre_weight_adjustments(scored, scoring_config, adjustments_config)`: preserves `base__*`, calculates all margin audit columns, attaches CMRA components and replaces the ordinary dimension columns with `Dᴿ`.
- `apply_final_score_adjustments(decision, adjusted_counties, dimension_order)`: applies the single county `A_M` after suitability and refreshes ranks.
- `load_robustness_factors(config)`: validates and loads the committed FIPS factor table.
- `dimension_score_records(scored, order)`: sends the current dimension columns to the unchanged decision matrix.

## Run

```bash
PYTHONPATH=src python3 -m dc_locator.indicator_scoring --state VA
PYTHONPATH=src python3 -m dc_locator.pipeline --state VA
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v
```

The full pipeline enables margin and temporal robustness by default. Use `--no-adjustments` only for a regression/diagnostic run.
