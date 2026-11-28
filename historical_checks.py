"""Read-only golden regressions for the original frozen QUANT workspace."""

import os
import shutil
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import dividends
import paper
import quant
import workbench
from ledger_data import balances_and_orders, catalog, replay_reports
from research import prices, replay
from workspace_paths import DATA, REPORTS, WORKSPACE_ROOT

SNAPSHOT = "2026-11-24-35b515c7cbb4"
BASE_LEDGERS = ("10000.00", "100000.00", "100000.00-retry")
SNAPSHOT_LEDGERS = ("10000.00", "10000.00-fixed")
REQUIRED_PATHS = (
    *(DATA / name for name in ("spy.json", "bil.json", "sp500.csv")),
    *(DATA / f"events-20261124-{symbol}.json" for symbol in paper.SYMBOLS),
    *(
        DATA / "snapshots" / SNAPSHOT / name
        for name in ("summary.json", "spy.json", "bil.json", "index.json", "sp500.csv")
    ),
    *(
        directory / f"offline-{variant}-{kind}.csv"
        for directory, variants in ((REPORTS, BASE_LEDGERS), (REPORTS / SNAPSHOT, SNAPSHOT_LEDGERS))
        for variant in variants
        for kind in ("account", "orders")
    ),
)


class FrozenWorkspaceTests(unittest.TestCase):
    def test_signal_ignores_execution_close_and_future_sessions(self):
        rows = prices()
        index = next(i for i, (day, _) in enumerate(rows) if day.year == 2023)
        day, price = rows[index]
        full = replay(rows, str(day), 0)
        for shock in (0.001, 1000):
            with self.subTest(shock=shock):
                self.assertEqual(
                    replay(rows[:index] + [(day, price * shock)], str(day), 0)[0][2], full[0][2]
                )
        earlier = replay(rows[:-252], "2019-01-01", 5)
        self.assertEqual(earlier, replay(rows, "2019-01-01", 5)[: len(earlier)])

    def test_rejected_buy_preserves_cash(self):
        orders, account = paper.simulate(Decimal(100000))
        rejected = [i for i, order in enumerate(orders) if order[5] == "insufficient_cash"]
        self.assertEqual(len(rejected), 3)
        held = {row[0]: row for row in account}
        for i in rejected:
            day, _, _, quantity, _, _, fee, cash = orders[i]
            self.assertGreater(quantity, 0)
            self.assertEqual(fee, 0)
            self.assertEqual(cash, orders[i - 1][-1])
            self.assertEqual(held[day][1:4], (cash, 0, 0))

    def test_tampered_ledger_rejected(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp)
            for kind in ("orders", "account"):
                shutil.copy(REPORTS / f"offline-100000.00-{kind}.csv", output)
            orders = output / "offline-100000.00-orders.csv"
            orders.write_text(
                orders.read_text(encoding="utf-8").replace("insufficient_cash", "filled", 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "委托状态"):
                quant.reconcile(Decimal(100000), output)

    def test_ex_date_rebalance(self):
        account = REPORTS / SNAPSHOT / "offline-10000.00-account.csv"
        sources = [DATA / f"events-20261124-{symbol}.json" for symbol in paper.SYMBOLS]
        rows, equity = dividends.attribute(account, sources)
        gross = {(day, symbol): amount for day, symbol, _, _, amount in rows}
        self.assertEqual(gross["2026-04-01", "BIL"], 0)
        self.assertEqual(gross["2026-05-01", "BIL"], Decimal("27.81"))
        self.assertEqual(equity + sum(gross.values()), Decimal("9663.479705"))

    def test_frozen_ledgers_reconcile(self):
        expected_paths = {path for path in REQUIRED_PATHS if path.name.endswith("-account.csv")}
        entries = [entry for _, entry in catalog(REPORTS) if entry[0] in expected_paths]
        self.assertEqual({entry[0] for entry in entries}, expected_paths)
        for entry in entries:
            with self.subTest(file=entry[0]):
                account, orders_path, orders = balances_and_orders(entry)
                self.assertIn("price_only_equity", account)
                self.assertTrue(orders_path.is_file())
                if entry[0].parent == REPORTS and not entry[2] and not entry[4]:
                    count = sum(order["status"] == "insufficient_cash" for order in orders)
                    self.assertEqual(count, {10000: 0, 100000: 3}[entry[1]])

    def test_base_dimensions_and_replay_endpoint(self):
        frame = workbench.frame("base")
        self.assertEqual(list(frame.columns), ["SPY", "BIL"])
        self.assertEqual(len(frame), 2011)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            relative = replay_reports("base", "10000", "fixed", root)
            entry = next(entry for _, entry in catalog(root) if entry[0] == root / relative)
            self.assertEqual(balances_and_orders(entry)[0]["date"], "2025-12-31")


def main():
    if not os.environ.get("QUANT_WORKSPACE_DIR"):
        print("请设置 QUANT_WORKSPACE_DIR，指向冻结样本工作区。", file=sys.stderr)
        return 2
    missing = [path.relative_to(WORKSPACE_ROOT) for path in REQUIRED_PATHS if not path.is_file()]
    if missing:
        print(f"历史复核缺少输入文件（{WORKSPACE_ROOT}）：", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        return 2
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FrozenWorkspaceTests)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
