# Data Center Location

Where should America's next sustainable AI data center be built? This project scores and ranks every county in **Virginia** (133 counties and independent cities) and **Georgia** (159 counties) for data-center siting. It uses **8 dimensions and 18 indicators**, and the dimension weights adjust to what each customer needs.

> Status: the full pipeline runs end to end for both states (133 tests pass). Judgment inputs (AHP comparisons, DEMATEL scores, interaction types) are still single-respondent drafts to be replaced after the team session. See [docs/WORKLOG.md](docs/WORKLOG.md) for the development log.

## How it works

```
① data_prep           county indicator table → long table (one row = county × indicator)
② indicator_scoring   raw value → clipped piecewise utility U (0–100) → base dimension D (0–1)
③ score adjustments   precomputed CMRA factor → Dᴿ for climate/water/cooling; weakest indicator → A_M
④ dimension_weights   4 customer inputs → Camille's dimension weights φ
⑤ decision            Dᴿ + φ + I → Choquet/weighted suitability Sᴿ → final score Sᴿ × A_M
⑥ feasibility gates   power availability, time to power, permitting/zoning per county (flags; optional strict exclusion)
⑦ validation          method comparison + SMAA-2 over weights, κ, λ_R, λ_M
```

In one line: **FinalScore = F × Sᴿ × A_M**, where Sᴿ = 100 × [Σ φ_k Dᴿ_k − ½ Σ I_kl |Dᴿ_k − Dᴿ_l|].

| Dimension | Indicators |
|---|---|
| Climate risk | Wildfire burn-probability percentile; inland flood loss percentile |
| Water | Baseline water stress; 2050 water stress |
| Land & ecology | Low-impervious land share; protected-land share; wetland share |
| Fiber | Business fiber availability at 100/20 and 1000/100 Mbps |
| Workforce & community | Labor force; social vulnerability percentile |
| Cooling climate | Cooling degree days; days above 90°F |
| Transportation | Distance to Interstate; distance to rail |
| Energy & carbon | Industrial electricity price; SAIDI; grid CO₂e intensity |

Customer inputs that adjust the dimension weights: **cooling type**, **latency sensitivity**, **reliability requirement**, and **priority** (balanced / sustainability / operations).

All 18 indicators use fixed, versioned upper/lower anchors from `configs/indicator_scoring.json`. The default live pipeline also applies the adjustment policy in `configs/score_adjustments.json`:

- one weakest-link margin factor across the 18 selected utilities (maximum reduction 20%);
- one CMRA RCP8.5 mid-century factor each for Cooling climate, Water and Climate risk (maximum reduction 20% per affected dimension);
- no automatic hard-zero gate. A zero utility becomes an exclusion only if its indicator is explicitly approved and added to `hard_zero_gate.indicators`.

The adjustment calculations do not use or modify Camille's dimension weights. See [docs/SCORING_ADJUSTMENTS.md](docs/SCORING_ADJUSTMENTS.md) for formulas, anchors, order of operations and audit columns.

All runtime inputs and processed reference workbooks are stored under `data/` and referenced with repository-relative paths. The project does not depend on files in a developer's home directory or in a parent workspace folder.

## Repository layout

```
├── configs/                  model configuration (dimensions, indicators, anchors, input defaults)
├── data/
│   ├── raw/                  pointers to source datasets
│   └── processed/            county indicators + version-locked robustness factors
├── src/dc_locator/
│   ├── data_prep/            ① data preparation — see its README.md
│   ├── indicator_scoring/    ② utilities, within-dimension weights, dimension scores — see its README.md
│   ├── dimension_weights/    ③a customer inputs → dimension weights — see its README.md
│   ├── interactions/         ③c/③d DEMATEL + correlation → 8 × 8 interaction matrix — see its README.md
│   ├── decision/             ⑤ decision matrix (matrix.py, CLI) — see its README.md
│   ├── gates/                ⑥ feasibility gates for Virginia and Georgia — see README.txt in each
│   ├── validation/           ⑦ cross-validation and SMAA robustness — see its README.md
│   └── pipeline.py           end-to-end run (CLI)
├── scripts/                  end-to-end pipeline scripts
├── tests/                    unit tests and fixtures
├── outputs/                  run outputs (not tracked)
└── docs/                     documentation
```

## Quick start

Requires Python 3.10+.

```bash
pip install -r requirements.txt     # numpy, pandas, openpyxl
```

```bash
# rank every county of a state for one customer (full pipeline, gates included)
PYTHONPATH=src python3 -m dc_locator.pipeline --state VA
PYTHONPATH=src python3 -m dc_locator.pipeline --state GA --cooling_type evaporative --priority sustainability \
  --power_mw 150 --target_date 2028-12-31

# strict screening: exclude counties whose gates detect a risk, then re-rank
PYTHONPATH=src python3 -m dc_locator.pipeline --state VA --exclude-gate-risks

# diagnostic legacy path: skip margin and CMRA adjustments
PYTHONPATH=src python3 -m dc_locator.pipeline --state VA --no-adjustments

# robustness analysis (SMAA, method comparison) for one state
PYTHONPATH=src python3 -m dc_locator.validation --state VA

# run the tests
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v

# dimension weights for a customer (evaporative cooling, sustainability first)
PYTHONPATH=src python3 -m dc_locator.dimension_weights --cooling_type evaporative --priority sustainability

# score and rank an example request (3 synthetic counties, gates disabled)
PYTHONPATH=src python3 -m dc_locator.decision recommend \
  --request tests/fixtures/decision_request_8d.json \
  --output-dir outputs/demo
```

## Progress

| Step | Module | Status |
|---|---|---|
| ④ | Decision matrix (`src/dc_locator/decision/`) | ✅ Done: n × 8 dimension scores + weights φ + optional interactions I → score, rank, Pareto; 38 tests |
| ③a | Dimension weights from customer inputs (`src/dc_locator/dimension_weights/`) | ✅ AHP base + 4 customer inputs; 17 tests |
| ③c | DEMATEL causal matrix (`src/dc_locator/interactions/`) | ✅ cause/effect roles, total-relation matrix; 8 tests |
| ③d | Correlation matrix + combined 8 × 8 interaction matrix | ✅ redundancies must be supported by the data; 8 tests |
| ④′ | 2-additive Choquet scoring with interactions | ✅ monotonicity enforced; checked against an independent implementation |
| ② | Indicator scoring (`src/dc_locator/indicator_scoring/`) | ✅ 18 fixed-anchor value functions, equal within-dimension aggregation, margin and dimension-specific robustness |
| ① | Data preparation (`src/dc_locator/data_prep/`) | ✅ 292 counties × 18 indicators, 0 missing; 3 tests |
| — | End-to-end pipeline (`src/dc_locator/pipeline.py`) | ✅ data → utilities → D → Dᴿ → weights/interactions → suitability → A_M → ranking; complete audit export |
| ③b | Cross-validation and robustness (`src/dc_locator/validation/`) | ✅ 6 weighting methods, SMAA-2 (10,000 samples over weights, κ, λ_R, λ_M), effective weights, input response, value-function shape; 17 tests |
| ⑥ | Feasibility gates (`src/dc_locator/gates/`) | ✅ connected to the pipeline: three gate statuses per county; optional strict exclusion; 3 tests |
| — | Final documentation | ✅ formulas and implementation contract in `docs/SCORING_ADJUSTMENTS.md` |

## Team

Camille (weights, interactions, validation, integration), Jane (data), Adelyn (decision matrix, indicator scoring, robustness and margin), MoonChild-1969 (feasibility gates).
