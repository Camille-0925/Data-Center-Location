# Slide brief: the decision matrix and customer-driven dynamic weights

> For the teammates building the slides. Each section is one slide, with a **suggested title**, **on-slide points**, **formulas**, **suggested visual** and **speaker notes**.
> All numbers come from actual runs of the repository (default customer: 100 MW by 2029-12-31; draft single-respondent judgments). They include Adelyn's indicator scoring, temporal robustness and safety margin (`docs/SCORING_ADJUSTMENTS.md`) and the feasibility gates. After the team scoring session, rerun and update them; see the last section.
> Code: `src/dc_locator/decision/`, `dimension_weights/`, `interactions/`, `validation/`.
> A Chinese–English version with the same content is in `docs/PPT_决策矩阵与动态权重.md`.

---

## Notation (appendix slide, or the first slide that shows a formula)

| Symbol | Meaning | Range |
|---|---|---|
| i | County | 133 in Virginia, 159 in Georgia |
| k, l | Dimension | 8 |
| D_ik | Base score of county i on dimension k (equal-weight mean of its indicator utilities) | 0–1, higher is better |
| Dᴿ_ik | Dimension score after the temporal-robustness adjustment | 0–1 |
| A_M,i | Safety-margin factor | 0.80–1 |
| F_i | Feasibility flag (gates) | 0 / 1 / unresolved |
| w0_k | Base weight from team judgment (AHP) | sums to 1 |
| M_k | Multiplier that the customer's needs put on dimension k | > 0, 1 by default |
| φ_k | Final dimension weight (importance in the Choquet integral) | sums to 1 |
| I_kl | Interaction index between dimensions k and l | [−1, 1]; > 0 complementarity, < 0 redundancy |
| κ | Interaction intensity | 0–1, default 0.5 |

The 8 dimensions: Climate risk, Water, Land & ecology, Fiber, Workforce & community, Cooling climate, Transportation, Energy & carbon.

---

## Slide 1: Framework

**Title**: *From customer needs to a county ranking*

**On slide (flow diagram)**:

```
County data (18 indicators) ──► utilities U ──► dimension scores D ──► climate projections ──► Dᴿ (n × 8)
Customer needs (4 questions) ──► dynamic weights φ (8)
Team judgment (DEMATEL) + county data (correlation) ──► interaction matrix I (8 × 8)
                                         │
              Choquet suitability Sᴿ(Dᴿ, φ, I) × safety margin A_M × feasibility F ──► final score, rank, robustness
```

**The one formula of the deck**:

$$
\text{FinalScore}_i = F_i \times S^{R}_i \times A_{M,i}
$$

**Speaker notes**:
- Four questions are answered in separate layers instead of one weighted average: **suitability** Sᴿ (how attractive overall), **feasibility** F (any non-negotiable obstacle?), **safety margin** A_M (how far from the weakest boundary?), and **temporal robustness** (how much will the climate deteriorate, applied to the affected dimensions).
- The customer's needs decide what matters (φ). Team judgment plus data decide how the dimensions affect each other (I). County data and climate projections say how each county performs on each dimension (Dᴿ).

**Visual**: the flow diagram above, with the three kinds of input in three colours.

---

## Slide 2: The decision matrix

**Title**: *The decision matrix: n counties × 8 dimensions*

**On slide**:
- Input: an n × 8 table of dimension scores, 8 weights, and an 8 × 8 interaction matrix.
- Output: each county's score (0–100), rank, Pareto status, and its gap to the leader on each dimension.

**Formula (large, centred)**:

$$
S^{R}_i = 100 \times \Big[\underbrace{\sum_{k} \varphi_k D^{R}_{ik}}_{\text{each dimension on its own}} \;-\; \underbrace{\tfrac{1}{2}\sum_{k<l} I_{kl}\,\lvert D^{R}_{ik}-D^{R}_{il}\rvert}_{\text{interactions between dimensions}}\Big]
$$

