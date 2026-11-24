"""Timbre inference engine. Started by the UI as a child process:

    python -I engine/worker.py

Reads JSON-lines commands on stdin and answers on stdout (see protocol.py).
Heavy work (model load, synthesis) runs on one job thread so that `cancel`
and `stats` are answered immediately.
"""

from __future__ import annotations

import io
import json
import os
import queue
import sys
import threading
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "vendor" / "ming")]
os.chdir(HERE / "vendor" / "ming")          # Ming resolves a few assets relative to cwd

import protocol  # noqa: E402

sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
protocol._out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
protocol.claim_stdout()
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


def main() -> None:
    protocol.send({"event": "booting"})
    import devices
    from ming_backend import DEFAULT_MODEL, Cancelled, MingBackend

    backend = MingBackend()
    jobs: queue.Queue = queue.Queue()
    cancel = threading.Event()
    protocol.send({"event": "ready", "version": protocol.PROTOCOL_VERSION,
                   "runtime": devices.runtime_info()})

    def run_job(req: dict) -> None:
        rid, cmd = req.get("id"), req.get("cmd")
        emit = lambda f, stage, msg="": protocol.progress(rid, f, stage, msg)  # noqa: E731
        try:
            if cmd == "load":
                status = backend.load(req.get("device", "cpu"), req.get("precision", "fp32"),
                                      req.get("model", DEFAULT_MODEL),
                                      bool(req.get("text_normalization", False)), emit)
                protocol.result(rid, **status)
            elif cmd == "unload":
                backend.unload()
                protocol.result(rid, **backend.status())
            elif cmd == "generate":
                cancel.clear()
                payload = backend.synthesize(req, cancel, lambda f, stage, msg="": emit(f, stage, msg))
                protocol.result(rid, **payload)
        except Cancelled:
            protocol.error(rid, "Generation cancelled.", kind="cancelled")
        except Exception as exc:  # report everything; the UI decides how to show it
            kind = "oom" if "out of memory" in str(exc).lower() else "error"
            if kind == "oom":
                backend.unload()
            protocol.error(rid, str(exc) or exc.__class__.__name__, kind=kind,
                           detail=traceback.format_exc())

    def job_loop() -> None:
        while True:
            req = jobs.get()
            if req is None:
                return
            run_job(req)

    threading.Thread(target=job_loop, daemon=True).start()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            protocol.error(None, f"Malformed request: {line[:200]}")
            continue
        rid, cmd = req.get("id"), req.get("cmd")
        if cmd == "probe":
            devs = devices.list_devices()
            protocol.result(rid, devices=devs, best=devices.best_device(devs)["id"],
                            runtime=devices.runtime_info(), status=backend.status())
        elif cmd == "stats":
            protocol.result(rid, status=backend.status(),
                            memory=devices.memory_stats(backend.device_id or "cpu"))
        elif cmd == "cancel":
            cancel.set()
            protocol.result(rid, ok=True)
        elif cmd == "shutdown":
            break
        elif cmd in ("load", "unload", "generate"):
            jobs.put(req)
        else:
            protocol.error(rid, f"Unknown command {cmd!r}")
    jobs.put(None)


if __name__ == "__main__":
    main()
