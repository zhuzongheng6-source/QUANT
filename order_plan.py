"""Build local, long-only whole-share order drafts at explicit reference prices."""
from fractions import Fraction
import re

from practice import cents, trade_fee


def affordable_shares(price, upper, budget):
    low, high = 0, upper
    while low < high:
        middle = (low + high + 1) // 2
        value = middle * price
        if value + trade_fee(value) <= budget:
            low = middle
        else:
            high = middle - 1
    return low


def plan_orders(cash_usd, holdings, prices_usd, weights):
    """Return an order draft and projected account values in integer cents.

    Inputs are USD strings, whole shares, and fractional target weights.
    Missing weights imply zero. Prices must be explicitly supplied for
    every held or targeted symbol. The unused weight sets the buy reserve.
    """
    cash = cents(cash_usd, allow_zero=True)
    symbols = sorted(holdings.keys() | weights.keys())
    if set(prices_usd) != set(symbols):
        raise ValueError("参考价必须与持仓和目标中的品种对应")
    prices = {}
    targets = {}
    balances = {}
    for symbol in symbols:
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,11}", symbol):
            raise ValueError(f"品种代码无效：{symbol}")
        qty = holdings.get(symbol, 0)
        if type(qty) is not int or qty < 0:
            raise ValueError(f"{symbol} 的持仓须为非负整数")
        try:
            weight = Fraction(str(weights.get(symbol, 0)))
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"{symbol} 的目标权重无效") from exc
        if weight < 0:
            raise ValueError("目标权重须非负")
        prices[symbol] = cents(prices_usd[symbol])
        targets[symbol] = weight
        balances[symbol] = qty
    invested = sum(targets.values())
    if invested > 1:
        raise ValueError("目标权重总和不得超过 100%")
    starting = cash + sum(balances[s] * prices[s] for s in symbols)
    if not starting:
        raise ValueError("期初现金和持仓总值须大于零")
    reserve_fraction = starting * (1 - invested)
    reserve = -(-reserve_fraction.numerator // reserve_fraction.denominator)
    desired = {s: starting * targets[s] // prices[s] for s in symbols}
    orders = []
    fees = 0

    def add_order(symbol, quantity):
        nonlocal cash, fees
        if quantity:
            value = quantity * prices[symbol]
            fee = trade_fee(value)
            cash -= value + fee
            fees += fee
            balances[symbol] += quantity
            orders.append(dict(symbol=symbol, signed_shares=quantity, price_cents=prices[symbol],
                               fee_cents=fee, cash_after_cents=cash))

    for symbol in symbols:
        add_order(symbol, min(0, desired[symbol] - balances[symbol]))
    for symbol in symbols:
        buy = desired[symbol] - balances[symbol]
        add_order(symbol, affordable_shares(prices[symbol], buy, max(0, cash - reserve)))
    return dict(orders=orders, holdings=balances, target_shares=desired,
                initial_equity_cents=starting, cash_reserve_cents=reserve, projected_cash_cents=cash,
                projected_equity_cents=starting-fees, total_fee_cents=fees)


def plan_from_csv(text, account):
    """Plan against an audited practice account and user-supplied references."""
    import csv
    from io import StringIO

    if not account["open"]:
        raise ValueError("请先建立练习账户")
    reader = csv.DictReader(StringIO(text.removeprefix("\ufeff"), newline=""), strict=True)
    if reader.fieldnames != ["symbol", "price_usd", "weight"]:
        raise ValueError("CSV 列名须为 symbol,price_usd,weight")
    prices, weights = {}, {}
    for row in reader:
        if None in row or None in row.values():
            raise ValueError(f"第 {reader.line_num} 行列数不符")
        symbol = row["symbol"].strip().upper()
        if symbol in prices:
            raise ValueError(f"第 {reader.line_num} 行品种重复")
        prices[symbol] = row["price_usd"].strip()
        weights[symbol] = row["weight"].strip()
    if not prices:
        raise ValueError("请至少输入一个品种")
    if not account["holdings"].keys() <= prices.keys():
        raise ValueError("请为每项现有持仓提供参考价，并填写权重 0 或更高")
    whole, fraction = divmod(account["cash"], 100)
    return plan_orders(f"{whole}.{fraction:02d}", account["holdings"], prices, weights)
