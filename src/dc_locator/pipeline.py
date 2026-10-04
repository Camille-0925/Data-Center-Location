"""End-to-end run: data -> dimension scores -> weights -> interactions -> Choquet ranking.

    python -m dc_locator.pipeline --state VA --cooling_type evaporative --priority sustainability

Writes outputs/<run_id>/ with the ranking table, the decision output, the weights and the
interaction matrix used, so every number in the report can be traced to one run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .data_prep import load_processed
from .decision import recommend
from .dimension_weights import compute_dimension_weights, load_config as load_weights_config
from .indicator_scoring import (
    apply_final_score_adjustments,
    apply_pre_weight_adjustments,
    dimension_score_records,
    load_adjustments_config,
    load_config as load_scoring_config,
    score_counties,
)
from .interactions import interaction_matrix, load_config as load_interactions_config

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "v0.4"


def run(
    state: str,
    customer_inputs: Mapping[str, Any] | None = None,
    scoring_model: str = "choquet",
    kappa: float | None = None,
    scored: pd.DataFrame | None = None,
    apply_adjustments: bool = True,
    adjustments_config: Mapping[str, Any] | None = None,
    robustness_factors: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Rank every county of one state for one customer. Returns all intermediate results."""

    if scoring_model not in {"choquet", "weighted_sum"}:
        raise ValueError("scoring_model must be choquet or weighted_sum")
    scoring_config = load_scoring_config()
    if scored is None:
        scored = score_counties(load_processed(), scoring_config)
    adjustment_config = None
    if apply_adjustments:
        adjustment_config = dict(adjustments_config or load_adjustments_config())
        scored = apply_pre_weight_adjustments(
            scored,
            scoring_config,
            adjustment_config,
            robustness_factors=robustness_factors,
        )
    counties = scored[scored["state"] == state].reset_index(drop=True)
    if counties.empty:
        raise ValueError(f"no counties for state {state}")

    weights = compute_dimension_weights(customer_inputs, mode="within_state", config=load_weights_config())
    order = weights["dimension_order"]
    interactions = None
    if scoring_model == "choquet":
        interactions = interaction_matrix(counties, weights["weights"], load_interactions_config(), kappa=kappa)

    run_id = f"{state}_{scoring_model}_" + "_".join(f"{v}" for v in weights["inputs"].values())
    context = {
        "schema_version": SCHEMA,
        "model_version": SCHEMA,
        "run_id": run_id,
        "run_mode": "real",
        "profile_id": "county_screening",
        "scenario_id": "baseline",
        "preference_profile_id": "_".join(weights["inputs"].values()),
        "evidence_version": "none",
        "scoring_config_version": weights["config_version"],
    }
    scoring_config_for_matrix = {
        "version": weights["config_version"],
        "status": "provisional",
        "preference_profile_id": context["preference_profile_id"],
        "dimension_order": order,
        "dimension_weights": weights["weights"],
        "interactions": interactions["interactions"] if interactions else [],
    }
    decision = recommend(
        {"context": dict(context), "records": dimension_score_records(counties, order)},
        scoring_config_for_matrix,
        context,
    )
    if apply_adjustments:
        decision = apply_final_score_adjustments(decision, counties, order)
    return {
        "run_id": run_id,
        "state": state,
        "scoring_model": scoring_model,
        "weights": weights,
        "interactions": interactions,
        "indicator_scoring_config": scoring_config,
        "adjustments_config": adjustment_config,
        "decision": decision,
        "counties": counties,
        "ranking": ranking_table(decision, counties, order),
    }


def ranking_table(decision: Mapping[str, Any], counties: pd.DataFrame, order) -> pd.DataFrame:
    rows = []
    flags = counties.set_index("fips")
    for item in decision["recommendations"]["records"]:
        f = flags.loc[item["candidate_id"]]
        rows.append(
            {
                "rank": item["rank"],
                "fips": item["candidate_id"],
                "county": item["candidate_name"],
                "score": item["score_0_100"],
                "suitability_before_margin": item.get("suitability_before_margin_0_100", item["score_0_100"]),
                "margin_adjustment": item.get("margin_adjustment", 1.0),
                "margin_limiting_indicator": item.get("margin_limiting_indicator"),
                "normalization_gate_status": item.get("normalization_gate_status", "not_applied"),
                "pareto": item["pareto_status"],
                **{f"D_{d}": item["dimension_scores"][d] for d in order},
                **{f"D_base_{d}": f.get(f"base__{d}", item["dimension_scores"][d]) for d in order},
                **{f"A_R_{d}": f.get(f"robustness_factor__{d}", 1.0) for d in order},
                "interaction_points": sum(c["contribution_points"] for c in item["interaction_contributions"]),
                "water_stress_change_2050": f["water_stress_change_2050_band"],
                "social_vulnerability": f["social_vulnerability_band"],
                "extreme_heat_days": f["extreme_heat_days_band"],
            }
        )
    return pd.DataFrame(rows).sort_values(["rank", "fips"]).reset_index(drop=True)


def save(result: Mapping[str, Any], out_dir: str | Path | None = None) -> Path:
    out = Path(out_dir or ROOT / "outputs" / result["run_id"])
    out.mkdir(parents=True, exist_ok=True)
    result["ranking"].to_csv(out / "ranking.csv", index=False)
    result["counties"].to_csv(out / "scored_counties_audit.csv", index=False)
    (out / "decision_output.json").write_text(json.dumps(result["decision"], indent=2))
    (out / "weights.json").write_text(json.dumps(result["weights"], indent=2))
    (out / "indicator_scoring.json").write_text(json.dumps(result["indicator_scoring_config"], indent=2))
    if result.get("adjustments_config"):
        (out / "score_adjustments.json").write_text(json.dumps(result["adjustments_config"], indent=2))
    if result["interactions"]:
        (out / "interactions.json").write_text(json.dumps(result["interactions"], indent=2))
    return out


def main() -> int:
    weights_config = load_weights_config()
    parser = argparse.ArgumentParser(description="Rank all counties of one state for one customer")
    parser.add_argument("--state", choices=["VA", "GA"], required=True)
    parser.add_argument("--model", choices=["choquet", "weighted_sum"], default="choquet")
    parser.add_argument("--kappa", type=float, help="interaction intensity 0-1 (default from configs/interactions.json)")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--out", help="output folder (default outputs/<run_id>)")
    parser.add_argument("--no-adjustments", action="store_true", help="disable margin and temporal robustness (diagnostic only)")
    for field, spec in weights_config["customer_inputs"].items():
        parser.add_argument(f"--{field}", choices=sorted(spec["options"]), help=f"default {spec['default']}")
    args = parser.parse_args()
    inputs = {f: getattr(args, f) for f in weights_config["customer_inputs"] if getattr(args, f)}
    result = run(args.state, inputs, args.model, args.kappa, apply_adjustments=not args.no_adjustments)
    path = save(result, args.out)
    w = result["weights"]["weights"]
    print(f"run {result['run_id']}  ({len(result['ranking'])} counties)")
    print("weights: " + ", ".join(f"{d} {v:.3f}" for d, v in w.items() if v > 0))
    if result["interactions"]:
        kept = [p for p in result["interactions"]["pairs"] if p["status"] == "kept"]
        print("interactions: " + ", ".join(f"{p['dimensions'][0]}-{p['dimensions'][1]} {p['interaction_index']:+.3f}" for p in kept))
    cols = ["rank", "county", "score", "pareto", "interaction_points"]
    print(result["ranking"][cols].head(args.top).round(2).to_string(index=False))
    print(f"\nsaved to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
