"""Private loopback service for the public static QUANT frontend."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hashlib import sha256
import json
import mimetypes
import re
from pathlib import Path
from threading import Lock
from public_release import atomic_write, package

import nbformat

from workbench import ROOT, PROJECTS, project_path, create, datasets, run
import daily_data
import practice
from ledger_data import REPORTS, catalog, balances_and_orders

SITE = ROOT / "docs"
ASSETS = {"index.html", "app.js", "style.css", "quant-workspace.zip"}
WRITE = Lock()


RUN_ID = re.compile(r"[0-9]{8}T[0-9]{12}Z")


def history(name, run_id=None):
    root = project_path(name)
    runs = root / "runs"
    if root.is_symlink() or runs.is_symlink() or not root.is_dir():
        raise ValueError("项目目录无效")
    if run_id is not None and not RUN_ID.fullmatch(run_id):
        raise ValueError("运行编号无效")
    entries = []
    for folder in sorted(runs.glob("*"), reverse=True):
        if not RUN_ID.fullmatch(folder.name) or folder.is_symlink():
            continue
        if run_id is not None and folder.name != run_id:
            continue
        manifest = folder / "run.json"
        if manifest.is_symlink() or not manifest.is_file():
            continue
        status = json.loads(manifest.read_text())
        if run_id is None:
            entries.append(dict(id=folder.name, status=status["status"]))
        else:
            file = folder / "result.ipynb"
            if file.is_symlink():
                raise ValueError("笔记文件无效")
            notebook = file.read_text()
            book = nbformat.reads(notebook, 4)
            return dict(notebook=notebook, message=status.get("error") or output_text(book)
                        or "此记录没有文本输出。")
    if run_id is not None:
        raise ValueError("未找到已归档的运行")
    return dict(runs=entries)


def edit_cell(name, change=None):
    root = project_path(name)
    path = root / "research.ipynb"
    if not path.is_file() or root.is_symlink() or path.is_symlink():
        raise ValueError("项目笔记不可用")
    raw = path.read_bytes()
    revision = sha256(raw).hexdigest()
    book = nbformat.reads(raw.decode(), as_version=4)
    cells = [c for c in book.cells if c.metadata.get("quant_web_editor") is True]
    if len(cells) > 1 or (cells and cells[0].cell_type != "code"):
        raise ValueError("笔记中的网页编辑标记不唯一或不属于代码单元")
    if change is None:
        return dict(revision=revision, code=cells[0].source if cells else "")
    if revision != change["revision"]:
        raise ValueError("笔记已有其他修改，请保留草稿并重新载入")
    code = change["code"]
    if not isinstance(code, str) or not code.strip() or len(code) > 100000:
        raise ValueError("请输入 1 至 100000 个字符的 Python 代码")
    if cells:
        cell = cells[0]
        cell.source, cell.outputs, cell.execution_count = code, [], None
    else:
        book.cells.append(nbformat.v4.new_code_cell(code, metadata={"quant_web_editor": True}))
    updated = nbformat.writes(book).encode()
    atomic_write(path, updated)
    return dict(revision=sha256(updated).hexdigest(), message="分析代码已保存")


def output_text(book):
    parts = []
    for cell in book.cells:
        for output in cell.get("outputs", []):
            text = output.get("text") or output.get("data", {}).get("text/plain") or output.get("evalue")
            if text:
                parts.append(text)
    return "\n".join(parts)[-6000:]


class Handler(BaseHTTPRequestHandler):
    def respond(self, code, body, kind):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def payload(self, code, obj):
        self.respond(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def trusted_host(self):
        return self.headers.get("Host") in {f"{h}:{self.server.server_port}" for h in ("localhost","127.0.0.1")}

    def do_GET(self):
        if not self.trusted_host():
            return self.payload(403, {"error":"主机名不匹配"})
        if self.path == "/api/state":
            available = [d for d in datasets() if d != "base" or (ROOT/"data/spy.json").exists()]
            return self.payload(200, dict(platform="quant-local", datasets=available,
                                          ledgers=[(label, str(entry[0].relative_to(REPORTS))) for label, entry in catalog()],
                                          projects=sorted(p.parent.name for p in PROJECTS.glob("*/project.json"))))
        name = "index.html" if self.path == "/" else self.path[1:]
        if name not in ASSETS:
            return self.payload(404, {"error":"路径不存在"})
        self.respond(200, (SITE/name).read_bytes(), mimetypes.guess_type(name)[0] or "application/octet-stream")

    def do_POST(self):
        if not self.trusted_host() or self.headers.get("Origin") != "http://" + self.headers.get("Host",""):
            return self.payload(403, {"error":"仅允许同源本机页面操作"})
        if not WRITE.acquire(blocking=False):
            return self.payload(409, {"error":"已有任务正在执行"})
        try:
            length = int(self.headers.get("Content-Length","0"))
            if not 0 < length <= 10_000_000 or self.headers.get_content_type() != "application/json":
                return self.payload(400, {"error":"请求类型或大小无效"})
            obj = json.loads(self.rfile.read(length))
            if self.path == "/api/import":
                key = daily_data.save(obj["csv"].encode())
                result = dict(dataset=key, message="行情已存入本机，并已选中。")
            elif self.path == "/api/create":
                path = create(obj["name"].strip(), obj["dataset"])
                result = dict(project=path.name, message=f"已创建 {path.name}/research.ipynb")
            elif self.path == "/api/run":
                out = run(obj["name"])
                book = nbformat.read(out/"result.ipynb",4)
                result = dict(message="运行成功 · "+str(out.relative_to(ROOT))+"\n"+output_text(book))
            elif self.path == "/api/editor":
                result = edit_cell(obj["name"])
            elif self.path == "/api/save-cell":
                result = edit_cell(obj["name"], obj)
            elif self.path == "/api/practice":
                result = practice.account(obj["action"], obj)
            elif self.path == "/api/ledger":
                entries = {str(entry[0].relative_to(REPORTS)): entry for _, entry in catalog()}
                if obj["id"] not in entries:
                    raise ValueError("未找到该模拟账本")
                account, _, orders = balances_and_orders(entries[obj["id"]])
                result = dict(account=account, orders=orders)
            elif self.path == "/api/history":
                result = history(obj["name"])
            elif self.path == "/api/archive":
                result = history(obj["name"], obj["id"])
            else:
                return self.payload(404, {"error":"未知操作"})
            self.payload(200, result)
        except Exception as exc:
            self.payload(400, {"error":str(exc)[-1500:]})
        finally:
            WRITE.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--package-only", action="store_true")
    args = parser.parse_args()
    package()
    if not args.package_only:
        with ThreadingHTTPServer(("127.0.0.1",args.port), Handler) as server:
            print(f"http://127.0.0.1:{server.server_port}/", flush=True)
            server.serve_forever()
