"""Attribute gross dividend entitlements to prior-close whole-share holdings."""
import argparse
import csv
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from paper import SYMBOLS

NY = ZoneInfo("America/New_York")


def day(timestamp):
    return datetime.fromtimestamp(timestamp, NY).date().isoformat()


def attribute(account, sources):
    with account.open() as f:
        records = list(csv.DictReader(f))
    dates = [r["date"] for r in records]
    if not dates or sorted(set(dates)) != dates:
        raise ValueError("Missing or disordered account sessions")
    prior = dict(zip(dates[1:], records[:-1]))
    rows = []
    for symbol, path in zip(SYMBOLS, sources, strict=True):
        result = json.loads(path.read_text(), parse_float=Decimal)["chart"]["result"][0]
        if result["meta"]["symbol"] != symbol or result["meta"]["currency"] != "USD":
            raise ValueError("Instrument mismatch")
        if [day(t) for t in result["timestamp"]] != dates:
            raise ValueError("Event coverage and account sessions differ")
        events = result.get("events", {})
        if events.get("splits") or not events.get("dividends"):
            raise ValueError("Check corporate actions and dividend data coverage")
        for event in events["dividends"].values():
            ex = day(event["date"])
            if ex not in prior and ex != dates[0]:
                raise ValueError("Unexpected ex-date")
            shares = int(prior[ex][symbol.lower()+"_shares"]) if ex in prior else 0
            rate = Decimal(event["amount"])
            if shares < 0 or not rate.is_finite() or rate <= 0:
                raise ValueError("Invalid shares or dividend rate")
            rows.append((ex, symbol, shares, rate, rate * shares))
    return sorted(rows), Decimal(records[-1]["price_only_equity"])


def main():
    parser = argparse.ArgumentParser(description="按除息前收盘持仓计算税前分红")
    parser.add_argument("account", type=Path)
    parser.add_argument("spy_events", type=Path)
    parser.add_argument("bil_events", type=Path)
    args = parser.parse_args()
    rows, equity = attribute(args.account, (args.spy_events, args.bil_events))
    path = args.account.with_name(args.account.stem + "-dividends.csv")
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("ex_date","symbol","prior_shares","usd_per_share","gross_entitlement_usd"))
        writer.writerows(rows)
    total = sum(r[-1] for r in rows)
    print(f"税前应得分红 {total:.2f} USD，含应得分红期末资产 {equity+total:.2f} USD")


if __name__ == "__main__":
    main()
