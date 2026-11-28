"""Personal ETF research and offline execution workspace."""
import argparse
import csv
import subprocess
from collections import defaultdict
from decimal import Decimal
import sys

from paper import FEE, SYMBOLS, data_window, market, report_prefix
from workspace_paths import CODE_ROOT, REPORTS, WORKSPACE_ENV, WORKSPACE_ROOT
import os


def reconcile(capital, directory, retry_next=False, snapshot=None, fixed=False):
    """Rebuild the reported cash and positions from simulated order decisions."""
    balances = dict.fromkeys(SYMBOLS, 0)
    cash = capital
    data, start = data_window(snapshot)
    quotes = market(data)
    grouped = defaultdict(list)
    prefix = report_prefix(capital, retry_next, fixed)
    with (directory / f"{prefix}-orders.csv").open() as f:
        for order in csv.DictReader(f):
            grouped[order["date"]].append(order)
    days = [day for day in sorted(quotes["SPY"]) if day.isoformat() >= start]
    refusals = 0
    with (directory / f"{prefix}-account.csv").open() as f:
        for day, record in zip(days, csv.DictReader(f), strict=True):
            if record["date"] != str(day):
                raise ValueError(f"{day} 账本日期错误")
            for order in grouped.pop(str(day), []):
                symbol = order["symbol"]
                px = quotes[symbol][day]
                qty = int(order["signed_shares"])
                value = qty * px
                fee = abs(value) * FEE
                enough = cash >= value + fee
                if (order["signal_asof"] >= str(day) or Decimal(order["fill_reference_close"]) != px
                        or order["status"] != ("filled" if enough else "insufficient_cash")
                        or Decimal(order["fee"]) != (fee if enough else 0) or qty == 0):
                    raise ValueError(f"{day} 委托状态或价格费用不符")
                if enough:
                    cash -= value + fee
                    balances[symbol] += qty
                else:
                    refusals += 1
                if Decimal(order["cash_after"]) != cash or balances[symbol] < 0:
                    raise ValueError(f"{day} 成交后余额不符")
            equity = cash + sum(q * quotes[s][day] for s, q in balances.items())
            if (Decimal(record["cash"]) != cash or Decimal(record["price_only_equity"]) != equity
                    or any(int(record[s.lower()+"_shares"]) != q for s, q in balances.items())):
                raise ValueError(f"{day} 现金、持仓或市值不符")
    if grouped:
        raise ValueError("存在账本日期以外的委托")
    print(f"{len(days)} 个交易日对账通过，资金不足拒单 {refusals} 笔")


def run(script, *args):
    subprocess.run([sys.executable, str(CODE_ROOT / script), *args], check=True,
                   env={**os.environ, WORKSPACE_ENV: str(WORKSPACE_ROOT)})


def main():
    parser = argparse.ArgumentParser(description="个人 ETF 研究工作区")
    cmds = parser.add_subparsers(dest="action", required=True)
    cmds.add_parser("research", help="复算趋势策略、基准与成本压力情景")
    cmds.add_parser("risk", help="比较不同股票仓位的历史回撤和恢复时间")
    paper = cmds.add_parser("paper", help="离线整股演练并对账")
    paper.add_argument("--capital", default="10000")
    paper.add_argument("--retry-next", action="store_true", help="次日重算一次被拒买单")
    paper.add_argument("--snapshot", help="指定公开行情快照目录名")
    paper.add_argument("--fixed", action="store_true", help="按月回放固定配置对照")
    refresh = cmds.add_parser("refresh", help="更新公开行情并回放追加区间")
    refresh.add_argument("end")
    args = parser.parse_args()
    if args.action == "research":
        run("research.py")
        run("research.py", "--cost-bps", "20")
        run("portfolio.py")
    elif args.action == "risk":
        run("risk.py")
    elif args.action == "paper":
        options = ["--retry-next"] if args.retry_next else []
        if args.fixed:
            options.append("--fixed")
        if args.snapshot is not None:
            options.extend(["--snapshot", args.snapshot])
        run("paper.py", "--capital", args.capital, *options)
        reconcile(Decimal(args.capital), REPORTS / (args.snapshot or ""), args.retry_next, args.snapshot, args.fixed)
    else:
        run("refresh.py", args.end)


if __name__ == "__main__":
    main()
