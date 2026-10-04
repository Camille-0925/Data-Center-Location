"""Decision matrix: gate evaluation, weighted suitability score, ranking, and run comparison.

Originally written by Adelyn for the v0.2 seven-dimension model with one metric per
dimension. v0.3 generalizes it so that the dimension list, the metrics in each
dimension, the dimension weights, the within-dimension (local) weights and the way
indicators combine into a dimension score (weighted mean, weighted geometric mean or
minimum) are all read from ``scoring_config`` instead of module constants. Gates are
optional (``constraint_rules.gates_enabled = false`` skips them).

The public functions consume and return JSON-serializable dictionaries. This module
does not collect data (data_prep), convert raw values to 0-100 utilities
(indicator_scoring), or derive weights from customer inputs (dimension_weights).
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import math
from typing import Any, Callable, Iterable, Mapping, Sequence


SCHEMA_VERSION = "v0.3"
MODEL_VERSION = "v0.3"

# Reference only: the v0.3 eight-dimension model. Validation uses scoring_config.
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
SCORE_TOLERANCE = 1e-7
AGGREGATION_METHODS = {"weighted_mean", "weighted_geometric", "min"}


class ContractError(ValueError):
    """Raised when an input violates the v0.3 interface contract."""


@dataclass(frozen=True)
class ModelSpec:
    """Dimension and metric structure declared by one scoring_config."""

    dimension_order: tuple[str, ...]
    metrics: tuple[str, ...]
    metric_to_dimension: Mapping[str, str]
    aggregation: Mapping[str, str]

    def metrics_in(self, dimension_id: str) -> list[str]:
        return [m for m in self.metrics if self.metric_to_dimension[m] == dimension_id]


def aggregate_dimension(method: str, scores_0_100: Sequence[float], local_weights: Sequence[float]) -> float:
    """Combine indicator utilities (0-100) into one dimension score (0-1).

    weighted_mean       D = sum(w * u) / 100
    weighted_geometric  D = prod((u / 100) ** w)      a low indicator cannot be fully offset
    min                 D = min(u) / 100 over indicators with w > 0   the worst indicator decides
    """

    pairs = list(zip(scores_0_100, local_weights))
    if method == "weighted_mean":
        return sum(w * u for u, w in pairs) / 100.0
    if method == "weighted_geometric":
        return math.prod((u / 100.0) ** w for u, w in pairs if w > 0)
    if method == "min":
        return min(u for u, w in pairs if w > 0) / 100.0
    raise ContractError(f"unknown aggregation method: {method}")


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


def _parse_date(value: Any, name: str) -> date:
    _require(isinstance(value, str) and bool(value), f"{name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{name} must be a valid YYYY-MM-DD date") from exc
    _require(parsed.isoformat() == value, f"{name} must be YYYY-MM-DD")
    return parsed


def _validate_scoring_config(
    scoring_config: Any, context: Mapping[str, Any]
) -> tuple[dict[str, Any], ModelSpec, list[str]]:
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

    indicators = config.get("indicators")
    _require(isinstance(indicators, list) and indicators, "scoring_config.indicators must be a non-empty array")
    metrics: list[str] = []
    metric_to_dimension: dict[str, str] = {}
    for indicator in indicators:
        item = _require_mapping(indicator, "scoring_config.indicators item")
        metric_id = item.get("metric_id")
        _require(isinstance(metric_id, str) and metric_id, "indicator metric_id is required")
        _require(metric_id not in metric_to_dimension, f"duplicate indicator: {metric_id}")
        _require(item.get("dimension_id") in order, f"unknown dimension for {metric_id}: {item.get('dimension_id')}")
        _require(item.get("direction") in {"low_better", "high_better"}, f"invalid direction for {metric_id}")
        for field in ["unit", "function_type", "anchor_rationale"]:
            _require(isinstance(item.get(field), str) and item[field], f"missing {field} for {metric_id}")
        for field in ["good_anchor", "bad_anchor"]:
            _require(_finite_number(item.get(field)), f"invalid {field} for {metric_id}")
        if item["direction"] == "low_better":
            _require(item["good_anchor"] < item["bad_anchor"], f"low_better anchors must satisfy good < bad for {metric_id}")
        else:
            _require(item["good_anchor"] > item["bad_anchor"], f"high_better anchors must satisfy good > bad for {metric_id}")
        _require(_finite_number(item.get("local_weight")) and item["local_weight"] >= 0, f"invalid local_weight for {metric_id}")
        metrics.append(metric_id)
        metric_to_dimension[metric_id] = item["dimension_id"]

    required = config.get("required_score_metrics", metrics)
    _require(required == metrics, "required_score_metrics must list the indicator metric_ids in the same order")

    declared = config.get("dimension_aggregation", {})
    _require(isinstance(declared, Mapping), "scoring_config.dimension_aggregation must be an object")
    _require(set(declared).issubset(order), "dimension_aggregation contains an unknown dimension id")
    aggregation = {dimension_id: declared.get(dimension_id, "weighted_mean") for dimension_id in order}
    for dimension_id, method in aggregation.items():
        _require(method in AGGREGATION_METHODS, f"invalid aggregation for {dimension_id}: {method}")
    spec = ModelSpec(tuple(order), tuple(metrics), metric_to_dimension, aggregation)
    for dimension_id in order:
        members = spec.metrics_in(dimension_id)
        _require(members, f"dimension {dimension_id} has no indicators")
        local_sum = sum(float(item["local_weight"]) for item in indicators if item["dimension_id"] == dimension_id)
        _require(abs(local_sum - 1.0) <= WEIGHT_TOLERANCE, f"local weights for {dimension_id} must sum to 1")

    if context["run_mode"] == "real" and config["status"] == "test_only":
        diagnostics.append("real runs cannot produce a complete recommendation with test_only scoring configuration")
    if config["status"] == "provisional":
        diagnostics.append("scoring anchors or preferences are provisional team assumptions")
    return config, spec, diagnostics


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


def _index_dimension_scores(dimension_scores: Any, spec: ModelSpec) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    order = list(spec.dimension_order)
    for record in _records(dimension_scores, "dimension_scores"):
        candidate_id = record.get("candidate_id")
        _require(isinstance(candidate_id, str) and candidate_id, "dimension score candidate_id is required")
        _require(candidate_id not in indexed, f"duplicate dimension score record for {candidate_id}")
        _require(record.get("dimension_order") == order, f"wrong dimension_order for {candidate_id}")
        scores = _require_mapping(record.get("scores"), f"dimension_scores[{candidate_id}].scores")
        _require(set(scores) == set(order), f"scores for {candidate_id} must contain exactly the configured dimensions")
        for dimension_id, value in scores.items():
            _require(value is None or (_finite_number(value) and 0 <= value <= 1), f"invalid {dimension_id} score for {candidate_id}")
        _require(record.get("score_status") in {"complete", "incomplete"}, f"invalid score_status for {candidate_id}")
        missing = record.get("missing_metric_ids")
        _require(isinstance(missing, list), f"missing_metric_ids must be an array for {candidate_id}")
        _require(set(missing).issubset(spec.metrics), f"unexpected missing metric id for {candidate_id}")
        if record["score_status"] == "complete":
            _require(not missing and all(value is not None for value in scores.values()), f"complete dimension score cannot contain missing values for {candidate_id}")
        indexed[candidate_id] = record
    _require(indexed, "dimension_scores.records must not be empty")
    return indexed


def _index_indicators(indicator_scores: Any, spec: ModelSpec) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for record in _records(indicator_scores, "indicator_scores"):
        candidate_id = record.get("candidate_id")
        metric_id = record.get("metric_id")
        _require(isinstance(candidate_id, str) and candidate_id, "indicator candidate_id is required")
        _require(metric_id in spec.metrics, f"unexpected indicator metric_id: {metric_id}")
        key = (candidate_id, metric_id)
        _require(key not in indexed, f"duplicate indicator score: {candidate_id}/{metric_id}")
        _require(record.get("score_status") in {"complete", "incomplete"}, f"invalid indicator score_status for {key}")
        _require(
            isinstance(record.get("scoring_config_version"), str)
            and bool(record["scoring_config_version"]),
            f"scoring_config_version is required for {key}",
        )
        _require(isinstance(record.get("unit"), str) and record["unit"], f"unit is required for {key}")
        value = record.get("score_0_100")
        _require(value is None or (_finite_number(value) and 0 <= value <= 100), f"invalid score_0_100 for {key}")
        if record["score_status"] == "complete":
            _require(value is not None, f"complete indicator must have score_0_100 for {key}")
        else:
            _require(value is None, f"incomplete indicator must have null score_0_100 for {key}")
        indexed[key] = record
    return indexed


def _index_metrics(metric_results: Any) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for record in _records(metric_results, "metric_results"):
        candidate_id = record.get("candidate_id")
        metric_id = record.get("metric_id")
        _require(isinstance(candidate_id, str) and candidate_id, "metric candidate_id is required")
        _require(isinstance(metric_id, str) and metric_id, "metric_id is required")
        key = (candidate_id, metric_id)
        _require(key not in indexed, f"duplicate metric result: {candidate_id}/{metric_id}")
        _require(record.get("data_status") in {"available", "missing"}, f"invalid data_status for {key}")
        _require(record.get("pedigree") in {"direct", "derived", "proxy", "assumed"}, f"invalid pedigree for {key}")
        for field in ["input_metric_ids", "source_ids", "assumptions"]:
            _require(isinstance(record.get(field), list), f"{field} must be an array for {key}")
        _require(isinstance(record.get("unit"), str) and record["unit"], f"unit is required for {key}")
        for field in ["reference_period", "geo_method"]:
            _require(record.get(field) is not None, f"{field} is required for {key}")
        value = record.get("value")
        _require(value is None or _finite_number(value), f"metric value must be a finite number or null for {key}")
        if record["data_status"] == "available":
            _require(value is not None, f"available metric must have a value for {key}")
        if record["data_status"] == "missing":
            _require(value is None, f"missing metric must have null value for {key}")
        indexed[key] = record
    return indexed


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


def _score_candidate(
    candidate_id: str,
    dimension_record: Mapping[str, Any],
    indicators: Mapping[tuple[str, str], Mapping[str, Any]],
    metrics: Mapping[tuple[str, str], Mapping[str, Any]],
    config: Mapping[str, Any],
    spec: ModelSpec,
    context: Mapping[str, Any],
) -> tuple[float | None, str, dict[str, list[dict[str, Any]]], list[str]]:
    missing = set(dimension_record["missing_metric_ids"])
    scores = dimension_record["scores"]
    for metric_id in spec.metrics:
        indicator = indicators.get((candidate_id, metric_id))
        if not indicator or indicator["score_status"] != "complete" or indicator["score_0_100"] is None:
            missing.add(metric_id)
        metric = metrics.get((candidate_id, metric_id))
        if not metric or metric["data_status"] != "available" or metric["value"] is None:
            missing.add(metric_id)
    for dimension_id, value in scores.items():
        if value is None:
            missing.update(spec.metrics_in(dimension_id))
    if context["run_mode"] == "real" and config["status"] == "test_only":
        return None, "incomplete", {"metrics": [], "dimensions": []}, sorted(missing)
    if missing:
        return None, "incomplete", {"metrics": [], "dimensions": []}, sorted(missing)

    by_metric = {item["metric_id"]: item for item in config["indicators"]}
    metric_contributions: list[dict[str, Any]] = []
    dimension_contributions: list[dict[str, Any]] = []
    total = 0.0
    for dimension_id in spec.dimension_order:
        method = spec.aggregation[dimension_id]
        members = spec.metrics_in(dimension_id)
        utilities = [float(indicators[(candidate_id, m)]["score_0_100"]) for m in members]
        local_weights = [float(by_metric[m]["local_weight"]) for m in members]
        expected = aggregate_dimension(method, utilities, local_weights)
        supplied = float(scores[dimension_id])
        _require(
            abs(expected - supplied) <= SCORE_TOLERANCE,
            f"dimension score for {candidate_id}/{dimension_id} is {supplied}, "
            f"but {method} of its indicator scores gives {expected}",
        )
        dimension_weight = float(config["dimension_weights"][dimension_id])
        dimension_points = 100.0 * dimension_weight * supplied
        total += dimension_points
        dimension_contributions.append(
            {
                "dimension_id": dimension_id,
                "aggregation": method,
                "dimension_weight": dimension_weight,
                "dimension_score_0_1": supplied,
                "contribution_points": dimension_points,
            }
        )
        additive = method == "weighted_mean"
        for metric_id, utility, local_weight in zip(members, utilities, local_weights):
            metric_contributions.append(
                {
                    "metric_id": metric_id,
                    "dimension_id": dimension_id,
                    "local_weight": local_weight,
                    "global_leaf_weight": dimension_weight * local_weight if additive else None,
                    "indicator_score_0_100": utility,
                    "contribution_points": dimension_weight * local_weight * utility if additive else None,
                }
            )
    return total, "complete", {"metrics": metric_contributions, "dimensions": dimension_contributions}, []


def _pareto_statuses(
    candidate_ids: Iterable[str],
    metric_index: Mapping[tuple[str, str], Mapping[str, Any]],
    config: Mapping[str, Any],
    spec: ModelSpec,
) -> dict[str, str]:
    ids = sorted(candidate_ids)
    directions = {item["metric_id"]: item["direction"] for item in config["indicators"]}
    vectors: dict[str, dict[str, float]] = {}
    for candidate_id in ids:
        values: dict[str, float] = {}
        complete = True
        for metric_id in spec.metrics:
            record = metric_index.get((candidate_id, metric_id))
            if not record or record["data_status"] != "available" or record["value"] is None:
                complete = False
                break
            values[metric_id] = float(record["value"])
        if complete:
            vectors[candidate_id] = values

    result = {candidate_id: "not_evaluated" for candidate_id in ids}
    for candidate_id, values in vectors.items():
        dominated = False
        for other_id, other in vectors.items():
            if other_id == candidate_id:
                continue
            no_worse = True
            strictly_better = False
            for metric_id in spec.metrics:
                if directions[metric_id] == "high_better":
                    if other[metric_id] + RANK_TOLERANCE < values[metric_id]:
                        no_worse = False
                        break
                    strictly_better |= other[metric_id] > values[metric_id] + RANK_TOLERANCE
                else:
                    if other[metric_id] > values[metric_id] + RANK_TOLERANCE:
                        no_worse = False
                        break
                    strictly_better |= other[metric_id] + RANK_TOLERANCE < values[metric_id]
            if no_worse and strictly_better:
                dominated = True
                break
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


def _tradeoffs(
    recommendations: list[dict[str, Any]],
    metric_index: Mapping[tuple[str, str], Mapping[str, Any]],
    spec: ModelSpec,
) -> None:
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
            differences: list[dict[str, Any]] = []
            for metric_id in spec.metrics:
                current = metric_index.get((item["candidate_id"], metric_id))
                other = metric_index.get((comparison["candidate_id"], metric_id))
                if not current or not other or current["value"] is None or other["value"] is None:
                    continue
                if current.get("unit") != other.get("unit"):
                    continue
                differences.append(
                    {
                        "comparison_candidate_id": comparison["candidate_id"],
                        "metric_id": metric_id,
                        "difference_current_minus_comparison": float(current["value"]) - float(other["value"]),
                        "unit": current.get("unit"),
                    }
                )
            item["tradeoffs"] = differences


def _constant_dimension_diagnostics(
    dimensions: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
    spec: ModelSpec,
) -> list[str]:
    """Flag weighted dimensions whose score is identical for every candidate."""

    messages: list[str] = []
    if len(dimensions) < 2:
        return messages
    for dimension_id in spec.dimension_order:
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
    metric_results: Mapping[str, Any],
    indicator_scores: Mapping[str, Any],
    dimension_scores: Mapping[str, Any],
    scoring_config: Mapping[str, Any],
    project_profile: Mapping[str, Any] | None,
    constraint_rules: Mapping[str, Any] | None,
    evidence_records: Mapping[str, Any] | None,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate optional gates and produce grouped, ranked recommendations."""

    context_value = _validate_context(context)
    rules = _validate_constraint_rules(constraint_rules)
    gates_enabled = rules["gates_enabled"]
    envelopes = [
        ("metric_results", metric_results),
        ("indicator_scores", indicator_scores),
        ("dimension_scores", dimension_scores),
    ]
    if gates_enabled:
        envelopes.append(("evidence_records", evidence_records))
    for name, envelope in envelopes:
        _validate_envelope_context(envelope, name, context_value)
    config, spec, diagnostics = _validate_scoring_config(scoring_config, context_value)
    if gates_enabled:
        profile, required_capacity = _validate_profile(project_profile, context_value)
        evidence, evidence_diagnostics = _evidence_records(evidence_records, context_value)
        diagnostics.extend(evidence_diagnostics)
    else:
        profile, required_capacity, evidence = None, None, []
        diagnostics.append("gates are disabled for this run; candidates are ranked as conditional without feasibility screening")
    dimensions = _index_dimension_scores(dimension_scores, spec)
    indicators = _index_indicators(indicator_scores, spec)
    metrics = _index_metrics(metric_results)

    config_indicators = {item["metric_id"]: item for item in config["indicators"]}
    dimension_candidates = set(dimensions)
    indicator_candidates = {candidate_id for candidate_id, _ in indicators}
    _require(indicator_candidates == dimension_candidates, "indicator_scores and dimension_scores candidate sets must match")
    for candidate_id in sorted(dimension_candidates):
        for metric_id in spec.metrics:
            metric_key = (candidate_id, metric_id)
            _require(metric_key in metrics, f"metric_results must retain a row for missing metric {candidate_id}/{metric_id}")
            _require(metric_key in indicators, f"indicator_scores must retain a row for {candidate_id}/{metric_id}")
            metric = metrics[metric_key]
            indicator = indicators[metric_key]
            expected_unit = config_indicators[metric_id]["unit"]
            _require(metric["unit"] == expected_unit, f"metric unit does not match scoring_config for {candidate_id}/{metric_id}")
            _require(indicator["unit"] == expected_unit, f"indicator unit does not match scoring_config for {candidate_id}/{metric_id}")
            _require(
                indicator["scoring_config_version"] == context_value["scoring_config_version"],
                f"indicator scoring_config_version mismatch for {candidate_id}/{metric_id}",
            )
            raw_value = indicator.get("raw_value")
            metric_value = metric.get("value")
            _require(
                raw_value is None or _finite_number(raw_value),
                f"indicator raw_value must be a finite number or null for {candidate_id}/{metric_id}",
            )
            if metric_value is None:
                _require(raw_value is None, f"missing metric must have null indicator raw_value for {candidate_id}/{metric_id}")
            else:
                _require(
                    raw_value is not None and abs(float(raw_value) - float(metric_value)) <= RANK_TOLERANCE,
                    f"indicator raw_value does not match metric result for {candidate_id}/{metric_id}",
                )
    diagnostics.extend(_constant_dimension_diagnostics(dimensions, config, spec))

    gate_records: list[dict[str, Any]] = []
    candidate_gates: dict[str, list[dict[str, Any]]] = {}
    for candidate_id in sorted(dimensions):
        if not gates_enabled:
            candidate_gates[candidate_id] = []
            continue
        scope, plan, scope_error = _select_scope_and_plan(candidate_id, evidence, rules)
        power, delivery = _power_gates(
            candidate_id,
            evidence,
            scope,
            plan,
            scope_error,
            required_capacity,
            profile["target_online_date"],
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

    pareto = _pareto_statuses(dimensions, metrics, config, spec)
    recommendations: list[dict[str, Any]] = []
    for candidate_id in sorted(dimensions):
        gates = candidate_gates[candidate_id]
        overall_gate = _aggregate_gate_status(gates)
        score, score_status, contributions, missing = _score_candidate(
            candidate_id, dimensions[candidate_id], indicators, metrics, config, spec, context_value
        )
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
        limitations = [
            f"{len(spec.metrics)} proxy metrics across {len(spec.dimension_order)} dimensions provide regional screening, not construction approval",
            "safety-margin and temporal-robustness multipliers are not enabled",
        ]
        limitations.insert(
            1,
            "eligibility gates depend on evidence scope and verification status"
            if gates_enabled
            else "feasibility gates were not evaluated in this run",
        )
        recommendations.append(
            {
                "candidate_id": candidate_id,
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
                "dimension_scores": dict(dimensions[candidate_id]["scores"]),
                "dimension_contributions": contributions["dimensions"],
                "metric_contributions": contributions["metrics"],
                "tradeoffs": [],
                "critical_unknown": unknowns,
                "next_check": next_check,
                "change_conditions": change_conditions,
                "limitations": limitations,
                "missing_metric_ids": missing,
            }
        )

    _assign_ranks(recommendations)
    _tradeoffs(recommendations, metrics, spec)
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
        (
            item.get("next_check")
            for item in current_recs
            if item.get("next_check") is not None
        ),
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
    project_profile: Mapping[str, Any] | None,
    candidates: Mapping[str, Any] | None,
    feature_inputs: Mapping[str, Any] | None,
    scenario_config: Mapping[str, Any],
    scoring_config: Mapping[str, Any],
    constraint_rules: Mapping[str, Any] | None,
    evidence_records: Mapping[str, Any] | None,
    context: Mapping[str, Any],
    metric_results: Mapping[str, Any] | None = None,
    indicator_scores: Mapping[str, Any] | None = None,
    dimension_scores: Mapping[str, Any] | None = None,
    compute_results_fn: Callable[..., Mapping[str, Any]] | None = None,
    score_metrics_fn: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Integration entry point for data_prep -> indicator_scoring -> decision.

    Callers may supply precomputed result envelopes, or provide the two upstream
    callables. No silent fallback to baseline or fabricated stub data occurs.
    """

    context_value = _validate_context(context)
    scenario = _require_mapping(scenario_config, "scenario_config")
    _require(scenario.get("scenario_id") == "baseline", "only baseline scenario_config is supported")
    _require(context_value["scenario_id"] == scenario["scenario_id"], "scenario_config does not match context")

    if metric_results is None:
        _require(compute_results_fn is not None, "metric_results or compute_results_fn is required")
        _require(candidates is not None, "candidates is required by compute_results_fn")
        _require(feature_inputs is not None, "feature_inputs is required by compute_results_fn")
        data_output = compute_results_fn(project_profile, candidates, feature_inputs, scenario_config, context_value)
        data_mapping = _require_mapping(data_output, "compute_results_fn output")
        metric_results = data_mapping.get("metric_results", data_output)

    if indicator_scores is None or dimension_scores is None:
        _require(score_metrics_fn is not None, "indicator_scores/dimension_scores or score_metrics_fn is required")
        scoring_output = score_metrics_fn(metric_results, scoring_config, context_value)
        scoring_mapping = _require_mapping(scoring_output, "score_metrics_fn output")
        indicator_scores = scoring_mapping.get("indicator_scores")
        dimension_scores = scoring_mapping.get("dimension_scores")
        _require(indicator_scores is not None and dimension_scores is not None, "score_metrics_fn must return indicator_scores and dimension_scores")

    return recommend(
        metric_results,
        indicator_scores,
        dimension_scores,
        scoring_config,
        project_profile,
        constraint_rules,
        evidence_records,
        context_value,
    )