**Speaker notes**:
- This is the **2-additive Choquet integral** (Grabisch 1997), the standard multi-criteria method for criteria that are not independent.
- The first term is the familiar weighted sum; the second term corrects for interactions. The matrix receives the robustness-adjusted scores Dᴿ (slide 10), and its output Sᴿ is multiplied by the safety margin A_M (slide 11) to give the final score.
- When every I is 0, the formula **reduces to the weighted sum**. The conventional method is a special case of our model.

**Visual**: an n × 8 heat-map table (rows = counties, columns = dimensions, colour = D), with a row of 8 weights beside it and an arrow to "Score".

---

## Slide 3: Innovation 1 — dimensions are not assumed independent

**Title**: *Dimensions interact: synergy and overlap*

**On slide**:

| Interaction | Meaning | Example | Effect on the score |
|---|---|---|---|
| **Complementarity** (I > 0) | Both dimensions must be good | A hot climate raises cooling water demand, exactly where water may be scarce | An imbalance between the two costs points |
| **Redundancy** (I < 0) | The two dimensions partly measure the same thing | Good transport and a large workforce both reflect proximity to a city | Being high on both is not rewarded twice |

**Worked example (two-county bar chart)**: both dimensions weighted 0.5, I = +0.4 (complementarity)

| County | Water | Cooling | Weighted sum | Choquet |
|---|---|---|---|---|
| Balanced | 0.5 | 0.5 | 50 | **50** |
| Imbalanced | 0.9 | 0.1 | 50 | **34** |

**Speaker notes**:
- A weighted sum rates these two counties as equal. For a data center, a site with plenty of water but extreme heat concentrates cooling demand on that water, so the risks compound. Choquet captures this.
- With I = −0.4 (redundancy) the imbalanced county scores 66 instead: when two dimensions measure the same thing, being strong on one is enough and should not be rewarded twice.

---

## Slide 4: Completeness 1 — mathematical guarantees

**Title**: *Guaranteed properties*

**On slide (checklist)**:

| Property | Meaning | How it is guaranteed |
|---|---|---|
| ✅ Monotone | Improving any dimension never lowers the score | Necessary and sufficient condition **φ_k ≥ ½ Σ_l \|I_kl\|**; the model refuses to run if it fails |
| ✅ Bounded | All dimensions 0 → 0 points; all 1 → 100 points | Σφ = 1 plus monotonicity |
| ✅ Idempotent | If every dimension scores c, the total is 100c | Interaction terms act only on gaps between dimensions |
| ✅ Exact decomposition | Score = 8 dimension contributions + one term per interaction, adding up exactly | Every term is listed in the output |
| ✅ Contains the weighted sum | With I = 0 it equals the conventional method | Verified by tests |
| ✅ Correct implementation | Matches an independent implementation of Grabisch's equivalent min/max form | 20 random counties, 8 dimensions |

**Derivation of the monotonicity condition (appendix slide)**: in Möbius form, m_k = φ_k − ½ Σ_l I_kl and m_kl = I_kl. The capacity is monotone if and only if, for every k and every set S not containing k, m_k + Σ_{l∈S} m_kl ≥ 0. The worst case is S = {l : I_kl < 0}, which simplifies to exactly φ_k − ½ Σ_l |I_kl| ≥ 0.

**Speaker notes**: the main risk of adding interaction terms is a perverse result, where a county improves on a dimension and its score goes down. We derived the exact condition that rules this out, enforce it in the code, and checked monotonicity with 200 random tests.

---

## Slide 5: Base weights from team judgment (AHP)

**Title**: *Base weights from team judgment (AHP)*

**On slide**:
- The team makes 28 pairwise comparisons of the 8 dimensions on Saaty's 1–9 scale.
- Weights are the principal eigenvector of the comparison matrix, cross-checked with the row geometric mean.
- Consistency check: CR = CI / RI must be below 0.10.
- With several team members, matrices are combined cell by cell with the geometric mean (Forman & Peniwati 1998).

**Formula**:

