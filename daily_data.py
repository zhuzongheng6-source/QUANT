"""Immutable user-provided USD adjusted-close datasets."""
import csv
import hashlib
import io
import math
import os
import re
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from research import ROOT

IMPORTS = ROOT / "data/imports"
FIELDS = ["date", "symbol", "adjusted_close"]


def parse(raw):
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        if sorted(reader.fieldnames or []) != sorted(FIELDS):
            raise ValueError("列名应为 date,symbol,adjusted_close")
        records = {}
        for row in reader:
            try:
                if None in row or None in row.values():
                    raise ValueError("列数不符")
                day = date.fromisoformat(row["date"])
                if day.isoformat() != row["date"]:
                    raise ValueError("日期应为 YYYY-MM-DD")
                symbol = row["symbol"].strip().upper()
                if not re.fullmatch(r"[A-Z0-9][A-Z0-9.^_-]{0,31}", symbol):
                    raise ValueError("品种代码无效")
                price = float(row["adjusted_close"])
                if not math.isfinite(price) or price <= 0:
                    raise ValueError("复权收盘价须为正的有限数值")
                key = day, symbol
                if key in records:
                    raise ValueError(f"{day} {symbol} 重复")
                records[key] = price
            except ValueError as exc:
                raise ValueError(f"第 {reader.line_num} 行：{exc}") from exc
    except csv.Error as exc:
        raise ValueError(f"第 {reader.line_num} 行 CSV 格式无效：{exc}") from exc
    except UnicodeError as exc:
        raise ValueError("请选择 UTF-8 编码的 CSV") from exc
    if not records:
        raise ValueError("表内缺少行情记录")
    series = pd.Series(records, dtype=float)
    return series.rename_axis(["date", "symbol"]).unstack().sort_index()


def save(raw):
    parse(raw)
    digest = hashlib.sha256(raw).hexdigest()
    IMPORTS.mkdir(parents=True, exist_ok=True)
    target = IMPORTS / f"csv-{digest}.csv"
    with tempfile.NamedTemporaryFile(dir=IMPORTS) as stage:
        stage.write(raw)
        stage.flush()
        try:
            os.link(stage.name, target)
        except FileExistsError:
            if target.read_bytes() != raw:
                raise ValueError("已有数据集校验失败")
    return target.stem


def read(dataset):
    if not re.fullmatch(r"csv-[a-f0-9]{64}", dataset):
        raise ValueError("数据集编号无效")
    raw = (IMPORTS / f"{dataset}.csv").read_bytes()
    if hashlib.sha256(raw).hexdigest() != dataset[4:]:
        raise ValueError("数据指纹不符")
    return parse(raw)
