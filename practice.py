"""One local USD practice account. Monetary amounts are integer cents."""
from contextlib import closing
from pathlib import Path
import re
import sqlite3
from uuid import UUID

DB = Path(__file__).resolve().parent / "data/practice.sqlite3"


def cents(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,2})?", value):
        raise ValueError("金额须为正数，最多两位小数")
    whole, _, fraction = value.partition(".")
    amount = int(whole)*100 + int(fraction.ljust(2, "0"))
    if not amount:
        raise ValueError("金额须大于零")
    return amount


def audit(conn, balance):
    baseline = conn.execute("SELECT capital, origin FROM opening WHERE id=1").fetchone()
    if baseline is None:
        # Older databases only recorded balances after each order.
        first = conn.execute("SELECT * FROM orders ORDER BY rowid LIMIT 1").fetchone()
        initial = balance if first is None else first["cash"]
        if first and first["status"] == "成交":
            initial += first["qty"] * first["price"] + first["fee"]
        origin = "inferred"
        conn.execute("INSERT INTO opening VALUES(1,?,?)", (initial, origin))
    else:
        initial, origin = baseline
    cash = initial
    positions = {}
    fees = count = 0
    if not isinstance(cash, int) or cash <= 0:
        raise ValueError("期初本金无效")
    for count, row in enumerate(conn.execute("SELECT * FROM orders ORDER BY rowid"), 1):
        symbol, qty, price = row["symbol"], row["qty"], row["price"]
        if not isinstance(qty,int) or qty == 0 or not isinstance(price,int) or price <= 0:
            raise ValueError(f"第 {count} 笔委托数量或价格异常")
        held = positions.get(symbol, 0)
        cost = qty * price
        fee = (abs(cost) + 1000) // 2000
        expected = "成交"
        if held + qty < 0:
            expected = "持仓不足"
        elif cost + fee > cash:
            expected = "现金不足"
        if expected == "成交":
            cash -= cost + fee
            positions[symbol] = held + qty
        else:
            fee = 0
        if (expected, fee, cash) != (row["status"], row["fee"], row["cash"]):
            raise ValueError(f"第 {count} 笔委托的状态、费用或余额与重算不符")
        fees += fee
    if cash != balance:
        raise ValueError("账户现金与委托流水不符")
    return dict(capital=initial, origin=origin, count=count, fees=fees), {s:q for s,q in positions.items() if q}


def account(action, data, db=DB):
    if action == "view" and not db.exists():
        return {"open": False}
    db.parent.mkdir(exist_ok=True, parents=True)
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK(id=1), cash INTEGER NOT NULL)")
        conn.execute("""CREATE TABLE IF NOT EXISTS orders (
            token TEXT PRIMARY KEY, symbol TEXT, qty INTEGER, price INTEGER,
            fee INTEGER, status TEXT, cash INTEGER, time TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("CREATE TABLE IF NOT EXISTS opening (id INTEGER PRIMARY KEY CHECK(id=1), capital INTEGER NOT NULL, origin TEXT NOT NULL)")
        row = conn.execute("SELECT cash FROM account WHERE id=1").fetchone()
        if action == "open":
            if row:
                raise ValueError("本机已有练习账户")
            initial = cents(data["capital"])
            conn.execute("INSERT INTO account VALUES (1,?)", (initial,))
            conn.execute("INSERT INTO opening VALUES (1,?,?)", (initial,"recorded"))
        elif action == "trade":
            if not row:
                raise ValueError("请先建立练习账户")
            if not conn.execute("SELECT 1 FROM opening WHERE id=1").fetchone():
                audit(conn, row["cash"])
            token = str(UUID(data["token"]))
            symbol = data["symbol"].strip().upper()
            if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,11}", symbol):
                raise ValueError("请输入有效品种代码")
            if not re.fullmatch(r"[1-9][0-9]{0,5}", str(data["quantity"])) or data["side"] not in ("buy","sell"):
                raise ValueError("买卖方向或整股数量无效")
            qty = int(data["quantity"]) * (1 if data["side"] == "buy" else -1)
            price = cents(data["price"])
            prior = conn.execute("SELECT symbol,qty,price FROM orders WHERE token=?", (token,)).fetchone()
            if prior and tuple(prior) != (symbol, qty, price):
                raise ValueError("委托编号已用于其他内容")
            if not prior:
                cash = row["cash"]
                held = conn.execute("SELECT COALESCE(SUM(qty),0) FROM orders WHERE status='成交' AND symbol=?", (symbol,)).fetchone()[0]
                value = qty * price
                fee = (abs(value) * 5 + 5000) // 10000
                status = "成交"
                if qty + held < 0:
                    status = "持仓不足"
                elif cash < value + fee:
                    status = "现金不足"
                if status == "成交":
                    cash -= value + fee
                    conn.execute("UPDATE account SET cash=? WHERE id=1", (cash,))
                else:
                    fee = 0
                conn.execute("INSERT INTO orders(token,symbol,qty,price,fee,status,cash) VALUES (?,?,?,?,?,?,?)",
                             (token,symbol,qty,price,fee,status,cash))
        elif action != "view":
            raise ValueError("未知操作")
        row = conn.execute("SELECT cash FROM account WHERE id=1").fetchone()
        if not row:
            return {"open": False}
        reconciliation, holdings = audit(conn, row["cash"])
        recent = conn.execute("SELECT time,symbol,qty,price,fee,status,cash FROM orders ORDER BY rowid DESC LIMIT 20")
        result = dict(open=True,cash=row["cash"],holdings=holdings,audit=reconciliation,orders=[dict(r) for r in recent])
        if action == "trade":
            result["outcome"] = conn.execute("SELECT status FROM orders WHERE token=?", (token,)).fetchone()[0]
        return result