$$
A\,w^{0} = \lambda_{\max}\, w^{0}, \qquad CI = \frac{\lambda_{\max}-n}{n-1}, \qquad CR = \frac{CI}{RI(8)=1.41} < 0.10
$$

**Current result (single-respondent draft)**: λ_max = 8.080, **CR = 0.008**, largest gap between the two methods 0.0009.

| Dimension | Base weight w0 |
|---|---|
| Energy & carbon | 0.245 |
| Water | 0.237 |
| Climate risk | 0.137 |
| Fiber | 0.130 |
| Land & ecology | 0.080 |
| Cooling climate | 0.070 |
| Workforce & community | 0.060 |
| Transportation | 0.041 |

**Speaker notes**: whether carbon matters more than water is a value judgment that data cannot settle. The team makes it, and the consistency check ensures the judgments do not contradict each other.

**Visual**: horizontal bar chart of the 8 base weights.

---

## Slide 6: Customer needs → dynamic weights (key slide)

**Title**: *Customer needs reshape the weights*

**On slide: the customer answers four multiple-choice questions, all with defaults**

| Question | Options (**default** in bold) | Effect |
|---|---|---|
| Cooling technology | evaporative / air economizer / closed-loop liquid / **unknown** | Evaporative: water ×1.5. Air: water ×0.6, cooling ×1.5. Liquid: water ×0.5, cooling ×0.5 |
| Latency sensitivity | low / **normal** / high | Fiber ×0.6 / ×1 / ×1.6 |
| Reliability requirement | **standard** / high (Tier IV or 30+ year life) | Climate risk ×1.5 |
| Overall priority | **balanced** / sustainability first / operations first | Sustainability: water, cooling, land (and energy in the cross-state comparison) ×2. Operations: fiber, workforce, transport ×2 |

**Formula (three steps)**:

$$
\varphi_k = \frac{w^{0}_k \, M_k}{\sum_l w^{0}_l \, M_l}
\quad\longrightarrow\quad
\text{within a state: } \varphi_{\text{energy}} = 0,\ \text{renormalize}
\quad\longrightarrow\quad
\varphi_k \le 0.40\ \text{(excess shared pro rata)}
$$

M_k is the product of the multipliers that the customer's answers put on dimension k.

**Speaker notes**:
- **Clear division of roles.** How much one dimension matters relative to another is decided once by the team (AHP). What this project needs comes from the customer. The customer's answers adjust the team's judgment; they do not replace it.
- **Every multiplier has a physical reason.** Evaporative cooling consumes water; air-side economizers depend on outside temperature; closed-loop liquid cooling uses little water and tolerates heat; latency-sensitive workloads depend on the network; a longer or more critical life accumulates more climate exposure.
- **The ratio scale is preserved.** Multiplying the weights is the same as multiplying every AHP ratio w_k / w_l by M_k / M_l, so the adjusted weights are still meaningful ratio-scale weights. For example, choosing "high latency sensitivity" makes the fiber-to-water weight ratio exactly 1.6 times its original value.
- **0.40 cap per dimension.** Prevents combined answers from letting one dimension dominate and turning the ranking into a single-criterion sort.
- **Energy weight is 0 within a state.** Electricity price, SAIDI and carbon intensity are state-level data, identical for every county in a state, so energy is used only to compare Virginia with Georgia.

---

## Slide 7: Dynamic weights in action

**Title**: *Same counties, different customer, different weights*

**On slide (grouped bar chart: default customer vs evaporative cooling + sustainability first)**:

| Dimension | Default customer (within state) | Evaporative + sustainability first |
|---|---|---|
| Water | 0.313 | **0.400** (0.515 before the cap) |
| Climate risk | 0.182 | 0.123 |
| Fiber | 0.172 | 0.117 |
| Land & ecology | 0.106 | 0.144 |
| Cooling climate | 0.093 | 0.126 |
| Workforce & community | 0.079 | 0.054 |
| Transportation | 0.054 | 0.037 |
| Energy & carbon | 0 | 0 |

