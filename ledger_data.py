"""Shared local simulation ledger access."""
import csv
import re
from decimal import Decimal

from quant import reconcile
from research import ROOT

REPORTS = ROOT / "reports"
FILENAME = re.compile(r"offline-(\d+\.\d{2})(-retry)?(-fixed)?-account\.csv")


def catalog(root=REPORTS):
    result = []
    for path in sorted(root.rglob("offline-*-account.csv")):
        m = FILENAME.fullmatch(path.name)
        if not m or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            continue
        snapshot = None if path.parent == root else path.parent.name
        if snapshot and (path.parent.parent != root or not re.fullmatch(r"\d{4}-\d{2}-\d{2}-[0-9a-f]{12}", snapshot)):
            continue
        capital, retry, fixed = Decimal(m[1]), bool(m[2]), bool(m[3])
        period = snapshot[:10] if snapshot else "2018–2025 数据"
        label = f"{period} · {capital:,.0f} USD · " + ("固定配置" if fixed else "月度趋势")
        if retry:
            label += " · 次日重试"
        result.append((label, (path, capital, retry, snapshot, fixed)))
    return result


def balances_and_orders(entry):
    path, capital, retry, snapshot, fixed = entry
    orders_path = path.with_name(path.name.replace("-account.csv", "-orders.csv"))
    if orders_path.is_symlink():
        raise ValueError("委托文件不是常规账本")
    reconcile(capital, path.parent, retry, snapshot, fixed)
    with path.open() as f:
        account = list(csv.DictReader(f))[-1]
    with orders_path.open() as f:
        orders = list(csv.DictReader(f))
    return account, orders_path, orders
