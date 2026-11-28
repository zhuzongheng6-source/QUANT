import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import paper
from ledger_data import balances_and_orders, catalog, equity_summary, replay_reports
from test_fixtures import LAST_SESSION, write_market


class LedgerDataTests(unittest.TestCase):
    def test_empty_catalog(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(catalog(Path(tmp)), [])

    def test_replays_publish_independent_reconciled_ledgers(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data, reports = root / "data", root / "reports"
            write_market(data)
            with patch.object(paper, "DATA", data):
                first = replay_reports("base", "10000", "fixed", reports)
                second = replay_reports("base", "10000", "fixed", reports)
                self.assertNotEqual(first, second)
                self.assertEqual((reports / first).read_bytes(), (reports / second).read_bytes())
                entries = catalog(reports)
                self.assertEqual(len(entries), 2)
                for _, entry in entries:
                    with self.subTest(file=entry[0]):
                        account, orders, _ = balances_and_orders(entry)
                        self.assertEqual(account["date"], str(LAST_SESSION))
                        self.assertIn("price_only_equity", account)
                        self.assertTrue(orders.is_file())

    def test_drawdown_includes_initial_cash(self):
        rows = [
            {"date": "2026-01-02", "price_only_equity": "95"},
            {"date": "2026-01-05", "price_only_equity": "110"},
            {"date": "2026-01-06", "price_only_equity": "99"},
        ]
        summary = equity_summary(rows, Decimal("100"))
        self.assertEqual(Decimal(summary["return_pct"]), Decimal("-1"))
        self.assertEqual(Decimal(summary["drawdown_pct"]), Decimal("-10"))
        self.assertEqual(
            Decimal(equity_summary(rows[:1], Decimal("100"))["drawdown_pct"]), Decimal("-5")
        )
