"""How indicator utilities (0-100) combine into one dimension score (0-1).

    weighted_mean       D = sum(w * u) / 100              indicators can offset each other
    weighted_geometric  D = prod((u / 100) ** w)          a poor indicator cannot be fully offset
    min                 D = min(u) / 100 over w > 0       the worst indicator decides

The within-dimension weights w of one dimension must sum to 1.
"""

from __future__ import annotations

import math
from typing import Sequence

AGGREGATION_METHODS = ("weighted_mean", "weighted_geometric", "min")


def aggregate_dimension(method: str, scores_0_100: Sequence[float], weights: Sequence[float]) -> float:
    """Return the dimension score (0-1) for one county."""

    if method not in AGGREGATION_METHODS:
        raise ValueError(f"unknown aggregation method: {method}")
    if len(scores_0_100) != len(weights) or not scores_0_100:
        raise ValueError("scores and weights must be non-empty and the same length")
    if any(w < 0 for w in weights) or abs(sum(weights) - 1.0) > 1e-9:
        raise ValueError("weights must be nonnegative and sum to 1")
    if any(not 0 <= u <= 100 for u in scores_0_100):
        raise ValueError("indicator scores must be between 0 and 100")

    pairs = list(zip(scores_0_100, weights))
    if method == "weighted_mean":
        return sum(w * u for u, w in pairs) / 100.0
    if method == "weighted_geometric":
        return math.prod((u / 100.0) ** w for u, w in pairs if w > 0)
    return min(u for u, w in pairs if w > 0) / 100.0
