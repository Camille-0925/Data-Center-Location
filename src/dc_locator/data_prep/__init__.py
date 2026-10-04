"""Step 1: load the county indicator workbook into one tidy table.

Source: ``data/raw/virginia_georgia_8d18_indicators_fcc.xlsx`` (Jane's processed workbook,
FCC update). One sheet per state; raw indicator values in columns E:V, data-quality notes
and coverage diagnostics after them. Indicator ids follow the workbook's own definition table.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RAW_WORKBOOK = ROOT / "data" / "raw" / "virginia_georgia_8d18_indicators_fcc.xlsx"
PROCESSED_CSV = ROOT / "data" / "processed" / "county_indicators_va_ga.csv"

STATES = {"VA": "Virginia", "GA": "Georgia"}
HEADER_ROW = 5
METRIC_IDS = [
    "wildfire_bp_national_percentile",
    "inland_flood_loss_rate_percentile",
    "baseline_water_stress",
    "water_stress_2050_bau",
    "low_impervious_land_share",
    "gap12_protected_land_share",
    "wetland_land_share",
    "fiber_business_100_20_availability",
    "fiber_business_1000_100_availability",
    "labor_force",
    "social_vulnerability_percentile",
    "historical_cdd65",
    "historical_days_tmax_gt90f",
    "distance_to_interstate_km",
    "distance_to_rail_km",
    "state_industrial_price",
    "state_ieee_saidi_without_med",
    "state_grid_co2e_intensity",
]
# Chinese column headers in the workbook, in the same order as METRIC_IDS (used to verify the layout).
WORKBOOK_HEADERS = [
    "野火全国百分位", "洪水损失率全国百分位", "基线水压力", "2050 BAU水压力", "低不透水土地比例",
    "GAP1/2保护地比例", "湿地陆地比例", "商业服务光纤可用占比100/20", "商业服务光纤可用占比1000/100",
    "劳动力人数", "社会脆弱性百分位", "历史CDD65", "历史>90°F天数", "到Interstate距离", "到铁路距离",
    "州工业电价", "州SAIDI不含重大事件日", "州电网CO₂e强度",
]
EXTRA_COLUMNS = {
    "缺失指标": "missing_metrics_note",
    "质量提示": "quality_note",
    "基线水有效覆盖": "coverage_baseline_water",
    "未来水有效覆盖": "coverage_2050_water",
    "NLCD县域有效覆盖": "coverage_nlcd",
    "不透水陆地有效覆盖": "coverage_impervious",
}


def _header(cell) -> str:
    return str(cell).split("\n")[0].split(" | ")[0].strip()


def load_state(state: str, workbook: str | Path = RAW_WORKBOOK) -> pd.DataFrame:
    """One row per county: identifiers, 18 raw indicators, quality notes and coverage."""

    raw = pd.read_excel(workbook, sheet_name=STATES[state], header=None, dtype=object)
    headers = [_header(c) for c in raw.iloc[HEADER_ROW]]
    if headers[4:22] != WORKBOOK_HEADERS:
        raise ValueError(f"unexpected indicator columns in the {STATES[state]} sheet: {headers[4:22]}")
    body = raw.iloc[HEADER_ROW + 1:]
    body = body[body[0].astype(str).str.fullmatch(r"\d{5}")]
    table = pd.DataFrame(
        {
            "fips": body[0].astype(str).values,
            "county_name": body[1].astype(str).values,
            "state": state,
            "land_area_km2": pd.to_numeric(body[3], errors="coerce").values,
        }
    )
    for offset, metric_id in enumerate(METRIC_IDS):
        table[metric_id] = pd.to_numeric(body[4 + offset], errors="coerce").values
    for chinese, english in EXTRA_COLUMNS.items():
        if chinese in headers:
            table[english] = body[headers.index(chinese)].values
    if table["fips"].duplicated().any():
        raise ValueError(f"duplicate FIPS codes in the {STATES[state]} sheet")
    return table.reset_index(drop=True)


def load_all(workbook: str | Path = RAW_WORKBOOK) -> pd.DataFrame:
    return pd.concat([load_state(s, workbook) for s in STATES], ignore_index=True)


def write_processed(workbook: str | Path = RAW_WORKBOOK, out: str | Path = PROCESSED_CSV) -> pd.DataFrame:
    table = load_all(workbook)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out, index=False)
    return table


def load_processed(path: str | Path = PROCESSED_CSV) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"fips": str})


__all__ = ["METRIC_IDS", "PROCESSED_CSV", "RAW_WORKBOOK", "STATES", "load_all", "load_processed", "load_state", "write_processed"]