**How the ranking responds (Virginia, one answer changed at a time; full table in `outputs/validation_VA/customer_input_response.csv`)**:
- Default customer: #1 is **Louisa County**.
- Evaporative cooling, low latency sensitivity, high reliability, or sustainability first: #1 becomes **Loudoun County**.
- Each answer replaces 1 to 2 counties in the top 10.
- Georgia: default #1 is **Fayette County**; with high latency sensitivity it becomes **Upson County**.

**Speaker notes**: whenever the customer changes an answer, the weights are recomputed by the formula and the ranking updates. The system also reports which answer changed which weight, and by how much.

---

## Slide 8: Interaction matrix — fusing judgment and data (innovation 2)

**Title**: *Interaction matrix: judgment proposes, data can veto*

**On slide**:

| Source | What it captures | Method |
|---|---|---|
| **B: team judgment** | Whether dimension k drives dimension l, how strongly, including indirect chains | **DEMATEL**: T = X(I − X)⁻¹ |
| **A: data** | Whether dimension scores move together across the counties of a state | Spearman correlation matrix |

**Fusion rule (the key point of this slide)**:

| Interaction type | Strength s (0–1) | Why |
|---|---|---|
| Complementarity (I > 0) | s = DEMATEL strength | A preference and causal statement; co-movement in data does not reveal it |
| Redundancy (I < 0) | s = ½·DEMATEL + ½·max(ρ, 0); **dropped if ρ ≤ 0** | An empirical statement: overlap must show up as positive correlation |

**DEMATEL result (cause–effect diagram: x = prominence r + c, y = relation r − c)**:
- **Causes**: Climate risk (r − c = +1.15), Cooling climate (+0.60), Transportation (+0.31).
- **Effects**: Water (−1.32), Energy & carbon (−0.48), Fiber (−0.34).
- In one line: **climate is the root driver; water and energy are where its effects land.**

**"Data veto" example (highlight box)**:
> We assumed fiber and workforce overlap, since both seem to track urbanization. In both states the fiber and workforce dimensions are **negatively** correlated (Virginia ρ = −0.13, Georgia ρ = −0.15), so the model dropped that interaction automatically.

**Current interaction matrix (default customer)**:

| Interaction | Type | Virginia | Georgia |
|---|---|---|---|
| Climate ↔ Water | complementarity | +0.060 | +0.051 |
| Cooling ↔ Water | complementarity | +0.049 | +0.042 |
| Transport ↔ Workforce | redundancy | −0.034 | −0.036 |
| Fiber ↔ Transport | redundancy | −0.020 | −0.018 |
| Fiber ↔ Workforce | redundancy | dropped (ρ < 0) | dropped (ρ < 0) |

---

## Slide 9: Interactions adapt to the customer's weights

**Title**: *Interactions scale with the customer's weights*

**Formula**:

$$
I_{kl} = \kappa \cdot \lambda_{\max}(\varphi)\cdot \operatorname{sign}_{kl}\, s_{kl},
\qquad
\lambda_{\max}(\varphi) = \min_k \frac{\varphi_k}{\tfrac12 \sum_l s_{kl}}
$$

**On slide**:
- λ_max is the largest interaction scale that keeps the score monotone under the **current customer's weights**. When the weights change, λ_max is recomputed, so **the model stays monotone whatever the customer chooses**.
- κ ∈ [0, 1] is the interaction intensity as a share of that maximum: 0.5 by default; κ = 0 gives the weighted sum. The robustness analysis samples κ uniformly between 0 and 1.
- A single global scale preserves the relative sizes of the interactions given by A and B.

**Speaker notes**: not only the weights are dynamic. The interaction terms also adjust to the customer's needs, and they always satisfy the mathematical condition.

---

## Slide 10: Temporal robustness — penalize projected deterioration (Adelyn)

**Title**: *Temporal robustness: penalize projected deterioration*

**On slide**:
- Data: CMRA 2025 county climate projections, **RCP8.5 mid-century** vs the historical mean. A conservative stress test, not a forecast.
- Only deterioration counts: Δ = max(0, future − historical); improvement earns nothing.
- Δ becomes a percentile p across the 292 Virginia and Georgia counties (ties get the average rank).
- **One factor per affected dimension**, never combined into a global factor:

