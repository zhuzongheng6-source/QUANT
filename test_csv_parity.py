import json
import shutil
import subprocess
import unittest
from pathlib import Path

from daily_data import parse


@unittest.skipUnless(shutil.which("node"), "JavaScript runtime unavailable")
class CSVParityTests(unittest.TestCase):
    def test_import_outcomes(self):
        head = "date,symbol,adjusted_close\n"
        sparse_input = head + ("2025-01-06, zzz ,20\n2025-01-02,aaa,10\n2025-01-03,ZZZ,19\n")
        sparse_summary = {
            "records": 3,
            "first": "2025-01-02",
            "last": "2025-01-06",
            "symbols": ["AAA", "ZZZ"],
            "missing": 3,
        }
        samples = [
            '\ufeff"symbol","adjusted_close","date"\r\n" ab ","1.25E+2","2024-02-29"\r\n',
            head + "\n2025-01-02,A,100\n\n2025-01-03,B,100",
            head + "2025-01-02,A,1_000.25",
            head + "2025-01-02,B,100\n2025-01-02,b,20",
            head + "2025-02-29,A,1",
            head + '2025-01-01,"A,INC",10',
            head + '2025-01-01,A,"10"x',
            head + '2025-01-01,A,"10',
            head + "0000-01-01,A,1",
            head + " 2025-01-02,A,1",
            head,
            sparse_input,
        ]
        js = Path(__file__).with_name("docs").joinpath("app.js").read_text(encoding="utf-8")
        parser = js[: js.index('el("file").onchange')]
        harness = """
const stub = {replaceChildren(){}, append(){}, insertRow(){return this}};
const document = {getElementById(){return stub}, createElement(){return stub}};
"""
        inspect_samples = """
const results = samples.map(sample => {
    inspect(sample, "test");
    if (summary === null) return null;
    const {records, first, last, symbols, missing} = summary;
    return {records, first, last, symbols: [...symbols].sort(), missing};
});
console.log(JSON.stringify(results));
"""
        program = (
            harness + parser + "\nconst samples = " + json.dumps(samples) + ";\n" + inspect_samples
        )
        result = json.loads(subprocess.check_output(["node", "-e", program], text=True))
        for raw, actual in zip(samples, result, strict=True):
            with self.subTest(raw=raw):
                try:
                    frame = parse(raw.encode("utf-8"))
                except ValueError:
                    expected = None
                else:
                    expected = {
                        "records": int(frame.count().sum()),
                        "first": frame.index.min().isoformat(),
                        "last": frame.index.max().isoformat(),
                        "symbols": sorted(frame.columns),
                        "missing": int(frame.isna().sum().sum()),
                    }
                self.assertEqual(actual, expected)
                if raw == sparse_input:
                    self.assertEqual(actual, sparse_summary)
