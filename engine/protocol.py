"""JSON-lines protocol between the Timbre UI and the inference engine.

The UI writes one JSON object per line to the engine's stdin:
    {"id": "<request id>", "cmd": "<command>", ...arguments}

The engine writes one JSON object per line to its stdout:
    {"id": "<request id>", "event": "progress" | "result" | "error", ...}
    {"event": "log", "level": "info", "message": "..."}       (no id)
    {"event": "ready", "version": 1}                         (once, on start)

Everything else the libraries print goes to stderr, so stdout stays a clean channel.
"""

from __future__ import annotations

import json
import sys
import threading

PROTOCOL_VERSION = 1

_out = sys.stdout          # the real stdout, reserved for protocol messages
_lock = threading.Lock()


def claim_stdout() -> None:
    """Point sys.stdout at stderr so stray prints cannot corrupt the channel."""
    sys.stdout = sys.stderr


def send(message: dict) -> None:
    line = json.dumps(message, ensure_ascii=False, default=str)
    with _lock:
        _out.write(line + "\n")
        _out.flush()


def log(message: str, level: str = "info") -> None:
    send({"event": "log", "level": level, "message": message})


def progress(req_id: str, fraction: float | None, stage: str, message: str = "", **extra) -> None:
    send({"id": req_id, "event": "progress", "fraction": fraction,
          "stage": stage, "message": message, **extra})


def result(req_id: str, **payload) -> None:
    send({"id": req_id, "event": "result", **payload})


def error(req_id: str | None, message: str, kind: str = "error", detail: str = "") -> None:
    send({"id": req_id, "event": "error", "kind": kind, "message": message, "detail": detail})
