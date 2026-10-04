# Indicator Scoring (`dc_locator.indicator_scoring`)

Step ② of the pipeline. It turns each county's raw indicators (km, %, persons, index points…) into **utilities from 0 to 100** with piecewise-linear value functions, then combines them into the **8 dimension scores D (0–1)** that the decision matrix uses. It also reports **context flags**: indicators that are shown to the user but deliberately not scored.

```
raw value x ──value function (T, L)──► utility u (0–100) ──aggregation (ω)──► dimension score D (0–1)
```

## Run it

Requires Python 3.10+, numpy and pandas. Run from the repository root.

```bash
PYTHONPATH=src python3 -m dc_locator.data_prep                          # workbook -> data/processed/county_indicators_va_ga.csv
PYTHONPATH=src python3 -m dc_locator.indicator_scoring                  # score all 292 counties, print a summary
PYTHONPATH=src python3 -m dc_locator.indicator_scoring --state VA --out outputs/scored_va.csv
PYTHONPATH=src python3 -m unittest tests.indicator_scoring.test_scoring tests.indicator_scoring.test_aggregation -v
```

Expected summary (medians of the dimension scores):

| Dimension | VA median | GA median | Note |
|---|---|---|---|
| Climate risk | 0.647 | 0.513 | |
| Water | 0.316 | 0.633 | 12 VA counties reach extremely high 2050 stress, so their water score is 0 |
| Land & ecology | 0.900 | 0.874 | |
| Fiber | 0.416 | 0.704 | |
| Workforce | 0.591 | 0.496 | |
| Cooling climate | 0.694 | 0.287 | Georgia is hotter |
| Transportation | 0.834 | 0.696 | |
| Energy & carbon | 0.583 (all counties) | 0.627 (all counties) | State-level data: constant within a state |

## Step 1: value functions (raw value → utility)

Each indicator has an ideal value **T** (utility 100) and an unacceptable value **L** (utility 0), with a straight line in between:

```
low_better:   u = 100 if x ≤ T;   100·(L − x)/(L − T) if T < x < L;   0 if x ≥ L
high_better:  u = 0 if x ≤ L;     100·(x − L)/(T − L) if L < x < T;   100 if x ≥ T
```

Worked example: grid carbon intensity with T = 100, L = 650 kg/MWh, and a county at 300 → u = 100 × (650 − 300)/(650 − 100) = **63.6**.

Fixed anchors are used instead of the min–max scaling in the source workbook for two reasons. They give every indicator a direction (higher is always better), and they keep utilities stable when counties or states are added.

| Indicator | Dimension | Direction | T (100) | L (0) | Basis |
|---|---|---|---|---|---|
| Wildfire burn-probability national percentile | Climate | low | 0 | 1 | Ends of a percentile |
| Inland flood loss-rate national percentile | Climate | low | 0 | 1 | Ends of a percentile |
| Baseline water stress | Water | low | 1 | 4 | Aqueduct: < 1 low, ≥ 4 extremely high (> 80% withdrawal/supply) |
| 2050 BAU water stress | Water | low | 1 | 4 | Same |
| Low-impervious land share | Land | high* | 0.95 | 0.25 | Team: < 25% open land leaves no room for a campus |
| GAP 1/2 protected land share | Land | low | 0 | 0.50 | Team: half a county protected is the limit |
| Wetland share | Land | low | 0 | 0.60 | Just above the observed maximum (0.58) |
| Business fiber 1000/100 availability | Fiber | high | 0.90 | 0 | Team: ≥ 90% coverage is saturated |
| Labor force (log scale) | Workforce | high | 50,000 | 2,000 | Log scale so metros do not win automatically |
| Cooling degree days (65 °F) | Cooling | low | 500 | 2,500 | Span of the two states |
| Distance to Interstate | Transport | low | 5 km | 60 km | ≈ 90th percentile |
| Distance to rail | Transport | low | 2 km | 30 km | Above the 90th percentile |
| State industrial price | Energy | low | 50 | 120 USD/MWh | US state range |
| State SAIDI (no major events) | Energy | low | 100 | 400 min | US utility range |
| State grid CO₂e intensity | Energy | low | 100 | 650 kg/MWh | Low-carbon vs coal-heavy grid |

