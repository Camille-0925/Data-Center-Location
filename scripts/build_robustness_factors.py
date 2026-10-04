"""Build the version-locked VA+GA county robustness-factor table from CMRA.

Usage:
  python scripts/build_robustness_factors.py

The pipeline reads the committed output and never recalculates cross-county percentiles.
Re-run this script only when the source, scenario, geography, or lambda changes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_SOURCE = "data/raw/cmra_2025_va_ga_robustness_inputs.csv"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


FIELDS = {
    "heat": ("HISTORIC_MEAN_TMAX90F", "RCP85MID_MEAN_TMAX90F", "cooling_climate"),
    "dry": ("HISTORIC_MEAN_CONSECDD", "RCP85MID_MEAN_CONSECDD", "water"),
    "heavy_rain": ("HISTORIC_MEAN_PR2IN", "RCP85MID_MEAN_PR2IN", "climate_risk"),
}


def build(source: str | Path, penalty_lambda: float = 0.2) -> pd.DataFrame:
    source_path = Path(source)
    if not source_path.is_absolute():
        source_path = PROJECT_ROOT / source_path
    raw = pd.read_csv(source_path, dtype={"GEOID": str})
    data = raw[raw["StateAbbr"].isin(["VA", "GA"])].copy()
    if len(data) != 292 or data["GEOID"].duplicated().any():
        raise ValueError("expected exactly 292 unique VA+GA county GEOIDs")
    out = data[["StateAbbr", "GEOID", "CountyName"]].rename(
        columns={"StateAbbr": "state", "GEOID": "fips", "CountyName": "county"}
    )
    n = len(data)
    for risk_id, (historic, future, dimension) in FIELDS.items():
        downside = (data[future] - data[historic]).clip(lower=0)
        percentile = (downside.rank(method="average") - 1) / (n - 1)
        percentile = percentile.where(downside > 0, 0.0)
        out[f"historic_{risk_id}"] = data[historic].to_numpy()
        out[f"future_{risk_id}"] = data[future].to_numpy()
        out[f"{risk_id}_downside_change"] = downside.to_numpy()
        out[f"{risk_id}_risk_percentile"] = percentile.to_numpy()
        out[f"{dimension}_robustness_factor"] = 1.0 - penalty_lambda * percentile.to_numpy()
    return out.sort_values("fips").reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "source",
        nargs="?",
        default=DEFAULT_SOURCE,
        help=f"CMRA input CSV (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--out",
        default="data/processed/county_robustness_va_ga.csv",
        help="output CSV",
    )
    parser.add_argument("--lambda", dest="penalty_lambda", type=float, default=0.2)
    args = parser.parse_args()
    output = build(args.source, args.penalty_lambda)
    path = Path(args.out)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)
    print(f"wrote {len(output)} counties to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
