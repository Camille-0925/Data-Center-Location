# Validation and Robustness (`dc_locator.validation`)

Step ③b of the pipeline. It answers the judges' obvious question: **would the recommendation change under a different weighting method, different weights, a different interaction strength, different robustness and margin penalties, or a different value-function shape?** It evaluates the same final score as the pipeline: FinalScore = Choquet suitability on the robustness-adjusted dimensions × safety-margin factor (see `docs/SCORING_ADJUSTMENTS.md`). It runs five checks and writes every table to `outputs/validation_<state>/`.

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
| 2 | Parameter uncertainty | **SMAA-2** (Lahdelma & Salminen 2001), 10,000 samples: weights ~ Dirichlet(20 · φ); interaction intensity κ ~ U(0, 1); each robustness coefficient λ_R (cooling, water, climate) and the margin coefficient λ_M ~ U(0.10, 0.30) around the configured 0.20. D^R and A_M are recomputed in every sample | How often is each county #1 or in the top 10? How far from the best can it fall? |
| 3 | Effective weights | Cov(t_k, Final) / Var(Final) with t_k = φ_k · D_k · A_M (interactions as the remainder); the shares sum to 1 | Which dimensions actually drive the ranking? |
| 4 | Customer inputs | Each non-default option, one at a time | Does every input matter? |
| 5 | Value-function shape | Exponential utilities with ρ = −2 and +2 instead of linear | Does the straight-line assumption matter? |

CRITIC and entropy reward dimensions that vary across counties. They measure discrimination, not importance, so they serve as a contrast to the team's judgment rather than a replacement for it.

## Results (default customer, draft judgments, with robustness and margin)

### Virginia

| Check | Result |
|---|---|
| Final #1 | **Louisa County** (66.48). Loudoun has the highest suitability (82.76) but the minimum margin factor 0.80, limited by distance to rail; final 66.21, #2 |
| SMAA p(#1) | Loudoun 37%, Louisa 33%, Washington County 21%, Bristol city 7% |
| SMAA p(top 10) | Louisa 100%, Washington 98%, Loudoun 98%, Bristol 97%, Hanover 92% |
| Lowest 90th-percentile regret | Louisa (4.9 points) |
| Other weighting methods | AHP picks Louisa, ROC picks Loudoun; equal, CRITIC and entropy pick Washington County; DEMATEL picks Hanover. Spearman with the final ranking 0.86–0.99; top-10 overlap 7–9 |
| Effective weights | Water 0.42 and fiber 0.34 of final-score variance (nominal 0.31 and 0.17) |
| Customer inputs | Each option keeps 8–9 of the top 10; evaporative cooling, low latency sensitivity, high reliability and sustainability first put Loudoun at #1 |
| Value-function shape | Top-10 overlap 7–9; Loudoun is #1 with ρ = −2, Louisa with ρ = +2 |

**Conclusion for Virginia:** Louisa, Loudoun and Washington County form a robust leading group (each top 10 in ≥ 97% of samples). Louisa is the safest choice (lowest regret); Loudoun is the most frequent #1 but has a weakest-link exposure (rail distance) that the margin penalizes.

### Georgia

| Check | Result |
|---|---|
| Final #1 | **Fayette County** (62.09), Upson #2 (60.93) |
| SMAA p(#1) | Fayette 52%, Upson 27%, Dade 7% |
| SMAA p(top 10) | Upson 94.5%, Fayette 94.4%, then a gap: Pike 64%, Candler 57%, Glynn 57% |
| Lowest 90th-percentile regret | Fayette (4.7 points) |
| Other weighting methods | AHP, equal, ROC and DEMATEL weights all pick Fayette; CRITIC picks Dade, entropy Forsyth. Spearman 0.23 (entropy) to 0.99 |
| Effective weights | Water 0.51 and fiber 0.34 of final-score variance |
| Customer inputs | 7–9 of the top 10 kept; Fayette stays #1 except with high latency sensitivity (Upson) |
| Value-function shape | Top-10 overlap 5; Glynn becomes #1 with ρ = −2 |

**Conclusion for Georgia:** Fayette and Upson are clear leaders (≈ 94% top-10 each, then a gap). Below them the order depends on the water weight and on the shape of the value functions, so the rest should be presented as a shortlist rather than a ranking.

## Design choices (talking points)

1. **Judgment versus data, shown side by side.** The primary weights come from team judgment (AHP); data-driven methods are a cross-check. Where they agree (Virginia), the result is robust; where they disagree (Georgia), we say so.
2. **Probabilities instead of one ranking.** SMAA reports how often each county wins over 10,000 plausible weight sets, so we can say "Loudoun is #1 in 57% of cases and top 10 in 99%".
3. **Regret.** The 90th-percentile regret says how far a county can fall behind the best one. Loudoun's 7 points is the lowest in Virginia.
4. **Effective weights expose hidden drivers.** Nominal weights understate water and fiber, because they vary most across counties.
5. **Every assumption is perturbed.** Weights, interaction intensity, the robustness and margin coefficients, customer inputs and the value-function shape are each varied.
6. **Exact agreement with the pipeline.** With the coefficients fixed at 0.20, the sampled SMAA reproduces the pipeline's final scores exactly (tested).

## Limitations

- SMAA perturbs weights around the customer's profile (α = 20); it does not explore completely different value systems. The method comparison covers those.
- The AHP, DEMATEL and interaction-type inputs are still single-respondent drafts; the analysis must be rerun after the team session.
- The robustness percentiles are relative to the joint Virginia–Georgia set and are held fixed; only their coefficients are sampled.
- Effective shares can be negative when a dimension moves against the total score; they describe these counties, not causal importance.
