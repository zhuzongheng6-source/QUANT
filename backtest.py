"""Long-only target-weight backtests on aligned, adjusted daily closes."""
import math

import numpy as np
import pandas as pd


def after_fees(holdings, gross, weights, rate):
    """Solve net NAV + fee on traded asset notional = gross NAV."""
    if rate == 0:
        return gross
    low, high = 0.0, gross
    for _ in range(54):
        net = (low + high) / 2
        turnover = np.abs(net * weights - holdings).sum()
        if net + rate * turnover > gross:
            high = net
        else:
            low = net
    return low


def backtest(prices, targets, *, capital=10_000, cost_bps=5):
    """Simulate target weights signalled at one close and filled at the next.

    Both inputs are DataFrames indexed by session date with matching asset
    columns. Targets may be sparse in dates. Unallocated weight stays in USD
    cash. Price and NAV columns are in USD. Drawdown is a decimal fraction.
    """
    if prices.empty or not prices.index.is_unique or not prices.index.is_monotonic_increasing:
        raise ValueError("行情日期必须非空、唯一并按升序排列")
    if not prices.columns.is_unique or not targets.columns.is_unique or set(targets.columns) != set(prices.columns):
        raise ValueError("行情和目标仓位须有相同且唯一的品种列")
    if not targets.index.is_unique or not targets.index.isin(prices.index).all():
        raise ValueError("每条信号须对应唯一的行情日期")
    close = prices.to_numpy(dtype=float)
    weights = targets.reindex(columns=prices.columns).to_numpy(dtype=float, copy=True)
    if not np.isfinite(close).all() or (close <= 0).any():
        raise ValueError("行情必须对齐，价格须为正且无缺失值")
    if not np.isfinite(weights).all() or (weights < 0).any() or (weights.sum(axis=1) > 1 + 1e-12).any():
        raise ValueError("目标仓位须非负，各日总仓位不得超过 100%")
    if not math.isfinite(capital) or capital <= 0 or not math.isfinite(cost_bps) or not 0 <= cost_bps < 10_000:
        raise ValueError("本金须大于零，单边成本须在 0 至 10000 基点之间")
    # Normalize only totals microscopically above one due to floating point.
    weights /= np.maximum(1, weights.sum(axis=1))[:, None]
    signals = dict(zip(targets.index, weights, strict=True))
    values = np.zeros(len(prices.columns))
    cash = peak = float(capital)
    rate = cost_bps / 10_000
    ledger = []
    for i, day in enumerate(prices.index):
        fee = turnover = 0.0
        signal_date = None
        if i:
            values *= close[i] / close[i-1]
            previous = prices.index[i-1]
            if previous in signals:
                signal_date = previous
                target = signals[previous]
                gross = cash + values.sum()
                net = after_fees(values, gross, target, rate)
                desired = net * target
                turnover = np.abs(desired - values).sum()
                fee = rate * turnover
                values = desired
                cash = net * max(0, 1 - target.sum())
        nav = cash + values.sum()
        if not math.isfinite(nav) or nav <= 0:
            raise ValueError(f"{day} 的净值超出可计算范围")
        peak = max(peak, nav)
        ledger.append((signal_date, nav, cash, turnover, fee, nav/peak-1))
    result = pd.DataFrame(ledger, index=prices.index,
                          columns=["signal_date", "nav", "cash", "turnover", "fee", "drawdown"])
    result.attrs["pending_signal"] = prices.index[-1] if prices.index[-1] in signals else None
    return result
