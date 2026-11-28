import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import daily_data as data
import workbench

HEADER = b"date,symbol,adjusted_close\n"


class ImportTests(unittest.TestCase):
    def test_project_and_missing_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = HEADER + b"2025-02-03,A,12\n2025-02-04,B,10\n"
            with patch.object(data, "IMPORTS", root/"imports"), patch.object(workbench, "PROJECTS", root/"projects"):
                key = data.save(raw)
                self.assertEqual(data.save(raw), key)
                self.assertIn(key, workbench.datasets())
                project = workbench.create("import-test", key)
                table = workbench.load_project(project)
                self.assertEqual(table.shape, (2,2))
                self.assertEqual(table.isna().sum().sum(), 2)
                (data.IMPORTS/f"{key}.csv").write_bytes(raw+b"\n")
                with self.assertRaises(ValueError):
                    workbench.load_project(project)

    def test_invalid_data(self):
        good = b"2025-02-03,A,12\n"
        for rows in (b"", good*2, b"2025-02-30,A,1", b"2025-02-03,A,nan", b"2025-02-03,B,-1", good+b"x,y,z,w"):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                data.parse(HEADER + rows)
