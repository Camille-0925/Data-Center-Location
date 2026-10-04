"""python -m dc_locator.validation --state VA [--samples 10000] [--seed 42]"""

from __future__ import annotations

import argparse

import pandas as pd

from . import run_validation


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-validation and SMAA robustness of the county ranking")
    parser.add_argument("--state", choices=["VA", "GA"], required=True)
    parser.add_argument("--samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = run_validation(args.state, args.samples, args.seed)
    pd.set_option("display.width", 160)
    print(f"== {args.state}: baseline #1 = {result['summary']['baseline_first']}")
    print("\n1. Weight methods (weighted sum) vs final AHP + Choquet ranking")
    print(result["methods"]["summary"].round(3).to_string(index=False))
    print("\n   weights by method")
    print(result["methods"]["weights"].round(3).to_string())
    print(f"\n2. SMAA-2 ({args.samples} samples; weights ~ Dirichlet(20 phi), kappa ~ U(0,1), lambda_R and lambda_M ~ U(0.1,0.3)): top 10 by p(top 10)")
    print(result["smaa_table"].head(10).round(3).to_string())
    print("\n3. Effective weights (share of score variance)")
    print(result["effective_weights"].round(3).to_string(index=False))
    print("\n4. Customer-input response")
    print(result["customer_response"].round(3).to_string(index=False))
    print("\n5. Value-function shape")
    print(result["utility_shape"].round(3).to_string(index=False))
    print(f"\nsaved to {result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
