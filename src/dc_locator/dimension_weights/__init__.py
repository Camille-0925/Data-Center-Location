"""Step 3a: customer inputs -> dimension weights (AHP base weights x customer multipliers)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .ahp import ahp_weights, build_matrix, consistency, eigenvector_priorities, geometric_mean_priorities
from .customer import MODES, adjust, apply_cap, resolve_inputs

DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "dimension_weights.json"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    with Path(path or DEFAULT_CONFIG).open(encoding="utf-8") as handle:
        return json.load(handle)


def compute_dimension_weights(
    customer_inputs: Mapping[str, Any] | None = None,
    mode: str = "within_state",
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the dimension weights for one customer, with the AHP base and an explanation."""

    config = config or load_config()
    order = config["dimension_order"]
    ahp = config["ahp"]
    base = ahp_weights(order, ahp["respondents"], ahp["max_consistency_ratio"], ahp["max_method_gap"])
    result = adjust(
        base["weights"],
        config["customer_inputs"],
        customer_inputs,
        mode,
        config["within_state_excluded"],
        config["max_dimension_weight"],
    )
    return {
        "config_version": config["version"],
        "config_status": config["status"],
        "dimension_order": order,
        **result,
        "ahp": {k: v for k, v in base.items() if k != "weights"} | {"base_weights": base["weights"]},
    }


__all__ = [
    "MODES",
    "adjust",
    "ahp_weights",
    "apply_cap",
    "build_matrix",
    "compute_dimension_weights",
    "consistency",
    "eigenvector_priorities",
    "geometric_mean_priorities",
    "load_config",
    "resolve_inputs",
]