| Climate change (RCP8.5 mid-century vs historical) | Dimension | Formula |
|---|---|---|
| More days above 90°F | Cooling climate | Dᴿ = D × (1 − 0.20·p_heat) |
| Longer dry spells | Water | Dᴿ = D × (1 − 0.20·p_dry) |
| More days with ≥ 2 inches of rain | Climate risk | Dᴿ = D × (1 − 0.20·p_rain) |

**Speaker notes**:
- A data center runs for 20–30 years; today's climate is not enough.
- These three variables are exogenous physical changes (not local policy), available for every county in both states, and directly linked to cooling, water supply and drainage.
- Aqueduct 2050 water stress is not reused as a second water factor: it is already in the water dimension and the margin, so using it again would double count.
- The factors do not depend on the customer's weights, so they are precomputed per county; changing the weights never requires recomputing them.

**Visual**: three state maps, one per factor, or a diagram "one climate change → one dimension".

---

## Slide 11: Weakest-link margin and feasibility gates (Adelyn + gates)

**Title**: *Weakest-link margin and feasibility gates*

**Safety-margin formula**:

$$
m_{ik} = \frac{U_{ik}}{100},\qquad
A_{M,i} = 1 - \lambda_M\Big(1-\min_{k} m_{ik}\Big),\qquad \lambda_M = 0.20
$$

