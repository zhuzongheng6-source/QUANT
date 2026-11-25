"""Local notebook workspace. The notebook kernel uses the project interpreter."""
import argparse
import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import nbformat as nb
from nbclient import NotebookClient
from jupyter_client.kernelspec import KernelSpecManager

import daily_data
from paper import data_window
from research import ROOT, prices

PROJECTS = ROOT / "projects"


def datasets():
    return ["base", *sorted(p.parent.name for p in (ROOT / "data/snapshots").glob("*/summary.json")),
            *sorted(p.stem for p in daily_data.IMPORTS.glob("csv-*.csv"))]


def project_path(name):
    if not re.fullmatch(r"[\w-]{1,64}", name):
        raise ValueError("项目名限 1–64 个字母、数字、中文、下划线或短横线")
    return PROJECTS / name


def inputs(dataset):
    if dataset not in datasets():
        raise ValueError("未知数据集")
    directory, _ = data_window(None if dataset == "base" else dataset)
    return directory


def frame(dataset):
    import pandas as pd
    if dataset.startswith("csv-"):
        return daily_data.read(dataset)
    directory = inputs(dataset)
    return pd.DataFrame({s: pd.Series(dict(prices(s, directory))) for s in ("SPY", "BIL")}).rename_axis("date")


def create(name, dataset):
    if dataset.startswith("csv-"):
        daily_data.read(dataset)
        stamps = {"prices.csv": dataset[4:]}
    else:
        directory = inputs(dataset)
        stamps = {n: hashlib.sha256((directory / n).read_bytes()).hexdigest()
                  for n in ("spy.json", "bil.json", "sp500.csv")}
    path = project_path(name)
    PROJECTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=PROJECTS) as tmp:
        stage = Path(tmp) / "project"
        stage.mkdir()
        (stage / "project.json").write_text(json.dumps(dict(dataset=dataset, sha256=stamps), indent=2))
        book = nb.v4.new_notebook(metadata={"kernelspec":{"display_name":"Python 3","name":"python3","language":"python"}})
        book.cells = [
            nb.v4.new_markdown_cell(f"# {name}\n\n数据检查 · 美元复权日收盘价。可在下面添加自己的分析。"),
            nb.v4.new_code_cell("import sys\nfrom pathlib import Path\nroot = next(p for p in (Path.cwd(), *Path.cwd().parents) if (p / 'workbench.py').is_file())\nsys.path.insert(0, str(root))\nfrom workbench import load_project\nprices = load_project(Path.cwd())\nprices.tail()"),
            nb.v4.new_code_cell("prices.describe().T.assign(missing=prices.isna().sum())")]
        nb.write(book, stage / "research.ipynb")
        if path.exists():
            raise ValueError("该项目已存在")
        stage.rename(path)
    return path


def load_project(path):
    config = json.loads((path / "project.json").read_text())
    if config["dataset"].startswith("csv-"):
        if config["sha256"] != {"prices.csv": config["dataset"][4:]}:
            raise ValueError("项目数据指纹不符")
        return frame(config["dataset"])
    directory = inputs(config["dataset"])
    for name in ("spy.json", "bil.json", "sp500.csv"):
        if hashlib.sha256((directory/name).read_bytes()).hexdigest() != config["sha256"][name]:
            raise ValueError(f"数据指纹不符：{name}")
    return frame(config["dataset"])


def execute_notebook(book, directory):
    # Scope this spec to the one execution; the user's Jupyter registry may
    # point python3 at a different environment or a removed interpreter.
    with tempfile.TemporaryDirectory() as tmp:
        kernel_name = "quant-local-python"
        spec = Path(tmp) / kernel_name
        spec.mkdir()
        (spec / "kernel.json").write_text(json.dumps({
            "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": "QUANT Python",
            "language": "python",
        }))
        client = NotebookClient(book, kernel_name=kernel_name, timeout=300)
        manager = client.create_kernel_manager()
        manager.kernel_spec_manager = KernelSpecManager(kernel_dirs=[tmp], ensure_native_kernel=False)
        client.execute(cwd=str(directory))


def run(name):
    path = project_path(name)
    load_project(path)
    source = (path / "research.ipynb").read_bytes()
    book = nb.reads(source.decode(), as_version=4)
    out = path / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out.mkdir(parents=True)
    (out / "source.ipynb").write_bytes(source)
    (out / "project.json").write_bytes((path / "project.json").read_bytes())
    error = None
    status = "failed"
    try:
        execute_notebook(book, path)
        status = "success"
    except Exception as exc:
        error = str(exc)[-1500:]
        raise
    finally:
        nb.write(book, out / "result.ipynb")
        (out / "run.json").write_text(json.dumps(dict(status=status, error=error, python=sys.version, executable=sys.executable, source_sha256=hashlib.sha256(source).hexdigest()), indent=2))
        print(out)
    return out


def main():
    parser = argparse.ArgumentParser(description="本地量化工作台")
    cmd = parser.add_subparsers(dest="action", required=True)
    cmd.add_parser("datasets", help="列出可用行情快照")
    ingest = cmd.add_parser("import-csv", help="导入美元复权日线数据")
    ingest.add_argument("file", type=Path)
    new = cmd.add_parser("new", help="创建研究项目")
    new.add_argument("name")
    new.add_argument("--dataset", default="base")
    cmd.add_parser("run", help="执行笔记并归档").add_argument("name")
    args = parser.parse_args()
    if args.action == "datasets":
        for d in datasets():
            df = frame(d)
            print(d, df.index.min(), df.index.max(), len(df), " / ".join(df.columns))
    elif args.action == "import-csv":
        print(daily_data.save(args.file.read_bytes()))
    elif args.action == "new":
        print(create(args.name, args.dataset))
    else:
        run(args.name)


if __name__ == "__main__":
    main()
