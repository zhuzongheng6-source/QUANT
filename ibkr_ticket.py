"""Build an IBKR BasketTrader ticket from explicit order instructions."""
import csv
from io import StringIO
import re

from practice import parse_order


def basket_ticket(data):
    symbol, quantity, price = parse_order(data)
    primary = data["primary_exchange"].strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{1,14}", primary):
        raise ValueError("请输入 TWS 中显示的主上市交易所代码")
    price_text = f"{price // 100}.{price % 100:02d}"
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("Action", "Quantity", "Symbol", "SecType", "Exchange", "Currency",
                     "TimeInForce", "OrderType", "LmtPrice", "OutsideRth"))
    writer.writerow(("BUY" if quantity > 0 else "SELL", abs(quantity), symbol, "STK",
                     f"SMART/{primary}", "USD", "DAY", "LMT", price_text, "FALSE"))
    return {"csv": output.getvalue(), "filename": f"ibkr-{symbol}-limit.csv"}
