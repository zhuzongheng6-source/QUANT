"""Measure the daily backtester with deterministic data entirely in memory."""

import json
import platform
from statistics import median
from time import perf_counter

import numpy as np
import pandas as pd

from backtest import backtest

SIZES = ((2500, 8), (10000, 32))
SEED = 20261127
REPEATS = 5


def inputs(sessions, assets):
    rng = np.random.default_rng(SEED)
    dates = pd.bdate_range("1985-01-01", periods=sessions)
    columns = [f"ASSET_{index}" for index in range(assets)]
    log_returns = rng.normal(0.0002, 0.01, size=(sessions, assets))
    prices = pd.DataFrame(100 * np.exp(log_returns.cumsum(axis=0)), index=dates, columns=columns)
    months = dates.to_period("M")
    rebalance_dates = dates[~months.duplicated()]
    weights = rng.dirichlet(np.ones(assets), size=len(rebalance_dates)) * 0.95
    return prices, pd.DataFrame(weights, index=rebalance_dates, columns=columns)


def verify(book, dates, signals):
    executed = book["signal_date"].dropna()
    expected_signals = signals[signals != dates[-1]]
    pending = dates[-1] if dates[-1] in signals else None
    numeric = book[["nav", "cash", "turnover", "fee", "drawdown"]]
    if (
        not book.index.equals(dates)
        or list(executed) != list(expected_signals)
        or list(executed.index) != list(dates[dates.get_indexer(expected_signals) + 1])
        or book.attrs["pending_signal"] != pending
        or not np.isfinite(numeric.to_numpy()).all()
        or (book["nav"] <= 0).any()
        or (book["cash"] < 0).any()
        or (book["drawdown"] > 0).any()
        or book["fee"].sum() <= 0
        or not np.allclose(book["fee"], book["turnover"] * 0.0005)
    ):
        raise ValueError("Benchmark 输出未通过账本校验")


def main():
    cases = []
    for sessions, assets in SIZES:
        prices, targets = inputs(sessions, assets)
        reference = backtest(prices, targets)
        verify(reference, prices.index, targets.index)
        times = []
        for _ in range(REPEATS):
            start = perf_counter()
            book = backtest(prices, targets)
            times.append(perf_counter() - start)
            if not book.equals(reference) or book.attrs != reference.attrs:
                raise ValueError("Benchmark 重复运行产生不同输出")
        cases.append({"sessions": sessions, "assets": assets, "median_seconds": median(times)})
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "pandas": pd.__version__,
                "machine": platform.machine(),
                "os": platform.platform(),
                "seed": SEED,
                "timed_runs": REPEATS,
                "workloads": cases,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
