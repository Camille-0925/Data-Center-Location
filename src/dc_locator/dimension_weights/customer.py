"""Customer inputs -> dimension weights.

    w_k = w0_k * M_k / sum_l (w0_l * M_l)

w0 are the AHP base weights and M_k is the product of the multipliers that the customer's
choices assign to dimension k. Multiplying weights is the same as multiplying every AHP
ratio w_k / w_l by M_k / M_l, so the adjusted weights stay on the AHP ratio scale.

After the adjustment the mode is applied (``within_state`` sets the dimensions listed in
``within_state_excluded`` to 0 because their data are identical for every county in a
state) and no dimension may exceed ``max_dimension_weight``; any excess is redistributed
in proportion to the remaining weights.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

MODES = ("within_state", "cross_state")


def resolve_inputs(spec: Mapping[str, Any], inputs: Mapping[str, Any] | None) -> dict[str, str]:
    """Fill defaults and reject unknown fields or options."""

    inputs = dict(inputs or {})
    unknown = set(inputs) - set(spec)
    if unknown:
        raise ValueError(f"unknown customer input(s): {', '.join(sorted(unknown))}")
    resolved = {}
    for field, field_spec in spec.items():
        choice = inputs.get(field, field_spec["default"])
        if choice not in field_spec["options"]:
            raise ValueError(f"{field} must be one of {sorted(field_spec['options'])}, got {choice!r}")
        resolved[field] = choice
    return resolved


def multipliers(spec: Mapping[str, Any], resolved: Mapping[str, str], order: Sequence[str]) -> tuple[dict[str, float], list[dict]]:
    """Product of multipliers per dimension, plus a trace of every non-neutral multiplier."""

    product = {d: 1.0 for d in order}
    trace = []
    for field, choice in resolved.items():
        for dimension_id, factor in spec[field]["options"][choice].items():
            if dimension_id not in product:
                raise ValueError(f"{field}={choice} refers to unknown dimension {dimension_id}")
            if factor <= 0:
                raise ValueError(f"multiplier for {field}={choice} on {dimension_id} must be positive")
            product[dimension_id] *= float(factor)
            trace.append({"input": field, "choice": choice, "dimension_id": dimension_id, "multiplier": float(factor)})
    return product, trace


def normalize(weights: Mapping[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights must have a positive sum")
    return {d: w / total for d, w in weights.items()}


def apply_cap(weights: Mapping[str, float], cap: float) -> tuple[dict[str, float], list[str]]:
    """Cap every weight at ``cap`` and give the excess to the uncapped positive weights pro rata."""

    weights = dict(weights)
    positive = [d for d, w in weights.items() if w > 0]
    if cap * len(positive) < 1 - 1e-12:
        raise ValueError(f"cap {cap} is infeasible for {len(positive)} positive weights")
    capped: list[str] = []
    while True:
        over = [d for d in positive if d not in capped and weights[d] > cap + 1e-12]
        if not over:
            return weights, capped
        capped.extend(over)
        for d in over:
            weights[d] = cap
        free = [d for d in positive if d not in capped]
        room = 1.0 - cap * len(capped)
        free_total = sum(weights[d] for d in free)
        for d in free:
            weights[d] = weights[d] / free_total * room


def adjust(
    base: Mapping[str, float],
    spec: Mapping[str, Any],
    inputs: Mapping[str, Any] | None,
    mode: str,
    excluded_within_state: Sequence[str],
    cap: float,
) -> dict[str, Any]:
    """Apply customer multipliers, the mode and the cap; return weights and an explanation."""

    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    order = list(base)
    resolved = resolve_inputs(spec, inputs)
    product, trace = multipliers(spec, resolved, order)
    adjusted = normalize({d: base[d] * product[d] for d in order})
    if mode == "within_state":
        adjusted = normalize({d: (0.0 if d in excluded_within_state else w) for d, w in adjusted.items()})
    reference = dict(base)
    if mode == "within_state":
        reference = normalize({d: (0.0 if d in excluded_within_state else w) for d, w in base.items()})
    final, capped = apply_cap(adjusted, cap)
    return {
        "mode": mode,
        "inputs": resolved,
        "weights": final,
        "reference_weights": reference,
        "change_from_reference": {d: final[d] - reference[d] for d in order},
        "multipliers": product,
        "multiplier_trace": trace,
        "capped_dimensions": capped,
    }
