"""Steps 3c/3d: relationships between dimensions (DEMATEL causal matrix, correlation, interaction matrix)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .dematel import dematel, direct_matrix, pairwise_strength, total_relation

DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "interactions.json"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    with Path(path or DEFAULT_CONFIG).open(encoding="utf-8") as handle:
        return json.load(handle)


def run_dematel(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    result = dematel(config["dimension_order"], config["dematel"]["respondents"])
    return {"config_version": config["version"], "config_status": config["status"], **result}


__all__ = ["dematel", "direct_matrix", "load_config", "pairwise_strength", "run_dematel", "total_relation"]
