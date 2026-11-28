"""Offline research and whole-share execution regressions."""

import csv
import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import dividends
import paper
import portfolio
import quant
from research import prices, replay
from test_fixtures import FIRST_SESSION, WARMUP_SESSIONS, chart, timestamp, write_market


class WorkspaceTests(unittest.TestCase):
    def test_decision_precedes_execution_price(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp) / "data"
            write_market(directory)
            rows = prices(directory=directory)
        warmup = rows[:WARMUP_SESSIONS]
        day, price = rows[WARMUP_SESSIONS]
        for shock in (0.001, 1000):
            with self.subTest(shock=shock):
                result = replay([*warmup, (day, price * shock)], str(day), 0)
                self.assertEqual(result[0][2], 1)

    def test_future_truncation(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp) / "data"
            write_market(directory)
            rows = prices(directory=directory)
        earlier = replay(rows[:-5], str(FIRST_SESSION), 5)
        self.assertGreater(len(earlier), 1)
        self.assertEqual(earlier, replay(rows, str(FIRST_SESSION), 5)[: len(earlier)])

    def test_fees_on_both_legs(self):
        for target in (0, 0.25, 0.5, 1):
            stock, bills = portfolio.allocate(70, 20, 10, target, 0.001)
            fees = 0.001 * (abs(stock - 70) + abs(bills - 20))
            self.assertAlmostEqual(stock + bills + fees, 100)
            self.assertAlmostEqual(stock / (stock + bills), target)

    def test_rejected_buy_preserves_cash(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp) / "data"
            write_market(directory, execution_shock=True)
            capital = Decimal(10000)
            with patch.object(paper, "DATA", directory):
                orders, account = paper.simulate(capital)
        rejected = [order for order in orders if order[5] == "insufficient_cash"]
        self.assertEqual(len(rejected), 1)
        day, signal, symbol, quantity, _, _, fee, cash = rejected[0]
        self.assertEqual((day, symbol, fee, cash), (FIRST_SESSION, "SPY", 0, capital))
        self.assertLess(signal, day)
        self.assertGreater(quantity, 0)
        self.assertEqual(account[0], (day, capital, 0, 0, capital))

    def test_tampered_ledger_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory, output = root / "data", root / "reports"
            write_market(directory, execution_shock=True)
            capital = Decimal(10000)
            with patch.object(paper, "DATA", directory):
                paper.write_reports(output, capital)
                quant.reconcile(capital, output)
                orders = output / "offline-10000.00-orders.csv"
                original = orders.read_text(encoding="utf-8")
                self.assertIn("insufficient_cash", original)
                orders.write_text(
                    original.replace("insufficient_cash", "filled", 1), encoding="utf-8"
                )
                with self.assertRaisesRegex(ValueError, "委托状态"):
                    quant.reconcile(capital, output)

    def test_ex_date_rebalance(self):
        days = [date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4)]
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = root / "account.csv"
            with account.open("w", encoding="utf-8", newline="") as output:
                writer = csv.writer(output)
                writer.writerow(("date", "spy_shares", "bil_shares", "price_only_equity"))
                writer.writerows(zip(days, [3, 0, 0], [0, 7, 7], [100, 102, 103], strict=True))
            sources = []
            for symbol in paper.SYMBOLS:
                events = {
                    "dividends": {
                        str(timestamp(day)): {"date": timestamp(day), "amount": 0.25}
                        for day in days[1:]
                    }
                }
                source = root / f"{symbol}.json"
                source.write_text(json.dumps(chart(symbol, days, events=events)), encoding="utf-8")
                sources.append(source)
            rows, equity = dividends.attribute(account, sources)

        gross = {(day, symbol): amount for day, symbol, _, _, amount in rows}
        self.assertEqual(gross[str(days[1]), "SPY"], Decimal("0.75"))
        self.assertEqual(gross[str(days[1]), "BIL"], Decimal(0))
        self.assertEqual(gross[str(days[2]), "BIL"], Decimal("1.75"))
        self.assertEqual(equity, Decimal(103))
