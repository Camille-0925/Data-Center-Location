"""Synthetic n x 8 dimension-score requests shared by the decision tests and the fixture script."""

from __future__ import annotations

from copy import deepcopy

from dc_locator.decision import DEFAULT_DIMENSION_ORDER

DIMENSIONS = list(DEFAULT_DIMENSION_ORDER)


def build_request(
    candidate_ids=("51107",),
    run_mode="test",
    config_status="ready",
    gates_enabled=True,
    default_score=0.40,
):
    """Every dimension of every candidate scores ``default_score`` so any weighting totals 100x that."""

    context = {
        "schema_version": "v0.4",
        "model_version": "v0.4",
        "run_id": "run_test_001",
        "run_mode": run_mode,
        "profile_id": "reference_v04",
        "scenario_id": "baseline",
        "preference_profile_id": "eight_equal_test",
        "evidence_version": "1",
        "scoring_config_version": "test_v04",
    }
    scoring_config = {
        "version": "test_v04",
        "status": config_status,
        "preference_profile_id": "eight_equal_test",
        "dimension_order": list(DIMENSIONS),
        "dimension_weights": {dimension_id: 1 / len(DIMENSIONS) for dimension_id in DIMENSIONS},
    }
    records = [
        {
            "candidate_id": candidate_id,
            "candidate_name": f"County {candidate_id}",
            "scores": {dimension_id: default_score for dimension_id in DIMENSIONS},
        }
        for candidate_id in candidate_ids
    ]
    return {
        "context": context,
        "scoring_config": scoring_config,
        "dimension_scores": {"context": deepcopy(context), "records": records},
        "project_profile": {
            "schema_version": "v0.4",
            "model_version": "v0.4",
            "profile_id": "reference_v04",
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
        "constraint_rules": {
            "gates_enabled": gates_enabled,
            "gates": [
                {"gate_id": gate_id}
                for gate_id in ["power_capacity", "delivery_date", "land_ecology", "network", "water_permission"]
            ],
            "assessment_scope_by_candidate": {},
            "supply_plan_by_candidate": {},
        },
        "evidence_records": {"context": deepcopy(context), "records": []},
    }


def set_score(request, candidate_id, dimension_id, value):
    for record in request["dimension_scores"]["records"]:
        if record["candidate_id"] == candidate_id:
            record["scores"][dimension_id] = value


def set_weights(request, **weights):
    """Override some dimension weights; the rest share what is left equally."""

    others = [d for d in DIMENSIONS if d not in weights]
    remaining = 1.0 - sum(weights.values())
    request["scoring_config"]["dimension_weights"] = {
        **weights,
        **{d: remaining / len(others) for d in others},
    }


def add_passing_evidence(request, candidate_id="51107", capacity=150, delivery="2030-12-31", reviewed=True, is_demo=False):
    verification = "reviewed" if reviewed else "reported"
    common = {
        "candidate_id": candidate_id,
        "profile_id": "reference_v04",
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
