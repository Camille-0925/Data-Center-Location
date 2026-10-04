"""Safety-margin and dimension-specific temporal-robustness adjustments.

This module deliberately does not know Camille's dimension weights.  It prepares
weight-independent county values, applies one robustness factor to each mapped
dimension, and applies one weakest-link margin factor after the decision model has
calculated suitability.
"""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "score_adjustments.json"
RANK_TOLERANCE = 1e-8


def load_adjustments_config(path: str | Path | None = None) -> dict[str, Any]:
    with Path(path or DEFAULT_CONFIG).open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_adjustments_config(config: Mapping[str, Any], scoring_config: Mapping[str, Any]) -> None:
    indicators = set(scoring_config["indicators"])
    dimensions = set(scoring_config["dimensions"])

    margin = config["margin"]
    if margin.get("aggregation") != "minimum":
        raise ValueError("margin.aggregation must be minimum")
    margin_lambda = float(margin["lambda"])
    if not 0 <= margin_lambda <= 1:
        raise ValueError("margin.lambda must be between 0 and 1")
    selected = margin.get("indicators", [])
    if margin.get("enabled") and not selected:
        raise ValueError("enabled margin requires at least one indicator")
    unknown = set(selected) - indicators
    if unknown:
        raise ValueError(f"margin uses undefined indicators: {sorted(unknown)}")
    thresholds = margin.get("thresholds", {})
    if set(thresholds) - set(selected):
        raise ValueError("margin thresholds may only be set for selected indicators")
    for metric_id in selected:
        tau = float(thresholds.get(metric_id, margin.get("default_tau", 0.0)))
        if not 0 <= tau < 100:
            raise ValueError(f"margin threshold for {metric_id} must be in [0, 100)")

    gate = config["hard_zero_gate"]
    gate_unknown = set(gate.get("indicators", [])) - indicators
    if gate_unknown:
        raise ValueError(f"hard-zero gate uses undefined indicators: {sorted(gate_unknown)}")

    robustness = config["robustness"]
    seen_factor_columns: set[str] = set()
    for dimension_id, spec in robustness.get("dimensions", {}).items():
        if dimension_id not in dimensions:
            raise ValueError(f"robustness uses undefined dimension {dimension_id}")
        factor_column = spec["factor_column"]
        if factor_column in seen_factor_columns:
            raise ValueError(f"robustness factor column is reused: {factor_column}")
        seen_factor_columns.add(factor_column)
        penalty = float(spec["lambda"])
        if not 0 <= penalty <= 1:
            raise ValueError(f"robustness lambda for {dimension_id} must be between 0 and 1")


def load_robustness_factors(
    config: Mapping[str, Any], path: str | Path | None = None
) -> pd.DataFrame:
    configured = Path(path or config["robustness"]["data_path"])
    source = configured if configured.is_absolute() else PROJECT_ROOT / configured
    table = pd.read_csv(source, dtype={"fips": str})
    if "fips" not in table:
        raise ValueError("robustness table must contain fips")
    table["fips"] = table["fips"].str.zfill(5)
    if table["fips"].duplicated().any():
        raise ValueError("robustness table contains duplicate fips values")
    expected_counties = config["robustness"].get("expected_counties")
    if expected_counties is not None and len(table) != int(expected_counties):
        raise ValueError(f"robustness table must contain {expected_counties} counties")
    required = {
        field
        for spec in config["robustness"]["dimensions"].values()
        for field in (spec["factor_column"], spec["risk_column"])
    }
    missing = required - set(table.columns)
    if missing:
        raise ValueError(f"robustness table is missing columns: {sorted(missing)}")
    return table


def _margin_columns(
    scored: pd.DataFrame, config: Mapping[str, Any]
) -> pd.DataFrame:
    out = pd.DataFrame(index=scored.index)
    margin = config["margin"]
    selected = list(margin.get("indicators", []))
    if not margin.get("enabled"):
        out["margin_adjustment"] = 1.0
        out["margin_limiting_indicator"] = None
        return out

    penalty = float(margin["lambda"])
    factors: list[str] = []
    for metric_id in selected:
        utility_column = f"u__{metric_id}"
        if utility_column not in scored:
            raise ValueError(f"scored table is missing {utility_column}")
        tau = float(margin.get("thresholds", {}).get(metric_id, margin.get("default_tau", 0.0)))
        headroom_column = f"margin_headroom__{metric_id}"
        factor_column = f"margin_factor__{metric_id}"
        out[headroom_column] = ((scored[utility_column] - tau) / (100.0 - tau)).clip(0.0, 1.0)
        out[factor_column] = 1.0 - penalty * (1.0 - out[headroom_column])
        factors.append(factor_column)

    out["margin_adjustment"] = out[factors].min(axis=1, skipna=False)
    factor_to_metric = dict(zip(factors, selected))
    out["margin_limiting_indicator"] = out[factors].idxmin(axis=1, skipna=False).map(factor_to_metric)
    return out


