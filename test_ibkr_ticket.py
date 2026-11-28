import csv
from io import StringIO
import unittest

from ibkr_ticket import basket_ticket


class BasketTicketTests(unittest.TestCase):
    order = dict(symbol="spy", primary_exchange="arca", side="sell", quantity="2", price="100.05")

    def test_basket_fields(self):
        row = next(csv.DictReader(StringIO(basket_ticket(self.order)["csv"])))
        self.assertEqual(row, dict(Action="SELL", Quantity="2", Symbol="SPY", SecType="STK",
                                   Exchange="SMART/ARCA", Currency="USD", TimeInForce="DAY",
                                   OrderType="LMT", LmtPrice="100.05", OutsideRth="FALSE"))

    def test_incomplete_or_invalid_input_is_rejected(self):
        for fields in (dict(side=""), dict(price="0"), dict(quantity="1.5"), dict(primary_exchange="")):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                basket_ticket(self.order | fields)

    def test_saved_ticket_reference_is_in_original_file(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from ibkr_ticket import read_ticket, recent_tickets, save_ticket

        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            ticket = save_ticket(self.order, directory)
            reference = ticket["reference"]
            row = next(csv.DictReader(StringIO(ticket["csv"])))
            self.assertEqual(row["OrderRef"], reference)
            self.assertEqual(read_ticket(reference, directory), ticket)
            self.assertEqual(recent_tickets(directory)[0]["reference"], reference)
            with self.assertRaises(ValueError):
                read_ticket("../test", directory)

    def test_manual_fill_progress_and_cancel(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from ibkr_ticket import record_ticket_status, recent_tickets, save_ticket

        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            ticket = save_ticket(self.order, directory)
            update = {"reference": ticket["reference"], "status": "partial", "filled": "1"}
            result = record_ticket_status(update, directory)
            self.assertEqual(result["filled"], 1)
            self.assertEqual(record_ticket_status(update, directory), result)
            with self.assertRaisesRegex(ValueError, "不能减少"):
                record_ticket_status(update | {"status": "cancelled", "filled": "0"}, directory)
            record_ticket_status(update | {"status": "cancelled"}, directory)
            self.assertEqual(recent_tickets(directory)[0]["latest"]["label"], "已撤销")
            with self.assertRaisesRegex(ValueError, "终态"):
                record_ticket_status(update | {"status": "filled", "filled": "2"}, directory)
