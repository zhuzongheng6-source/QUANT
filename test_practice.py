from contextlib import closing
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from practice import account


class PracticeTests(unittest.TestCase):
    def test_transactions(self):
        with TemporaryDirectory() as tmp:
            db=Path(tmp)/"sample.sqlite3"
            self.assertFalse(account("view",{},db)["open"])
            account("open",{"capital":"1000"},db)
            order=dict(token=str(uuid4()),symbol="SPY",side="buy",quantity="2",price="100")
            result=account("trade",order,db)
            self.assertEqual(result["cash"],79990)
            self.assertEqual(account("trade",order,db),result)
            with self.assertRaises(ValueError):
                account("trade",order|{"quantity":"3"},db)
            for qty,side in (("3","sell"),("9","buy")):
                refused=account("trade",order|dict(token=str(uuid4()),quantity=qty,side=side),db)
                self.assertEqual(refused["cash"],79990)
                self.assertEqual(refused["holdings"],{"SPY":2})
                self.assertEqual(refused["orders"][0]["fee"],0)
            final=account("trade",order|dict(token=str(uuid4()),side="sell"),db)
            self.assertEqual(final["cash"],99980)
            self.assertEqual(final["holdings"],{})
            self.assertEqual(account("view",{},db)["orders"],final["orders"])

    def test_mismatch_rolls_back_and_legacy_baseline(self):
        import sqlite3
        with TemporaryDirectory() as tmp:
            db=Path(tmp)/"legacy.sqlite3"
            account("open",{"capital":"100"},db)
            ticket=dict(token=str(uuid4()),symbol="TEST",side="buy",quantity="1",price="10")
            account("trade",ticket,db)
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute("DROP TABLE opening")
            report=account("view",{},db)["audit"]
            self.assertEqual(report,dict(origin="inferred",capital=10000,fees=1,count=1,open_cost=1001,realized_pnl=0))
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute("UPDATE orders SET fee=0")
            with self.assertRaisesRegex(ValueError,"第 1 笔"):
                account("trade",ticket|dict(token=str(uuid4())),db)
            with closing(sqlite3.connect(db)) as conn, conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],1)

    def test_preview_matches_order_without_recording(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "preview.sqlite3"
            order = dict(symbol="SPY", side="buy", quantity="2", price="100")
            account("open", {"capital": "1000"}, db)
            before = account("view", {}, db)
            result = account("preview", order, db)
            self.assertEqual(result, dict(symbol="SPY", status="成交", cash=79990, fee=10, shares=2, value=20000))
            self.assertEqual(account("view", {}, db), before)
            trade = account("trade", order | {"token": str(uuid4())}, db)
            self.assertEqual((trade["cash"], trade["orders"][0]["fee"]), (result["cash"], result["fee"]))
            result = account("preview", order | {"side": "sell", "quantity": "3"}, db)
            self.assertEqual((result["status"], result["fee"], result["shares"]), ("持仓不足", 0, 2))

    def test_full_export_includes_older_orders_and_rejections(self):
        import csv
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "export.sqlite3"
            account("open", {"capital": "100"}, db)
            order = dict(symbol="SPY", side="buy", quantity="1", price="10")
            for _ in range(22):
                recent = account("trade", order | {"token": str(uuid4())}, db)
            self.assertEqual(len(recent["orders"]), 20)
            result = account("export", {}, db)
            rows = list(csv.DictReader(result["csv"].splitlines()))
            self.assertEqual(result["count"], 22)
            self.assertEqual(len(rows), 22)
            self.assertEqual((rows[0]["fee_usd"], rows[0]["cash_after_usd"]), ("0.01", "89.99"))
            self.assertEqual((rows[-1]["sequence"], rows[-1]["status"]), ("22", "现金不足"))

    def test_fifo_realized_profit_with_partial_sale(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "fifo.sqlite3"
            account("open", {"capital": "1000"}, db)

            def order(side, qty, price):
                ticket = dict(token=str(uuid4()), symbol="SPY", side=side, quantity=qty, price=price)
                return account("trade", ticket, db)["audit"]

            self.assertEqual(order("buy", "3", "101")["realized_pnl"], 0)
            self.assertEqual(order("buy", "2", "110")["open_cost"], 52326)
            partial = order("sell", "1", "120")
            self.assertEqual((partial["open_cost"], partial["realized_pnl"]), (42221, 1889))
            across_lots = order("sell", "3", "120")
            self.assertEqual((across_lots["open_cost"], across_lots["realized_pnl"]), (11006, 6656))
            flat = order("sell", "1", "100")
            self.assertEqual((flat["open_cost"], flat["realized_pnl"]), (0, 5645))

    def test_manual_marks_use_net_cost_and_leave_ledger_unchanged(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "marks.sqlite3"
            account("open", {"capital": "1000"}, db)
            for symbol, qty, price in (("SPY", "2", "100"), ("BIL", "1", "90")):
                account("trade", dict(token=str(uuid4()), symbol=symbol, side="buy", quantity=qty, price=price), db)
            before = account("view", {}, db)
            with self.assertRaises(ValueError):
                account("valuation", {"marks": {"SPY": "110"}}, db)
            result = account("valuation", {"marks": {"SPY": "110", "BIL": "89"}}, db)
            self.assertEqual(result, dict(market_value=30900, unrealized_pnl=1885, equity=101885, total_pnl=1885))
            self.assertEqual(account("view", {}, db), before)

    def test_record_batch_rejects_stale_preview(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "batch.sqlite3"
            account("open", {"capital": "1000"}, db)
            seed = dict(token=str(uuid4()), symbol="AAA", side="buy", quantity="2", price="100")
            account("trade", seed, db)
            data = {"csv": "symbol,price_usd,weight\nAAA,100,0\nBBB,50,.5"}
            plan = account("plan", data, db)
            ticket = data | {"count": plan["count"], "revision": plan["revision"]}
            with self.assertRaisesRegex(ValueError, "草案已变化"):
                account("record-plan", ticket | {"revision": "wrong"}, db)
            self.assertEqual(account("view", {}, db)["audit"]["count"], 1)
            recorded = account("record-plan", ticket, db)
            self.assertEqual(recorded["recorded"], 2)
            self.assertEqual(len(recorded["batch_id"]), 32)
            view = account("view", {}, db)
            self.assertEqual(view["cash"], plan["projected_cash_cents"])
            self.assertEqual(view["holdings"], {"BBB": 9})
            self.assertEqual([order["batch_id"] for order in view["orders"]],
                             [recorded["batch_id"], recorded["batch_id"], None])
            self.assertEqual(account("export", {}, db)["csv"].count(recorded["batch_id"]), 2)
            with self.assertRaisesRegex(ValueError, "账户记录已变化"):
                account("record-plan", ticket, db)
            self.assertEqual(account("view", {}, db), view)

    def test_legacy_ledger_gets_nullable_batch_column(self):
        import sqlite3
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "old.sqlite3"
            account("open", {"capital": "100"}, db)
            ticket = dict(token=str(uuid4()), symbol="AAA", side="buy", quantity="1", price="10")
            before = account("trade", ticket, db)
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute("ALTER TABLE orders DROP COLUMN batch_id")
            self.assertEqual(account("view", {}, db)["orders"], before["orders"])
