"""DEMATEL: the team's causal-influence judgments between dimensions.

Gabus, A. & Fontela, E. (1972). World problems, an invitation to further thought within
    the framework of DEMATEL. Battelle Geneva Research Centre.
Si, S.-L., You, X.-Y., Liu, H.-C. & Zhang, P. (2018). DEMATEL technique: a systematic
    review of the state-of-the-art literature on methodologies and applications.
    Mathematical Problems in Engineering, 2018, 3696457.

Procedure:
    Z  average direct-influence matrix, z_kl in 0..4 = how strongly k directly influences l
    X  = Z / s,  s = max(largest row sum, largest column sum)
    T  = X (I - X)^-1          total influence: direct plus all indirect chains
    r  = row sums of T         influence given
    c  = column sums of T      influence received
    r + c  prominence          how central a dimension is in the system
    r - c  relation            > 0 cause, < 0 effect
    alpha = mean(T)            links with t_kl > alpha are drawn on the impact-relation map
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

SCALE = (0, 4)


def direct_matrix(order: Sequence[str], influences: Mapping[str, Mapping[str, float]]) -> np.ndarray:
    """Build one respondent's direct-influence matrix; unspecified pairs are 0."""

    index = {d: i for i, d in enumerate(order)}
    n = len(order)
    matrix = np.zeros((n, n))
    for source, targets in influences.items():
        if source not in index:
            raise ValueError(f"unknown dimension in DEMATEL influences: {source}")
        for target, value in targets.items():
            if target not in index:
                raise ValueError(f"unknown dimension in DEMATEL influences: {target}")
            if source == target:
                raise ValueError(f"self-influence is not allowed: {source}")
            if not SCALE[0] <= value <= SCALE[1]:
                raise ValueError(f"DEMATEL score {value} for {source} -> {target} is outside 0-4")
            matrix[index[source], index[target]] = float(value)
    return matrix


def total_relation(average_direct: np.ndarray) -> tuple[np.ndarray, float]:
    """Return (T, s). Raises if the normalized matrix does not converge."""

    s = max(average_direct.sum(axis=1).max(), average_direct.sum(axis=0).max())
    if s <= 0:
        raise ValueError("DEMATEL matrix has no influences")
    x = average_direct / s
    radius = max(abs(np.linalg.eigvals(x)))
    if radius >= 1 - 1e-12:
        raise ValueError("normalized DEMATEL matrix has spectral radius 1; T = X(I - X)^-1 does not exist")
    t = x @ np.linalg.inv(np.eye(len(x)) - x)
    return t, float(s)


def dematel(order: Sequence[str], respondents: Sequence[Mapping]) -> dict:
    """Run DEMATEL on one or more respondents and return everything needed for the report."""

    if not respondents:
        raise ValueError("at least one DEMATEL respondent is required")
    matrices = [direct_matrix(order, r["influences"]) for r in respondents]
    z = np.mean(matrices, axis=0)
    t, s = total_relation(z)
    r = t.sum(axis=1)
    c = t.sum(axis=0)
    alpha = float(t.mean())
    links = [
        {"from": order[i], "to": order[j], "total_influence": float(t[i, j])}
        for i in range(len(order))
        for j in range(len(order))
        if i != j and t[i, j] > alpha
    ]
    links.sort(key=lambda item: -item["total_influence"])
    dimensions = [
        {
            "dimension_id": d,
            "influence_given_r": float(r[i]),
            "influence_received_c": float(c[i]),
            "prominence_r_plus_c": float(r[i] + c[i]),
            "relation_r_minus_c": float(r[i] - c[i]),
            "role": "cause" if r[i] - c[i] > 1e-12 else ("effect" if r[i] - c[i] < -1e-12 else "neutral"),
        }
        for i, d in enumerate(order)
    ]
    return {
        "dimension_order": list(order),
        "respondent_ids": [r["respondent_id"] for r in respondents],
        "normalizer_s": s,
        "direct_matrix": z.tolist(),
        "total_relation_matrix": t.tolist(),
        "threshold_alpha": alpha,
        "dimensions": dimensions,
        "significant_links": links,
    }


def pairwise_strength(order: Sequence[str], total: Sequence[Sequence[float]]) -> dict[tuple[str, str], float]:
    """Symmetric link strength for each unordered pair: (t_kl + t_lk) / max over pairs, in 0..1."""

    t = np.asarray(total)
    raw = {}
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            raw[(order[i], order[j])] = float(t[i, j] + t[j, i])
    top = max(raw.values()) if raw else 0.0
    return {pair: (value / top if top > 0 else 0.0) for pair, value in raw.items()}
