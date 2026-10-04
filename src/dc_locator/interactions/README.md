# Dimension Interactions (`dc_locator.interactions`)

Steps ③c and ③d of the pipeline. The 8 dimensions are not independent: hot climates raise both cooling load and water stress, and urban counties score high on fiber, workforce and transport at the same time. This module builds the **8 × 8 interaction matrix I** that the decision matrix uses to account for these links. It draws on two sources:

| Source | What it captures | Status |
|---|---|---|
| **B: DEMATEL causal matrix** (team judgment) | Which dimension drives which, and how strongly, including indirect chains | ✅ Step ③c (this page) |
| **A: correlation matrix** (data, all counties in a state) | Which dimensions move together in the data | ⏳ Step ③d |

Neither source alone can tell a **synergy** (both must be good, e.g. water and cooling for evaporative cooling) from a **redundancy** (two dimensions measuring the same thing, e.g. fiber and workforce both tracking urbanization). The team assigns the sign of each interaction; A and B set its size (step ③d).

## Run it

Requires Python 3.10+ and numpy. Run from the repository root.

```bash
PYTHONPATH=src python3 -m dc_locator.interactions dematel          # summary table and impact-relation links
PYTHONPATH=src python3 -m dc_locator.interactions dematel --json   # full matrices
PYTHONPATH=src python3 -m unittest tests.interactions.test_dematel -v
```

Expected output with the current draft scores (`configs/interactions.json`):

| Dimension | r (gives) | c (receives) | Prominence r + c | Relation r − c | Role |
|---|---|---|---|---|---|
| Climate risk | 1.517 | 0.371 | 1.888 | **+1.146** | cause |
| Cooling climate | 0.904 | 0.305 | 1.208 | +0.599 | cause |
| Transportation | 0.845 | 0.536 | 1.381 | +0.310 | cause |
| Land & ecology | 0.410 | 0.323 | 0.733 | +0.087 | cause |
| Workforce & community | 0.717 | 0.724 | 1.442 | −0.007 | effect |
| Fiber connectivity | 0.382 | 0.724 | 1.106 | −0.343 | effect |
| Energy & carbon | 0.540 | 1.016 | 1.556 | −0.476 | effect |
| Water | 0.171 | 1.487 | 1.658 | **−1.316** | effect |

The strongest total influences are climate → water (0.527), cooling → water (0.440), cooling → energy (0.395) and climate → energy (0.371). In words: **climate is the root driver; water and energy are where its effects land.** A site cannot be judged on water or energy alone without looking at the climate that drives them.

## Method (DEMATEL)

| Step | Formula | Meaning |
|---|---|---|
| 1. Score | z_kl ∈ {0, 1, 2, 3, 4} | How strongly dimension k *directly* influences l (0 none … 4 very high). Several members' tables are averaged |
| 2. Normalize | X = Z / s, s = max(largest row sum, largest column sum) | Makes the influence chain converge |
| 3. Total relation | T = X (I − X)⁻¹ = X + X² + X³ + … | Adds every indirect chain (a → b → c) to the direct links |
| 4. Roles | r = row sums of T, c = column sums | r + c: how central; r − c > 0: cause, < 0: effect |
| 5. Map | links with t_kl > α = mean(T) | The impact-relation map for the slides |

Sources: Gabus & Fontela (1972), Battelle Geneva Research Centre; Si, You, Liu & Zhang (2018), "DEMATEL technique: a systematic review", *Mathematical Problems in Engineering*. Citations are from memory; verify before quoting.

The module also exports `pairwise_strength()`: for each pair, (t_kl + t_lk) divided by the largest such sum, giving a 0–1 strength. Step ③d combines it with the data correlation. Currently the strongest two-way link is transportation ↔ workforce (1.00), ahead of climate ↔ water (0.95).

## Configuration

`configs/interactions.json` → `dematel.respondents`: each team member's influence scores as `{source: {target: score}}`; pairs left out score 0. The current draft (one respondent) records a one-line causal rationale for every nonzero score, for example:

- *cooling_climate → energy_carbon (3)*: higher cooling load raises PUE, electricity use and emissions;
- *transportation → fiber_connectivity (2)*: long-haul fiber is laid along highway and rail rights-of-way.

To replace the draft, each member fills the same 8 × 8 table (about 30 minutes) and is added as another respondent.

## Output (`run_dematel()`)

| Field | Use in report / slides |
|---|---|
| `dimensions` (r, c, r + c, r − c, role) | Cause–effect diagram: x = prominence, y = relation |
| `significant_links` | Arrows on the impact-relation map |
| `total_relation_matrix` | 8 × 8 heat map |
| `direct_matrix`, `normalizer_s`, `threshold_alpha` | Methodology appendix |

## Design choices (talking points)

1. **Dimensions are not assumed independent.** Most site-selection scores add dimensions as if they were unrelated. We measure how they drive one another.
2. **Indirect effects count.** T includes chains such as climate → cooling → energy, not just direct links.
3. **Judgment and data stay separate.** DEMATEL records the team's causal reasoning; the correlation matrix (step ③d) records what the data show. Each can be checked against the other.
4. **Every score is justified in writing.** The configuration stores a rationale for each nonzero influence.

## Limitations

- The draft is one person's judgment; the team session will replace it.
- DEMATEL measures how strong a link is, not whether it is a synergy or a redundancy. That sign is assigned explicitly in step ③d.
