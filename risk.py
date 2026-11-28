"""Historical fixed-weight SPY/BIL drawdown scenarios, in USD."""
import csv

from portfolio import simulate
from research import prices
from workspace_paths import REPORTS


def episode(records):
    trough = min(range(len(records)), key=lambda i: records[i][3])
    # Initial cash immediately before the first closing trade is also a peak.
    peak_value = max([1.0] + [r[2] for r in records[:trough+1]])
    peak_day = next((r[0] for r in reversed(records[:trough+1]) if r[2] == peak_value), records[0][0])
    recovery = next((r[0] for r in records[trough+1:] if r[2] >= peak_value), None)
    return peak_day, records[trough][0], recovery, records[trough][3]


def main():
    rows = []
    for (day, stock), (other, bills) in zip(prices(), prices("BIL"), strict=True):
        if day != other:
            raise ValueError("Unaligned prices")
        rows.append((day, stock, bills))
    REPORTS.mkdir(parents=True, exist_ok=True)
    with (REPORTS / "risk.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("start","end","spy_weight","cumulative_return","max_drawdown","peak","trough","recovered","peak_to_recovery_calendar_days"))
        for weight in (0,.25,.5,.75,1):
            ledger = simulate(rows, {}, weight, .0005)
            peak, trough, recovered, dd = episode(ledger)
            duration = (recovered - peak).days if recovered else None
            gain = ledger[-1][2] - 1
            writer.writerow((rows[0][0],rows[-1][0],weight,gain,dd,peak,trough,recovered,duration))
            print(f"SPY {weight:4.0%}  累计 {gain:8.2%}  最大回撤 {dd:7.2%}  高点 {peak}  谷底 {trough}  恢复 {recovered}  历时 {duration} 天")


if __name__ == "__main__":
    main()
