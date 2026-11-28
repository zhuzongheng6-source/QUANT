"""Build an IBKR BasketTrader ticket from explicit order instructions."""
import csv
from datetime import datetime, timezone
import json
from uuid import uuid4
from io import StringIO
import re

from practice import parse_order
from public_release import atomic_write


from workspace_paths import DATA

TICKETS = DATA / "ibkr-tickets"
REFERENCE = re.compile(r"Q[0-9a-f]{20}")


def basket_ticket(data, reference=None):
    symbol, quantity, price = parse_order(data)
    primary = data["primary_exchange"].strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{1,14}", primary):
        raise ValueError("请输入 TWS 中显示的主上市交易所代码")
    price_text = f"{price // 100}.{price % 100:02d}"
    output = StringIO(newline="")
    writer = csv.writer(output)
    header = ("Action", "Quantity", "Symbol", "SecType", "Exchange", "Currency",
                     "TimeInForce", "OrderType", "LmtPrice", "OutsideRth")
    row = ("BUY" if quantity > 0 else "SELL", abs(quantity), symbol, "STK",
                     f"SMART/{primary}", "USD", "DAY", "LMT", price_text, "FALSE")
    writer.writerow(header + (("OrderRef",) if reference else ()))
    writer.writerow(row + ((reference,) if reference else ()))
    return {"csv": output.getvalue(), "filename": f"ibkr-{symbol}-limit.csv"}


def ticket_path(reference, directory):
    if not isinstance(reference, str) or not REFERENCE.fullmatch(reference):
        raise ValueError("无效的委托参考号")
    path = directory / f"{reference}.json"
    if directory.is_symlink() or path.is_symlink():
        raise ValueError("无效的委托记录路径")
    return path


def save_ticket(data, directory=TICKETS):
    reference = "Q" + uuid4().hex[:20]
    ticket = basket_ticket(data, reference)
    path = ticket_path(reference, directory)
    directory.mkdir(parents=True, exist_ok=True)
    ticket.update(reference=reference, filename=f"ibkr-{reference}.csv",
                  utc=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                  symbol=data["symbol"].strip().upper(), side=data["side"],
                  quantity=data["quantity"], price=data["price"])
    atomic_write(path, json.dumps(ticket, ensure_ascii=False).encode())
    return ticket


def read_ticket(reference, directory=TICKETS):
    path = ticket_path(reference, directory)
    if not path.is_file():
        raise ValueError("找不到此委托文件")
    return json.loads(path.read_bytes())


def recent_tickets(directory=TICKETS):
    rows = [
        read_ticket(path.stem, directory)
        for path in directory.glob("Q*.json") if REFERENCE.fullmatch(path.stem)
    ]
    fields = ("reference", "utc", "symbol", "side", "quantity", "price")
    return [
        dict({field: row[field] for field in fields}, latest=(row.get("manual_updates") or [None])[-1])
        for row in sorted(rows, key=lambda row: row["utc"], reverse=True)[:20]
    ]


STATUSES = {
    "submitted": "已送出",
    "partial": "部分成交",
    "filled": "全部成交",
    "cancelled": "已撤销",
    "rejected": "已拒绝",
}
TERMINAL = {"filled", "cancelled", "rejected"}


def record_ticket_status(data, directory=TICKETS):
    reference = data["reference"]
    ticket = read_ticket(reference, directory)
    status, text = data["status"], data["filled"]
    if status not in STATUSES or not isinstance(text, str) or not re.fullmatch(r"[0-9]{1,6}", text):
        raise ValueError("请选择 TWS 状态，并输入累计成交整股数")
    filled, quantity = int(text), int(ticket["quantity"])
    updates = ticket.setdefault("manual_updates", [])
    previous = updates[-1] if updates else {"status": None, "filled": 0}
    if previous["status"] == status and previous["filled"] == filled:
        return previous
    if previous["status"] in TERMINAL:
        raise ValueError("此委托已有终态记录")
    if filled < previous["filled"] or filled > quantity:
        raise ValueError("累计成交股数不能减少或超过委托数量")
    valid = {
        "submitted": filled == 0,
        "partial": 0 < filled < quantity,
        "filled": filled == quantity,
        "cancelled": filled < quantity,
        "rejected": filled == 0,
    }
    if not valid[status]:
        raise ValueError("状态与累计成交股数不一致")
    update = dict(status=status, label=STATUSES[status], filled=filled,
                  utc=datetime.now(timezone.utc).isoformat(timespec="milliseconds"))
    updates.append(update)
    atomic_write(ticket_path(reference, directory), json.dumps(ticket, ensure_ascii=False).encode())
    return update
