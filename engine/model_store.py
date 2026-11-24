"""Model weights: download once into Timbre's own folder, verified and resumable.

Layout:  <models_dir>/<repo name>/
             model.safetensors, config.json, ...      plain files (no symlinks)
             <file>.part                               in-progress download (resumable)
             .timbre-model.json                        written last, after verification

Once the marker exists, loading never touches the network.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

MARKER = ".timbre-model.json"
SKIP_PREFIXES = ("figures/",)
SKIP_SUFFIXES = (".pdf", ".md", ".gitattributes")
CHUNK = 1 << 20
RETRIES = 6


class DownloadCancelled(Exception):
    pass


@dataclass
class RemoteFile:
    name: str
    size: int
    sha256: str | None      # present for LFS files


def model_folder(models_dir: str | os.PathLike, repo_id: str) -> Path:
    return Path(models_dir) / repo_id.split("/")[-1]


def is_complete(folder: Path) -> bool:
    marker = folder / MARKER
    if not marker.is_file():
        return False
    try:
        info = json.loads(marker.read_text(encoding="utf-8"))
        return all((folder / f["name"]).is_file() and (folder / f["name"]).stat().st_size == f["size"]
                   for f in info["files"])
    except Exception:
        return False


def _remote_files(repo_id: str) -> tuple[str, list[RemoteFile]]:
    from huggingface_hub import HfApi
    info = HfApi().model_info(repo_id, files_metadata=True)
    files = []
    for s in info.siblings:
        name = s.rfilename
        if name.startswith(SKIP_PREFIXES) or name.endswith(SKIP_SUFFIXES):
            continue
        lfs = s.lfs
        sha = (lfs.get("sha256") if isinstance(lfs, dict) else getattr(lfs, "sha256", None)) if lfs else None
        files.append(RemoteFile(name, int(s.size or 0), sha))
    return info.sha, files


def _hf_cache_copy(repo_id: str, revision: str, name: str) -> Path | None:
    """A file from the standard Hugging Face cache, if that revision is already there."""
    try:
        from huggingface_hub import constants
        snap = Path(constants.HF_HUB_CACHE) / ("models--" + repo_id.replace("/", "--")) / "snapshots" / revision
        path = snap / name
        return path if path.is_file() else None
    except Exception:
        return None


class _Meter:
    """Aggregate progress across files with a smoothed speed and ETA."""

    def __init__(self, total: int, emit: Callable[[float, str], None], cancel: threading.Event):
        self.total = max(total, 1)
        self.done = 0
        self.emit = emit
        self.cancel = cancel
        self.samples: list[tuple[float, int]] = []
        self.last = 0.0
        self.verb = "Downloading model"

    def add(self, n: int) -> None:
        if self.cancel.is_set():
            raise DownloadCancelled()
        self.done += n
        now = time.monotonic()
        if now - self.last < 0.25:
            return
        self.last = now
        self.samples.append((now, self.done))
        self.samples = [s for s in self.samples if now - s[0] <= 8]
        speed = 0.0
        if len(self.samples) > 1:
            (t0, b0), (t1, b1) = self.samples[0], self.samples[-1]
            speed = (b1 - b0) / max(t1 - t0, 1e-6)
        msg = f"{self.verb}  {self.done / 1e9:.2f} / {self.total / 1e9:.2f} GB"
        if speed > 0:
            left = (self.total - self.done) / speed
            eta = f"{int(left // 60)} min {int(left % 60):02d} s" if left >= 60 else f"{int(left)} s"
            msg += f"  ·  {speed / 1e6:.1f} MB/s  ·  {eta} left"
        self.emit(min(self.done / self.total, 0.999), msg)


def _sha256(path: Path, meter: _Meter | None = None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK * 8):
            h.update(chunk)
            if meter and meter.cancel.is_set():
                raise DownloadCancelled()
    return h.hexdigest()


def _download(url: str, dest: Path, rf: RemoteFile, meter: _Meter, headers: dict) -> None:
    import requests
    part = dest.with_name(dest.name + ".part")
    if part.exists() and part.stat().st_size > rf.size:     # stale/corrupt partial
        part.unlink()
    meter.verb = "Resuming model download" if part.exists() else "Downloading model"
    meter.add(part.stat().st_size if part.exists() else 0)  # bytes already on disk count as done
    attempt = 0
    while True:
        have = part.stat().st_size if part.exists() else 0
        try:
            if have < rf.size:
                h = dict(headers)
                if have:
                    h["Range"] = f"bytes={have}-"
                with requests.get(url, headers=h, stream=True, timeout=(15, 60), allow_redirects=True) as r:
                    if have and r.status_code == 200:      # server ignored Range: start over
                        meter.done -= have
                        have = 0
                        part.unlink(missing_ok=True)
                    elif r.status_code not in (200, 206):
                        r.raise_for_status()
                    with open(part, "ab") as f:
                        for chunk in r.iter_content(CHUNK):
                            f.write(chunk)
                            meter.add(len(chunk))
            if part.stat().st_size != rf.size:
                raise IOError(f"{rf.name}: got {part.stat().st_size} of {rf.size} bytes")
            break
        except DownloadCancelled:
            raise
        except Exception as exc:
            attempt += 1
            if attempt > RETRIES:
                raise IOError(f"Downloading {rf.name} failed after {RETRIES} retries: {exc}") from exc
            # Progress already counted for bytes that are still on disk; nothing to undo.
            wait = min(2 ** attempt, 30)
            meter.emit(meter.done / meter.total, f"Connection problem, retrying in {wait} s ({attempt}/{RETRIES})")
            for _ in range(wait * 10):
                if meter.cancel.is_set():
                    raise DownloadCancelled()
                time.sleep(0.1)
    if rf.sha256:
        meter.emit(meter.done / meter.total, f"Verifying {rf.name}")
        if _sha256(part, meter) != rf.sha256:
            part.unlink(missing_ok=True)
            raise IOError(f"{rf.name} failed its checksum and was deleted. Try again.")
    os.replace(part, dest)


def ensure(repo_id: str, models_dir: str, emit: Callable[[float, str], None],
           cancel: threading.Event) -> str:
    """Return a complete local folder for repo_id, downloading what is missing."""
    folder = model_folder(models_dir, repo_id)
    if is_complete(folder):
        return str(folder)

    emit(0.0, "Checking the model on Hugging Face")
    try:
        revision, files = _remote_files(repo_id)
    except Exception as exc:
        raise ConnectionError(
            "Couldn't reach Hugging Face to download the model (about 3 GB, needed once). "
            f"Check your internet connection and try again. ({exc.__class__.__name__})") from exc

    folder.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(folder).free
    needed = sum(f.size for f in files if not ((folder / f.name).is_file()
                                              and (folder / f.name).stat().st_size == f.size))
    if needed > free:
        raise OSError(f"Not enough disk space in {folder}: the model needs {needed / 1e9:.1f} GB, "
                      f"{free / 1e9:.1f} GB free. Choose another model folder in Settings.")

    from huggingface_hub import hf_hub_url
    from huggingface_hub.utils import build_hf_headers
    headers = build_hf_headers()
    total = sum(f.size for f in files)
    meter = _Meter(total, emit, cancel)

    for rf in files:
        dest = folder / rf.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file() and dest.stat().st_size == rf.size:
            meter.add(rf.size)
            continue
        cached = _hf_cache_copy(repo_id, revision, rf.name)
        if cached and cached.stat().st_size == rf.size:
            meter.verb = "Copying model from the Hugging Face cache"
            part = dest.with_name(dest.name + ".part")
            with open(cached, "rb") as src, open(part, "wb") as out:
                while chunk := src.read(CHUNK * 8):
                    out.write(chunk)
                    meter.add(len(chunk))
            if rf.sha256 and _sha256(part, meter) != rf.sha256:
                part.unlink(missing_ok=True)       # bad cache copy: fall back to downloading
                meter.done -= rf.size
            else:
                os.replace(part, dest)
                continue
        _download(hf_hub_url(repo_id, rf.name, revision=revision), dest, rf, meter, headers)

    (folder / MARKER).write_text(json.dumps({
        "repo_id": repo_id, "revision": revision,
        "files": [{"name": f.name, "size": f.size, "sha256": f.sha256} for f in files],
        "completed": time.time()}, indent=2), encoding="utf-8")
    emit(1.0, "Model ready")
    return str(folder)
