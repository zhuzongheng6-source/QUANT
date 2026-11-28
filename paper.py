"""Offline, price-only execution rehearsal using public historical closing prices."""
import argparse
import csv
import hashlib
import json
import re
import math
from decimal import Decimal as D

from research import prices, replay
from workspace_paths import DATA, REPORTS

SYMBOLS = ("SPY", "BIL")
FEE = D("0.0005")


def data_window(snapshot):
    if snapshot is None:
        return DATA, "2023-01-01"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-[a-f0-9]{12}", snapshot):
        raise ValueError("Invalid snapshot identifier")
    directory = DATA / "snapshots" / snapshot
    manifest = (directory / "summary.json").read_bytes()
    if hashlib.sha256(manifest).hexdigest()[:12] != snapshot[-12:]:
        raise ValueError("Snapshot manifest checksum mismatch")
    hashes = json.loads(manifest)["sha256"]
    for name in ("spy.json", "bil.json", "index.json"):
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != hashes[name]:
            raise ValueError(f"Snapshot checksum mismatch for {name}")
    return directory, "2026-01-01"


def market(directory=DATA):
    quotes = {}
    for symbol in SYMBOLS:
        adjusted = prices(symbol, directory)
        raw = json.loads((directory / f"{symbol.lower()}.json").read_text())
        close = raw["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        quotes[symbol] = {}
        for (day, _), value in zip(adjusted, close, strict=True):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"Invalid {symbol} execution price on {day}")
            quotes[symbol][day] = D(str(value)).quantize(D(".01"))
    return quotes


def report_prefix(capital, retry_next, fixed=False):
    return f"offline-{capital:.2f}" + ("-retry" if retry_next else "") + ("-fixed" if fixed else "")


def fixed_orders(holdings, quotes, prior, cash):
    marked = {s: holdings[s] * quotes[s][prior] for s in SYMBOLS}
    # Reserve fees for at most a complete sale and purchase before sizing.
    budget = (cash + sum(marked.values())) / (1 + 2 * FEE)
    changes = []
    for symbol, parts in zip(SYMBOLS, (17, 7), strict=True):
        shares = int(budget * parts / (24 * quotes[symbol][prior]))
        changes.append((symbol, shares - holdings[symbol]))
    return sorted(changes, key=lambda order: order[1] >= 0)


def simulate(capital, retry_next=False, snapshot=None, fixed=False):
    directory, start = data_window(snapshot)
    quotes = market(directory)
    signals = replay(prices("SPY", directory), start, 0)
    days = sorted(quotes["SPY"])
    previous = dict(zip(days[1:], days[:-1]))
    cash = capital
    holdings = dict.fromkeys(SYMBOLS, 0)
    ledger, orders = [], []
    retry_due = False
    for day, _, weight, *_ in signals:
        target = "SPY" if weight else "BIL"
        prior = previous[day]
        monthly = day.month != prior.month
        if monthly or retry_due:
            retry_due = False
            if fixed:
                planned = fixed_orders(holdings, quotes, prior, cash)
            else:
                sell = next(s for s in SYMBOLS if s != target)
                budget = cash + holdings[sell] * quotes[sell][prior] * (1-FEE)
                buy_qty = int(budget / (quotes[target][prior] * (1+FEE)))
                planned = ((sell, -holdings[sell]), (target, buy_qty))
            for symbol, quantity in planned:
                if not quantity:
                    continue
                price = quotes[symbol][day]
                value = quantity * price
                fee = abs(value) * FEE
                filled = cash >= value + fee
                if filled:
                    cash -= value + fee
                    holdings[symbol] += quantity
                elif retry_next and monthly and quantity > 0:
                    retry_due = True
                orders.append((day, prior, symbol, quantity, price, "filled" if filled else "insufficient_cash", fee if filled else 0, cash))
        nav = cash + sum(q * quotes[s][day] for s, q in holdings.items())
        ledger.append((day, cash, holdings["SPY"], holdings["BIL"], nav))
    return orders, ledger


def parse_capital(value):
    capital = D(value)
    if not capital.is_finite() or not D(".01") <= capital <= D("1000000000"):
        raise ValueError("模拟本金须在 0.01 至 10 亿美元之间")
    if capital != capital.quantize(D(".01")):
        raise ValueError("模拟本金精确到美分")
    return capital


def write_reports(output, capital, retry_next=False, snapshot=None, fixed=False):
    orders, ledger = simulate(capital, retry_next, snapshot, fixed)
    output.mkdir(parents=True, exist_ok=True)
    for label, fields, rows in (
        ("orders", "date signal_asof symbol signed_shares fill_reference_close status fee cash_after", orders),
        ("account", "date cash spy_shares bil_shares price_only_equity", ledger),
    ):
        path = output / f"{report_prefix(capital, retry_next, fixed)}-{label}.csv"
        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(fields.split())
            writer.writerows(rows)
    return orders, ledger


def main():
    parser = argparse.ArgumentParser(description="历史整股模拟成交，金额单位 USD")
    parser.add_argument("--capital", default="10000")
    parser.add_argument("--retry-next", action="store_true", help="月初买单被拒后于下一交易日重新估算一次")
    parser.add_argument("--snapshot", help="公开行情快照目录名")
    parser.add_argument("--fixed", action="store_true", help="固定配置 SPY 17/24，BIL 7/24")
    args = parser.parse_args()
    if args.fixed and args.retry_next:
        parser.error("Fixed allocation currently supports monthly execution only")
    try:
        capital = parse_capital(args.capital)
    except (ArithmeticError, ValueError) as exc:
        parser.error(str(exc))
    output = REPORTS / (args.snapshot or "")
    orders, ledger = write_reports(output, capital, args.retry_next, args.snapshot, args.fixed)
    print(f"委托 {len(orders)}，成交 {sum(r[5]=='filled' for r in orders)}，期末现金 {ledger[-1][1]:.2f} USD")


if __name__ == "__main__":
    main()
