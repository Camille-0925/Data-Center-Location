"""Synthetic eight-dimension request builder shared by the decision tests and fixture script."""

from __future__ import annotations

from copy import deepcopy

from dc_locator.decision import aggregate_dimension

# dimension_id -> [(metric_id, unit, direction)]
MODEL_8D = {
    "climate_risk": [
        ("wildfire_bp_national_pct", "fraction", "low_better"),
        ("inland_flood_eal_national_pct", "fraction", "low_better"),
    ],
    "water": [
        ("baseline_water_stress", "aqueduct_index_0_5", "low_better"),
        ("future_water_stress_2050", "aqueduct_index_0_5", "low_better"),
    ],
    "land_ecology": [
        ("low_impervious_share", "fraction", "high_better"),
        ("protected_gap12_share", "fraction", "low_better"),
        ("wetland_share", "fraction", "low_better"),
    ],
    "fiber_connectivity": [
        ("commercial_fiber_100_20_share", "fraction", "high_better"),
        ("commercial_fiber_1000_100_share", "fraction", "high_better"),
    ],
    "workforce_community": [
        ("labor_force", "persons", "high_better"),
        ("svi_national_pct", "fraction", "low_better"),
    ],
    "cooling_climate": [
        ("cdd65", "degF_day_per_year", "low_better"),
        ("hot_days_over_90f", "days_per_year", "low_better"),
    ],
    "transportation": [
        ("interstate_distance_km", "km", "low_better"),
        ("rail_distance_km", "km", "low_better"),
    ],
    "energy_carbon": [
        ("industrial_electricity_price", "USD_per_MWh", "low_better"),
        ("saidi_no_major_events", "minutes_per_customer_year", "low_better"),
        ("grid_co2e_intensity", "kgCO2e_per_MWh", "low_better"),
    ],
}
DIMENSIONS = list(MODEL_8D)
METRICS = [metric for items in MODEL_8D.values() for metric, _, _ in items]


def build_request(
    candidate_ids=("51107",),
    run_mode="test",
    config_status="ready",
    gates_enabled=True,
    indicator_score=40.0,
):
    """Every indicator scores ``indicator_score`` so any valid weighting totals that value."""

    context = {
        "schema_version": "v0.3",
        "model_version": "v0.3",
        "run_id": "run_test_001",
        "run_mode": run_mode,
        "profile_id": "reference_v03",
        "scenario_id": "baseline",
        "preference_profile_id": "eight_equal_test",
        "evidence_version": "1",
        "scoring_config_version": "test_v03",
    }
    indicators = []
    for dimension_id, items in MODEL_8D.items():
        for metric_id, unit, direction in items:
            indicators.append(
                {
                    "metric_id": metric_id,
                    "dimension_id": dimension_id,
                    "unit": unit,
                    "direction": direction,
                    "good_anchor": 0 if direction == "low_better" else 1,
                    "bad_anchor": 1 if direction == "low_better" else 0,
                    "function_type": "linear_clipped",
                    "local_weight": 1 / len(items),
                    "anchor_rationale": "test fixture",
                }
            )
    scoring_config = {
        "version": "test_v03",
        "status": config_status,
        "preference_profile_id": "eight_equal_test",
        "dimension_order": list(DIMENSIONS),
        "required_score_metrics": list(METRICS),
        "dimension_weights": {dimension_id: 1 / len(DIMENSIONS) for dimension_id in DIMENSIONS},
        "indicators": indicators,
    }
    metric_records, indicator_records, dimension_records = [], [], []
    for candidate_id in candidate_ids:
        for index, item in enumerate(indicators):
            metric_records.append(
                {
                    "candidate_id": candidate_id,
                    "metric_id": item["metric_id"],
                    "value": float(index + 1),
                    "unit": item["unit"],
                    "data_status": "available",
                    "pedigree": "proxy",
                    "input_metric_ids": [],
                    "source_ids": ["fixture"],
                    "reference_period": "test",
                    "geo_method": "fixture",
                    "assumptions": ["synthetic test data"],
                    "missing_reason": None,
                }
            )
            indicator_records.append(
                {
                    "candidate_id": candidate_id,
                    "metric_id": item["metric_id"],
                    "raw_value": float(index + 1),
                    "unit": item["unit"],
                    "score_0_100": indicator_score,
                    "score_status": "complete",
                    "scoring_config_version": "test_v03",
                    "explanation": "fixture",
                }
            )
        dimension_records.append(
            {
                "candidate_id": candidate_id,
                "scores": {dimension_id: indicator_score / 100 for dimension_id in DIMENSIONS},
                "dimension_order": list(DIMENSIONS),
                "score_status": "complete",
                "missing_metric_ids": [],
            }
        )
    request = {
        "context": context,
        "project_profile": {
            "schema_version": "v0.3",
            "model_version": "v0.3",
            "profile_id": "reference_v03",
            "it_capacity_mw": 100,
            "utilization": 0.8,
            "operating_hours_per_year": 8760,
            "pue_annual": 1.25,
            "pue_design": 1.25,
            "reserve_margin": 0.2,
            "wue_l_per_kwh_it": 0.5,
            "cooling_config_id": "illustrative_reference",
            "target_online_date": "2030-12-31",
        },
        "scoring_config": scoring_config,
        "constraint_rules": {
            "gates_enabled": gates_enabled,
            "gates": [
                {"gate_id": gate_id}
                for gate_id in ["power_capacity", "delivery_date", "land_ecology", "network", "water_permission"]
            ],
            "assessment_scope_by_candidate": {},
            "supply_plan_by_candidate": {},
        },
        "metric_results": {"context": deepcopy(context), "records": metric_records},
        "indicator_scores": {"context": deepcopy(context), "records": indicator_records},
        "dimension_scores": {"context": deepcopy(context), "records": dimension_records},
        "evidence_records": {"context": deepcopy(context), "records": []},
    }
    return request


