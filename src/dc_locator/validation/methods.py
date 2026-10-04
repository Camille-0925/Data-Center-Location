"""Alternative dimension-weighting methods, used only to cross-check the AHP-based weights.

    equal     1/n for every scored dimension
    ROC       rank-order centroid of the AHP ordering: w_r = (1/n) sum_{m=r..n} 1/m
              (Barron & Barrett 1996, Management Science 42(11))
    CRITIC    w_j proportional to sigma_j * sum_k (1 - r_jk) on the county scores
              (Diakoulaki, Mavrotas & Papayannakis 1995, Computers & Operations Research 22(7))
    entropy   w_j proportional to 1 - e_j, e_j = -(1/ln n) sum_i p_ij ln p_ij (Shannon entropy;
              common in MCDA, e.g. Zeleny 1982)
    DEMATEL   w_k proportional to sqrt((r+c)^2 + (r-c)^2) from the total-relation matrix
              (common DEMATEL weighting; see Si et al. 2018)

CRITIC and entropy are data-driven: they reward dimensions that vary a lot across counties and
are not redundant. They measure discrimination, not importance, which is why they are
diagnostics here rather than the primary method.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd


def _normalize(values: Mapping[str, float]) -> dict[str, float]:
    total = sum(values.values())
    if total <= 0:
        raise ValueError("weights must have a positive sum")
    return {k: v / total for k, v in values.items()}


def equal_weights(dimensions: Sequence[str]) -> dict[str, float]:
    return {d: 1 / len(dimensions) for d in dimensions}


def roc_weights(ordered: Sequence[str]) -> dict[str, float]:
    """``ordered`` from most to least important."""

    n = len(ordered)
    return {d: sum(1 / m for m in range(r, n + 1)) / n for r, d in enumerate(ordered, start=1)}


def critic_weights(scores: pd.DataFrame, dimensions: Sequence[str]) -> dict[str, float]:
    data = scores[list(dimensions)].astype(float)
    sigma = data.std(ddof=1)
    corr = data.corr(method="pearson").fillna(0.0)
    info = {d: float(sigma[d] * (1 - corr[d]).sum()) for d in dimensions}
    return _normalize(info)


def entropy_weights(scores: pd.DataFrame, dimensions: Sequence[str], eps: float = 1e-3) -> dict[str, float]:
    data = scores[list(dimensions)].astype(float) + eps
    p = data / data.sum()
    n = len(data)
    e = -(p * np.log(p)).sum() / np.log(n)
    return _normalize({d: float(1 - e[d]) for d in dimensions})


def dematel_weights(dematel_result: Mapping, dimensions: Sequence[str]) -> dict[str, float]:
    rows = {item["dimension_id"]: item for item in dematel_result["dimensions"]}
    raw = {
        d: float(np.hypot(rows[d]["prominence_r_plus_c"], rows[d]["relation_r_minus_c"]))
        for d in dimensions
    }
    return _normalize(raw)
