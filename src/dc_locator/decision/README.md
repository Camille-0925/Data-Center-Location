# Decision Matrix (`dc_locator.decision`)

Step ④ of the pipeline. It takes each county's indicator scores and dimension scores, plus the dimension weights derived from customer inputs, and produces a **suitability score (0–100)**, a **rank**, a **Pareto status**, and **trade-offs** against the leading county.

Originally written by Adelyn for a 7-dimension model with one indicator per dimension. Version v0.3 generalizes it: dimensions, indicators, both layers of weights, and the way indicators combine into a dimension score now come from configuration, so the same code runs the 8-dimension model.

## Run it

Requires Python 3.10+, standard library only. Run from the repository root.

```bash
# 1. Tests (33 should pass)
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v

# 2. Score and rank an example request (2 counties, synthetic values, gates disabled)
PYTHONPATH=src python3 -m dc_locator.decision recommend \
  --request tests/fixtures/decision_request_8d.json \
  --output-dir outputs/demo
```

Expected result in `outputs/demo/recommendations.json`:

| candidate_id | score_0_100 | rank | why |
|---|---|---|---|
| 51107 | 43.125 | 1 | Its cooling-climate dimension scores 0.65; every other dimension scores 0.40 |
| 51013 | 40.000 | 2 | All dimensions score 0.40 |

`outputs/demo/diagnostics.json` will also list the 7 dimensions on which both counties score the same, since those dimensions cannot change the ranking.

To compare two runs, for example before and after a customer changes an input:

```bash
PYTHONPATH=src python3 -m dc_locator.decision compare \
  --previous outputs/run_a/decision_output.json \
  --current  outputs/run_b/decision_output.json \
  --output   outputs/change_report.json
```

From Python:

```python
from dc_locator.decision import recommend

result = recommend(metric_results, indicator_scores, dimension_scores,
                   scoring_config, project_profile=None, constraint_rules=None,
                   evidence_records=None, context=context)
```

## How the score is calculated

*u* is an indicator's utility score (0–100), *ω* its within-dimension weight (the ω in one dimension sum to 1), *D* a dimension score (0–1), and *w* a dimension weight (the w sum to 1).

**Step 1. Indicators → dimension score.** Each dimension declares one aggregation method in `scoring_config.dimension_aggregation` (default `weighted_mean`):

| Method | Formula | Use when | Planned for |
|---|---|---|---|
| `weighted_mean` | D = Σ ω·u / 100 | Indicators can offset each other | Transportation, energy & carbon |
| `weighted_geometric` | D = Π (u/100)^ω | A poor indicator should not be hidden by a good one | Climate risk, land & ecology |
| `min` | D = min(u) / 100 | The worst indicator decides | Water (current vs 2050 stress) |

Example: wildfire u = 90, flood u = 10. The weighted mean gives D = 0.50; the geometric mean gives D = √(0.9 × 0.1) = 0.30. A county with a severe flood risk is not rescued by low wildfire risk.

**Step 2. Dimension scores → suitability score.**

```
Score_i = 100 × Σ_k w_k · D_ik
```

The module recomputes every dimension score from its indicator scores using the declared method and stops with an error if the supplied value differs by more than 1e-7. Mistakes in the upstream scoring step are caught instead of silently ranked.

## Inputs

All inputs are JSON objects. Every envelope carries the same `context` (run id, versions, run mode).

| Input | Produced by | Contents |
|---|---|---|
| `scoring_config` | ② + ③ | `dimension_order`; `dimension_weights` (*w*, sum to 1); `dimension_aggregation` (optional, per dimension); `indicators` (each with `metric_id`, `dimension_id`, `unit`, `direction`, anchors, `local_weight` *ω*) |
| `metric_results` | ① | Raw value of each county × indicator, with unit, data status and provenance |
| `indicator_scores` | ② | Utility *u* (0–100) for each county × indicator |
| `dimension_scores` | ② | *D* (0–1) for each county × dimension |
| `constraint_rules` | optional | `{"gates_enabled": false}` or `null` skips the feasibility gates |

See `tests/fixtures/decision_request_8d.json` for a complete example.

## Outputs

| Field per county | Meaning |
|---|---|
| `score_0_100`, `rank` | Suitability score and competition rank (ties within 1e-8 share a rank: 1, 1, 3) |
| `dimension_scores` | The 8 dimension scores, useful for radar charts |
| `dimension_contributions` | Points each dimension contributes (100 · *w* · *D*); they always sum to the total score. Use for a stacked bar per county |
| `metric_contributions` | Points each indicator contributes (*w · ω · u*). Only defined for `weighted_mean` dimensions; `null` for geometric / min dimensions, where an indicator's share cannot be separated |
| `pareto_status` | `non_dominated` if no other county is at least as good on every raw indicator and strictly better on one |
| `tradeoffs` | Raw indicator differences from the top-ranked county (or from #2, for the leader) |
| `eligibility_status` | `conditional` when gates are off; `incomplete` when an indicator is missing |
| `missing_metric_ids` | Indicators that blocked a score |

Run-level `diagnostics` list warnings, for example that gates are disabled, or that a dimension has the same score for every county.

## Design choices (talking points for the report)

1. **Configuration-driven.** Adding or removing a dimension or indicator changes only the configuration, not the code. The same matrix ran the earlier 7-dimension design and runs the current 8-dimension design.
2. **Two layers of weights.** *w* captures what the customer cares about across dimensions; *ω* balances indicators within a dimension. Customer inputs change *w* only, so every shift in the ranking traces back to a specific input.
3. **Transparent scores.** Every total decomposes into 8 dimension contributions, and linear dimensions further into indicator contributions, so the explanation for "why this county" can be shown directly in a chart.
4. **Aggregation matches the meaning of each dimension.** Risks that should not offset each other use a geometric mean; near-duplicate indicators (current vs 2050 water stress) use the worse of the two instead of counting the same signal twice; everything else is a weighted mean.
5. **No silent gap-filling.** A missing indicator leaves the score empty and the county unranked. It is never filled with 0 or 50.
6. **Flags weights that do nothing.** If a dimension has the same score in every county, as energy & carbon does within a state (price, SAIDI and CO₂e are state-level data), the module warns that its weight cannot change the ranking.
7. **Pareto status alongside the weighted score.** A county that no other county beats on every indicator is flagged `non_dominated` regardless of the weights. This guards against conclusions that depend entirely on one set of weights.
8. **Feasibility gates are separate from scoring.** Power capacity, delivery date, land, network and water permission are pass / fail / unknown checks, not scores. They are switched off in the current version and can be re-enabled without code changes.

## Limitations

- The score is a regional screen built on proxy indicators. It does not approve construction on a specific site.
- Gates are disabled for now, so no county is marked verified feasible.
- Across dimensions the weighted sum is compensatory: strength in one dimension can offset weakness in another. Geometric and minimum aggregation limit this only within a dimension. The Pareto status and contributions are there to expose it.
- With `weighted_geometric` or `min`, a single indicator scoring 0 makes the whole dimension 0. Anchors for those indicators must put 0 at a truly unacceptable value (handled in step ②).
