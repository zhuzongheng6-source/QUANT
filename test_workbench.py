import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import workbench
import daily_data
import paper
from test_fixtures import write_market


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        data = root / "data"
        self.days = write_market(data)
        for patcher in (
            patch.object(workbench, "PROJECTS", root / "projects"),
            patch.object(workbench, "DATA", data),
            patch.object(paper, "DATA", data),
            patch.object(daily_data, "IMPORTS", data / "imports"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_create_and_load(self):
        path = workbench.create("试验", "base")
        data = workbench.load_project(path)
        self.assertEqual(list(data.columns), ["SPY", "BIL"])
        self.assertEqual(list(data.index), self.days)
        with self.assertRaises(ValueError):
            workbench.create("试验", "base")

    def test_invalid_inputs(self):
        for name, dataset in (("../x", "base"), ("x", "missing"), ("", "base")):
            with self.subTest(name=name), self.assertRaises(ValueError):
                workbench.create(name, dataset)

    def test_data_fingerprint(self):
        path = workbench.create("试验", "base")
        file = path / "project.json"
        manifest = json.loads(file.read_text(encoding="utf-8"))
        self.assertIn("spy.json", manifest["sha256"])
        source = workbench.DATA / "spy.json"
        source.write_bytes(source.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "指纹"):
            workbench.load_project(path)

    def test_rerun_refuses_modified_archived_source(self):
        path = workbench.create("试验", "base")
        with patch.object(workbench, "execute_notebook"):
            archived = workbench.run("试验")
        source = archived / "source.ipynb"
        source.write_bytes(source.read_bytes() + b"\n")
        with patch.object(workbench, "execute_notebook") as execute:
            with self.assertRaisesRegex(ValueError, "源笔记指纹不符"):
                workbench.run("试验", archived.name)
            execute.assert_not_called()
