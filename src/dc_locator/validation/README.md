# Validation and Robustness (`dc_locator.validation`)

Step ③b of the pipeline. It answers the judges' obvious question: **would the recommendation change under a different weighting method, different weights, a different interaction strength, or a different value-function shape?** It runs five checks and writes every table to `outputs/validation_<state>/`.

## Run it

Requires Python 3.10+, numpy and pandas. About 2 seconds per state.

```bash
PYTHONPATH=src python3 -m dc_locator.validation --state VA            # 10,000 SMAA samples, seed 42
PYTHONPATH=src python3 -m dc_locator.validation --state GA --samples 20000
PYTHONPATH=src python3 -m unittest tests.validation.test_validation -v
```

Output files: `method_weights.csv`, `method_comparison.csv`, `smaa_robustness.csv`, `smaa_rank_acceptability.csv`, `effective_weights.csv`, `customer_input_response.csv`, `utility_shape_sensitivity.csv`, `summary.json`.

## The five checks

| # | Check | Method | Question |
|---|---|---|---|
| 1 | Weighting method | Same counties ranked with AHP, equal, ROC (Barron & Barrett 1996), CRITIC (Diakoulaki et al. 1995), entropy, and DEMATEL-derived weights | Does the result hinge on AHP? |
| 2 | Weight uncertainty | **SMAA-2** (Lahdelma & Salminen 2001): weights ~ Dirichlet(20 · φ), interaction intensity κ ~ U(0, 1), 10,000 samples | How often is each county #1 or in the top 10? How far from the best can it fall? |
| 3 | Effective weights | φ_k · Cov(D_k, S) / Var(S): each dimension's share of the variance of the final score | Which dimensions actually drive the ranking? |
| 4 | Customer inputs | Each non-default option, one at a time | Does every input matter? |
| 5 | Value-function shape | Exponential utilities with ρ = −2 and +2 instead of linear | Does the straight-line assumption matter? |

CRITIC and entropy reward dimensions that vary across counties. They measure discrimination, not importance, so they serve as a contrast to the team's judgment rather than a replacement for it.

## Results (default customer, draft judgments)

### Virginia: robust

| Check | Result |
|---|---|
| Final #1 | **Loudoun County** |
| SMAA p(#1) | Loudoun 57%, Washington County 36%, Bristol city 3%, Louisa 2% |
| SMAA p(top 10) | Louisa 99.7%, Washington 99.6%, Loudoun 98.7%, Smyth 94%, Bristol 91% |
| Lowest 90th-percentile regret | Loudoun (7.0 points) |
| Other weighting methods | AHP and ROC pick Loudoun; equal, CRITIC, entropy and DEMATEL weights pick Washington County. Spearman with the final ranking 0.81–0.99; top-10 overlap 7–10 |
| Effective weights | Water 0.49 and fiber 0.33 of score variance (nominal 0.31 and 0.17); climate −0.06, because in Virginia low climate risk comes with weaker other dimensions |
| Customer inputs | Each option keeps 8–10 of the top 10; air cooling, high latency sensitivity and operations priority move Washington County to #1; liquid cooling moves Louisa to #1 |
| Value-function shape | Top-10 overlap 8–9, Spearman 0.96–0.97; Loudoun stays #1 |

**Conclusion for Virginia:** Loudoun and Washington County are the two robust leaders. Which one is first depends on the weights, and the customer inputs show exactly when Washington overtakes.

### Georgia: weight-sensitive

| Check | Result |
|---|---|
| Final #1 | **Dade County** |
| SMAA p(#1) | Dade 38%, Candler 20%, Bulloch 9%, Fayette 8%, Glynn 7%, Sumter 6% |
| SMAA p(top 10) | Dade 79%, Candler 77%, Sumter 76%, Upson 71%, Fayette 65% |
| Other weighting methods | Strong disagreement: Spearman 0.19 (entropy) to 0.94 (ROC); equal and entropy weights pick Whitfield County |
| Effective weights | **Water explains 66% of score variance** (nominal 0.31) |
| Customer inputs | 7–9 of the top 10 kept; Dade stays #1 except under liquid cooling (Spalding) and high reliability (Candler) |
| Value-function shape | Top-10 overlap 8; Fayette becomes #1 with ρ = +2 |

**Conclusion for Georgia:** recommend a shortlist (Dade, Candler, Sumter), not a single winner. The ranking is driven by water stress. Weighting methods that discount water reorder the field, so the water weight should be stated explicitly.

## Design choices (talking points)

1. **Judgment versus data, shown side by side.** The primary weights come from team judgment (AHP); data-driven methods are a cross-check. Where they agree (Virginia), the result is robust; where they disagree (Georgia), we say so.
2. **Probabilities instead of one ranking.** SMAA reports how often each county wins over 10,000 plausible weight sets, so we can say "Loudoun is #1 in 57% of cases and top 10 in 99%".
3. **Regret.** The 90th-percentile regret says how far a county can fall behind the best one. Loudoun's 7 points is the lowest in Virginia.
4. **Effective weights expose hidden drivers.** Nominal weights understate water and fiber, because they vary most across counties.
5. **Every assumption is perturbed.** Weights, interaction intensity, customer inputs and the value-function shape are each varied.

## Limitations

- SMAA perturbs weights around the customer's profile (α = 20); it does not explore completely different value systems. The method comparison covers those.
- The AHP, DEMATEL and interaction-type inputs are still single-respondent drafts; the analysis must be rerun after the team session.
- Effective shares can be negative when a dimension moves against the total score; they describe these counties, not causal importance.
