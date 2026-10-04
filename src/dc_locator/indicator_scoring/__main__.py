"""python -m dc_locator.indicator_scoring [--state VA|GA] [--out file.csv]

Scores every county: utilities (0-100), 8 dimension scores (0-1) and context flags.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dc_locator.data_prep import load_processed

from . import load_config, score_counties, zero_utility_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Raw indicators -> utilities -> dimension scores")
    parser.add_argument("--state", choices=["VA", "GA"], help="limit to one state (default: both)")
    parser.add_argument("--out", help="write the scored table to this CSV")
    args = parser.parse_args()

    config = load_config()
    table = load_processed()
    if args.state:
        table = table[table["state"] == args.state].reset_index(drop=True)
    scored = score_counties(table, config)
    dims = list(config["dimensions"])
    print(f"{len(scored)} counties scored; dimension score summary (0-1):")
    print(scored.groupby("state")[dims].agg(["min", "median", "max"]).T.round(3).to_string())
    report = zero_utility_report(scored, config)
    zeros = report[report["zero"] > 0]
    if len(zeros):
        print("\nindicators with utility 0 (value at or beyond the unacceptable anchor):")
        print(zeros.to_string(index=False))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        scored.to_csv(args.out, index=False)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
