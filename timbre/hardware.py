"""Hardware inventory without PyTorch.

Reads the Windows display-adapter class key, which every GPU driver registers
(NVIDIA, AMD, Intel, Qualcomm, Moore Threads...), including the real VRAM size
(`HardwareInformation.qwMemorySize`; WMI's AdapterRAM is capped at 4 GB).
"""

from __future__ import annotations

import os
import platform
import re
from dataclasses import dataclass

DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"

VENDORS = {
    "10de": "nvidia", "1002": "amd", "1022": "amd", "8086": "intel",
    "5143": "qualcomm", "1ed5": "moorethreads", "1414": "microsoft",
}
VENDOR_LABEL = {"nvidia": "NVIDIA", "amd": "AMD", "intel": "Intel", "qualcomm": "Qualcomm",
                "moorethreads": "Moore Threads", "microsoft": "Microsoft", "other": "Other"}
_VIRTUAL = re.compile(r"basic display|basic render|remote|virtual|parsec|meta|citrix|indirect", re.I)


@dataclass
class Gpu:
    name: str
    vendor: str
    vram: int | None
    driver: str
    integrated: bool

    @property
    def vendor_label(self) -> str:
        return VENDOR_LABEL.get(self.vendor, "Other")


@dataclass
class Cpu:
    name: str
    threads: int
    ram: int | None


def _qword(value) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, (bytes, bytearray)) and len(value) in (4, 8):
        return int.from_bytes(value, "little")
    return None


def gpus() -> list[Gpu]:
    found: list[Gpu] = []
    try:
        import winreg
    except ImportError:
        return found
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, DISPLAY_CLASS)
    except OSError:
        return found
    i = 0
    while True:
        try:
            sub = winreg.EnumKey(root, i)
        except OSError:
            break
        i += 1
        if not sub.isdigit():
            continue
        try:
            key = winreg.OpenKey(root, sub)
        except OSError:
            continue

        def get(name):
            try:
                return winreg.QueryValueEx(key, name)[0]
            except OSError:
                return None

        name = (get("DriverDesc") or "").strip()
        if not name or _VIRTUAL.search(name):
            continue
        match = re.search(r"ven_([0-9a-f]{4})", (get("MatchingDeviceId") or "").lower())
        vendor = VENDORS.get(match.group(1), "other") if match else "other"
        if vendor == "microsoft":
            continue
        vram = _qword(get("HardwareInformation.qwMemorySize")) or _qword(get("HardwareInformation.MemorySize"))
        integrated = vendor == "intel" and not re.search(r"\barc\b", name, re.I) or \
            (vendor == "amd" and re.search(r"radeon\(tm\) graphics|vega \d+ graphics|\b\d{3}m\b", name, re.I) is not None)
        found.append(Gpu(name=name, vendor=vendor, vram=vram, driver=str(get("DriverVersion") or ""),
                         integrated=bool(integrated)))
    # De-duplicate (some drivers register twice)
    unique: dict[str, Gpu] = {}
    for g in found:
        unique.setdefault(g.name, g)
    return sorted(unique.values(), key=lambda g: (g.integrated, -(g.vram or 0)))


def cpu() -> Cpu:
    name = platform.processor()
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    except Exception:
        pass
    ram = None
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + \
                       [(n, ctypes.c_ulonglong) for n in ("t", "a", "tp", "ap", "tv", "av", "ae")]
        s = MEMORYSTATUSEX()
        s.dwLength = ctypes.sizeof(s)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
        ram = int(s.t)
    except Exception:
        pass
    return Cpu(name=name or "CPU", threads=os.cpu_count() or 1, ram=ram)


def recommended_variant(gpu_list: list[Gpu]) -> str:
    """Pick the compute runtime that matches the strongest GPU in the machine."""
    discrete = [g for g in gpu_list if not g.integrated] or gpu_list
    for g in discrete:
        if g.vendor == "nvidia":
            return "cuda"
    for g in discrete:
        if g.vendor == "amd":
            return "rocm"
        if g.vendor == "intel" and not g.integrated:
            return "xpu"
    if any(g.vendor in ("intel", "amd", "qualcomm") for g in gpu_list):
        return "directml"
    return "cpu"


def human_bytes(n: int | None) -> str:
    if not n:
        return "—"
    gb = n / 1024 ** 3
    return f"{gb:.0f} GB" if gb >= 10 else f"{gb:.1f} GB"
