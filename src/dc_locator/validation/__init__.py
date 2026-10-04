"""Step 3b: cross-validation and robustness of the county ranking.

    python -m dc_locator.validation --state VA [--samples 10000]

1. Weight-method comparison: AHP (primary) vs equal, ROC, CRITIC, entropy, DEMATEL weights.
2. SMAA-2: Dirichlet-sampled weights, uniform kappa, and uniform robustness / margin
   coefficients (lambda_R, lambda_M in [0.1, 0.3]) -> rank acceptability, p(top 10), regret.
3. Effective weights: each dimension's share of the variance of the total score.
4. Customer-input response: how each option changes the top 10.
5. Value-function shape: linear vs exponential (rho = +/-2) utilities.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from ..data_prep import load_processed
from ..dimension_weights import load_config as load_weights_config
from ..indicator_scoring import load_config as load_scoring_config, score_counties
from ..interactions import run_dematel
from ..pipeline import ROOT, run
from .methods import critic_weights, dematel_weights, entropy_weights, equal_weights, roc_weights
from .smaa import raw_interaction_pattern, smaa


def _rank(scores: pd.Series) -> pd.Series:
    return scores.rank(ascending=False, method="min")


def _top(scores: pd.Series, n: int = 10) -> set:
    return set(scores.sort_values(ascending=False).index[:n])


def weighted_sum(D: pd.DataFrame, weights: Mapping[str, float]) -> pd.Series:
    cols = [d for d, w in weights.items() if w > 0]
    return 100 * (D[cols] * pd.Series({d: weights[d] for d in cols})).sum(axis=1)


def final_multiplier(baseline: Mapping[str, Any]) -> pd.Series:
    """Weight-independent factor applied after suitability (safety margin A_M); 1 if absent."""

    ranking = baseline["ranking"].set_index("fips")
    if "margin_adjustment" not in ranking:
        return pd.Series(1.0, index=ranking.index)
    return ranking["margin_adjustment"].fillna(1.0).astype(float)


LAMBDA_RANGE = (0.10, 0.30)  # around the configured 0.20; same range as the weights guide uses for lambda


def adjustment_inputs(baseline: Mapping[str, Any], lambda_range=LAMBDA_RANGE) -> dict[str, Any] | None:
    """Inputs for sampling the robustness and margin coefficients in SMAA (None if adjustments are off)."""

    config = baseline.get("adjustments_config")
    if not config:
        return None
    counties = baseline["counties"].set_index("fips")
    order = baseline["weights"]["dimension_order"]
    base = counties[[f"base__{d}" for d in order]].rename(columns=lambda c: c.split("__", 1)[1])
    risk = {}
    if config["robustness"].get("enabled"):
        for dimension_id, spec in config["robustness"]["dimensions"].items():
            risk[dimension_id] = counties[spec["risk_column"]].astype(float)
    headroom_columns = [c for c in counties.columns if c.startswith("margin_headroom__")]
    if config["margin"].get("enabled") and headroom_columns:
        min_headroom = counties[headroom_columns].min(axis=1)
        lambda_m_range = lambda_range
    else:
        min_headroom = pd.Series(1.0, index=counties.index)
        lambda_m_range = (0.0, 0.0)
    return {
        "base": base,
        "risk": risk,
        "min_headroom": min_headroom,
        "lambda_r_range": lambda_range,
        "lambda_m_range": lambda_m_range,
    }


def compare_methods(baseline: Mapping[str, Any]) -> dict[str, Any]:
    """Rank the same counties under six weighting methods (weighted sum x margin) and compare."""

    counties = baseline["counties"].set_index("fips")
    multiplier = final_multiplier(baseline)
    phi = baseline["weights"]["weights"]
    active = [d for d, w in phi.items() if w > 0]
    D = counties[active]
    ahp = {d: phi[d] for d in active}
    methods = {
        "AHP (primary)": ahp,
        "equal": equal_weights(active),
        "ROC (AHP order)": roc_weights(sorted(active, key=lambda d: -ahp[d])),
        "CRITIC (data)": critic_weights(D, active),
        "entropy (data)": entropy_weights(D, active),
        "DEMATEL (influence)": dematel_weights(run_dematel(), active),
    }
    choquet = baseline["ranking"].set_index("fips")["score"]
    scores = {"AHP + Choquet (final)": choquet}
    scores.update({name: weighted_sum(D, w) * multiplier.reindex(D.index) for name, w in methods.items()})
    reference = scores["AHP + Choquet (final)"]
    summary = []
    for name, s in scores.items():
        summary.append(
            {
                "method": name,
                "spearman_vs_final": float(_rank(s).corr(_rank(reference.reindex(s.index)), method="spearman")),
                "top10_overlap_with_final": len(_top(s) & _top(reference)),
                "same_first": s.idxmax() == reference.idxmax(),
                "first": counties.loc[s.idxmax(), "county_name"],
            }
        )
    weights_table = pd.DataFrame(methods).T[active]
    return {"weights": weights_table, "summary": pd.DataFrame(summary)}


def effective_weights(baseline: Mapping[str, Any]) -> pd.DataFrame:
    """Share of Var(final score) explained by each term; the shares sum to 1.

    Final = A_M * [sum_k phi_k D_k + interaction part], so with t_k = phi_k D_k A_M and the
    interaction term taken as the remainder, Final = sum_k t_k + t_I exactly and
    share_k = Cov(t_k, Final) / Var(Final).
    """

    ranking = baseline["ranking"].set_index("fips")
    phi = baseline["weights"]["weights"]
    active = [d for d, w in phi.items() if w > 0]
    final = ranking["score"] / 100
    margin = ranking["margin_adjustment"].astype(float) if "margin_adjustment" in ranking else 1.0
    var = final.var()
    terms = {d: phi[d] * ranking[f"D_{d}"] * margin for d in active}
    terms["interactions"] = final - sum(terms.values())
    return pd.DataFrame(
        [
            {
                "term": name,
                "nominal_weight": phi.get(name, np.nan),
                "effective_share": float(t.cov(final) / var),
            }
            for name, t in terms.items()
        ]
    )


def customer_response(state: str, scored: pd.DataFrame, baseline: Mapping[str, Any]) -> pd.DataFrame:
    spec = load_weights_config()["customer_inputs"]
    base = baseline["ranking"].set_index("fips")["score"]
    rows = []
    for field, field_spec in spec.items():
        for option in field_spec["options"]:
            if option == field_spec["default"]:
                continue
            alt = run(state, {field: option}, scored=scored)["ranking"].set_index("fips")["score"]
            rows.append(
                {
                    "input": field,
                    "option": option,
                    "top10_overlap_with_default": len(_top(alt) & _top(base)),
                    "spearman_vs_default": float(_rank(alt).corr(_rank(base.reindex(alt.index)))),
                    "new_first": baseline["counties"].set_index("fips").loc[alt.idxmax(), "county_name"],
                }
            )
    return pd.DataFrame(rows)


def utility_shape(state: str, baseline: Mapping[str, Any]) -> pd.DataFrame:
    base = baseline["ranking"].set_index("fips")["score"]
    table = load_processed()
    rows = []
    for rho in (-2.0, 2.0):
        alt_scored = score_counties(table, load_scoring_config(), shape="exponential", rho=rho)
        alt = run(state, scored=alt_scored)["ranking"].set_index("fips")["score"]
        rows.append(
            {
                "utility_shape": f"exponential rho={rho:+.0f}",
                "top10_overlap_with_linear": len(_top(alt) & _top(base)),
                "spearman_vs_linear": float(_rank(alt).corr(_rank(base.reindex(alt.index)))),
                "first": baseline["counties"].set_index("fips").loc[alt.idxmax(), "county_name"],
            }
        )
    return pd.DataFrame(rows)


def run_validation(state: str, samples: int = 10_000, seed: int = 42, out_dir: str | Path | None = None) -> dict[str, Any]:
    scored = score_counties(load_processed())
    baseline = run(state, scored=scored)
    counties = baseline["counties"].set_index("fips")
    names = counties["county_name"]

    methods = compare_methods(baseline)
    pattern = raw_interaction_pattern(baseline["interactions"]["pairs"])
    robust = smaa(
        counties,
        baseline["weights"]["weights"],
        pattern,
        samples=samples,
        seed=seed,
        final_multiplier=final_multiplier(baseline),
        adjustments=adjustment_inputs(baseline),
    )
    robust_table = robust["table"].copy()
    robust_table.insert(0, "county", names.reindex(robust_table.index))
    effective = effective_weights(baseline)
    response = customer_response(state, scored, baseline)
    shape = utility_shape(state, baseline)

    out = Path(out_dir or ROOT / "outputs" / f"validation_{state}")
    out.mkdir(parents=True, exist_ok=True)
    methods["weights"].round(4).to_csv(out / "method_weights.csv")
    methods["summary"].to_csv(out / "method_comparison.csv", index=False)
    robust_table.round(4).to_csv(out / "smaa_robustness.csv")
    robust["rank_acceptability"].round(4).to_csv(out / "smaa_rank_acceptability.csv")
    effective.round(4).to_csv(out / "effective_weights.csv", index=False)
    response.to_csv(out / "customer_input_response.csv", index=False)
    shape.to_csv(out / "utility_shape_sensitivity.csv", index=False)
    summary = {
        "state": state,
        "baseline_first": names[baseline["ranking"]["fips"].iloc[0]],
        "smaa_settings": robust["settings"],
        "smaa_most_robust": names[robust["most_robust"]],
        "smaa_min_regret_q90": names[robust["min_regret_q90"]],
        "central_weights_of_winners": {names[k]: v for k, v in robust["central_weights"].items()},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return {
        "baseline": baseline,
        "methods": methods,
        "smaa": robust,
        "smaa_table": robust_table,
        "effective_weights": effective,
        "customer_response": response,
        "utility_shape": shape,
        "summary": summary,
        "out_dir": out,
    }


__all__ = ["adjustment_inputs", "compare_methods", "customer_response", "effective_weights", "run_validation", "smaa", "utility_shape"]
