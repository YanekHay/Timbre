"""UI-side client for the engine process (see engine/protocol.py)."""

from __future__ import annotations

import json
import os
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from . import paths


@dataclass
class _Pending:
    on_result: Callable | None
    on_error: Callable | None
    on_progress: Callable | None


class EngineClient(QObject):
    stateChanged = Signal(str)          # stopped | starting | ready | crashed
    readyInfo = Signal(dict)            # runtime info from the "ready" event
    logLine = Signal(str)
    busyChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc: QProcess | None = None
        self.state = "stopped"
        self.runtime: dict = {}
        self.python = ""
        self._buf = b""
        self._pending: dict[str, _Pending] = {}
        self._busy: set[str] = set()
        self.log = deque(maxlen=2000)
        self._expected_stop = False

    # ------------------------------------------------------------- lifecycle
    def start(self, python: str) -> None:
        self.stop()
        self.python = python
        proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUNBUFFERED", "1")
        env.remove("PYTHONPATH")
        env.remove("PYTHONHOME")
        proc.setProcessEnvironment(env)
        proc.setWorkingDirectory(str(paths.engine_script().parent))
        proc.readyReadStandardOutput.connect(self._read_stdout)
        proc.readyReadStandardError.connect(self._read_stderr)
        proc.finished.connect(self._finished)
        proc.errorOccurred.connect(self._error)
        self.proc = proc
        self._set_state("starting")
        self._expected_stop = False
        proc.start(python, ["-I", "-X", "utf8", str(paths.engine_script())])

    def stop(self) -> None:
        if self.proc and self.proc.state() != QProcess.NotRunning:
            self._expected_stop = True
            try:
                self._write({"cmd": "shutdown"})
            except Exception:
                pass
            if not self.proc.waitForFinished(2500):
                self.proc.kill()
                self.proc.waitForFinished(1000)
        self.proc = None
        self._fail_all("The engine was stopped.")
        self._set_state("stopped")

    def _set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.stateChanged.emit(state)

    @property
    def is_ready(self) -> bool:
        return self.state == "ready"

    @property
    def busy(self) -> bool:
        return bool(self._busy)

    # --------------------------------------------------------------- requests
    def request(self, cmd: str, on_result=None, on_error=None, on_progress=None, **args) -> str:
        rid = uuid.uuid4().hex[:10]
        self._pending[rid] = _Pending(on_result, on_error, on_progress)
        if cmd in ("load", "generate", "unload"):
            self._busy.add(rid)
            self.busyChanged.emit(True)
        if not self.proc or self.state not in ("ready", "starting"):
            self._resolve_error(rid, {"message": "The engine is not running.", "kind": "engine"})
            return rid
        self._write({"id": rid, "cmd": cmd, **args})
        return rid

    def cancel(self) -> None:
        if self.proc:
            self._write({"id": uuid.uuid4().hex[:10], "cmd": "cancel"})

    def _write(self, obj: dict) -> None:
        if self.proc:
            self.proc.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))

    # --------------------------------------------------------------- reading
    def _read_stdout(self) -> None:
        self._buf += bytes(self.proc.readAllStandardOutput())
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except Exception:
                self._append_log(line.decode("utf-8", "replace"))
                continue
            self._dispatch(msg)

    def _read_stderr(self) -> None:
        text = bytes(self.proc.readAllStandardError()).decode("utf-8", "replace")
        for line in text.splitlines():
            if line.strip():
                self._append_log(line)

    def _append_log(self, line: str) -> None:
        self.log.append(line)
        self.logLine.emit(line)

    def _dispatch(self, msg: dict) -> None:
        event = msg.get("event")
        if event == "ready":
            self.runtime = msg.get("runtime", {})
            self._set_state("ready")
            self.readyInfo.emit(self.runtime)
            return
        if event == "booting":
            return
        if event == "log":
            self._append_log(msg.get("message", ""))
            return
        rid = msg.get("id")
        pending = self._pending.get(rid)
        if event == "progress":
            if pending and pending.on_progress:
                pending.on_progress(msg)
        elif event == "result":
            self._pending.pop(rid, None)
            self._unbusy(rid)
            if pending and pending.on_result:
                pending.on_result(msg)
        elif event == "error":
            if rid is None:
                self._append_log("engine: " + msg.get("message", ""))
                return
            self._resolve_error(rid, msg)

    def _resolve_error(self, rid: str, msg: dict) -> None:
        pending = self._pending.pop(rid, None)
        self._unbusy(rid)
        if msg.get("detail"):
            self._append_log(msg["detail"])
        if pending and pending.on_error:
            pending.on_error(msg)

    def _unbusy(self, rid: str) -> None:
        if rid in self._busy:
            self._busy.discard(rid)
            if not self._busy:
                self.busyChanged.emit(False)

    def _fail_all(self, message: str) -> None:
        for rid in list(self._pending):
            self._resolve_error(rid, {"message": message, "kind": "engine"})

    def _finished(self, code: int, status) -> None:
        crashed = not self._expected_stop
        self._fail_all("The engine stopped unexpectedly. See Devices → Engine log." if crashed
                       else "The engine was stopped.")
        self.proc = None
        self._set_state("crashed" if crashed else "stopped")

    def _error(self, err) -> None:
        if err == QProcess.FailedToStart:
            self._append_log(f"Could not start the engine with {self.python}")
            self._set_state("crashed")
