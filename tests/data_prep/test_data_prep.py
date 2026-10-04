from __future__ import annotations

import unittest

from dc_locator.data_prep import METRIC_IDS, load_all, load_processed


class DataPrepTests(unittest.TestCase):
    def test_workbook_loads_both_states_completely(self):
        table = load_all()
        self.assertEqual(table.groupby("state").size().to_dict(), {"GA": 159, "VA": 133})
        self.assertFalse(table["fips"].duplicated().any())
        self.assertTrue(table["fips"].str.fullmatch(r"\d{5}").all())
        self.assertEqual(int(table[METRIC_IDS].isna().sum().sum()), 0)

    def test_processed_csv_matches_workbook(self):
        processed = load_processed()
        fresh = load_all()
        self.assertEqual(list(processed["fips"]), list(fresh["fips"]))
        for metric_id in METRIC_IDS:
            self.assertTrue(((processed[metric_id] - fresh[metric_id]).abs() < 1e-12).all(), metric_id)

    def test_state_level_energy_indicators_are_constant_within_state(self):
        table = load_all()
        for metric_id in ["state_industrial_price", "state_ieee_saidi_without_med", "state_grid_co2e_intensity"]:
            self.assertTrue((table.groupby("state")[metric_id].nunique() == 1).all())


if __name__ == "__main__":
    unittest.main()
