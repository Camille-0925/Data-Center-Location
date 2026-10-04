"""CLI for the interaction analysis.

    python -m dc_locator.interactions dematel [--json]
"""

from __future__ import annotations

import argparse
import json

from . import load_config, run_dematel


def main() -> int:
    parser = argparse.ArgumentParser(description="Relationships between dimensions")
    sub = parser.add_subparsers(dest="command", required=True)
    dem = sub.add_parser("dematel", help="causal influence analysis from the team's 0-4 scores")
    dem.add_argument("--config", help="path to interactions.json (default: configs/interactions.json)")
    dem.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args()

    result = run_dematel(load_config(args.config))
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"DEMATEL ({', '.join(result['respondent_ids'])}); s = {result['normalizer_s']:.0f}, alpha = {result['threshold_alpha']:.4f}")
    print(f"{'dimension':22s} {'r (gives)':>9s} {'c (gets)':>9s} {'r+c':>7s} {'r-c':>7s}  role")
    for item in sorted(result["dimensions"], key=lambda x: -x["relation_r_minus_c"]):
        print(
            f"{item['dimension_id']:22s} {item['influence_given_r']:9.3f} {item['influence_received_c']:9.3f} "
            f"{item['prominence_r_plus_c']:7.3f} {item['relation_r_minus_c']:+7.3f}  {item['role']}"
        )
    print("\nlinks above alpha (impact-relation map):")
    for link in result["significant_links"]:
        print(f"  {link['from']:22s} -> {link['to']:22s} {link['total_influence']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
