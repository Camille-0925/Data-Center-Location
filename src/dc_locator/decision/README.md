# Decision Matrix (`dc_locator.decision`)

Step ④ of the pipeline. It takes each county's indicator scores and dimension scores, plus the dimension weights derived from customer inputs, and produces a **suitability score (0–100)**, a **rank**, a **Pareto status**, and **trade-offs** against the leading county.

Originally written by Adelyn for a 7-dimension model with one indicator per dimension. Version v0.3 generalizes it: dimensions, indicators and both layers of weights now come from configuration, so the same code runs the 8-dimension, 18-indicator model.

## Run it

Requires Python 3.10+, standard library only. Run from the repository root.

```bash
# 1. Tests (25 should pass)
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

Each county *i* is scored as follows. *u* is an indicator's utility score (0–100), *ω* is its within-dimension weight, *D* is a dimension score (0–1), and *w* is a dimension weight.

```
D_ik = Σ_{j ∈ dimension k} ω_j · u_ij / 100          (within-dimension weights ω sum to 1)
Score_i = 100 × Σ_k w_k · D_ik                        (dimension weights w sum to 1)
```

The module computes the score two ways, from the dimension scores and from the indicator contributions *w · ω · u*, and stops with an error if they differ by more than 1e-7. Each county's output lists the contribution of all 18 indicators, so its total can be explained term by term.

## Inputs

All inputs are JSON objects. Every envelope carries the same `context` (run id, versions, run mode).

| Input | Produced by | Contents |
|---|---|---|
| `scoring_config` | ② + ③ | `dimension_order`; `dimension_weights` (*w*, sum to 1); `indicators` (each with `metric_id`, `dimension_id`, `unit`, `direction`, anchors, `local_weight` *ω*) |
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
| `metric_contributions` | Points each indicator contributes (*w · ω · u*); they sum to the total score |
| `pareto_status` | `non_dominated` if no other county is at least as good on every raw indicator and strictly better on one |
| `tradeoffs` | Raw indicator differences from the top-ranked county (or from #2, for the leader) |
| `eligibility_status` | `conditional` when gates are off; `incomplete` when an indicator is missing |
| `missing_metric_ids` | Indicators that blocked a score |

Run-level `diagnostics` list warnings, for example that gates are disabled, or that a dimension has the same score for every county.

## Design choices (talking points for the report)

1. **Configuration-driven.** Adding or removing a dimension or indicator changes only the configuration, not the code. The same matrix ran the earlier 7-dimension design and runs the current 8-dimension design.
2. **Two layers of weights.** *w* captures what the customer cares about across dimensions; *ω* balances indicators within a dimension. Customer inputs change *w* only, so every shift in the ranking traces back to a specific input.
3. **Transparent scores.** Every total decomposes into 18 indicator contributions, so the explanation for "why this county" can be shown directly in a chart.
4. **No silent gap-filling.** A missing indicator leaves the score empty and the county unranked. It is never filled with 0 or 50.
5. **Flags weights that do nothing.** If a dimension has the same score in every county, as energy & carbon does within a state (price, SAIDI and CO₂e are state-level data), the module warns that its weight cannot change the ranking.
6. **Pareto status alongside the weighted score.** A county that no other county beats on every indicator is flagged `non_dominated` regardless of the weights. This guards against conclusions that depend entirely on one set of weights.
7. **Feasibility gates are separate from scoring.** Power capacity, delivery date, land, network and water permission are pass / fail / unknown checks, not scores. They are switched off in the current version and can be re-enabled without code changes.

## Limitations

- The score is a regional screen built on proxy indicators. It does not approve construction on a specific site.
- Gates are disabled for now, so no county is marked verified feasible.
- The weighted sum is compensatory: strength in one dimension can offset weakness in another. The Pareto status and per-indicator contributions are there to expose this.
