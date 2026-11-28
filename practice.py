"""One local USD practice account. Monetary amounts are integer cents."""
from collections import defaultdict, deque
from contextlib import closing
import csv
from io import StringIO
from hashlib import sha256
import json
import re
import sqlite3
from uuid import UUID, uuid4

from workspace_paths import DATA

DB = DATA / "practice.sqlite3"


def cents(value, *, allow_zero=False):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,2})?", value):
        raise ValueError("金额须为正数，最多两位小数")
    whole, _, fraction = value.partition(".")
    amount = int(whole)*100 + int(fraction.ljust(2, "0"))
    if not amount and not allow_zero:
        raise ValueError("金额须大于零")
    return amount


def consume_fifo(lots, quantity):
    """Return the sold cost in cents, including the allocated entry fees."""
    sold_cost = 0
    while quantity:
        shares, basis, consumed = lots[0]
        delta = min(quantity, shares - consumed)
        next_consumed = consumed + delta
        sold_cost += basis * next_consumed // shares - basis * consumed // shares
        if next_consumed == shares:
            lots.popleft()
        else:
            lots[0] = shares, basis, next_consumed
        quantity -= delta
    return sold_cost


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
    lots = defaultdict(deque)
    open_cost = 0
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
            if qty > 0:
                basis = cost + fee
                lots[symbol].append((qty, basis, 0))
                open_cost += basis
            else:
                open_cost -= consume_fifo(lots[symbol], -qty)
        else:
            fee = 0
        if (expected, fee, cash) != (row["status"], row["fee"], row["cash"]):
            raise ValueError(f"第 {count} 笔委托的状态、费用或余额与重算不符")
        fees += fee
    if cash != balance:
        raise ValueError("账户现金与委托流水不符")
    return dict(capital=initial, origin=origin, count=count, fees=fees,
                open_cost=open_cost, realized_pnl=cash+open_cost-initial), {s:q for s,q in positions.items() if q}


def parse_order(data):
    symbol = data["symbol"].strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,11}", symbol):
        raise ValueError("请输入有效品种代码")
    if not re.fullmatch(r"[1-9][0-9]{0,5}", str(data["quantity"])) or data["side"] not in ("buy", "sell"):
        raise ValueError("买卖方向或整股数量无效")
    quantity = int(data["quantity"]) * (1 if data["side"] == "buy" else -1)
    return symbol, quantity, cents(data["price"])


def trade_fee(value):
    return (abs(value) * 5 + 5000) // 10000


def estimate(holdings, cash, symbol, quantity, price):
    held = holdings.get(symbol, 0)
    value = quantity * price
    fee = trade_fee(value)
    if held + quantity < 0:
        status = "持仓不足"
    elif cash < value + fee:
        status = "现金不足"
    else:
        return dict(status="成交", fee=fee, cash=cash-value-fee, shares=held+quantity)
    return dict(status=status, fee=0, cash=cash, shares=held)


def valuation(marks, holdings, cash, reconciliation):
    if not holdings:
        raise ValueError("当前没有待估值的持仓")
    if not isinstance(marks, dict) or marks.keys() != holdings.keys():
        raise ValueError("当前持仓已变化，或参考价未覆盖所有持仓。请重新读取账户。")
    market_value = sum(quantity * cents(marks[symbol]) for symbol, quantity in holdings.items())
    equity = cash + market_value
    return dict(market_value=market_value, unrealized_pnl=market_value-reconciliation["open_cost"],
                equity=equity, total_pnl=equity-reconciliation["capital"])


def orders_csv(conn):
    def dollars(amount):
        whole, cents = divmod(amount, 100)
        return f"{whole}.{cents:02d}"

    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("sequence", "time_utc", "symbol", "signed_shares", "price_usd",
                     "status", "fee_usd", "cash_after_usd", "batch_id"))
    orders = conn.execute("SELECT time,symbol,qty,price,status,fee,cash,batch_id FROM orders ORDER BY rowid")
    for index, row in enumerate(orders, 1):
        writer.writerow((index, row["time"], row["symbol"], row["qty"], dollars(row["price"]),
                         row["status"], dollars(row["fee"]), dollars(row["cash"]), row["batch_id"] or ""))
    return output.getvalue()


def checked_plan(data, cash, holdings, count):
    from order_plan import plan_from_csv

    plan = plan_from_csv(data["csv"], dict(open=True, cash=cash, holdings=holdings))
    content = json.dumps([count, plan], sort_keys=True, separators=(",", ":")).encode()
    return dict(plan, revision=sha256(content).hexdigest())


def record_plan(conn, plan, csv_text, cash_before):
    if not plan["orders"]:
        raise ValueError("当前草案没有需要记录的委托")
    batch_id = uuid4().hex
    conn.execute("INSERT INTO batches(id, source_csv, cash_before) VALUES (?,?,?)",
                 (batch_id, csv_text, cash_before))
    conn.executemany(
        "INSERT INTO orders(token,symbol,qty,price,fee,status,cash,batch_id) VALUES (?,?,?,?,?,'成交',?,?)",
        [(str(uuid4()), o["symbol"], o["signed_shares"], o["price_cents"], o["fee_cents"], o["cash_after_cents"], batch_id)
         for o in plan["orders"]],
    )
    conn.execute("UPDATE account SET cash=? WHERE id=1", (plan["projected_cash_cents"],))
    return batch_id


