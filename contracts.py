"""Prepare TWS contract requests and check completed responses offline."""
import argparse
import json
from pathlib import Path

from paper import SYMBOLS


def request_fields(symbol):
    return dict(symbol=symbol, secType="STK", currency="USD", exchange="SMART",
                primaryExchange="ARCA")


def resolve(batch):
    resolved = {}
    for symbol in SYMBOLS:
        reply = batch.get(symbol, {})
        if reply.get("complete") is not True:
            raise ValueError(f"{symbol} 合约回传未完成")
        expected = request_fields(symbol)
        matches = [c for c in reply["contracts"] if all(c.get(k) == v for k, v in expected.items())]
        if len(matches) != 1:
            raise ValueError(f"{symbol} 找到 {len(matches)} 个匹配合约")
        contract_id = matches[0].get("conId")
        if type(contract_id) is not int or contract_id <= 0 or contract_id in resolved.values():
            raise ValueError(f"{symbol} 合约编号无效或重复")
        resolved[symbol] = contract_id
    return resolved


def main():
    parser = argparse.ArgumentParser(description="生成合约查询字段，或离线核对已收齐的合约详情")
    parser.add_argument("--responses", type=Path)
    args = parser.parse_args()
    if args.responses:
        try:
            result = resolve(json.loads(args.responses.read_text()))
        except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
            parser.error(str(exc))
    else:
        result = [request_fields(symbol) for symbol in SYMBOLS]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