\* direction to be confirmed by the team. All anchors live in `configs/indicator_scoring.json` together with their basis. A sensitivity variant with an exponential (diminishing-returns) curve is built in (`shape="exponential"`, Kirkwood 1997).

**Where utilities hit 0** (checked on the real data; printed by the CLI):

| Indicator | Counties at 0 | Why that is acceptable |
|---|---|---|
| 2050 water stress | 12 (VA) | Index ≥ 4 is Aqueduct's "extremely high" class |
| Low-impervious land | 15 (VA, mostly independent cities) | Dense urban cores have no room for a campus |
| Labor force | 11 (GA), 2 (VA) | Under 2,000 workers |
| Interstate / rail distance | up to 17 per state | Offset by the other transport indicator (weighted mean) |

## Step 2: aggregation (utilities → dimension score)

Following the teammate proposal. The aggregation method is chosen per dimension by what that dimension means:

| Dimension | Scored indicators (ω) | Aggregation | Why |
|---|---|---|---|
| Climate risk | wildfire 0.5, flood 0.5 | weighted geometric | A severe flood risk should not be hidden by a low wildfire risk |
| Water | baseline, 2050 | **min** | The two are nearly identical (ρ ≈ 0.98); take the worse instead of counting stress twice, so the 20–30-year horizon counts |
| Land & ecology | open land 0.5, protected 0.25, wetland 0.25 | weighted geometric | No room, or heavy protection, cannot be offset |
| Fiber | 1000/100 (1.0) | — | 100/20 overlaps it (ρ 0.73–1.0); shown as a flag |
| Workforce | ln(labor force) (1.0) | — | SVI is context, not a siting penalty (see flags) |
| Cooling climate | CDD65 (1.0) | — | Days > 90 °F overlap CDD (ρ 0.84–0.91); shown as a flag |
| Transportation | Interstate 0.7, rail 0.3 | weighted mean | Most construction and operating freight moves by truck |
| Energy & carbon | price 0.25, SAIDI 0.35, CO₂e 0.40 | weighted mean | Cross-state comparison only (constant within a state) |

Formulas: `weighted_mean` D = Σ ω·u/100; `weighted_geometric` D = Π (u/100)^ω; `min` D = min(u)/100. The land weights 0.5/0.25/0.25 are exponents that sum to 1, so equal utilities give the same D under every method. (The original proposal u₁·√(u₂·u₃) has exponents summing to 2, which would push land scores systematically lower.)

## Context flags (shown, not scored)

| Flag | Value | Bands |
|---|---|---|
| Water stress change | 2050 − baseline (index points) | improving < −0.5 ≤ stable < 0.5 ≤ worsening |
| Fiber 100/20 availability | share | — |
| Social vulnerability (CDC SVI) | percentile | low < 0.25 ≤ low-moderate < 0.5 ≤ moderate-high < 0.75 ≤ high (CDC quartile convention) |
| Days above 90 °F | days/year | normal < 15 ≤ elevated < 45 ≤ high < 75 ≤ extreme |

SVI is **not** scored. Treating high vulnerability as a poor score would steer investment away from the communities that most need jobs and resilience support. It is shown instead, to decide what community commitments a project should make.

## Output

`score_counties(table)` returns one row per county: `fips`, `county_name`, `state`, the 8 dimension scores, the 15 utilities (`u__<indicator>`), and the flags. `dimension_score_records()` converts it into the input of the decision matrix.

## Design choices (talking points)

1. **Fixed, documented anchors** instead of min–max scaling: utilities have a meaning ("0 = unacceptable") and do not shift when the sample changes.
2. **Aggregation matches meaning**: geometric means where weaknesses must not be hidden, min where two indicators measure the same risk at two dates, weighted means where trade-offs are acceptable.
3. **No double counting**: near-duplicate indicators (fiber speeds, CDD vs hot days, current vs future water) are either merged by min or moved to flags.
4. **Equity-aware**: social vulnerability informs mitigation, not ranking.
5. **Checked by hand**: tests recompute Loudoun County's climate, water, land and transport scores from the raw values.

## Limitations

- Several anchors are team assumptions and are labelled as such in the configuration.
- County values are representative-point or county-average proxies; a specific parcel can differ.
- Energy indicators are state-level, so they do not differentiate counties within a state.
