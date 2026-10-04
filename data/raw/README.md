# Raw data

`virginia_georgia_8d18_indicators_fcc.xlsx`: county-level indicator workbook prepared by Jane (FCC fiber update). One sheet per state (Virginia: 133 counties and independent cities; Georgia: 159 counties). Columns E–V hold the 18 raw indicators; the table under the data lists each indicator's id, dimension, unit, period, spatial resolution and formula.

Original sources (as documented in the workbook): Wildfire Risk to Communities (USFS), FEMA National Risk Index, WRI Aqueduct 4.0, USGS Annual NLCD, USGS PAD-US 4.1, FCC National Broadband Map, BLS LAUS, CDC/ATSDR SVI 2022, NOAA/CMRA climate summaries, Census TIGER (Interstates), rail network, EIA electricity data, EPA eGRID 2023.

Regenerate the processed table with:

```bash
PYTHONPATH=src python3 -m dc_locator.data_prep
```