def _hard_zero_columns(
    scored: pd.DataFrame, config: Mapping[str, Any]
) -> pd.DataFrame:
    out = pd.DataFrame(index=scored.index)
    gate = config["hard_zero_gate"]
    selected = list(gate.get("indicators", []))
    if not gate.get("enabled") or not selected:
        out["normalization_gate_status"] = "not_configured"
        out["normalization_feasibility_flag"] = np.nan
        out["normalization_gate_failed_indicators"] = ""
        return out

    utility_columns = [f"u__{metric_id}" for metric_id in selected]
    missing_columns = [column for column in utility_columns if column not in scored]
    if missing_columns:
        raise ValueError(f"scored table is missing hard-zero utilities: {missing_columns}")

    statuses: list[str] = []
    flags: list[float] = []
    failures: list[str] = []
    for _, row in scored[utility_columns].iterrows():
        failed = [metric for metric in selected if not pd.isna(row[f"u__{metric}"]) and row[f"u__{metric}"] <= 0]
        if failed:
            statuses.append("fail")
            flags.append(0.0)
        elif row.isna().any():
            statuses.append("unknown")
            flags.append(np.nan)
        else:
            statuses.append("pass")
            flags.append(1.0)
        failures.append("|".join(failed))
    out["normalization_gate_status"] = statuses
    out["normalization_feasibility_flag"] = flags
    out["normalization_gate_failed_indicators"] = failures
    return out


