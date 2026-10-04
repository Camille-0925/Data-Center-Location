"""Analytic Hierarchy Process (AHP) for the base dimension weights.

Saaty, T. L. (1980). The Analytic Hierarchy Process. McGraw-Hill.
    Pairwise comparison on the 1-9 scale; priority vector = principal eigenvector;
    consistency ratio CR = CI / RI with CI = (lambda_max - n) / (n - 1).
Crawford, G. & Williams, C. (1985). A note on the analysis of subjective judgment
    matrices. Journal of Mathematical Psychology 29(4).
    Row geometric mean as an alternative priority vector (used here as a cross-check).
Forman, E. & Peniwati, K. (1998). Aggregating individual judgments and priorities
    with the analytic hierarchy process. European Journal of Operational Research 108(1).
    Aggregation of individual judgments (AIJ) by element-wise geometric mean.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

# Saaty's random consistency index by matrix size.
RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
SAATY_SCALE = (1 / 9, 9)


def build_matrix(order: Sequence[str], judgments: Sequence[Sequence]) -> np.ndarray:
    """Build a reciprocal matrix from upper-triangle judgments [row_id, col_id, value].

    ``value`` says how much more important ``row_id`` is than ``col_id`` (1 = equal, 9 = extreme).
    Every unordered pair must be judged exactly once.
    """

    index = {d: i for i, d in enumerate(order)}
    n = len(order)
    matrix = np.ones((n, n))
    seen: set[frozenset[str]] = set()
    for row_id, col_id, value in judgments:
        if row_id not in index or col_id not in index or row_id == col_id:
            raise ValueError(f"invalid AHP pair: {row_id} vs {col_id}")
        pair = frozenset((row_id, col_id))
        if pair in seen:
            raise ValueError(f"AHP pair judged twice: {row_id} vs {col_id}")
        value = float(value)
        if not SAATY_SCALE[0] - 1e-9 <= value <= SAATY_SCALE[1] + 1e-9:
            raise ValueError(f"AHP judgment {value} for {row_id} vs {col_id} is outside the 1/9-9 scale")
        seen.add(pair)
        i, j = index[row_id], index[col_id]
        matrix[i, j] = value
        matrix[j, i] = 1.0 / value
    expected = n * (n - 1) // 2
    if len(seen) != expected:
        raise ValueError(f"AHP needs {expected} pairwise judgments for {n} dimensions, got {len(seen)}")
    return matrix


def aggregate_judgments(matrices: Sequence[np.ndarray]) -> np.ndarray:
    """AIJ: element-wise geometric mean of several respondents' matrices (keeps reciprocity)."""

    if not matrices:
        raise ValueError("at least one AHP respondent is required")
    stacked = np.stack(matrices)
    return np.exp(np.log(stacked).mean(axis=0))


def eigenvector_priorities(matrix: np.ndarray) -> tuple[np.ndarray, float]:
    """Principal right eigenvector (normalized to sum 1) and the principal eigenvalue."""

    values, vectors = np.linalg.eig(matrix)
    k = int(np.argmax(values.real))
    vector = np.abs(vectors[:, k].real)
    return vector / vector.sum(), float(values[k].real)


def geometric_mean_priorities(matrix: np.ndarray) -> np.ndarray:
    row = np.exp(np.log(matrix).mean(axis=1))
    return row / row.sum()


def consistency(matrix: np.ndarray, lambda_max: float) -> dict[str, float]:
    n = matrix.shape[0]
    ci = (lambda_max - n) / (n - 1) if n > 2 else 0.0
    ri = RANDOM_INDEX.get(n)
    if ri is None:
        raise ValueError(f"no random index for n = {n}")
    cr = ci / ri if ri > 0 else 0.0
    return {"lambda_max": lambda_max, "consistency_index": ci, "random_index": ri, "consistency_ratio": cr}


def ahp_weights(
    order: Sequence[str],
    respondents: Sequence[Mapping],
    max_consistency_ratio: float = 0.10,
    max_method_gap: float = 0.01,
) -> dict:
    """Base weights from one or more respondents' pairwise judgments.

    Returns the eigenvector weights (primary), the geometric-mean weights (cross-check),
    consistency statistics for the aggregated matrix and for each respondent, and warnings.
    Raises ValueError if the aggregated matrix fails the consistency threshold.
    """

    individual = []
    matrices = []
    for respondent in respondents:
        matrix = build_matrix(order, respondent["judgments"])
        _, lam = eigenvector_priorities(matrix)
        stats = consistency(matrix, lam)
        individual.append({"respondent_id": respondent["respondent_id"], **stats})
        matrices.append(matrix)

    team = aggregate_judgments(matrices)
    eigen, lam = eigenvector_priorities(team)
    geometric = geometric_mean_priorities(team)
    stats = consistency(team, lam)
    gap = float(np.max(np.abs(eigen - geometric)))
    warnings = []
    for item in individual:
        if item["consistency_ratio"] >= max_consistency_ratio:
            warnings.append(
                f"respondent {item['respondent_id']} has CR = {item['consistency_ratio']:.3f} >= {max_consistency_ratio}"
            )
    if gap > max_method_gap:
        warnings.append(f"eigenvector and geometric-mean weights differ by up to {gap:.4f}")
    if stats["consistency_ratio"] >= max_consistency_ratio:
        raise ValueError(
            f"aggregated AHP matrix is inconsistent: CR = {stats['consistency_ratio']:.3f} >= {max_consistency_ratio}"
        )
    return {
        "weights": {d: float(w) for d, w in zip(order, eigen)},
        "weights_geometric_mean": {d: float(w) for d, w in zip(order, geometric)},
        "max_method_gap": gap,
        **stats,
        "respondents": individual,
        "warnings": warnings,
        "matrix": [[float(x) for x in row] for row in team],
    }
