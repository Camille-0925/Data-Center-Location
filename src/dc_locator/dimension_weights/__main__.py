"""CLI: print the dimension weights for one set of customer inputs.

    python -m dc_locator.dimension_weights --cooling_type evaporative --priority sustainability
"""

from __future__ import annotations

import argparse
import json

from . import compute_dimension_weights, load_config


def main() -> int:
    config = load_config()
    parser = argparse.ArgumentParser(description="Customer inputs -> dimension weights")
    parser.add_argument("--mode", choices=["within_state", "cross_state"], default="within_state")
    parser.add_argument("--config", help="path to a dimension_weights.json (default: configs/dimension_weights.json)")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    for field, spec in config["customer_inputs"].items():
        parser.add_argument(f"--{field}", choices=sorted(spec["options"]), help=f"{spec['label']} (default {spec['default']})")
    args = parser.parse_args()
    if args.config:
        config = load_config(args.config)
    inputs = {field: getattr(args, field) for field in config["customer_inputs"] if getattr(args, field, None)}
    result = compute_dimension_weights(inputs, args.mode, config)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"mode: {result['mode']}   inputs: {result['inputs']}")
    print(f"AHP: lambda_max = {result['ahp']['lambda_max']:.3f}, CR = {result['ahp']['consistency_ratio']:.3f}")
    print(f"{'dimension':22s} {'AHP base':>9s} {'reference':>10s} {'final':>8s} {'change':>8s}")
    for d in result["dimension_order"]:
        print(
            f"{d:22s} {result['ahp']['base_weights'][d]:9.3f} {result['reference_weights'][d]:10.3f} "
            f"{result['weights'][d]:8.3f} {result['change_from_reference'][d]:+8.3f}"
        )
    if result["capped_dimensions"]:
        print("capped at the maximum weight:", ", ".join(result["capped_dimensions"]))
    for warning in result["ahp"]["warnings"]:
        print("warning:", warning)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
