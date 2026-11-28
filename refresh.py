"""Download public daily prices, validate sessions and replay frozen strategy rules."""
import argparse
import csv
import hashlib
import json
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import subprocess

from portfolio import simulate
from research import prices, replay
from workspace_paths import DATA


def download(end, directory):
    stop = datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc)
    urls = {
        f"{s.lower()}.json": f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1=1735689600&period2={int(stop.timestamp())}&interval=1d"
        for s in ("SPY", "BIL")
    }
    urls["index.json"] = urls["spy.json"].replace("/SPY?", "/%5EGSPC?")
    for name, url in urls.items():
        subprocess.run(["curl", "-fLsS", "--retry", "2", "--max-time", "30", "-A", "Mozilla/5.0", url, "-o", str(directory / name)], check=True)
    path = directory / "sp500.csv"
    index = json.loads((directory / "index.json").read_text())["chart"]["result"][0]
    if index["meta"]["symbol"] != "^GSPC":
        raise ValueError("Unexpected reference index")
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("observation_date", "SP500"))
        for stamp, price in zip(index["timestamp"], index["indicators"]["quote"][0]["close"], strict=True):
            if price is not None and price > 0:
                writer.writerow((datetime.fromtimestamp(stamp, timezone.utc).date(), price))
    return urls


def evaluate(directory, end):
    spy = prices("SPY", directory)
    bills = prices("BIL", directory)
    signals = {r[0]: r[2] for r in replay(spy, "2026-01-01", 0)}
    if not signals or max(signals) > end or min(signals) > date(2026, 1, 5):
        raise ValueError("Missing start or invalid end of evaluation window")
    rows = [(day, p, b) for (day, p), (_, b) in zip(spy, bills, strict=True) if day in signals]
    results = {}
    for name, target in (("trend", None), ("fixed", 17/24), ("hold", 1.0)):
        ledger = simulate(rows, signals, target, 0.0005)
        results[name] = {"return": ledger[-1][2]-1, "max_drawdown": min(r[3] for r in ledger)}
        with (directory / f"{name}.csv").open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(("date","spy_weight","nav","drawdown","fee_in_nav_units"))
            writer.writerows(ledger)
    return {"first":str(rows[0][0]), "last":str(rows[-1][0]), "sessions":len(rows), "results":results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("end", type=date.fromisoformat, help="Requested cutoff YYYY-MM-DD")
    end = parser.parse_args().end
    if end < date(2026,1,2) or end >= datetime.now(timezone.utc).date():
        parser.error("Select a past date from 2026-01-02 onward")
    parent = DATA / "snapshots"
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as tmp:
        stage = Path(tmp) / "snapshot"
        stage.mkdir()
        urls = download(end, stage)
        summary = evaluate(stage, end)
        hashes = {name:hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in urls}
        summary.update(requested=str(end), urls=urls, sha256=hashes)
        manifest = json.dumps(summary, indent=2)
        (stage / "summary.json").write_text(manifest)
        destination = parent / f"{end}-{hashlib.sha256(manifest.encode()).hexdigest()[:12]}"
        if not destination.exists():
            stage.rename(destination)
        print(destination, summary["last"], summary["results"])


if __name__ == "__main__":
    main()
