# Raw data

`virginia_georgia_8d18_indicators_fcc.xlsx`: county-level indicator workbook prepared by Jane (FCC fiber update). One sheet per state (Virginia: 133 counties and independent cities; Georgia: 159 counties). Columns E–V hold the 18 raw indicators; the table under the data lists each indicator's id, dimension, unit, period, spatial resolution and formula.

`cmra_2025_va_ga_robustness_inputs.csv`: repository-local extract of the CMRA 2025 county climate projections. It contains only the 292 VA/GA GEOIDs and the six historical/RCP8.5-mid fields needed to reproduce the three robustness factors. The builder does not require the original 20 MB national file or any machine-specific path.

Original sources (as documented in the workbook): Wildfire Risk to Communities (USFS), FEMA National Risk Index, WRI Aqueduct 4.0, USGS Annual NLCD, USGS PAD-US 4.1, FCC National Broadband Map, BLS LAUS, CDC/ATSDR SVI 2022, NOAA/CMRA climate summaries, Census TIGER (Interstates), rail network, EIA electricity data, EPA eGRID 2023.

Regenerate the processed table with:

```bash
PYTHONPATH=src python3 -m dc_locator.data_prep

# reproduce data/processed/county_robustness_va_ga.csv from the local CMRA extract
python3 scripts/build_robustness_factors.py
```
