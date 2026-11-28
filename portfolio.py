"""Forward-window SPY/BIL comparison with monthly close execution."""
import csv
from statistics import mean

from research import prices, replay
from workspace_paths import REPORTS


def allocate(stock, bills, cash, weight, fee):
    # After both legs trade, assets plus transaction costs equal pre-trade NAV.
    gross = stock + bills + cash
    low, high = 0.0, gross
    for _ in range(54):
        net = (low + high) / 2
        turnover = abs(net * weight - stock) + abs(net * (1 - weight) - bills)
        if net + fee * turnover > gross:
            high = net
        else:
            low = net
    return low * weight, low * (1 - weight)


def simulate(rows, signals, fixed, fee):
    stock = bills = 0.0
    cash = peak = 1.0
    records = []
    for i, (day, spy, bil) in enumerate(rows):
        if i:
            stock *= spy / rows[i-1][1]
            bills *= bil / rows[i-1][2]
        before = stock + bills + cash
        if not i or day.month != rows[i-1][0].month:
            target = signals[day] if fixed is None else fixed
            stock, bills = allocate(stock, bills, cash, target, fee)
            cash = 0.0
        nav = stock + bills
        peak = max(peak, nav)
        records.append((day, stock/nav, nav, nav/peak-1, before-nav))
    return records


def main():
    spy = prices()
    bil = prices("BIL")
    signals = {r[0]: r[2] for r in replay(spy, "2019-01-01", 0)}
    prior = [w for d, w in signals.items() if d.year < 2023]
    fixed = mean(prior)
    rows = []
    for (d, p), (bd, b) in zip(spy, bil, strict=True):
        if d != bd:
            raise ValueError("Unaligned inputs")
        if d.year >= 2023:
            rows.append((d, p, b))
    print(f"2019–2022 平均股票仓位 {fixed:.4%}")
    matched = mean(signals[d] for d, _, _ in rows)
    REPORTS.mkdir(parents=True, exist_ok=True)
    for name, weight in (("trend", None), ("fixed", fixed), ("matched_posthoc", matched), ("spy", 1.0)):
        ledger = simulate(rows, signals, weight, 0.0005)
        with (REPORTS / f"portfolio-{name}.csv").open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(("date", "spy_weight", "nav", "drawdown", "fee_in_nav_units"))
            writer.writerows(ledger)
        print(name, f"累计 {ledger[-1][2]-1:.2%}  最大回撤 {min(r[3] for r in ledger):.2%}  平均股票仓位 {mean(r[1] for r in ledger):.2%}")


if __name__ == "__main__":
    main()