def set_indicator_score(request, candidate_id, metric_id, score):
    """Change one indicator score and recompute that candidate's dimension score with the configured aggregation."""

    config = {item["metric_id"]: item for item in request["scoring_config"]["indicators"]}
    for record in request["indicator_scores"]["records"]:
        if record["candidate_id"] == candidate_id and record["metric_id"] == metric_id:
            record["score_0_100"] = score
    dimension_id = config[metric_id]["dimension_id"]
    members = [m for m, item in config.items() if item["dimension_id"] == dimension_id]
    by_key = {
        r["metric_id"]: r["score_0_100"]
        for r in request["indicator_scores"]["records"]
        if r["candidate_id"] == candidate_id
    }
    method = request["scoring_config"].get("dimension_aggregation", {}).get(dimension_id, "weighted_mean")
    value = aggregate_dimension(method, [by_key[m] for m in members], [config[m]["local_weight"] for m in members])
    for record in request["dimension_scores"]["records"]:
        if record["candidate_id"] == candidate_id:
            record["scores"][dimension_id] = value


def add_passing_evidence(request, candidate_id="51107", capacity=150, delivery="2030-12-31", reviewed=True, is_demo=False):
    verification = "reviewed" if reviewed else "reported"
    common = {
        "candidate_id": candidate_id,
        "profile_id": "reference_v03",
        "assessment_scope_id": f"scope_{candidate_id}",
        "asserted_status": "pass",
        "source": "fixture",
        "as_of": "2026-10-03",
        "verification_status": verification,
        "is_demo": is_demo,
        "notes": "synthetic test evidence",
    }
    request["evidence_records"]["records"].append(
        {
            **common,
            "evidence_id": f"power_{candidate_id}",
            "supply_plan_id": f"plan_{candidate_id}",
            "gate_ids": ["power_capacity", "delivery_date"],
            "attributes": {
                "available_capacity_mw": capacity,
                "capacity_as_of_date": "2026-10-03",
                "required_capacity_delivery_date": delivery,
            },
        }
    )
    for gate_id in ["land_ecology", "network", "water_permission"]:
        request["evidence_records"]["records"].append(
            {
                **common,
                "evidence_id": f"{gate_id}_{candidate_id}",
                "gate_ids": [gate_id],
                "attributes": {"review_complete": True},
            }
        )
