"""Steps 3c/3d: relationships between dimensions (DEMATEL causal matrix, correlation, interaction matrix)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .dematel import dematel, direct_matrix, pairwise_strength, total_relation
from .interaction import build_interactions, spearman_matrix

DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "interactions.json"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    with Path(path or DEFAULT_CONFIG).open(encoding="utf-8") as handle:
        return json.load(handle)


def run_dematel(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    result = dematel(config["dimension_order"], config["dematel"]["respondents"])
    return {"config_version": config["version"], "config_status": config["status"], **result}


def interaction_matrix(
    dimension_scores,
    weights: Mapping[str, float],
    config: Mapping[str, Any] | None = None,
    kappa: float | None = None,
) -> dict[str, Any]:
    """DEMATEL + Spearman correlation of these counties + team signs -> scaled interactions."""

    config = config or load_config()
    order = config["dimension_order"]
    dem = run_dematel(config)
    strength = pairwise_strength(order, dem["total_relation_matrix"])
    corr, constant = spearman_matrix(dimension_scores, order)
    model = config["interaction_model"]
    result = build_interactions(
        order,
        weights,
        strength,
        corr,
        model["pairs"],
        kappa=model["kappa"] if kappa is None else kappa,
        beta=model["beta"],
    )
    result["correlation"] = corr.round(6).to_dict()
    result["constant_dimensions"] = constant
    return result


__all__ = [
    "build_interactions",
    "dematel",
    "direct_matrix",
    "interaction_matrix",
    "load_config",
    "pairwise_strength",
    "run_dematel",
    "spearman_matrix",
    "total_relation",
]
