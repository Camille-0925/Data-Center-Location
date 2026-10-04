"""Decision matrix: weighted suitability score, ranking, Pareto status, and run comparison.

Input is an n x K matrix of dimension scores (n counties, K dimensions, each score 0-1,
higher is better) plus K dimension weights that sum to 1:

    Score_i = 100 * sum_k w_k * D_ik

Everything below the dimension level (raw indicators, utility functions, how indicators
combine into a dimension score) belongs to ``dc_locator.indicator_scoring``. The weights
come from ``dc_locator.dimension_weights``.

Originally written by Adelyn (v0.2: seven dimensions, one indicator each, gates
required). v0.4 takes dimension scores only, reads the dimension list from the
configuration, and makes the feasibility gates optional.

All public functions consume and return JSON-serializable dictionaries.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import math
from typing import Any, Callable, Mapping, Sequence


SCHEMA_VERSION = "v0.4"
MODEL_VERSION = "v0.4"

# Reference only: the eight-dimension model. Validation uses scoring_config.dimension_order.
DEFAULT_DIMENSION_ORDER = [
    "climate_risk",
    "water",
    "land_ecology",
    "fiber_connectivity",
    "workforce_community",
    "cooling_climate",
    "transportation",
    "energy_carbon",
]

GATE_ORDER = [
    "power_capacity",
    "delivery_date",
    "land_ecology",
    "network",
    "water_permission",
]

NEXT_CHECK_ORDER = [
    "power_capacity",
    "delivery_date",
    "water_permission",
    "land_ecology",
    "network",
]

VALID_RUN_MODES = {"real", "demo", "test"}
VALID_CONFIG_STATUSES = {"test_only", "provisional", "ready"}
VALID_GATE_STATUSES = {"pass", "fail", "unknown"}
VALID_VERIFICATION_STATUSES = {"reported", "reviewed"}
RANK_TOLERANCE = 1e-8
WEIGHT_TOLERANCE = 1e-9


class ContractError(ValueError):
    """Raised when an input violates the interface contract."""


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{name} must be a JSON object")
    return value


def _records(value: Any, name: str) -> list[dict[str, Any]]:
    envelope = _require_mapping(value, name)
    records = envelope.get("records")
    _require(isinstance(records, list), f"{name}.records must be an array")
    _require(
        all(isinstance(record, Mapping) for record in records),
        f"every {name}.records item must be an object",
    )
    return [dict(record) for record in records]


def _validate_envelope_context(value: Any, name: str, expected: Mapping[str, Any]) -> None:
    envelope = _require_mapping(value, name)
    actual = _validate_context(envelope.get("context"))
    _require(actual == dict(expected), f"{name}.context must exactly match the run context")


def _validate_context(context: Any) -> dict[str, Any]:
    result = dict(_require_mapping(context, "context"))
    required = [
        "schema_version",
        "model_version",
        "run_id",
        "run_mode",
        "profile_id",
        "scenario_id",
        "preference_profile_id",
        "evidence_version",
        "scoring_config_version",
    ]
    missing = [field for field in required if field not in result]
    _require(not missing, f"context is missing fields: {', '.join(missing)}")
    _require(result["schema_version"] == SCHEMA_VERSION, f"schema_version must be {SCHEMA_VERSION}")
    _require(result["model_version"] == MODEL_VERSION, f"model_version must be {MODEL_VERSION}")
    _require(result["run_mode"] in VALID_RUN_MODES, "run_mode must be real, demo, or test")
    _require(result["scenario_id"] == "baseline", "only scenario_id=baseline is supported")
    for field in required:
        _require(
            isinstance(result[field], str) and bool(result[field]),
            f"context.{field} must be a non-empty string",
        )
    return result


def _parse_date(value: Any, name: str) -> date:
    _require(isinstance(value, str) and bool(value), f"{name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{name} must be a valid YYYY-MM-DD date") from exc
    _require(parsed.isoformat() == value, f"{name} must be YYYY-MM-DD")
    return parsed


def _validate_scoring_config(scoring_config: Any, context: Mapping[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    """Return (config, dimension_order, diagnostics)."""

    config = dict(_require_mapping(scoring_config, "scoring_config"))
    diagnostics: list[str] = []
    _require(config.get("version") == context["scoring_config_version"], "scoring_config.version does not match context")
    _require(config.get("status") in VALID_CONFIG_STATUSES, "invalid scoring_config.status")
    _require(
        config.get("preference_profile_id") == context["preference_profile_id"],
        "scoring_config.preference_profile_id does not match context",
    )
    order = config.get("dimension_order")
    _require(
        isinstance(order, list) and order and all(isinstance(d, str) and d for d in order),
        "scoring_config.dimension_order must be a non-empty array of dimension ids",
    )
    _require(len(set(order)) == len(order), "scoring_config.dimension_order contains duplicates")

    weights = _require_mapping(config.get("dimension_weights"), "scoring_config.dimension_weights")
    _require(set(weights) == set(order), "dimension_weights must contain exactly the dimension ids in dimension_order")
    for dimension_id, weight in weights.items():
        _require(_finite_number(weight) and weight >= 0, f"invalid weight for {dimension_id}")
    _require(abs(sum(float(weights[d]) for d in order) - 1.0) <= WEIGHT_TOLERANCE, "dimension weights must sum to 1")

    if context["run_mode"] == "real" and config["status"] == "test_only":
        diagnostics.append("real runs cannot produce a complete recommendation with test_only scoring configuration")
    if config["status"] == "provisional":
        diagnostics.append("weights or scoring anchors are provisional team assumptions")
    return config, list(order), diagnostics


def _index_dimension_scores(dimension_scores: Any, order: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Validate the n x K matrix: one record per candidate, one score (0-1 or null) per dimension."""

    indexed: dict[str, dict[str, Any]] = {}
    for record in _records(dimension_scores, "dimension_scores"):
        candidate_id = record.get("candidate_id")
        _require(isinstance(candidate_id, str) and candidate_id, "dimension score candidate_id is required")
        _require(candidate_id not in indexed, f"duplicate dimension score record for {candidate_id}")
        scores = _require_mapping(record.get("scores"), f"dimension_scores[{candidate_id}].scores")
        _require(set(scores) == set(order), f"scores for {candidate_id} must contain exactly the configured dimensions")
        for dimension_id, value in scores.items():
            _require(
                value is None or (_finite_number(value) and 0 <= value <= 1),
                f"{dimension_id} score for {candidate_id} must be between 0 and 1, or null",
            )
        indexed[candidate_id] = record
    _require(indexed, "dimension_scores.records must not be empty")
    return indexed