**On slide**:
- Suitability is average performance and cannot tell whether a county sits **right at a boundary** on one indicator. The margin looks at the **weakest of the 18 indicators** and removes up to 20%.
- Only the minimum is used; the 18 factors are never multiplied, so adding indicators does not compound the penalty.
- **Case**: Loudoun has Virginia's highest suitability (82.76), but its distance to rail reaches the boundary (utility 0), so its margin factor is 0.80 and its final score 66.21. Louisa has suitability 77.76 and margin 0.855, final **66.48, #1**.
- **Feasibility F** (gate modules, run with the customer's MW and target date): power availability, time to power, permitting/zoning.
  - Virginia (100 MW by 2029-12-31): 98 counties with no obvious risk, 33 with insufficient reference data, 2 with a permitting risk.
  - Georgia: 154 / 4 / 1.
- Gate results are screening signals, not verified pass/fail evidence, so by default they flag but do not exclude (every county is Conditional). A strict option excludes counties with a detected risk and re-ranks the rest.

**Speaker notes**: the layers separate what may be traded off from what may not. Suitability lets dimensions compensate; the margin looks at the weakest indicator and does not; feasibility is a hard gate.

---

## Slide 12: Completeness 2 — robustness checks

**Title**: *Is the answer robust?*

**On slide**:

| Check | Virginia | Georgia |
|---|---|---|
| Choquet vs weighted sum | Same #1, 9 of top 10 shared, ρ = 0.994 | Same #1, 8 of top 10 shared, ρ = 0.991 |
| SMAA-2 (10,000 samples; weights, κ, λ_R and λ_M all random) | #1: Loudoun 37%, Louisa 33%, Washington 21%. Top 10: Louisa 100%, Washington 98%, Loudoun 98% | #1: Fayette 52%, Upson 27%. Top 10: both about 94%, the next county only 64% |
| Lowest 90th-percentile regret | Louisa (4.9 points) | Fayette (4.7 points) |
| Six weighting methods | AHP picks Louisa, ROC Loudoun; equal, CRITIC and entropy pick Washington (ρ 0.86–0.99) | AHP, equal, ROC and DEMATEL weights all pick Fayette (ρ 0.23–0.99) |
| Effective weights (share of final-score variance) | Water 0.42, fiber 0.34 | Water 0.51, fiber 0.34 |
| Value-function shape (exponential, ρ = ±2) | 7–9 of top 10 shared | 5 of top 10 shared |

**Speaker notes**:
- **Virginia**: Louisa, Loudoun and Washington form a robust leading group. Louisa has the lowest regret and is the safest choice; Loudoun is most often #1 but has a weakest-link exposure (rail distance) that the margin penalizes.
- **Georgia**: Fayette and Upson are clear leaders, followed by a gap. Below them, the order depends on the water weight and the value-function shape, so it is presented as a shortlist. We do not hide this uncertainty.
- SMAA also perturbs Adelyn's 20% robustness and margin coefficients (sampled between 10% and 30%). With both fixed at 0.20 it reproduces the pipeline exactly (tested).
- Methods: SMAA-2 (Lahdelma & Salminen 2001); CRITIC (Diakoulaki et al. 1995); ROC (Barron & Barrett 1996).

**Visual**: stacked bar chart of rank acceptability (probability that each county takes rank 1, 2, 3, …); data in `outputs/validation_<state>/smaa_rank_acceptability.csv`.

---

## Slide 13: What is new

**Title**: *What is new*

1. **Customer-driven dynamic weights.** Four multiple-choice questions map to physically motivated multipliers and then to weights, preserving the ratio scale. Team judgment and customer needs have clearly separated roles.
2. **Dimensions are not assumed independent.** A Choquet integral models complementarity and redundancy; the conventional weighted sum is a special case.
3. **Judgment and data are fused, and data can veto.** DEMATEL captures causal structure; the correlation matrix tests claimed redundancies, and unsupported ones are dropped automatically.
4. **Explainability with mathematical guarantees.** Monotonicity has a necessary and sufficient condition that is enforced; every score decomposes exactly into dimensions and interactions.
5. **Layers instead of one average.** Suitability may compensate; the margin looks at the weakest indicator; each projected climate change touches exactly one dimension; feasibility is a hard gate. Every layer has an explicit rule against double counting.
6. **Uncertainty stated openly.** Conclusions are expressed as probabilities (SMAA) rather than a single ranking, together with the conditions under which they hold or change.

---

## Slide 14: Limitations (can go in the appendix)

- AHP, DEMATEL and the interaction types are currently **single-respondent drafts**; rerun after the team scoring session.
- Energy and carbon data are state-level and cannot separate counties within a state; utility-level data would fix this.
- The 2-additive model captures pairwise interactions only, not three-way ones. This is the standard trade-off between expressiveness and the number of parameters a team can justify (28 pairs for 8 dimensions).
- The 20% margin cap and the three 20% robustness caps are policy parameters; SMAA varies them between 10% and 30%.
- Robustness percentiles are relative to the 292 Virginia and Georgia counties and must be recomputed if the comparison set changes.
- Gate results are screening signals, not verified pass/fail evidence, so by default no county is excluded.
- The model is a regional screen and does not approve construction on a specific site.

---

## Appendix: where the numbers come from (rerun after team scoring)

```bash
cd final
PYTHONPATH=src python3 -m dc_locator.dimension_weights                     # slides 5–7: weights
PYTHONPATH=src python3 -m dc_locator.dimension_weights --cooling_type evaporative --priority sustainability
PYTHONPATH=src python3 -m dc_locator.interactions dematel                  # slide 8: DEMATEL
PYTHONPATH=src python3 -m dc_locator.pipeline --state VA                   # slides 8–11: interactions, ranking, margin, gates
PYTHONPATH=src python3 -m dc_locator.validation --state VA                 # slides 7 and 12 (same for GA)
```

Full robustness and margin formulas: `docs/SCORING_ADJUSTMENTS.md`.

References (from memory; verify before putting them on slides): Grabisch (1997) *Fuzzy Sets and Systems* 92(2); Marichal (2000) *IEEE Trans. Fuzzy Systems* 8(6); Saaty (1980) *The Analytic Hierarchy Process*; Forman & Peniwati (1998) *EJOR* 108(1); Gabus & Fontela (1972) Battelle Geneva; Lahdelma & Salminen (2001) *Operations Research* 49(3); Diakoulaki et al. (1995) *Computers & OR* 22(7); Barron & Barrett (1996) *Management Science* 42(11).