def apply_pre_weight_adjustments(
    scored: pd.DataFrame,
    scoring_config: Mapping[str, Any],
    adjustments_config: Mapping[str, Any] | None = None,
    robustness_factors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return audit columns plus robustness-adjusted dimensions.

    Base dimension columns are preserved as ``base__<dimension>``.  The ordinary
    dimension columns are replaced with D^R so every existing downstream consumer
    (interactions, Choquet, validation) receives the adjusted matrix unchanged.
    """

    config = adjustments_config or load_adjustments_config()
    validate_adjustments_config(config, scoring_config)
    out = scored.copy()
    dimensions = list(scoring_config["dimensions"])
    for dimension_id in dimensions:
        if dimension_id not in out:
            raise ValueError(f"scored table is missing dimension {dimension_id}")
        out[f"base__{dimension_id}"] = out[dimension_id]

    out = pd.concat([out, _margin_columns(out, config), _hard_zero_columns(out, config)], axis=1)

    robustness = config["robustness"]
    for dimension_id in dimensions:
        out[f"robustness_factor__{dimension_id}"] = 1.0
    if not robustness.get("enabled"):
        return out

    factors = robustness_factors.copy() if robustness_factors is not None else load_robustness_factors(config)
    factors["fips"] = factors["fips"].astype(str).str.zfill(5)
    component_columns = [column for column in factors.columns if column not in {"state", "county"}]
    out = out.merge(factors[component_columns], on="fips", how="left", validate="one_to_one")

    for dimension_id, spec in robustness["dimensions"].items():
        factor_column = spec["factor_column"]
        risk_column = spec["risk_column"]
        if out[[factor_column, risk_column]].isna().any().any():
            missing_fips = out.loc[out[factor_column].isna() | out[risk_column].isna(), "fips"].tolist()
            raise ValueError(f"missing robustness factor for fips: {missing_fips[:10]}")
        expected = 1.0 - float(spec["lambda"]) * out[risk_column].astype(float)
        if not out[risk_column].between(0.0, 1.0).all():
            raise ValueError(f"robustness risk percentile for {dimension_id} must be between 0 and 1")
        if not np.allclose(out[factor_column].astype(float), expected, atol=1e-10):
            raise ValueError(f"stored robustness factors do not match risk percentile and lambda for {dimension_id}")
        if not out[factor_column].between(0.0, 1.0).all():
            raise ValueError(f"robustness factor for {dimension_id} must be between 0 and 1")
        out[f"robustness_factor__{dimension_id}"] = out[factor_column].astype(float)
        out[dimension_id] = out[f"base__{dimension_id}"] * out[f"robustness_factor__{dimension_id}"]
    return out


def _assign_ranks(records: list[dict[str, Any]]) -> None:
    for item in records:
        item["rank"] = None
    for pool in ("verified_feasible", "conditional"):
        eligible = [item for item in records if item["ranking_pool"] == pool and item["score_0_100"] is not None]
        eligible.sort(key=lambda item: (-item["score_0_100"], item["candidate_id"]))
        previous_score: float | None = None
        previous_rank: int | None = None
        for position, item in enumerate(eligible, start=1):
            if previous_score is not None and abs(item["score_0_100"] - previous_score) <= RANK_TOLERANCE:
                item["rank"] = previous_rank
            else:
                item["rank"] = position
                previous_rank = position
            previous_score = item["score_0_100"]


def _refresh_tradeoffs(records: list[dict[str, Any]], order: Sequence[str]) -> None:
    for item in records:
        item["tradeoffs"] = []
    pools: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        if item["rank"] is not None:
            pools.setdefault(item["ranking_pool"], []).append(item)
    for members in pools.values():
        ordered = sorted(members, key=lambda item: (item["rank"], item["candidate_id"]))
        if len(ordered) < 2:
            continue
        leader = ordered[0]
        for item in ordered:
            comparison = ordered[1] if item is leader else leader
            item["tradeoffs"] = [
                {
                    "comparison_candidate_id": comparison["candidate_id"],
                    "dimension_id": dimension_id,
                    "score_difference_current_minus_comparison": float(item["dimension_scores"][dimension_id])
                    - float(comparison["dimension_scores"][dimension_id]),
                    "points_difference": 100.0
                    * float(item["dimension_weights_used"][dimension_id])
                    * (
                        float(item["dimension_scores"][dimension_id])
                        - float(comparison["dimension_scores"][dimension_id])
                    ),
                }
                for dimension_id in order
            ]


def apply_final_score_adjustments(
    decision: Mapping[str, Any],
    adjusted_counties: pd.DataFrame,
    dimension_order: Sequence[str],
) -> dict[str, Any]:
    """Apply A_M once to suitability and enforce only configured normalization gates."""

    result = deepcopy(decision)
    by_fips = adjusted_counties.set_index("fips", drop=False)
    records = result["recommendations"]["records"]
    for item in records:
        row = by_fips.loc[item["candidate_id"]]
        before = item["score_0_100"]
        margin = None if pd.isna(row["margin_adjustment"]) else float(row["margin_adjustment"])
        gate_status = str(row["normalization_gate_status"])
        item["suitability_before_margin_0_100"] = before
        item["margin_adjustment"] = margin
        item["margin_limiting_indicator"] = row["margin_limiting_indicator"]
        item["normalization_gate_status"] = gate_status
        item["normalization_gate_failed_indicators"] = (
            str(row["normalization_gate_failed_indicators"]).split("|")
            if row["normalization_gate_failed_indicators"]
            else []
        )
        item["robustness_factors"] = {
            dimension_id: float(row[f"robustness_factor__{dimension_id}"])
            for dimension_id in dimension_order
        }
        gate_failed = gate_status == "fail" or item.get("gate_status") == "fail"
        multiplier = 0.0 if gate_failed else margin
        for contribution in item["dimension_contributions"]:
            contribution["final_contribution_points"] = (
                None if multiplier is None else contribution["contribution_points"] * multiplier
            )
        for contribution in item["interaction_contributions"]:
            contribution["final_contribution_points"] = (
                None if multiplier is None else contribution["contribution_points"] * multiplier
            )

        if gate_failed:
            item["score_0_100"] = 0.0
            item["score_status"] = "excluded"
            item["eligibility_status"] = "excluded"
            item["ranking_pool"] = "excluded"
        elif gate_status == "unknown" or before is None or margin is None or not math.isfinite(margin):
            item["score_0_100"] = None
            item["score_status"] = "incomplete"
            if gate_status == "unknown":
                item["eligibility_status"] = "incomplete"
                item["ranking_pool"] = "incomplete"
        else:
            item["score_0_100"] = float(before) * margin

    _assign_ranks(records)
    _refresh_tradeoffs(records, dimension_order)
    result["diagnostics"].append(
        "dimension-specific robustness was applied before dimension weighting; one weakest-link margin adjustment was applied after suitability"
    )
    return result


__all__ = [
    "apply_final_score_adjustments",
    "apply_pre_weight_adjustments",
    "load_adjustments_config",
    "load_robustness_factors",
    "validate_adjustments_config",
]
