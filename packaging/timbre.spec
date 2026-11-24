# PyInstaller spec for Timbre (onedir, windowed).
# The UI bundle contains only Qt; PyTorch lives in the per-GPU runtime that
# Timbre installs on first launch (see runtimes.json / timbre/runtime.py).
from pathlib import Path

root = Path(SPECPATH).parent

def tree(src, dest):
    out = []
    for p in Path(src).rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            out.append((str(p), str(Path(dest) / p.relative_to(src).parent)))
    return out

datas = tree(root / "engine", "engine") + [(str(root / "runtimes.json"), ".")]
if (root / "bin" / "uv.exe").exists():
    datas.append((str(root / "bin" / "uv.exe"), "bin"))

a = Analysis(
    [str(root / "run.py")],
    pathex=[str(root)],
    datas=datas,
    hiddenimports=["PySide6.QtSvg", "PySide6.QtMultimedia"],
    excludes=["torch", "numpy", "tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtBluetooth"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Timbre",
    icon=str(root / "packaging" / "timbre.ico"),
    console=False,
    version=str(root / "packaging" / "version.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="Timbre")
