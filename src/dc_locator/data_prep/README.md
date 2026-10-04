# Data Preparation (`dc_locator.data_prep`)

Step ① of the pipeline. It reads `data/raw/virginia_georgia_8d18_indicators_fcc.xlsx` and writes one tidy table, `data/processed/county_indicators_va_ga.csv`: 292 rows (133 VA + 159 GA) with FIPS, county name, state, land area, the 18 raw indicators (ids from the workbook's own definition table), data-quality notes and coverage diagnostics.

```bash
PYTHONPATH=src python3 -m dc_locator.data_prep
# wrote data/processed/county_indicators_va_ga.csv: 292 counties {'GA': 159, 'VA': 133}, 18 indicators, 0 missing values
PYTHONPATH=src python3 -m unittest tests.data_prep.test_data_prep -v
```

The loader checks that the indicator columns are where expected (by header), that every FIPS is a unique 5-digit code, and that there are no missing values; tests also confirm that the three energy indicators are constant within each state.
