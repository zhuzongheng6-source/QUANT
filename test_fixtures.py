"""Deterministic test data in the production loaders' input formats."""

import csv
import json
from datetime import date, datetime, timedelta, timezone

FIRST_SESSION = date(2023, 1, 2)
LAST_SESSION = date(2023, 3, 3)
WARMUP_SESSIONS = 210


def timestamp(day):
    return int(datetime(day.year, day.month, day.day, 16, tzinfo=timezone.utc).timestamp())


def chart(symbol, days, **fields):
    return {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": symbol, "currency": "USD"},
                    "timestamp": [timestamp(day) for day in days],
                    **fields,
                }
            ]
        }
    }


def write_market(directory, *, execution_shock=False):
    """Generate weekday sessions with a rising SPY and a flat BIL."""
    previous = []
    day = FIRST_SESSION
    while len(previous) < WARMUP_SESSIONS:
        day -= timedelta(days=1)
        if day.weekday() < 5:
            previous.append(day)
    days = list(reversed(previous))
    day = FIRST_SESSION
    while day <= LAST_SESSION:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)

    directory.mkdir(parents=True)
    for symbol, adjusted in (
        ("SPY", [100 + index for index in range(len(days))]),
        ("BIL", [100] * len(days)),
    ):
        raw = adjusted.copy()
        if execution_shock and symbol == "SPY":
            raw[WARMUP_SESSIONS] *= 2
        document = chart(
            symbol,
            days,
            indicators={"adjclose": [{"adjclose": adjusted}], "quote": [{"close": raw}]},
        )
        (directory / f"{symbol.lower()}.json").write_text(json.dumps(document), encoding="utf-8")

    with (directory / "sp500.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("observation_date", "SP500"))
        writer.writerows((day.isoformat(), 1) for day in days)
    return days