# ---------------------------------------------------------------------------
# Optional feasibility gates (Adelyn's v0.2 logic, unchanged when enabled)
# ---------------------------------------------------------------------------


def _unwrap_profile(project_profile: Any) -> dict[str, Any]:
    profile = dict(_require_mapping(project_profile, "project_profile"))
    if "profile" in profile:
        profile = dict(_require_mapping(profile["profile"], "project_profile.profile"))
    return profile


def _validate_profile(project_profile: Any, context: Mapping[str, Any]) -> tuple[dict[str, Any], float]:
    profile = _unwrap_profile(project_profile)
    _require(profile.get("schema_version") == SCHEMA_VERSION, f"project profile schema_version must be {SCHEMA_VERSION}")
    _require(profile.get("model_version") == MODEL_VERSION, f"project profile model_version must be {MODEL_VERSION}")
    _require(profile.get("profile_id") == context["profile_id"], "project profile_id does not match context")
    required = [
        "it_capacity_mw",
        "utilization",
        "operating_hours_per_year",
        "pue_annual",
        "pue_design",
        "reserve_margin",
        "wue_l_per_kwh_it",
        "cooling_config_id",
        "target_online_date",
    ]
    missing = [field for field in required if field not in profile]
    _require(not missing, f"project_profile is missing fields: {', '.join(missing)}")
    for field in [
        "it_capacity_mw",
        "utilization",
        "operating_hours_per_year",
        "pue_annual",
        "pue_design",
        "reserve_margin",
        "wue_l_per_kwh_it",
    ]:
        _require(_finite_number(profile[field]), f"project_profile.{field} must be a finite number")
    _require(profile["it_capacity_mw"] >= 0, "it_capacity_mw must be nonnegative")
    _require(0 <= profile["utilization"] <= 1, "utilization must be between 0 and 1")
    _require(profile["operating_hours_per_year"] > 0, "operating_hours_per_year must be positive")
    _require(profile["pue_annual"] > 0, "pue_annual must be positive")
    _require(profile["pue_design"] > 0, "pue_design must be positive")
    _require(profile["reserve_margin"] >= 0, "reserve_margin must be nonnegative")
    _require(profile["wue_l_per_kwh_it"] >= 0, "wue_l_per_kwh_it must be nonnegative")
    _require(isinstance(profile["cooling_config_id"], str) and profile["cooling_config_id"], "cooling_config_id must be a non-empty string")
    _parse_date(profile["target_online_date"], "project_profile.target_online_date")
    required_capacity = (
        float(profile["it_capacity_mw"])
        * float(profile["pue_design"])
        * (1.0 + float(profile["reserve_margin"]))
    )
    return profile, required_capacity


