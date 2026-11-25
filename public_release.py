"""Build reproducible end-user and GitHub Pages bundles from explicit file lists."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
PUBLIC_FILES = (
    "web_platform.py", "workbench.py", "daily_data.py", "quant.py", "ledger_data.py", "practice.py", "paper.py", "research.py",
    "public_release.py", "requirements-web.txt", "WEB-README.md",
    "docs/index.html", "docs/style.css", "docs/app.js",
)


def bundle(files):
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in sorted(files.items()):
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, content, compress_type=ZIP_DEFLATED)
    return buffer.getvalue()


def atomic_write(target, content):
    target.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as staging:
        tmp = Path(staging) / target.name
        tmp.write_bytes(content)
        tmp.replace(target)


def sources():
    return {name: (ROOT / name).read_bytes() for name in PUBLIC_FILES}


def package():
    atomic_write(ROOT/"docs/quant-workspace.zip", bundle(sources()))


def github_bundle():
    files = sources()
    download = bundle(files)
    atomic_write(ROOT/"docs/quant-workspace.zip", download)
    files.update({
        "docs/quant-workspace.zip": download,
        "docs/.nojekyll": b"",
        "README.md": files["WEB-README.md"],
        ".gitignore": b"data/\nprojects/\nreports/\nrelease/\n.venv/\n__pycache__/\n.ipynb_checkpoints/\n.env\n.env.*\n.DS_Store\n",
    })
    path = ROOT/"release/quant-pages.zip"
    result = bundle(files)
    atomic_write(path, result)
    return path, sha256(result).hexdigest()


if __name__ == "__main__":
    print(*github_bundle(), sep="\n")
