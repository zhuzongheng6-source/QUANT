"""Private loopback service for the public static QUANT frontend."""
import argparse
import errno
import csv
from io import StringIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hashlib import sha256
import json
import mimetypes
from pathlib import Path
from threading import Lock, Timer
from urllib.request import ProxyHandler, build_opener
import webbrowser
from public_release import atomic_write, bundle, package, sources

import nbformat

from workbench import project_path, create, datasets, frame, run, RUN_CSV, RUN_ID
import daily_data
import practice
from ibkr_ticket import read_ticket, recent_tickets, record_ticket_status, save_ticket
from ledger_data import catalog, ledger_report, replay_reports
from workspace_paths import CODE_ROOT, PROJECTS, REPORTS, WORKSPACE_ROOT

SITE = CODE_ROOT / "docs"
ASSETS = {"index.html", "app.js", "style.css", "quant-workspace.zip"}
WRITE = Lock()
WORKSPACE = sha256(str(WORKSPACE_ROOT).encode()).hexdigest()


def dataset_csv(key):
    if key not in datasets():
        raise ValueError("未找到所选数据集")
    prices = frame(key)
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(daily_data.FIELDS)
    for symbol in prices.columns:
        writer.writerows((day.isoformat(), symbol, value) for day, value in prices[symbol].dropna().items())
    return output.getvalue()


def history(name, run_id=None, *, table=None):
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
            table_dir = folder / "tables"
            tables = [] if table_dir.is_symlink() else [
                p.name for p in sorted(table_dir.glob("*.csv"))
                if RUN_CSV.fullmatch(p.name) and p.is_file() and not p.is_symlink()
            ]
            if table is not None:
                if table not in tables:
                    raise ValueError("找不到该次运行的 CSV")
                return {"csv": (table_dir / table).read_bytes().decode("utf-8")}
            file = folder / "result.ipynb"
            if file.is_symlink():
                raise ValueError("笔记文件无效")
            notebook = file.read_text()
            book = nbformat.reads(notebook, 4)
            return dict(notebook=notebook, tables=tables, message=status.get("error") or output_text(book)
                        or "此记录没有文本输出。")
    if run_id is not None:
        raise ValueError("未找到已归档的运行")
    manifest = root / "project.json"
    if manifest.is_symlink():
        raise ValueError("项目配置文件无效")
    config = json.loads(manifest.read_text())
    return dict(runs=entries, dataset=config["dataset"])


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
            return self.payload(200, dict(platform="quant-local", datasets=datasets(),
                                          workspace_label=WORKSPACE_ROOT.name,
                                          ledgers=[(label, str(entry[0].relative_to(REPORTS))) for label, entry in catalog()],
                                          projects=sorted(p.parent.name for p in PROJECTS.glob("*/project.json"))))
        if self.path == "/api/health":
            return self.payload(200, {"workspace": WORKSPACE})
        name = "index.html" if self.path == "/" else self.path[1:]
        if name not in ASSETS:
            return self.payload(404, {"error":"路径不存在"})
        asset = SITE / name
        if name == "quant-workspace.zip" and not asset.is_file():
            # The download itself cannot contain a copy of its own archive.
            return self.respond(200, bundle(sources()), "application/zip")
        if not asset.is_file():
            return self.payload(404, {"error": "本地缺少此文件"})
        self.respond(200, asset.read_bytes(), mimetypes.guess_type(name)[0] or "application/octet-stream")

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
            elif self.path == "/api/dataset":
                result = {"csv": dataset_csv(obj["dataset"])}
            elif self.path == "/api/create":
                path = create(obj["name"].strip(), obj["dataset"])
                result = dict(project=path.name, message=f"已创建 {path.name}/research.ipynb")
            elif self.path in ("/api/run", "/api/rerun"):
                previous = obj["id"] if self.path == "/api/rerun" else None
                if self.path == "/api/rerun" and previous is None:
                    raise ValueError("请选择历史归档")
                out = run(obj["name"], previous)
                book = nbformat.read(out/"result.ipynb",4)
                result = dict(message="运行成功 · "+str(out.relative_to(WORKSPACE_ROOT))+"\n"+output_text(book))
            elif self.path == "/api/editor":
                result = edit_cell(obj["name"])
            elif self.path == "/api/save-cell":
                result = edit_cell(obj["name"], obj)
            elif self.path == "/api/ibkr-ticket":
                result = save_ticket(obj)
            elif self.path == "/api/ibkr-tickets":
                result = {"tickets": recent_tickets()}
            elif self.path == "/api/ibkr-ticket-status":
                result = record_ticket_status(obj)
            elif self.path == "/api/ibkr-ticket-file":
                result = read_ticket(obj["reference"])
            elif self.path == "/api/order-plan":
                result = practice.account("plan", obj)
            elif self.path == "/api/practice":
                result = practice.account(obj["action"], obj)
            elif self.path == "/api/replay":
                result = {"id": replay_reports(obj["dataset"], obj["capital"], obj["method"])}
            elif self.path == "/api/ledger":
                entries = {str(entry[0].relative_to(REPORTS)): entry for _, entry in catalog()}
                if obj["id"] not in entries:
                    raise ValueError("未找到该模拟账本")
                result = ledger_report(entries[obj["id"]])
            elif self.path == "/api/history":
                result = history(obj["name"])
            elif self.path == "/api/archive":
                result = history(obj["name"], obj["id"])
            elif self.path == "/api/run-table":
                if not isinstance(obj["id"], str) or not isinstance(obj["table"], str):
                    raise ValueError("请选择归档中的 CSV")
                result = history(obj["name"], obj["id"], table=obj["table"])
            else:
                return self.payload(404, {"error":"未知操作"})
            self.payload(200, result)
        except Exception as exc:
            self.payload(400, {"error":str(exc)[-1500:]})
        finally:
            WRITE.release()


