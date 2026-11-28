"""Shared local simulation ledger access."""
import csv
from io import StringIO
import re
import tempfile
from pathlib import Path
from uuid import uuid4
from decimal import Decimal

from paper import parse_capital, report_prefix, write_reports
from quant import reconcile
from workspace_paths import REPORTS
FILENAME = re.compile(r"offline-(\d+\.\d{2})(-retry)?(-fixed)?-account\.csv")


def catalog(root=REPORTS):
    result = []
    for path in sorted(root.rglob("offline-*-account.csv")):
        m = FILENAME.fullmatch(path.name)
        if not m or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            continue
        parts = path.relative_to(root).parts
        run = len(parts) == 4 and parts[0] == "replays" and re.fullmatch(r"[0-9a-f]{32}", parts[1])
        if len(parts) > 2 and not run:
            continue
        name = path.parent.name if len(parts) > 1 else "base"
        snapshot = None if name == "base" else name
        if snapshot and not re.fullmatch(r"\d{4}-\d{2}-\d{2}-[0-9a-f]{12}", snapshot):
            continue
        capital, retry, fixed = Decimal(m[1]), bool(m[2]), bool(m[3])
        period = snapshot[:10] if snapshot else "2018–2025 数据"
        label = f"{period} · {capital:,.2f} USD · " + ("固定配置" if fixed else "月度趋势")
        if retry:
            label += " · 次日重试"
        if run:
            label += " · 网页演练 "+parts[1][:6]
        result.append((label, (path, capital, retry, snapshot, fixed)))
    return result


def checked_csv(entry):
    path, capital, retry, snapshot, fixed = entry
    orders_path = path.with_name(path.name.replace("-account.csv", "-orders.csv"))
    if orders_path.is_symlink():
        raise ValueError("委托文件不是常规账本")
    reconcile(capital, path.parent, retry, snapshot, fixed)
    return path.read_bytes().decode(), orders_path, orders_path.read_bytes().decode()


def balances_and_orders(entry):
    account_csv, orders_path, orders_csv = checked_csv(entry)
    account = list(csv.DictReader(StringIO(account_csv)))[-1]
    orders = list(csv.DictReader(StringIO(orders_csv)))
    return account, orders_path, orders


def equity_curve(rows, capital):
    peak = capital
    points = []
    for row in rows:
        equity = Decimal(row["price_only_equity"])
        peak = max(peak, equity)
        points.append((row["date"], str(equity), str((equity / peak - 1) * 100)))
    return points


def equity_summary(rows, capital, curve=None):
    if curve is None:
        curve = equity_curve(rows, capital)
    trough = min(curve, key=lambda point: Decimal(point[2]))
    return {
        "first": rows[0]["date"],
        "sessions": len(rows),
        "capital": str(capital),
        "return_pct": str((Decimal(curve[-1][1]) / capital - 1) * 100),
        "drawdown_pct": trough[2],
        "trough_date": trough[0] if Decimal(trough[2]) < 0 else None,
    }


def ledger_report(entry):
    account_csv, orders_path, orders_csv = checked_csv(entry)
    rows = list(csv.DictReader(StringIO(account_csv)))
    curve = equity_curve(rows, entry[1])
    return dict(
        account=rows[-1],
        curve=curve,
        orders=list(csv.DictReader(StringIO(orders_csv))),
        summary=equity_summary(rows, entry[1], curve),
        files=[
            {"name": entry[0].name, "csv": account_csv},
            {"name": orders_path.name, "csv": orders_csv},
        ],
    )


def replay_reports(dataset, capital_text, method, root=REPORTS):
    if method not in ("fixed", "trend"):
        raise ValueError("请选择历史演练样例")
    capital = parse_capital(capital_text)
    if dataset != "base" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}-[0-9a-f]{12}", dataset):
        raise ValueError("请选择支持整股演练的行情快照")
    snapshot = None if dataset == "base" else dataset
    fixed = method == "fixed"
    parent = root / "replays"
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / uuid4().hex
    with tempfile.TemporaryDirectory(dir=parent) as temp:
        stage = Path(temp) / "replay"
        output = stage / dataset
        write_reports(output, capital, snapshot=snapshot, fixed=fixed)
        reconcile(capital, output, snapshot=snapshot, fixed=fixed)
        stage.rename(destination)
    return str((destination / dataset / f"{report_prefix(capital, False, fixed)}-account.csv").relative_to(root))
