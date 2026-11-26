"""Compute runtimes: private Python environments with the right PyTorch build.

No single PyTorch build supports every GPU, so Timbre installs the matching one
(CUDA, ROCm, XPU, DirectML or CPU) into %LOCALAPPDATA%\\Timbre\\runtimes\\<variant>
using the bundled `uv` binary. The UI itself never imports torch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from . import paths


@dataclass
class Variant:
    key: str
    label: str
    summary: str
    vendors: list[str]
    packages: list[str]
    index_url: str
    download_gb: float
    status: str
    note: str = ""

    @property
    def python(self) -> Path:
        return paths.runtimes_dir() / self.key / "Scripts" / "python.exe"

    @property
    def installed(self) -> bool:
        folder = paths.runtimes_dir() / self.key
        return self.python.exists() and (folder / ".timbre-ok").exists() and _base_python_ok(folder)


def _base_python_ok(venv: Path) -> bool:
    """A venv only works while the Python it was made from still exists (e.g. after a reinstall elsewhere)."""
    try:
        for line in (venv / "pyvenv.cfg").read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip().lower() == "home":
                return (Path(value.strip()) / "python.exe").exists()
    except OSError:
        return False
    return True


def manifest() -> dict:
    return json.loads(paths.manifest_path().read_text(encoding="utf-8"))


def variants() -> dict[str, Variant]:
    data = manifest()
    return {k: Variant(key=k, **{f: v.get(f, "") for f in
                                 ("label", "summary", "vendors", "packages", "index_url",
                                  "download_gb", "status", "note")})
            for k, v in data["variants"].items()}


def resolve_python(settings) -> tuple[str | None, str]:
    """Return (python path, source description) for the engine."""
    if settings.python_path and Path(settings.python_path).exists():
        return settings.python_path, "custom"
    vs = variants()
    if settings.runtime_variant in vs and vs[settings.runtime_variant].installed:
        return str(vs[settings.runtime_variant].python), settings.runtime_variant
    for v in vs.values():
        if v.installed:
            return str(v.python), v.key
    dev = paths.dev_python()
    if dev:
        return str(dev), "development"
    return None, ""


class RuntimeInstaller(QObject):
    """Runs the uv steps one after another and streams their output."""

    output = Signal(str)
    stepChanged = Signal(int, int, str)     # index, total, label
    finished = Signal(bool, str)            # ok, message

    def __init__(self, variant: Variant, index_override: str = "", parent=None):
        super().__init__(parent)
        self.variant = variant
        self.index = index_override or variant.index_url
        self.proc: QProcess | None = None
        self.steps: list[tuple[str, list[str]]] = []
        self.current = -1
        self.cancelled = False

    def _plan(self, uv: str) -> list[tuple[str, list[str]]]:
        target = str(paths.runtimes_dir() / self.variant.key)
        py = str(self.variant.python)
        data = manifest()
        torch_step = [uv, "pip", "install", "--python", py, *self.variant.packages]
        if self.index:
            torch_step += ["--index-url", self.index, "--extra-index-url", "https://pypi.org/simple",
                           "--index-strategy", "unsafe-best-match"]
        bundled = paths.bundled_python()
        if bundled:
            # Build from the Python shipped with Timbre. uv never downloads or installs a Python then,
            # which avoids the folder junction uv creates for its own Pythons; some PCs block those
            # ("untrusted mount point", os error 448).
            venv_step = [uv, "venv", target, "--python", str(bundled), "--seed", "--allow-existing",
                         "--no-python-downloads", "--no-managed-python"]
        else:
            venv_step = [uv, "venv", target, "--python", data["python"], "--seed", "--allow-existing"]
        return [
            ("Preparing Python " + data["python"], venv_step),
            (f"Installing PyTorch ({self.variant.label})", torch_step),
            ("Installing speech model libraries",
             [uv, "pip", "install", "--python", py, *data["common"]]),
        ]

    def start(self) -> None:
        uv = paths.uv_executable()
        if not uv:
            self.finished.emit(False, "The bundled installer (uv.exe) is missing. Reinstall Timbre, "
                                      "or point Timbre to an existing Python environment in Advanced.")
            return
        paths.runtimes_dir().mkdir(parents=True, exist_ok=True)
        (paths.runtimes_dir() / self.variant.key / ".timbre-ok").unlink(missing_ok=True)
        self.steps = self._plan(uv)
        self.current = -1
        self._next()

    def cancel(self) -> None:
        self.cancelled = True
        if self.proc and self.proc.state() != QProcess.NotRunning:
            self.proc.kill()

    def _next(self) -> None:
        self.current += 1
        if self.current >= len(self.steps):
            (paths.runtimes_dir() / self.variant.key / ".timbre-ok").write_text("ok")
            self.finished.emit(True, f"{self.variant.label} runtime installed.")
            return
        label, cmd = self.steps[self.current]
        self.stepChanged.emit(self.current, len(self.steps), label)
        self.output.emit(f"$ {' '.join(cmd[1:])}\n")
        proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("UV_CACHE_DIR", str(paths.data_dir() / "uv-cache"))
        env.insert("UV_PYTHON_INSTALL_DIR", str(paths.data_dir() / "python"))
        env.insert("UV_NO_PROGRESS", "0")
        proc.setProcessEnvironment(env)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(
            lambda: self.output.emit(bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")))
        proc.finished.connect(self._done)
        self.proc = proc
        proc.start(cmd[0], cmd[1:])

    def _done(self, code: int, status) -> None:
        if self.cancelled:
            self.finished.emit(False, "Installation cancelled.")
            return
        if code != 0:
            label = self.steps[self.current][0]
            self.finished.emit(False, f"“{label}” failed (exit code {code}). See the log for details.")
            return
        self._next()
