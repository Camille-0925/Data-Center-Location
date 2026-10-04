# Data Center Location

Where should America's next sustainable AI data center be built? This project scores and ranks every county in **Virginia** (133 counties and independent cities) and **Georgia** (159 counties) for data-center siting. It uses **8 dimensions and 18 indicators**, and the dimension weights adjust to what each customer needs.

> Status: work in progress. The decision matrix is done; the data, scoring and weighting modules are under construction. See [docs/WORKLOG.md](docs/WORKLOG.md) for the step-by-step development log.

## How it works

```
① data_prep           county indicator table → long table (one row = county × indicator)
② indicator_scoring   raw value → utility score u (0–100); within-dimension weights ω → dimension score D (0–1)
③ dimension_weights   4 customer inputs → dimension weights w
④ decision            D (n × 8) + φ (8) + I (8 × 8) → Choquet score 100 × [Σ φ_k·D_k − ½ Σ I_kl·|D_k − D_l|], rank, Pareto
```

| Dimension | Indicators |
|---|---|
| Climate risk | Wildfire burn-probability percentile; inland flood loss percentile |
| Water | Baseline water stress; 2050 water stress |
| Land & ecology | Low-impervious land share; protected-land share; wetland share |
| Fiber | Business fiber availability at 1000/100 Mbps (100/20 shown as context) |
| Workforce & community | Labor force; social vulnerability percentile |
| Cooling climate | Cooling degree days; days above 90°F |
| Transportation | Distance to Interstate; distance to rail |
| Energy & carbon | Industrial electricity price; SAIDI; grid CO₂e intensity |

Customer inputs that adjust the dimension weights: **cooling type**, **latency sensitivity**, **reliability requirement**, and **priority** (balanced / sustainability / operations).

## Repository layout

```
├── configs/                  model configuration (dimensions, indicators, anchors, input defaults)
├── data/
│   ├── raw/                  pointers to source datasets
│   └── processed/            county-level indicator table
├── src/dc_locator/
│   ├── data_prep/            ① data preparation — see its README.md
│   ├── indicator_scoring/    ② utilities, within-dimension weights, dimension scores — see its README.md
│   ├── dimension_weights/    ③a customer inputs → dimension weights — see its README.md
│   ├── interactions/         ③c/③d DEMATEL + correlation → 8 × 8 interaction matrix — see its README.md
│   └── decision/             ④ decision matrix (matrix.py, CLI) — see its README.md
│   ├── validation/           ③b cross-validation and SMAA robustness — see its README.md
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
# rank every county of a state for one customer (full pipeline)
PYTHONPATH=src python3 -m dc_locator.pipeline --state VA
PYTHONPATH=src python3 -m dc_locator.pipeline --state GA --cooling_type evaporative --priority sustainability

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
| ② | Indicator scoring (`src/dc_locator/indicator_scoring/`) | ✅ value functions with fixed anchors, per-dimension aggregation, context flags; 26 tests |
| ① | Data preparation (`src/dc_locator/data_prep/`) | ✅ 292 counties × 18 indicators, 0 missing; 3 tests |
| — | End-to-end pipeline (`src/dc_locator/pipeline.py`) | ✅ data → scores → weights → interactions → Choquet ranking; 6 tests |
| ③b | Cross-validation and robustness (`src/dc_locator/validation/`) | ✅ 6 weighting methods, SMAA-2 (10,000 samples), effective weights, input response, value-function shape; 11 tests |
| — | Final documentation | ⏳ |

## Team

Camille (weights and integration), Jane (data), Adelyn (decision matrix).
