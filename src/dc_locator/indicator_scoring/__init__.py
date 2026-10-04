"""Step 2: raw indicators -> utilities (0-100) -> dimension scores D (0-1), plus context flags."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .aggregation import AGGREGATION_METHODS, aggregate_dimension
from .utility import utility

DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "indicator_scoring.json"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    with Path(path or DEFAULT_CONFIG).open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_config(config: Mapping[str, Any]) -> None:
    indicators = config["indicators"]
    for dimension_id, spec in config["dimensions"].items():
        if spec["aggregation"] not in AGGREGATION_METHODS:
            raise ValueError(f"unknown aggregation for {dimension_id}: {spec['aggregation']}")
        if abs(sum(spec["weights"].values()) - 1) > 1e-9:
            raise ValueError(f"within-dimension weights of {dimension_id} must sum to 1")
        for metric_id in spec["weights"]:
            if metric_id not in indicators:
                raise ValueError(f"{dimension_id} uses undefined indicator {metric_id}")
            if indicators[metric_id]["dimension"] != dimension_id:
                raise ValueError(f"{metric_id} is declared in {indicators[metric_id]['dimension']}, not {dimension_id}")
    scored = {m for spec in config["dimensions"].values() for m in spec["weights"]}
    unused = set(indicators) - scored
    if unused:
        raise ValueError(f"indicators defined but not scored: {sorted(unused)}")


def utilities(table: pd.DataFrame, config: Mapping[str, Any], shape: str = "linear", rho: float = 0.0) -> pd.DataFrame:
    """One utility column per scored indicator, named u__<metric_id>."""

    out = pd.DataFrame(index=table.index)
    for metric_id, spec in config["indicators"].items():
        out[f"u__{metric_id}"] = utility(
            table[metric_id].astype(float).values,
            spec["direction"],
            spec["ideal_T"],
            spec["unacceptable_L"],
            spec.get("transform"),
            shape=shape,
            rho=rho,
            floor=config.get("utility_floor", 0.0),
        )
    return out


def dimension_scores(util: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
    """One column per dimension (0-1). NaN if any of its indicators is missing."""

    out = pd.DataFrame(index=util.index)
    for dimension_id, spec in config["dimensions"].items():
        members = list(spec["weights"])
        weights = [spec["weights"][m] for m in members]
        values = []
        for _, row in util[[f"u__{m}" for m in members]].iterrows():
            scores = row.tolist()
            values.append(np.nan if any(pd.isna(scores)) else aggregate_dimension(spec["aggregation"], scores, weights))
        out[dimension_id] = values
    return out


def _band(value: float, bands: Sequence[Sequence]) -> str | None:
    if pd.isna(value):
        return None
    for low, high, label in bands:
        if low <= value < high:
            return label
    return None


def flags(table: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
    """Context indicators that are shown but not scored."""

    out = pd.DataFrame(index=table.index)
    out["water_stress_change_2050"] = table["water_stress_2050_bau"] - table["baseline_water_stress"]
    out["fiber_100_20_availability"] = table["fiber_business_100_20_availability"]
    out["social_vulnerability"] = table["social_vulnerability_percentile"]
    out["extreme_heat_days"] = table["historical_days_tmax_gt90f"]
    for flag_id, spec in config["flags"].items():
        if spec.get("bands"):
            out[f"{flag_id}_band"] = [_band(v, spec["bands"]) for v in out[flag_id]]
    return out


def score_counties(
    table: pd.DataFrame,
    config: Mapping[str, Any] | None = None,
    shape: str = "linear",
    rho: float = 0.0,
) -> pd.DataFrame:
    """Identifiers + utilities + dimension scores + flags, one row per county."""

    config = config or load_config()
    validate_config(config)
    util = utilities(table, config, shape, rho)
    dims = dimension_scores(util, config)
    ids = table[["fips", "county_name", "state"]]
    return pd.concat([ids, dims, util, flags(table, config)], axis=1)


def zero_utility_report(scored: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
    """How many counties per state hit utility 0 or 100 on each indicator."""

    rows = []
    for metric_id in config["indicators"]:
        column = scored[f"u__{metric_id}"]
        for state, values in column.groupby(scored["state"]):
            rows.append({"metric_id": metric_id, "state": state, "zero": int((values <= 0).sum()), "saturated": int((values >= 100).sum())})
    return pd.DataFrame(rows)


def dimension_score_records(scored: pd.DataFrame, dimension_order: Sequence[str]) -> list[dict[str, Any]]:
    """Records for the decision matrix: candidate_id, candidate_name, scores {dimension: D or None}."""

    records = []
    for _, row in scored.iterrows():
        records.append(
            {
                "candidate_id": row["fips"],
                "candidate_name": f"{row['county_name']}, {row['state']}",
                "scores": {d: (None if pd.isna(row[d]) else float(row[d])) for d in dimension_order},
            }
        )
    return records


__all__ = [
    "AGGREGATION_METHODS",
    "aggregate_dimension",
    "dimension_score_records",
    "dimension_scores",
    "flags",
    "load_config",
    "score_counties",
    "utilities",
    "utility",
    "validate_config",
    "zero_utility_report",
]
