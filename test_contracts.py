import unittest

from contracts import request_fields, resolve


class ContractTests(unittest.TestCase):
    def batch(self):
        return {s: {"complete": True, "contracts": [dict(request_fields(s), conId=i)]}
                for i, s in enumerate(("SPY", "BIL"), start=1)}

    def test_unique(self):
        self.assertEqual(resolve(self.batch()), {"SPY": 1, "BIL": 2})

    def test_mismatch(self):
        for key, value in (("symbol", "SPY"), ("secType", "OPT"), ("currency", "CAD"),
                           ("primaryExchange", "NYSE"), ("exchange", "ARCA"), ("conId", 1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                batch = self.batch()
                batch["BIL"]["contracts"][0][key] = value
                resolve(batch)

    def test_ambiguous_or_incomplete(self):
        batch = self.batch()
        batch["SPY"]["complete"] = False
        with self.assertRaises(ValueError):
            resolve(batch)
        batch["SPY"]["complete"] = True
        batch["SPY"]["contracts"] *= 2
        with self.assertRaises(ValueError):
            resolve(batch)


class QueryTests(unittest.TestCase):
    def test_query_and_cleanup(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from ibkr_contracts import query

        def reply(contract, timeout):
            self.assertEqual(timeout, 10)
            contract.conId = {"SPY": 1, "BIL": 2}[contract.symbol]
            return [SimpleNamespace(contract=contract)]

        app = Mock()
        app.get_contract_details.side_effect = reply
        self.assertEqual(query(app, SimpleNamespace, 7497), {"SPY": 1, "BIL": 2})
        app.disconnect_and_stop.assert_called_once()

    def test_timeout_cleanup(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from ibkr_contracts import query

        app = Mock()
        app.get_contract_details.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            query(app, SimpleNamespace, 7497)
        app.disconnect_and_stop.assert_called_once()