def same_workspace(url):
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(url + "api/health", timeout=1) as response:
            return json.loads(response.read(4096)).get("workspace") == WORKSPACE
    except (OSError, ValueError, AttributeError):
        return False


DEFAULT_PORTS = range(8765, 8785)


def select_server(ports):
    """Find this workspace before binding, even if an earlier port is free."""
    candidates = [(port, f"http://127.0.0.1:{port}/") for port in ports]
    for _, url in candidates:
        if same_workspace(url):
            return None, url

    for port, url in candidates:
        try:
            return ThreadingHTTPServer(("127.0.0.1", port), Handler), url
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE:
                raise
            # Another launcher may have bound the port during discovery.
            if same_workspace(url):
                return None, url
    raise OSError(errno.EADDRINUSE, "候选端口均已被占用")


def open_browser(url):
    if not webbrowser.open(url):
        print(f"请在浏览器中打开 {url}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="启动本地量化工作台")
    parser.add_argument("--port", type=int, help="固定本机端口，省略时自动选取")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--open", action="store_true", help="启动后打开默认浏览器")
    mode.add_argument("--package-only", action="store_true", help="仅生成下载包")
    args = parser.parse_args()
    if args.package_only:
        package()
        return
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("端口须在 1 至 65535 之间")
    ports = DEFAULT_PORTS if args.port is None else (args.port,)
    try:
        server, url = select_server(ports)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            occupied = f"端口 {args.port}" if args.port is not None else "端口 8765–8784"
            parser.exit(1, f"{occupied}已被占用。可用 --port 指定其他端口。\n")
        parser.exit(1, f"无法启动本机服务。{exc}\n")
    if server is None:
        print(f"工作台已经运行。{url}", flush=True)
        if args.open:
            open_browser(url)
        return
    with server:
        print(f"量化工作台已启动。{url}  按 Ctrl+C 停止。\n个人资料目录：{WORKSPACE_ROOT}", flush=True)
        if args.open:
            browser = Timer(0.2, open_browser, (url,))
            browser.daemon = True
            browser.start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n工作台已停止。")


if __name__ == "__main__":
    main()
