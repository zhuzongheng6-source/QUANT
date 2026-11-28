import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nbformat
from web_platform import edit_cell


class EditorTests(unittest.TestCase):
    def test_legacy_notebook_and_stale_revision(self):
        with tempfile.TemporaryDirectory() as temp, patch("web_platform.project_path", return_value=Path(temp)):
            path = Path(temp)/"research.ipynb"
            orig = nbformat.v4.new_code_cell("x=1")
            nbformat.write(nbformat.v4.new_notebook(cells=[orig]), path)
            state = edit_cell("example")
            self.assertEqual(state["code"], "")
            edit_cell("example",dict(**state | {"code":"print(x)"}))
            with self.assertRaisesRegex(ValueError,"其他修改"):
                edit_cell("example", state)
            state = edit_cell("example")
            self.assertEqual(state["code"],"print(x)")
            edit_cell("example", state | {"code":"print(x+1)"})
            cells = nbformat.read(path,4).cells
            self.assertEqual(cells[0], orig)
            self.assertEqual(len(cells),2)
