"""SMAA-2 robustness analysis for the Choquet ranking.

Lahdelma, R. & Salminen, P. (2001). SMAA-2: Stochastic multicriteria acceptability analysis
    for group decision making. Operations Research 49(3), 444-454.

Weights are sampled around the customer's weights phi0 from a Dirichlet(alpha * phi0)
distribution (mean phi0; larger alpha = tighter). The interaction intensity kappa is sampled
uniformly on [kappa_low, kappa_high]. For every sample the 2-additive Choquet score

    S = D phi - 1/2 * G (kappa * lambda_max(phi) * I_raw)

is computed for all counties at once (G = |D_k - D_l| per interacting pair), and counties are
ranked. Outputs per county:

    rank acceptability b_r   share of samples in which the county takes rank r
    p_top1, p_top10          shares of samples with rank 1 / rank <= 10
    rank median, p05, p95
    regret q90               90th percentile of (best score in the sample - county score)
    central weights          mean weights over the samples in which the county ranks first
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd


def raw_interaction_pattern(pairs: Sequence[Mapping]) -> list[tuple[str, str, float]]:
    """Unscaled sign * strength for the kept pairs of build_interactions()."""

    sign = {"complementarity": 1.0, "redundancy": -1.0}
    return [
        (p["dimensions"][0], p["dimensions"][1], sign[p["type"]] * p["strength"])
        for p in pairs
        if p["status"] == "kept"
    ]


def lambda_max(weights: np.ndarray, index: Mapping[str, int], pattern: Sequence[tuple[str, str, float]]) -> np.ndarray:
    """Largest admissible interaction scale for each row of ``weights`` (M x K)."""

    load = np.zeros(weights.shape[1])
    for k, l, value in pattern:
        load[index[k]] += abs(value) / 2
        load[index[l]] += abs(value) / 2
    active = load > 0
    if not active.any():
        return np.zeros(weights.shape[0])
    return (weights[:, active] / load[active]).min(axis=1)


def choquet_scores(
    D: np.ndarray, weights: np.ndarray, kappa: np.ndarray, index: Mapping[str, int], pattern
) -> np.ndarray:
    """Scores (M samples x n counties, 0-100)."""

    linear = weights @ D.T
    if not pattern:
        return 100 * linear
    gaps = np.stack([np.abs(D[:, index[k]] - D[:, index[l]]) for k, l, _ in pattern], axis=1)  # n x P
    raw = np.array([v for _, _, v in pattern])  # P
    scale = kappa * lambda_max(weights, index, pattern)  # M
    penalty = 0.5 * (scale[:, None] * raw[None, :]) @ gaps.T  # M x n
    return 100 * (linear - penalty)


def _scores_with_adjustments(
    base: np.ndarray,
    risk: Mapping[int, np.ndarray],
    min_headroom: np.ndarray,
    weights: np.ndarray,
    kappa: np.ndarray,
    lambda_r: Mapping[int, np.ndarray],
    lambda_m: np.ndarray,
    index: Mapping[str, int],
    pattern,
    chunk: int = 500,
) -> np.ndarray:
    """Final scores when the robustness and margin coefficients are sampled too.

    For sample s:  D^R_ik = base_ik * (1 - lambda_R[k]_s * p_ik) for the robustness dimensions,
    S = Choquet(D^R, w_s, kappa_s), A_M = 1 - lambda_M_s * (1 - min_k headroom_ik),
    Final = S * A_M.
    """

    samples, n = weights.shape[0], base.shape[0]
    out = np.empty((samples, n))
    raw = np.array([v for _, _, v in pattern]) if pattern else np.zeros(0)
    scale_all = kappa * lambda_max(weights, index, pattern) if pattern else np.zeros(samples)
    for start in range(0, samples, chunk):
        stop = min(start + chunk, samples)
        c = stop - start
        D = np.broadcast_to(base, (c,) + base.shape).copy()  # c x n x K
        for k, p in risk.items():
            D[:, :, k] = base[None, :, k] * (1 - lambda_r[k][start:stop, None] * p[None, :])
        linear = np.einsum("cnk,ck->cn", D, weights[start:stop])
        penalty = np.zeros((c, n))
        for j, (k, l, _) in enumerate(pattern):
            gap = np.abs(D[:, :, index[k]] - D[:, :, index[l]])
            penalty += 0.5 * (scale_all[start:stop] * raw[j])[:, None] * gap
        margin = 1 - lambda_m[start:stop, None] * (1 - min_headroom[None, :])
        out[start:stop] = 100 * (linear - penalty) * margin
    return out


def smaa(
    D: pd.DataFrame,
    phi0: Mapping[str, float],
    pattern: Sequence[tuple[str, str, float]],
    samples: int = 10_000,
    alpha: float = 20.0,
    kappa_range: tuple[float, float] = (0.0, 1.0),
    top: int = 10,
    seed: int = 42,
    final_multiplier: pd.Series | None = None,
    adjustments: Mapping | None = None,
) -> dict:
    """Run SMAA-2 on dimension scores D (rows = counties, columns = dimensions).

    ``final_multiplier`` (one value per county, independent of the weights) is applied to
    every sampled score, e.g. the safety-margin factor A_M of the score adjustments, so that
    SMAA ranks counties on the same final score as the pipeline.

    ``adjustments`` (optional) also samples the score-adjustment coefficients instead of
    holding them fixed: {"base": DataFrame of unadjusted dimension scores,
    "risk": {dimension: Series of robustness risk percentiles},
    "min_headroom": Series of each county's smallest margin headroom,
    "lambda_r_range": (low, high), "lambda_m_range": (low, high)}. Each robustness dimension
    gets its own uniformly sampled lambda. When given, ``final_multiplier`` is ignored.
    """

    rng = np.random.default_rng(seed)
    active = [d for d, w in phi0.items() if w > 0]
    index = {d: i for i, d in enumerate(active)}
    matrix = D[active].to_numpy(dtype=float)
    base = np.array([phi0[d] for d in active])
    weights = rng.dirichlet(alpha * base, size=samples)
    kappa = rng.uniform(*kappa_range, size=samples)
    pattern = [p for p in pattern if p[0] in index and p[1] in index]

    sampled_lambdas = {}
    if adjustments is not None:
        base = adjustments["base"].reindex(D.index)[active].to_numpy(dtype=float)
        risk = {index[d]: s.reindex(D.index).to_numpy(dtype=float) for d, s in adjustments["risk"].items() if d in index}
        lambda_r = {k: rng.uniform(*adjustments["lambda_r_range"], size=samples) for k in risk}
        lambda_m = rng.uniform(*adjustments["lambda_m_range"], size=samples)
        headroom = adjustments["min_headroom"].reindex(D.index).to_numpy(dtype=float)
        scores = _scores_with_adjustments(base, risk, headroom, weights, kappa, lambda_r, lambda_m, index, pattern)
        sampled_lambdas = {
            "lambda_r_range": list(adjustments["lambda_r_range"]),
            "lambda_m_range": list(adjustments["lambda_m_range"]),
            "robustness_dimensions": [d for d in adjustments["risk"] if d in index],
        }
    else:
        scores = choquet_scores(matrix, weights, kappa, index, pattern)  # M x n
        if final_multiplier is not None:
            scores = scores * final_multiplier.reindex(D.index).to_numpy(dtype=float)[None, :]
    order = np.argsort(-scores, axis=1)
    ranks = np.empty_like(order)
    rows = np.arange(samples)[:, None]
    ranks[rows, order] = np.arange(1, matrix.shape[0] + 1)[None, :]
    regret = scores.max(axis=1, keepdims=True) - scores

    winners = order[:, 0]
    central = {}
    for i in range(matrix.shape[0]):
        mask = winners == i
        if mask.any():
            central[D.index[i]] = dict(zip(active, weights[mask].mean(axis=0).round(4).tolist()))

    table = pd.DataFrame(
        {
            "p_top1": (ranks == 1).mean(axis=0),
            f"p_top{top}": (ranks <= top).mean(axis=0),
            "rank_median": np.median(ranks, axis=0),
            "rank_p05": np.percentile(ranks, 5, axis=0),
            "rank_p95": np.percentile(ranks, 95, axis=0),
            "regret_q90": np.percentile(regret, 90, axis=0),
        },
        index=D.index,
    ).sort_values([f"p_top{top}", "p_top1"], ascending=False)
    acceptability = pd.DataFrame(
        {f"rank_{r}": (ranks == r).mean(axis=0) for r in range(1, top + 1)}, index=D.index
    ).loc[table.index]
    weight_sd = weights.std(axis=0)
    return {
        "table": table,
        "rank_acceptability": acceptability,
        "central_weights": central,
        "settings": {
            "samples": samples,
            "alpha": alpha,
            "kappa_range": list(kappa_range),
            "seed": seed,
            "weight_mean": dict(zip(active, weights.mean(axis=0).round(4).tolist())),
            "weight_sd": dict(zip(active, weight_sd.round(4).tolist())),
            **sampled_lambdas,
        },
        "most_robust": table.index[0],
        "min_regret_q90": table["regret_q90"].idxmin(),
    }
