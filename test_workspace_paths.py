from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import nbformat

import workbench
import workspace_paths


class WorkspacePathTests(TestCase):
    def test_existing_install_keeps_its_data_and_clean_install_uses_home(self):
        with TemporaryDirectory() as tmp:
            code = Path(tmp).resolve() / "code"
            home = Path(tmp).resolve() / "person"
            code.mkdir()
            with (
                patch.object(workspace_paths, "CODE_ROOT", code),
                patch.object(Path, "home", return_value=home),
                patch.dict("os.environ", {workspace_paths.WORKSPACE_ENV: ""}),
            ):
                self.assertEqual(workspace_paths.workspace_root(), home / "QUANT-Workspace")
                (code / "data").mkdir()
                self.assertEqual(workspace_paths.workspace_root(), code)
                with patch.dict("os.environ", {workspace_paths.WORKSPACE_ENV: str(home / "mine")}):
                    self.assertEqual(workspace_paths.workspace_root(), home / "mine")

    def test_legacy_notebook_bootstrap_keeps_analysis(self):
        source = "import sys\nfrom pathlib import Path\n" + workbench.LEGACY_BOOTSTRAP + "prices = load_project(Path.cwd())"
        original = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(source)])
        execution = nbformat.reads(nbformat.writes(original), 4)
        workbench.update_legacy_bootstrap(execution)
        self.assertEqual(original.cells[0].source, source)
        self.assertNotIn("next(p for p in", execution.cells[0].source)
        self.assertTrue(execution.cells[0].source.endswith("prices = load_project(Path.cwd())"))
