"""Correlation matrix (A) + DEMATEL (B) + team signs -> Choquet interaction matrix I.

Interaction types (assigned by the team, one per pair; most pairs have none):

    complementarity (I > 0)  both dimensions must be good: a weakness in one compounds
                             the other (e.g. a hot climate raises water demand exactly where
                             water may be scarce). A preference/causal statement, so its
                             strength comes from DEMATEL only.
    redundancy (I < 0)       the two dimensions partly measure the same thing. An empirical
                             statement, so it must be visible in the data: strength mixes the
                             DEMATEL link and the positive Spearman correlation rho+; if
                             rho <= 0 in the state, the redundancy is dropped with a warning.

    strength s_kl in [0, 1]:
        complementarity  s = dematel_kl
        redundancy       s = beta * dematel_kl + (1 - beta) * max(rho_kl, 0)
    raw  I^_kl = sign_kl * s_kl
    scale I = kappa * lambda_max * I^,  lambda_max = min_k phi_k / (1/2 sum_l |I^_kl|)

lambda_max is the largest scale that keeps the Choquet capacity monotone for the given
weights phi (phi_k >= 1/2 sum_l |I_kl|), so kappa in [0, 1] is the interaction intensity as a
share of the admissible maximum. Dimensions with phi_k = 0 (e.g. energy within a state) get no
interactions: their score is constant within the state and would otherwise enter the ranking
through |D_k - D_l|.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

TYPES = {"complementarity": 1.0, "redundancy": -1.0}


def spearman_matrix(dimension_scores: pd.DataFrame, order: Sequence[str]) -> tuple[pd.DataFrame, list[str]]:
    """Spearman rank correlation between dimension scores; constant dimensions get 0 and a note."""

    data = dimension_scores[list(order)].astype(float)
    constant = [d for d in order if data[d].nunique() <= 1]
    corr = data.corr(method="spearman").reindex(index=order, columns=order)
    corr = corr.fillna(0.0)
    for d in order:
        corr.loc[d, d] = 1.0
    return corr, constant


def build_interactions(
    order: Sequence[str],
    weights: Mapping[str, float],
    dematel_strength: Mapping[tuple[str, str], float],
    correlation: pd.DataFrame,
    pair_types: Sequence[Mapping[str, Any]],
    kappa: float = 0.5,
    beta: float = 0.5,
) -> dict[str, Any]:
    """Return the scaled interaction list for scoring_config plus a full audit trail."""

    if not 0 <= kappa <= 1:
        raise ValueError("kappa must be in [0, 1]")
    if not 0 <= beta <= 1:
        raise ValueError("beta must be in [0, 1]")

    def strength_of(k: str, l: str) -> float:
        return dematel_strength.get((k, l), dematel_strength.get((l, k), 0.0))

    raw: dict[tuple[str, str], float] = {}
    audit: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[frozenset[str]] = set()
    for entry in pair_types:
        k, l = entry["dimensions"]
        kind = entry["type"]
        if kind not in TYPES:
            raise ValueError(f"interaction type must be complementarity or redundancy, got {kind}")
        if k not in order or l not in order or k == l:
            raise ValueError(f"invalid interaction pair {k}, {l}")
        if frozenset((k, l)) in seen:
            raise ValueError(f"interaction pair listed twice: {k}, {l}")
        seen.add(frozenset((k, l)))
        rho = float(correlation.loc[k, l])
        dem = strength_of(k, l)
        record = {"dimensions": [k, l], "type": kind, "dematel_strength": dem, "spearman_rho": rho,
                  "rationale": entry.get("rationale", "")}
        if weights[k] == 0 or weights[l] == 0:
            record.update(strength=0.0, status="dropped: a dimension has weight 0 in this mode")
        elif kind == "redundancy" and rho <= 0:
            record.update(strength=0.0, status="dropped: redundancy not supported by the data (rho <= 0)")
            warnings.append(f"redundancy {k}-{l} dropped: Spearman rho = {rho:.2f} <= 0 in this state")
        else:
            s = dem if kind == "complementarity" else beta * dem + (1 - beta) * max(rho, 0.0)
            record.update(strength=s, status="kept" if s > 0 else "dropped: zero strength")
            if s > 0:
                raw[(k, l)] = TYPES[kind] * s
        audit.append(record)

    load = {d: 0.0 for d in order}
    for (k, l), value in raw.items():
        load[k] += abs(value) / 2
        load[l] += abs(value) / 2
    ratios = {d: weights[d] / load[d] for d in order if load[d] > 0}
    if ratios:
        binding = min(ratios, key=ratios.get)
        lambda_max = ratios[binding]
    else:
        binding, lambda_max = None, 0.0
    scale = kappa * lambda_max
    interactions = []
    for (k, l), value in raw.items():
        scaled = float(np.clip(scale * value, -1.0, 1.0))
        interactions.append({"dimensions": [k, l], "value": scaled})
        for record in audit:
            if record["dimensions"] == [k, l]:
                record["interaction_index"] = scaled
    return {
        "interactions": interactions,
        "kappa": kappa,
        "beta": beta,
        "lambda_max": lambda_max,
        "binding_dimension": binding,
        "pairs": audit,
        "warnings": warnings,
    }
