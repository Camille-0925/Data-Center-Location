# Data Center Location

Where should America's next sustainable AI data center be built? This project scores and ranks every county in **Virginia** (133 counties and independent cities) and **Georgia** (159 counties) for data-center siting. It uses **8 dimensions and 18 indicators**, and the dimension weights adjust to what each customer needs.

> Status: work in progress. The decision matrix is done; the data, scoring and weighting modules are under construction. See [docs/WORKLOG.md](docs/WORKLOG.md) for the step-by-step development log.

## How it works

```
① data_prep           county indicator table → long table (one row = county × indicator)
② indicator_scoring   raw value → utility score u (0–100); within-dimension weights ω → dimension score D (0–1)
③ dimension_weights   4 customer inputs → dimension weights w
④ decision            n × 8 matrix D + 8 weights w → Score = 100 × Σ w_k · D_k, rank, Pareto status, trade-offs
```

| Dimension | Indicators |
|---|---|
| Climate risk | Wildfire burn-probability percentile; inland flood loss percentile |
| Water | Baseline water stress; 2050 water stress |
| Land & ecology | Low-impervious land share; protected-land share; wetland share |
| Fiber connectivity | Commercial fiber coverage (100/20 and 1000/100 Mbps) |
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
│   ├── data_prep/            ① data preparation
│   ├── indicator_scoring/    ② utilities, within-dimension weights, dimension scores
│   ├── dimension_weights/    ③a customer inputs → dimension weights — see its README.md
│   ├── interactions/         ③c/③d DEMATEL + correlation → 8 × 8 interaction matrix — see its README.md
│   └── decision/             ④ decision matrix (matrix.py, CLI) — see its README.md
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
| ④ | Decision matrix (`src/dc_locator/decision/`) | ✅ Done: n × 8 dimension scores + 8 weights → score, rank, Pareto; 28 tests |
| ② (part) | Indicator → dimension aggregation (`src/dc_locator/indicator_scoring/aggregation.py`) | ✅ mean / geometric / min; 8 tests |
| ③a | Dimension weights from customer inputs (`src/dc_locator/dimension_weights/`) | ✅ AHP base + 4 customer inputs; 17 tests |
| ③c | DEMATEL causal matrix (`src/dc_locator/interactions/`) | ✅ cause/effect roles, total-relation matrix; 8 tests |
| ③d | Correlation matrix + combined 8 × 8 interaction matrix | ⏳ |
| ④′ | Choquet scoring with interactions in the decision matrix | ⏳ |
| ② | Indicator scoring and within-dimension weights | ⏳ |
| ① | Data preparation | ⏳ |
| — | End-to-end pipeline and documentation | ⏳ |

## Team

Camille (weights and integration), Jane (data), Adelyn (decision matrix).
