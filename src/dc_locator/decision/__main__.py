"""Command-line interface for the decision matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .matrix import ContractError, compare_runs, recommend


def _load(path: str) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _dump(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Decision matrix (v0.3, config-driven dimensions)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    recommend_parser = subparsers.add_parser("recommend", help="score, rank and (optionally) gate candidates")
    recommend_parser.add_argument("--request", required=True, help="path to one JSON request object")
    recommend_parser.add_argument("--output-dir", required=True, help="directory for output JSON files")

    compare_parser = subparsers.add_parser("compare", help="compare two saved recommend outputs")
    compare_parser.add_argument("--previous", required=True)
    compare_parser.add_argument("--current", required=True)
    compare_parser.add_argument("--output", required=True)

    args = parser.parse_args()
    try:
        if args.command == "recommend":
            request = _load(args.request)
            result = recommend(
                request["metric_results"],
                request["indicator_scores"],
                request["dimension_scores"],
                request["scoring_config"],
                request.get("project_profile"),
                request.get("constraint_rules"),
                request.get("evidence_records"),
                request["context"],
            )
            output_dir = Path(args.output_dir)
            _dump(result["gate_results"], output_dir / "gate_results.json")
            _dump(result["recommendations"], output_dir / "recommendations.json")
            _dump({"context": request["context"], "records": result["diagnostics"]}, output_dir / "diagnostics.json")
            _dump(result, output_dir / "decision_output.json")
        else:
            report = compare_runs(_load(args.previous), _load(args.current))
            _dump(report, Path(args.output))
    except (ContractError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(2, f"contract error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
