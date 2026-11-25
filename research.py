"""Run from any directory with the bundled, frozen public price snapshots."""
import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent


def prices(symbol="SPY", directory=ROOT / "data"):
    item = json.loads((directory / f"{symbol.lower()}.json").read_text())["chart"]["result"][0]
    if item["meta"]["symbol"] != symbol or item["meta"]["currency"] != "USD":
        raise ValueError("Unexpected instrument")
    rows = []
    for stamp, price in zip(item["timestamp"], item["indicators"]["adjclose"][0]["adjclose"], strict=True):
        day = datetime.fromtimestamp(stamp, timezone.utc).date()
        if not math.isfinite(price) or price <= 0 or (rows and day <= rows[-1][0]):
            raise ValueError(f"Invalid price history on {day}")
        rows.append((day, price))
    with (directory / "sp500.csv").open() as src:
        sessions = {r["observation_date"] for r in csv.DictReader(src) if r["SP500"] not in ("", ".")}
    if sessions != {day.isoformat() for day, _ in rows}:
        raise ValueError("ETF and index trading calendars differ")
    return rows


def replay(rows, start, cost, hold=False):
    closes = [p for _, p in rows]
    equity = peak = 1.0
    position = 0
    ledger = []
    for i, (day, price) in enumerate(rows):
        if day.isoformat() < start:
            continue
        if i < 200:
            raise ValueError("Need 200 warm-up sessions")
        equity *= 1 + position * (price / closes[i-1] - 1)
        target = position
        if not ledger or day.month != rows[i-1][0].month:
            target = int(hold or closes[i-1] > mean(closes[i-200:i]))
        trade = target - position
        equity *= 1 - abs(trade) * cost / 10000
        peak = max(peak, equity)
        ledger.append((day, price, target, trade, equity, equity / peak - 1))
        position = target
    return ledger


def main():
    parser = argparse.ArgumentParser(description="SPY 月度趋势研究")
    parser.add_argument("--cost-bps", type=float, default=5)
    args = parser.parse_args()
    if not 0 <= args.cost_bps < 10000:
        parser.error("cost must be in [0, 10000)")
    rows = prices()
    for start in ("2019-01-01", "2023-01-01"):
        for hold in (False, True):
            name = "hold" if hold else "trend"
            ledger = replay(rows, start, args.cost_bps, hold)
            path = ROOT / "reports" / f"{name}-{start}-cost{args.cost_bps:g}.csv"
            with path.open("w", newline="") as out:
                writer = csv.writer(out)
                writer.writerow(("date", "adjusted_close", "closing_weight", "trade_weight", "nav", "drawdown"))
                writer.writerows(ledger)
            print(start, name, f"累计 {ledger[-1][4]-1:.2%}  最大回撤 {min(r[5] for r in ledger):.2%}  买卖次数 {sum(abs(r[3]) for r in ledger)}")


if __name__ == "__main__":
    main()
