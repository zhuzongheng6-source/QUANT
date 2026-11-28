import unittest

from order_plan import plan_orders


class OrderPlanTests(unittest.TestCase):
    def test_sell_then_buy_with_reserve_and_fees(self):
        result = plan_orders("100", {"AAA": 10}, {"AAA": "100", "BBB": "50"},
                             {"AAA": ".25", "BBB": ".50"})
        orders = result["orders"]
        self.assertEqual([o["signed_shares"] for o in orders], [-8, 11])
        self.assertEqual(result["projected_cash_cents"], 34932)
        self.assertEqual(result["projected_equity_cents"], 109932)
        self.assertGreaterEqual(result["projected_cash_cents"], result["cash_reserve_cents"])

    def test_fee_reduces_buy_when_cash_is_tight(self):
        result = plan_orders("100", {}, {"AAA": "10"}, {"AAA": "1"})
        self.assertEqual(result["target_shares"], {"AAA": 10})
        self.assertEqual(result["holdings"], {"AAA": 9})
        self.assertEqual(result["projected_cash_cents"], 995)

    def test_constraints(self):
        with self.assertRaisesRegex(ValueError, "参考价"):
            plan_orders("0", {"AAA": 1}, {}, {})
        with self.assertRaisesRegex(ValueError, "100%"):
            plan_orders("100", {}, {"AAA": "10"}, {"AAA": "1.01"})

    def test_csv_uses_current_practice_balances(self):
        from order_plan import plan_from_csv
        account = {"open": True, "cash": 10000, "holdings": {"AAA": 10}}
        header = "symbol,price_usd,weight\n"
        result = plan_from_csv(header+"aaa,100,.25\nBBB,50,.5", account)
        self.assertEqual([o["signed_shares"] for o in result["orders"]], [-8, 11])
        with self.assertRaisesRegex(ValueError, "现有持仓"):
            plan_from_csv(header+"BBB,50,.5", account)
        with self.assertRaisesRegex(ValueError, "重复"):
            plan_from_csv(header+"AAA,100,.25\naaa,100,.25", account)