def _validate_constraint_rules(constraint_rules: Any) -> dict[str, Any]:
    if constraint_rules is None:
        return {"gates_enabled": False}
    rules = dict(_require_mapping(constraint_rules, "constraint_rules"))
    enabled = rules.get("gates_enabled", True)
    _require(isinstance(enabled, bool), "constraint_rules.gates_enabled must be boolean")
    rules["gates_enabled"] = enabled
    if not enabled:
        return rules
    gate_items = rules.get("gates", rules.get("records"))
    _require(isinstance(gate_items, list), "constraint_rules.gates must be an array")
    gate_ids = [item.get("gate_id") for item in gate_items if isinstance(item, Mapping)]
    _require(gate_ids == GATE_ORDER, "constraint_rules must define the five gate ids in fixed order")
    scope_map = rules.get("assessment_scope_by_candidate", {})
    plan_map = rules.get("supply_plan_by_candidate", {})
    _require(isinstance(scope_map, Mapping), "assessment_scope_by_candidate must be an object")
    _require(isinstance(plan_map, Mapping), "supply_plan_by_candidate must be an object")
    return rules


def _evidence_records(evidence_records: Any, context: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    diagnostics: list[str] = []
    valid: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in _records(evidence_records, "evidence_records"):
        evidence_id = record.get("evidence_id")
        _require(isinstance(evidence_id, str) and evidence_id, "evidence_id is required")
        _require(evidence_id not in seen, f"duplicate evidence_id: {evidence_id}")
        seen.add(evidence_id)
        _require(isinstance(record.get("candidate_id"), str) and record["candidate_id"], f"candidate_id required for {evidence_id}")
        _require(isinstance(record.get("assessment_scope_id"), str) and record["assessment_scope_id"], f"assessment_scope_id required for {evidence_id}")
        _require(isinstance(record.get("gate_ids"), list), f"gate_ids must be an array for {evidence_id}")
        _require(set(record["gate_ids"]).issubset(GATE_ORDER), f"unknown gate_id in {evidence_id}")
        _require(record.get("asserted_status") in VALID_GATE_STATUSES, f"invalid asserted_status for {evidence_id}")
        _require(record.get("verification_status") in VALID_VERIFICATION_STATUSES, f"invalid verification_status for {evidence_id}")
        _require(isinstance(record.get("is_demo"), bool), f"is_demo must be boolean for {evidence_id}")
        _parse_date(record.get("as_of"), f"{evidence_id}.as_of")
        _require(record.get("source") is not None, f"source is required for {evidence_id}")
        if {"power_capacity", "delivery_date"}.intersection(record["gate_ids"]):
            _require(isinstance(record.get("supply_plan_id"), str) and record["supply_plan_id"], f"supply_plan_id required for power evidence {evidence_id}")
            attributes = _require_mapping(record.get("attributes"), f"{evidence_id}.attributes")
            for field in ["available_capacity_mw", "capacity_as_of_date", "required_capacity_delivery_date"]:
                _require(field in attributes, f"{field} required for power evidence {evidence_id}")
            _require(
                attributes["available_capacity_mw"] is None
                or (_finite_number(attributes["available_capacity_mw"]) and attributes["available_capacity_mw"] >= 0),
                f"invalid available_capacity_mw for {evidence_id}",
            )
            if attributes["capacity_as_of_date"] is not None:
                _parse_date(attributes["capacity_as_of_date"], f"{evidence_id}.capacity_as_of_date")
            if attributes["required_capacity_delivery_date"] is not None:
                _parse_date(attributes["required_capacity_delivery_date"], f"{evidence_id}.required_capacity_delivery_date")
        if record.get("profile_id") != context["profile_id"]:
            diagnostics.append(f"ignored {evidence_id}: profile_id does not match the run")
            continue
        if context["run_mode"] == "real" and record["is_demo"]:
            diagnostics.append(f"ignored {evidence_id}: demo evidence is forbidden in a real run")
            continue
        valid.append(record)
    return valid, diagnostics


def _select_scope_and_plan(
    candidate_id: str,
    evidence: Sequence[dict[str, Any]],
    rules: Mapping[str, Any],
) -> tuple[str | None, str | None, str | None]:
    candidate_evidence = [item for item in evidence if item["candidate_id"] == candidate_id]
    requested_scope = rules.get("assessment_scope_by_candidate", {}).get(candidate_id)
    scopes = sorted({item["assessment_scope_id"] for item in candidate_evidence})
    if requested_scope:
        scope = requested_scope
    elif len(scopes) == 1:
        scope = scopes[0]
    elif len(scopes) > 1:
        return None, None, "multiple assessment scopes exist; select one explicitly"
    else:
        return None, None, None

    scope_evidence = [item for item in candidate_evidence if item["assessment_scope_id"] == scope]
    power_evidence = [
        item
        for item in scope_evidence
        if {"power_capacity", "delivery_date"}.intersection(item["gate_ids"])
    ]
    requested_plan = rules.get("supply_plan_by_candidate", {}).get(candidate_id)
    plans = sorted({item.get("supply_plan_id") for item in power_evidence if item.get("supply_plan_id")})
    if requested_plan:
        plan = requested_plan
    elif len(plans) == 1:
        plan = plans[0]
    elif len(plans) > 1:
        return scope, None, "multiple supply plans exist; select one explicitly"
    else:
        plan = None
    return scope, plan, None


def _verification(records: Sequence[Mapping[str, Any]]) -> str:
    return "reviewed" if records and all(item["verification_status"] == "reviewed" for item in records) else "reported"


def _gate_record(
    candidate_id: str,
    gate_id: str,
    status: str,
    evidence: Sequence[Mapping[str, Any]],
    scope: str | None,
    observed_value: Any,
    required_value: Any,
    unit: str | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "gate_id": gate_id,
        "status": status,
        "verification_status": _verification(evidence),
        "evidence_ids": [item["evidence_id"] for item in evidence],
        "assessment_scope_id": scope,
        "observed_value": observed_value,
        "required_value": required_value,
        "unit": unit,
        "reason": reason,
        "is_demo": any(item["is_demo"] for item in evidence),
    }


def _manual_gate(
    candidate_id: str,
    gate_id: str,
    evidence: Sequence[dict[str, Any]],
    scope: str | None,
    scope_error: str | None,
) -> dict[str, Any]:
    if scope_error:
        return _gate_record(candidate_id, gate_id, "unknown", [], None, None, None, None, scope_error)
    matching = [
        item
        for item in evidence
        if item["candidate_id"] == candidate_id
        and item["assessment_scope_id"] == scope
        and gate_id in item["gate_ids"]
    ]
    if not matching:
        return _gate_record(candidate_id, gate_id, "unknown", [], scope, None, None, None, "no applicable evidence")
    statuses = {item["asserted_status"] for item in matching}
    conclusive = statuses.intersection({"pass", "fail"})
    if len(conclusive) > 1:
        return _gate_record(candidate_id, gate_id, "unknown", matching, scope, None, None, None, "conflicting evidence is unresolved")
    status = next(iter(conclusive)) if len(conclusive) == 1 else "unknown"
    reason = (
        f"applicable evidence asserts {status}"
        if status != "unknown"
        else "applicable evidence does not establish pass or fail"
    )
    return _gate_record(candidate_id, gate_id, status, matching, scope, status, "documented evidence", None, reason)


def _numeric_consensus(records: Sequence[Mapping[str, Any]], field: str) -> tuple[float | None, bool]:
    values = [float(item["attributes"][field]) for item in records if _finite_number(item.get("attributes", {}).get(field))]
    if not values:
        return None, False
    first = values[0]
    return first, any(abs(value - first) > RANK_TOLERANCE for value in values[1:])


def _power_gates(
    candidate_id: str,
    evidence: Sequence[dict[str, Any]],
    scope: str | None,
    plan: str | None,
    scope_error: str | None,
    required_capacity: float,
    target_online_date: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if scope_error:
        unknown_capacity = _gate_record(candidate_id, "power_capacity", "unknown", [], scope, None, required_capacity, "MW", scope_error)
        unknown_date = _gate_record(candidate_id, "delivery_date", "unknown", [], scope, None, target_online_date, "date", scope_error)
        return unknown_capacity, unknown_date

    relevant = [
        item
        for item in evidence
        if item["candidate_id"] == candidate_id
        and item["assessment_scope_id"] == scope
        and {"power_capacity", "delivery_date"}.intersection(item["gate_ids"])
        and (plan is None or item.get("supply_plan_id") == plan)
    ]
    if relevant and plan is None and any(item.get("supply_plan_id") for item in relevant):
        relevant = []
    if not relevant:
        return (
            _gate_record(candidate_id, "power_capacity", "unknown", [], scope, None, required_capacity, "MW", "no applicable same-plan capacity evidence"),
            _gate_record(candidate_id, "delivery_date", "unknown", [], scope, None, target_online_date, "date", "no applicable same-plan delivery evidence"),
        )

    capacity, capacity_conflict = _numeric_consensus(relevant, "available_capacity_mw")
    if capacity_conflict:
        capacity_gate = _gate_record(candidate_id, "power_capacity", "unknown", relevant, scope, None, required_capacity, "MW", "conflicting capacity evidence is unresolved")
    elif capacity is None:
        capacity_gate = _gate_record(candidate_id, "power_capacity", "unknown", relevant, scope, None, required_capacity, "MW", "available_capacity_mw is missing")
    else:
        status = "pass" if capacity + RANK_TOLERANCE >= required_capacity else "fail"
        reason = f"available capacity {'meets' if status == 'pass' else 'is below'} required capacity"
        capacity_gate = _gate_record(candidate_id, "power_capacity", status, relevant, scope, capacity, required_capacity, "MW", reason)

    full_capacity_records = [
        item
        for item in relevant
        if _finite_number(item.get("attributes", {}).get("available_capacity_mw"))
        and float(item["attributes"]["available_capacity_mw"]) + RANK_TOLERANCE >= required_capacity
        and item.get("attributes", {}).get("required_capacity_delivery_date") is not None
    ]
    dates: list[str] = []
    for item in full_capacity_records:
        value = item["attributes"]["required_capacity_delivery_date"]
        _parse_date(value, f"{item['evidence_id']}.attributes.required_capacity_delivery_date")
        dates.append(value)
    if not dates:
        delivery_gate = _gate_record(
            candidate_id,
            "delivery_date",
            "unknown",
            relevant,
            scope,
            None,
            target_online_date,
            "date",
            "no date evidence showing when the full required capacity is deliverable",
        )
    elif len(set(dates)) > 1:
        delivery_gate = _gate_record(candidate_id, "delivery_date", "unknown", full_capacity_records, scope, None, target_online_date, "date", "conflicting full-capacity delivery dates are unresolved")
    else:
        delivery = dates[0]
        status = "pass" if _parse_date(delivery, "delivery date") <= _parse_date(target_online_date, "target_online_date") else "fail"
        reason = f"full required capacity delivery date {'meets' if status == 'pass' else 'misses'} target date"
        delivery_gate = _gate_record(candidate_id, "delivery_date", status, full_capacity_records, scope, delivery, target_online_date, "date", reason)
    return capacity_gate, delivery_gate


def _aggregate_gate_status(gates: Sequence[Mapping[str, Any]]) -> str:
    if not gates:
        return "not_evaluated"
    statuses = {item["status"] for item in gates}
    if "fail" in statuses:
        return "fail"
    if statuses == {"pass"}:
        return "pass"
    return "unknown"


# ---------------------------------------------------------------------------
# Scoring, ranking, Pareto, trade-offs
# ---------------------------------------------------------------------------


def _score_candidate(
    scores: Mapping[str, Any],
    config: Mapping[str, Any],
    order: Sequence[str],
    context: Mapping[str, Any],
) -> tuple[float | None, str, list[dict[str, Any]], list[str]]:
    """Return (score_0_100, score_status, dimension_contributions, missing_dimension_ids)."""

    missing = [dimension_id for dimension_id in order if scores[dimension_id] is None]
    if missing or (context["run_mode"] == "real" and config["status"] == "test_only"):
        return None, "incomplete", [], missing
    contributions: list[dict[str, Any]] = []
    total = 0.0
    for dimension_id in order:
        weight = float(config["dimension_weights"][dimension_id])
        value = float(scores[dimension_id])
        points = 100.0 * weight * value
        total += points
        contributions.append(
            {
                "dimension_id": dimension_id,
                "dimension_weight": weight,
                "dimension_score_0_1": value,
                "contribution_points": points,
            }
        )
    return total, "complete", contributions, []


def _pareto_statuses(dimensions: Mapping[str, Mapping[str, Any]], order: Sequence[str]) -> dict[str, str]:
    """Non-dominated = no other candidate is at least as good on every dimension and better on one."""

    vectors = {
        candidate_id: [float(record["scores"][d]) for d in order]
        for candidate_id, record in dimensions.items()
        if all(record["scores"][d] is not None for d in order)
    }
    result = {candidate_id: "not_evaluated" for candidate_id in sorted(dimensions)}
    for candidate_id, values in vectors.items():
        dominated = any(
            other_id != candidate_id
            and all(o + RANK_TOLERANCE >= v for o, v in zip(other, values))
            and any(o > v + RANK_TOLERANCE for o, v in zip(other, values))
            for other_id, other in vectors.items()
        )
        result[candidate_id] = "dominated" if dominated else "non_dominated"
    return result


def _assign_ranks(recommendations: list[dict[str, Any]]) -> None:
    for pool in ["verified_feasible", "conditional"]:
        eligible = [
            item
            for item in recommendations
            if item["ranking_pool"] == pool and item["score_0_100"] is not None
        ]
        eligible.sort(key=lambda item: (-item["score_0_100"], item["candidate_id"]))
        previous_score: float | None = None
        previous_rank: int | None = None
        for position, item in enumerate(eligible, start=1):
            if previous_score is not None and abs(item["score_0_100"] - previous_score) <= RANK_TOLERANCE:
                item["rank"] = previous_rank
            else:
                item["rank"] = position
                previous_rank = position
            previous_score = item["score_0_100"]


def _tradeoffs(recommendations: list[dict[str, Any]], order: Sequence[str]) -> None:
    """Dimension-score differences from the top-ranked candidate (or from #2, for the leader)."""

    pools: dict[str, list[dict[str, Any]]] = {}
    for item in recommendations:
        if item["rank"] is not None:
            pools.setdefault(item["ranking_pool"], []).append(item)
    for members in pools.values():
        ordered = sorted(members, key=lambda item: (item["rank"], item["candidate_id"]))
        if len(ordered) < 2:
            continue
        leader = ordered[0]
        for item in ordered:
            comparison = ordered[1] if item is leader else leader
            differences = []
            for dimension_id in order:
                gap = float(item["dimension_scores"][dimension_id]) - float(comparison["dimension_scores"][dimension_id])
                differences.append(
                    {
                        "comparison_candidate_id": comparison["candidate_id"],
                        "dimension_id": dimension_id,
                        "score_difference_current_minus_comparison": gap,
                        "points_difference": 100.0 * float(item["dimension_weights_used"][dimension_id]) * gap,
                    }
                )
            item["tradeoffs"] = differences


def _constant_dimension_diagnostics(
    dimensions: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
    order: Sequence[str],
) -> list[str]:
    """Flag weighted dimensions whose score is identical for every candidate."""

    messages: list[str] = []
    if len(dimensions) < 2:
        return messages
    for dimension_id in order:
        values = [record["scores"][dimension_id] for record in dimensions.values()]
        if any(value is None for value in values):
            continue
        if max(values) - min(values) <= RANK_TOLERANCE and float(config["dimension_weights"][dimension_id]) > 0:
            messages.append(
                f"dimension {dimension_id} has the same score for every candidate; "
                "its weight shifts all totals equally and cannot change the ranking"
            )
    return messages


def recommend(
    dimension_scores: Mapping[str, Any],
    scoring_config: Mapping[str, Any],
    context: Mapping[str, Any],
    project_profile: Mapping[str, Any] | None = None,
    constraint_rules: Mapping[str, Any] | None = None,
    evidence_records: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Score, rank and (optionally) gate candidates from an n x K dimension-score matrix."""

    context_value = _validate_context(context)
    rules = _validate_constraint_rules(constraint_rules)
    gates_enabled = rules["gates_enabled"]
    _validate_envelope_context(dimension_scores, "dimension_scores", context_value)
    config, order, diagnostics = _validate_scoring_config(scoring_config, context_value)
    dimensions = _index_dimension_scores(dimension_scores, order)

    if gates_enabled:
        _validate_envelope_context(evidence_records, "evidence_records", context_value)
        profile, required_capacity = _validate_profile(project_profile, context_value)
        evidence, evidence_diagnostics = _evidence_records(evidence_records, context_value)
        diagnostics.extend(evidence_diagnostics)
    else:
        profile, required_capacity, evidence = None, None, []
        diagnostics.append("gates are disabled for this run; candidates are ranked as conditional without feasibility screening")
    diagnostics.extend(_constant_dimension_diagnostics(dimensions, config, order))

    gate_records: list[dict[str, Any]] = []
    candidate_gates: dict[str, list[dict[str, Any]]] = {}
    for candidate_id in sorted(dimensions):
        if not gates_enabled:
            candidate_gates[candidate_id] = []
            continue
        scope, plan, scope_error = _select_scope_and_plan(candidate_id, evidence, rules)
        power, delivery = _power_gates(
            candidate_id, evidence, scope, plan, scope_error, required_capacity, profile["target_online_date"]
        )
        gates = [
            power,
            delivery,
            _manual_gate(candidate_id, "land_ecology", evidence, scope, scope_error),
            _manual_gate(candidate_id, "network", evidence, scope, scope_error),
            _manual_gate(candidate_id, "water_permission", evidence, scope, scope_error),
        ]
        candidate_gates[candidate_id] = gates
        gate_records.extend(gates)

    pareto = _pareto_statuses(dimensions, order)
    weights_used = {d: float(config["dimension_weights"][d]) for d in order}
    recommendations: list[dict[str, Any]] = []
    for candidate_id in sorted(dimensions):
        record = dimensions[candidate_id]
        gates = candidate_gates[candidate_id]
        overall_gate = _aggregate_gate_status(gates)
        score, score_status, contributions, missing = _score_candidate(record["scores"], config, order, context_value)
        if overall_gate == "fail":
            eligibility = "excluded"
        elif score_status != "complete":
            eligibility = "incomplete"
        elif (
            overall_gate == "pass"
            and all(gate["verification_status"] == "reviewed" for gate in gates)
            and not any(gate["is_demo"] for gate in gates)
            and context_value["run_mode"] != "demo"
        ):
            eligibility = "verified_feasible"
        else:
            eligibility = "conditional"

        unknowns = [gate["gate_id"] for gate in gates if gate["status"] == "unknown"]
        failed = [gate["gate_id"] for gate in gates if gate["status"] == "fail"]
        next_gate = next((gate_id for gate_id in NEXT_CHECK_ORDER if gate_id in unknowns), None)
        if next_gate is None:
            next_gate = next((gate_id for gate_id in NEXT_CHECK_ORDER if gate_id in failed), None)
        next_check = (
            {
                "gate_id": next_gate,
                "reason": "heuristic priority order: capacity, delivery, water, land, network; not optimized information value",
            }
            if next_gate
            else None
        )
        change_conditions = (
            [
                {
                    "field": "available_capacity_mw",
                    "operator": ">=",
                    "value": required_capacity,
                    "unit": "MW",
                    "scope": "same assessment_scope_id and supply_plan_id",
                },
                {
                    "field": "required_capacity_delivery_date",
                    "operator": "<=",
                    "value": profile["target_online_date"],
                    "unit": "date",
                    "scope": "date at which full required capacity is deliverable",
                },
            ]
            if gates_enabled
            else []
        )
        recommendations.append(
            {
                "candidate_id": candidate_id,
                "candidate_name": record.get("candidate_name"),
                "eligibility_status": eligibility,
                "gate_status": overall_gate,
                "gate_reasons": [
                    {"gate_id": gate["gate_id"], "status": gate["status"], "reason": gate["reason"]}
                    for gate in gates
                ],
                "score_0_100": score,
                "score_status": score_status,
                "scoring_config_status": config["status"],
                "rank": None,
                "ranking_pool": eligibility,
                "pareto_status": pareto[candidate_id],
                "dimension_scores": dict(record["scores"]),
                "dimension_weights_used": dict(weights_used),
                "dimension_contributions": contributions,
                "tradeoffs": [],
                "missing_dimension_ids": missing,
                "critical_unknown": unknowns,
                "next_check": next_check,
                "change_conditions": change_conditions,
                "limitations": [
                    f"weighted sum of {len(order)} dimension scores; regional screening, not construction approval",
                    "eligibility gates depend on evidence scope and verification status"
                    if gates_enabled
                    else "feasibility gates were not evaluated in this run",
                ],
            }
        )

    _assign_ranks(recommendations)
    _tradeoffs(recommendations, order)
    output_context = deepcopy(context_value)
    return {
        "gate_results": {"context": output_context, "records": gate_records},
        "recommendations": {"context": deepcopy(output_context), "records": recommendations},
        "diagnostics": diagnostics,
    }


def _recommendation_records(outputs: Mapping[str, Any], name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = _require_mapping(outputs, name)
    recommendations = _require_mapping(root.get("recommendations"), f"{name}.recommendations")
    context = _validate_context(recommendations.get("context"))
    return context, _records(recommendations, f"{name}.recommendations")


def compare_runs(previous_outputs: Mapping[str, Any], current_outputs: Mapping[str, Any]) -> dict[str, Any]:
    """Compare two recommend() outputs and return a change report."""

    previous_context, previous_recs = _recommendation_records(previous_outputs, "previous_outputs")
    current_context, current_recs = _recommendation_records(current_outputs, "current_outputs")
    _require(previous_context["run_id"] != current_context["run_id"], "previous and current run_id must differ")

    context_fields = [
        "profile_id",
        "scenario_id",
        "preference_profile_id",
        "evidence_version",
        "scoring_config_version",
    ]
    changed_inputs = [
        {"field": field, "previous": previous_context[field], "current": current_context[field]}
        for field in context_fields
        if previous_context[field] != current_context[field]
    ]

    def gate_map(outputs: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
        root = _require_mapping(outputs, "outputs")
        gates = _records(root.get("gate_results"), "outputs.gate_results")
        return {(item["candidate_id"], item["gate_id"]): item for item in gates}

    previous_gates = gate_map(previous_outputs)
    current_gates = gate_map(current_outputs)
    changed_gates: list[dict[str, Any]] = []
    for key in sorted(set(previous_gates) | set(current_gates)):
        before = previous_gates.get(key)
        after = current_gates.get(key)
        fields = ["status", "verification_status", "observed_value", "required_value", "evidence_ids"]
        if before is None or after is None or any(before.get(field) != after.get(field) for field in fields):
            changed_gates.append(
                {
                    "candidate_id": key[0],
                    "gate_id": key[1],
                    "previous": {field: before.get(field) for field in fields} if before else None,
                    "current": {field: after.get(field) for field in fields} if after else None,
                }
            )

    previous_by_id = {item["candidate_id"]: item for item in previous_recs}
    current_by_id = {item["candidate_id"]: item for item in current_recs}
    changed_recommendations: list[dict[str, Any]] = []
    rec_fields = [
        "eligibility_status",
        "score_0_100",
        "score_status",
        "rank",
        "ranking_pool",
        "pareto_status",
    ]
    for candidate_id in sorted(set(previous_by_id) | set(current_by_id)):
        before = previous_by_id.get(candidate_id)
        after = current_by_id.get(candidate_id)
        changes = {
            field: {
                "previous": before.get(field) if before else None,
                "current": after.get(field) if after else None,
            }
            for field in rec_fields
            if before is None or after is None or before.get(field) != after.get(field)
        }
        if changes:
            changed_recommendations.append({"candidate_id": candidate_id, "changes": changes})

    if changed_recommendations:
        explanation = "Recommendation eligibility, score, pool, Pareto status, or rank changed; see changed_recommendations."
    elif changed_gates:
        explanation = "Gate evidence changed but did not change the recommendation fields."
    elif changed_inputs:
        explanation = "Run metadata changed but calculated gates and recommendations did not."
    else:
        explanation = "No material input, gate, or recommendation change was detected."

    next_check = next(
        (item.get("next_check") for item in current_recs if item.get("next_check") is not None),
        None,
    )
    report = {
        "previous_run_id": previous_context["run_id"],
        "current_run_id": current_context["run_id"],
        "changed_inputs": changed_inputs,
        "changed_gates": changed_gates,
        "changed_recommendations": changed_recommendations,
        "explanation": explanation,
        "next_check": next_check,
    }
    return {"context": deepcopy(current_context), "records": [report]}


def run_decision(
    *,
    scoring_config: Mapping[str, Any],
    context: Mapping[str, Any],
    dimension_scores: Mapping[str, Any] | None = None,
    compute_dimension_scores_fn: Callable[..., Mapping[str, Any]] | None = None,
    project_profile: Mapping[str, Any] | None = None,
    constraint_rules: Mapping[str, Any] | None = None,
    evidence_records: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Integration entry point: precomputed dimension scores, or a callable that returns them."""

    context_value = _validate_context(context)
    if dimension_scores is None:
        _require(compute_dimension_scores_fn is not None, "dimension_scores or compute_dimension_scores_fn is required")
        dimension_scores = compute_dimension_scores_fn(context_value)
    return recommend(
        dimension_scores,
        scoring_config,
        context_value,
        project_profile=project_profile,
        constraint_rules=constraint_rules,
        evidence_records=evidence_records,
    )
