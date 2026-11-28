import unittest

import pandas as pd
from backtest import backtest


class BacktestTests(unittest.TestCase):
    def test_future_inputs_do_not_change_prefix(self):
        dates = pd.date_range("2020-01-01", periods=6)
        prices = pd.DataFrame({"A": [10, 11, 10, 12, 17, 9]}, index=dates)
        targets = pd.DataFrame({"A": [1.0, 0.5, 0.0]}, index=dates[[0, 3, 4]])
        earlier = backtest(prices.iloc[:4], targets.iloc[:2])
        full = backtest(prices, targets)
        self.assertEqual(earlier.attrs["pending_signal"], dates[3])
        self.assertIsNone(full.attrs["pending_signal"])
        pd.testing.assert_frame_equal(earlier, full.iloc[:4])

    def test_two_asset_switch_conserves_nav_after_both_fees(self):
        dates = pd.date_range("2020-01-01", periods=3)
        prices = pd.DataFrame({"A": [10.0, 20.0, 22.0], "B": [4.0, 4.0, 4.0]}, index=dates)
        targets = pd.DataFrame({"A": [1.0, 0.0], "B": [0.0, 1.0]}, index=dates[:2])
        book = backtest(prices, targets, capital=100, cost_bps=100)
        gross = book.iloc[1]["nav"] * 22 / 20
        switched = book.iloc[2]
        expected_net = gross * 0.99 / 1.01
        self.assertAlmostEqual(switched["nav"], expected_net)
        self.assertAlmostEqual(switched["turnover"], gross + expected_net)
        self.assertAlmostEqual(switched["fee"], switched["turnover"] * 0.01)
        self.assertAlmostEqual(switched["nav"] + switched["fee"], gross)
        self.assertEqual(switched["cash"], 0)

    def test_signal_at_next_close_and_cost(self):
        dates = pd.date_range("2020-01-01", periods=4)
        prices = pd.DataFrame({"A": [10.0, 20.0, 21.0, 25.0]}, index=dates)
        targets = pd.DataFrame({"A": [1.0, 0.0, 1.0]}, index=dates[[0, 1, 3]])
        book = backtest(prices, targets, capital=100, cost_bps=100)
        self.assertEqual(book.iloc[0]["nav"], 100)
        self.assertEqual(book.iloc[1]["signal_date"], dates[0])
        self.assertAlmostEqual(book.iloc[1]["nav"], 100 / 1.01)
        self.assertAlmostEqual(book.iloc[2]["cash"], 100 / 1.01 * 21 / 20 * 0.99)
        self.assertEqual(book.iloc[2]["nav"], book.iloc[3]["nav"])
        self.assertEqual(book.attrs["pending_signal"], dates[-1])

    def test_missing_quotes_or_leverage_rejected(self):
        prices = pd.DataFrame({"A": [10.0, 11.0]}, index=[1, 2])
        with self.assertRaisesRegex(ValueError, "100%"):
            backtest(prices, pd.DataFrame({"A": [1.1]}, index=[1]))
        prices.loc[2, "A"] = float("nan")
        with self.assertRaisesRegex(ValueError, "缺失值"):
            backtest(prices, pd.DataFrame({"A": [1.0]}, index=[1]))
