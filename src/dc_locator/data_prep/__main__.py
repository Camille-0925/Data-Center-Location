"""python -m dc_locator.data_prep  ->  data/processed/county_indicators_va_ga.csv"""

from __future__ import annotations

from . import METRIC_IDS, PROCESSED_CSV, write_processed


def main() -> int:
    table = write_processed()
    counts = table.groupby("state").size().to_dict()
    missing = int(table[METRIC_IDS].isna().sum().sum())
    print(f"wrote {PROCESSED_CSV.relative_to(PROCESSED_CSV.parents[2])}: {len(table)} counties {counts}, "
          f"{len(METRIC_IDS)} indicators, {missing} missing values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
