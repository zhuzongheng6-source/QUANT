"""Query only public instrument details through an explicitly selected local session."""
import argparse
import json

from contracts import request_fields, resolve
from paper import SYMBOLS


def query(app, contract_type, port):
    batch = {}
    try:
        if not app.connect_and_start(host="127.0.0.1", port=port, client_id=7319):
            raise ConnectionError("本机 TWS 会话未连接")
        for symbol in SYMBOLS:
            fields = request_fields(symbol)
            contract = contract_type()
            for key, value in fields.items():
                setattr(contract, key, value)
            details = app.get_contract_details(contract=contract, timeout=10)
            if not details:
                raise ValueError(f"{symbol} 未收到合约详情")
            records = []
            for detail in details:
                candidate = getattr(detail, "contract", detail)
                records.append({key: getattr(candidate, key) for key in (*fields, "conId")})
            batch[symbol] = {"complete": True, "contracts": records}
        return resolve(batch)
    finally:
        app.disconnect_and_stop()


def main():
    parser = argparse.ArgumentParser(description="查询已选定本机模拟会话的 SPY 和 BIL 合约编号")
    parser.add_argument("--paper-port", required=True, type=int, help="当前 Paper 会话配置的端口")
    args = parser.parse_args()
    if not 1 <= args.paper_port <= 65535:
        parser.error("端口应在 1 至 65535 之间")
    try:
        from ibapi.contract import Contract
        from ibapi.sync_wrapper import TWSSyncWrapper
    except ImportError:
        parser.exit(2, "需要安装含同步接口的 IBKR 官方 TWS Python API。\n")
    try:
        result = query(TWSSyncWrapper(timeout=10), Contract, args.paper_port)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"合约查询失败：{exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
