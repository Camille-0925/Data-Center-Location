# Decision Matrix (`dc_locator.decision`)

Step ④ of the pipeline, and the simplest one. It takes an **n × 8 matrix** of dimension scores (n counties, 8 dimensions, each 0–1, higher is better) and **8 dimension weights**. For each county it returns a **suitability score (0–100)**, a **rank**, a **Pareto status**, and its **trade-offs** against the leader.

```
Score_i = 100 × Σ_k w_k · D_ik          (Σ w_k = 1,  0 ≤ D_ik ≤ 1)
```

The matrix does not look below the dimension level. Raw indicators, utility functions and how indicators combine into a dimension score belong to step ② (`dc_locator.indicator_scoring`); the weights come from step ③ (`dc_locator.dimension_weights`).

Originally written by Adelyn for a 7-dimension model. v0.4 takes dimension scores only, reads the dimension list from the configuration, and makes the feasibility gates optional.

## Run it

Requires Python 3.10+, standard library only. Run from the repository root.

```bash
# 1. Tests (36 in the repo; 28 cover this module)
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v

# 2. Score and rank the example (3 synthetic counties, gates disabled)
PYTHONPATH=src python3 -m dc_locator.decision recommend \
  --request tests/fixtures/decision_request_8d.json \
  --output-dir outputs/demo
```

The example uses the default within-state weights. Energy & carbon gets weight 0 because its data is state-level and identical for every county in a state. Expected `outputs/demo/recommendations.json`:

| rank | county (synthetic) | score | strong on | weak on | Pareto |
|---|---|---|---|---|---|
| 1 | Example A (rural, water-secure) | 62.17 | water 0.85, land 0.80 | fiber 0.30, workforce 0.25 | non-dominated |
| 2 | Example B (urban, connected) | 60.17 | fiber 0.95, transport 0.95 | water 0.40, land 0.30 | non-dominated |
| 3 | Example C (balanced) | 60.00 | 0.60 everywhere | — | non-dominated |

All three are non-dominated: each beats the others somewhere. The weights decide the order, and that is exactly what the customer inputs in step ③ change.

Hand check for Example A, with weights water 0.267, climate 0.200, fiber 0.167, land 0.133, workforce 0.100, cooling 0.067, transport 0.067:
0.267·0.85 + 0.200·0.70 + 0.167·0.30 + 0.133·0.80 + 0.100·0.25 + 0.067·0.70 + 0.067·0.40 = 0.6217 → **62.17**.

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

result = recommend(dimension_scores, scoring_config, context)   # gates off by default
```

## Inputs

| Input | Produced by | Contents |
|---|---|---|
| `dimension_scores` | step ② | One record per county: `candidate_id`, optional `candidate_name`, `scores` = {dimension_id: D (0–1) or `null`} |
| `scoring_config` | step ③ | `dimension_order` (list of dimension ids), `dimension_weights` (sum to 1; 0 allowed), `version`, `status` |
| `context` | pipeline | Run id, versions, run mode (`test` / `demo` / `real`) |
| `constraint_rules`, `project_profile`, `evidence_records` | optional | Feasibility gates; omitted = gates off |

See `tests/fixtures/decision_request_8d.json` for a complete example.

## Outputs (per county, in `recommendations.json`)

| Field | Meaning | Use in report / slides |
|---|---|---|
| `score_0_100`, `rank` | Suitability score; competition rank (ties within 1e-8 share a rank: 1, 1, 3) | Ranking table, map colour |
| `dimension_scores` | The 8 scores D | Radar chart per county |
| `dimension_contributions` | Points from each dimension, 100·w·D; they sum to the score | Stacked bar: why this county scores high |
| `pareto_status` | `non_dominated` if no other county is at least as good on all 8 dimensions and better on one | Shortlist that holds under any weights |
| `tradeoffs` | Per-dimension gap from the leader (or from #2, for the leader), in score and in weighted points | "B loses 12 points to A on water but gains 10 on fiber" |
| `missing_dimension_ids` | Dimensions with no score; the county is then unranked | Data-gap table |
| `eligibility_status` | `conditional` when gates are off; `incomplete` when a dimension is missing | — |

Run-level `diagnostics` include a warning when a dimension with weight > 0 has the same score for every county, since its weight then cannot change the ranking.

## Design choices (talking points for the report)

1. **One job only.** The matrix multiplies an n × 8 table by 8 weights. How each dimension score is built is decided upstream, so changing a utility function or an aggregation rule never touches the ranking code.
2. **Configuration-driven.** The dimension list and weights come from the configuration. The same code ran the earlier 7-dimension design and runs the current 8-dimension one; a test also runs a 3-dimension configuration.
3. **Transparent totals.** Every score splits exactly into 8 dimension contributions, so "why this county" can be shown in one chart.
4. **No silent gap-filling.** A missing dimension leaves the score empty and the county unranked. It is never filled with 0 or 50. A real score of 0 is kept.
5. **Flags weights that do nothing.** A dimension that scores the same everywhere (energy & carbon within one state) cannot change the ranking; the module says so instead of letting its weight look meaningful.
6. **Pareto status alongside the weighted score.** Counties that no other county beats on every dimension are flagged regardless of the weights, so conclusions do not rest on a single weight set.
7. **Feasibility gates are separate from scoring.** Power capacity, delivery date, land, network and water permission are pass / fail / unknown checks, not scores. They are switched off for now and can be re-enabled without code changes.

## Limitations

- The score is a regional screen. It does not approve construction on any specific site.
- The weighted sum is compensatory across dimensions: strength in one can offset weakness in another. Pareto status and the trade-off table expose this; step ② limits compensation within a dimension.
- With gates off, no county is marked verified feasible.