def batch_detail(conn, batch_id):
    if not isinstance(batch_id, str) or not re.fullmatch(r"[0-9a-f]{32}", batch_id):
        raise ValueError("无效的调仓批次编号")
    record = conn.execute("SELECT source_csv,cash_before FROM batches WHERE id=?", (batch_id,)).fetchone()
    rows = conn.execute("SELECT time,fee,cash FROM orders WHERE batch_id=? ORDER BY rowid", (batch_id,)).fetchall()
    if not rows:
        raise ValueError("找不到该调仓批次")
    return dict(batch_id=batch_id, orders=len(rows), utc=rows[0]["time"],
                fee=sum(row["fee"] for row in rows), cash_after=rows[-1]["cash"],
                source_csv=record["source_csv"] if record else None,
                cash_before=record["cash_before"] if record else None)


def account(action, data, db=DB):
    if not db.exists():
        if action == "view":
            return {"open": False}
        if action in ("preview", "trade", "export", "valuation", "plan", "record-plan", "batch"):
            raise ValueError("请先建立练习账户")
    db.parent.mkdir(exist_ok=True, parents=True)
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK(id=1), cash INTEGER NOT NULL)")
        conn.execute("""CREATE TABLE IF NOT EXISTS orders (
            token TEXT PRIMARY KEY, symbol TEXT, qty INTEGER, price INTEGER,
            fee INTEGER, status TEXT, cash INTEGER, time TEXT DEFAULT CURRENT_TIMESTAMP,
            batch_id TEXT)""")
        if not any(column["name"] == "batch_id" for column in conn.execute("PRAGMA table_info(orders)")):
            conn.execute("ALTER TABLE orders ADD COLUMN batch_id TEXT")
        conn.execute("CREATE TABLE IF NOT EXISTS opening (id INTEGER PRIMARY KEY CHECK(id=1), capital INTEGER NOT NULL, origin TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, source_csv TEXT NOT NULL, cash_before INTEGER NOT NULL)")
        row = conn.execute("SELECT cash FROM account WHERE id=1").fetchone()
        if action == "open":
            if row:
                raise ValueError("本机已有练习账户")
            initial = cents(data["capital"])
            conn.execute("INSERT INTO account VALUES (1,?)", (initial,))
            conn.execute("INSERT INTO opening VALUES (1,?,?)", (initial,"recorded"))
        elif action in ("preview", "trade"):
            if not row:
                raise ValueError("请先建立练习账户")
            symbol, qty, price = parse_order(data)
            _, holdings = audit(conn, row["cash"])
            order = estimate(holdings, row["cash"], symbol, qty, price)
            if action == "preview":
                return dict(order, symbol=symbol, value=abs(qty * price))
            token = str(UUID(data["token"]))
            prior = conn.execute("SELECT symbol,qty,price FROM orders WHERE token=?", (token,)).fetchone()
            if prior and tuple(prior) != (symbol, qty, price):
                raise ValueError("委托编号已用于其他内容")
            if not prior:
                if order["status"] == "成交":
                    conn.execute("UPDATE account SET cash=? WHERE id=1", (order["cash"],))
                conn.execute("INSERT INTO orders(token,symbol,qty,price,fee,status,cash) VALUES (?,?,?,?,?,?,?)",
                             (token, symbol, qty, price, order["fee"], order["status"], order["cash"]))
        elif action not in ("view", "export", "valuation", "plan", "record-plan", "batch"):
            raise ValueError("未知操作")
        row = conn.execute("SELECT cash FROM account WHERE id=1").fetchone()
        if not row:
            if action in ("export", "valuation", "plan", "record-plan", "batch"):
                raise ValueError("请先建立练习账户")
            return {"open": False}
        reconciliation, holdings = audit(conn, row["cash"])
        if action == "batch":
            return batch_detail(conn, data["batch_id"])
        if action in ("plan", "record-plan"):
            if action == "record-plan" and data.get("count") != reconciliation["count"]:
                raise ValueError("账户记录已变化，请重新计算草案")
            plan = checked_plan(data, row["cash"], holdings, reconciliation["count"])
            if action == "plan":
                return dict(plan, count=reconciliation["count"])
            if plan["revision"] != data.get("revision"):
                raise ValueError("草案已变化，请重新计算")
            batch_id = record_plan(conn, plan, data["csv"], row["cash"])
            audit(conn, plan["projected_cash_cents"])
            return {"recorded": len(plan["orders"]), "batch_id": batch_id}
        if action == "valuation":
            return valuation(data["marks"], holdings, row["cash"], reconciliation)
        if action == "export":
            return {"csv": orders_csv(conn), "count": reconciliation["count"]}
        recent = conn.execute("SELECT time,symbol,qty,price,fee,status,cash,batch_id FROM orders ORDER BY rowid DESC LIMIT 20")
        result = dict(open=True,cash=row["cash"],holdings=holdings,audit=reconciliation,orders=[dict(r) for r in recent])
        if action == "trade":
            result["outcome"] = conn.execute("SELECT status FROM orders WHERE token=?", (token,)).fetchone()[0]
        return result
