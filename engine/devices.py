"""Compute-device discovery inside the engine (torch level).

Reports every device that the installed PyTorch build can actually use:
  * CUDA devices: NVIDIA on CUDA builds, AMD Radeon on ROCm builds (torch.version.hip)
  * Intel XPU devices: Arc / Core Ultra graphics on XPU builds
  * DirectML adapters: any DirectX 12 GPU when torch-directml is installed
  * CPU: always available
"""

from __future__ import annotations

import os
import platform

import torch


def _cpu_name() -> str:
    name = platform.processor() or "CPU"
    try:  # the registry has the marketing name on Windows
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    except Exception:
        pass
    return name


def _total_ram() -> int | None:
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return int(stat.ullTotalPhys)
    except Exception:
        return None


def list_devices() -> list[dict]:
    devices: list[dict] = []

    if torch.cuda.is_available():
        backend = "rocm" if getattr(torch.version, "hip", None) else "cuda"
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            try:
                free, total = torch.cuda.mem_get_info(i)
            except Exception:
                free, total = None, props.total_memory
            try:
                bf16 = torch.cuda.is_bf16_supported()
            except Exception:
                bf16 = False
            cap = f"{props.major}.{props.minor}" if backend == "cuda" else getattr(props, "gcnArchName", "")
            devices.append({
                "id": f"cuda:{i}", "kind": "gpu", "backend": backend,
                "name": props.name, "memory_total": total, "memory_free": free,
                "capability": cap,
                "precisions": (["bf16"] if bf16 else []) + ["fp16", "fp32"],
                "recommended_precision": "bf16" if bf16 else "fp32",
            })

    xpu = getattr(torch, "xpu", None)
    if xpu is not None and xpu.is_available():
        for i in range(xpu.device_count()):
            props = xpu.get_device_properties(i)
            devices.append({
                "id": f"xpu:{i}", "kind": "gpu", "backend": "xpu",
                "name": props.name, "memory_total": getattr(props, "total_memory", None),
                "memory_free": None, "capability": "",
                "precisions": ["bf16", "fp16", "fp32"], "recommended_precision": "bf16",
            })

    try:
        import torch_directml  # type: ignore
        for i in range(torch_directml.device_count()):
            devices.append({
                "id": f"privateuseone:{i}", "kind": "gpu", "backend": "directml",
                "name": torch_directml.device_name(i), "memory_total": None, "memory_free": None,
                "capability": "", "precisions": ["fp32"], "recommended_precision": "fp32",
            })
    except Exception:
        pass

    devices.append({
        "id": "cpu", "kind": "cpu", "backend": "cpu", "name": _cpu_name(),
        "memory_total": _total_ram(), "memory_free": None,
        "capability": f"{os.cpu_count()} threads",
        "precisions": ["bf16", "fp32"], "recommended_precision": "fp32",
    })
    return devices


def best_device(devices: list[dict]) -> dict:
    """Largest-memory GPU first (CUDA/ROCm > XPU > DirectML), CPU last."""
    rank = {"cuda": 0, "rocm": 0, "xpu": 1, "directml": 2, "cpu": 9}
    return sorted(devices, key=lambda d: (rank.get(d["backend"], 5), -(d["memory_total"] or 0)))[0]


def runtime_info() -> dict:
    return {
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "hip": getattr(torch.version, "hip", None),
        "xpu": bool(getattr(torch, "xpu", None) and torch.xpu.is_available()),
        "python": platform.python_version(),
    }


def memory_stats(device_id: str) -> dict:
    if device_id.startswith("cuda") and torch.cuda.is_available():
        idx = torch.device(device_id).index or 0
        free, total = torch.cuda.mem_get_info(idx)
        return {"allocated": torch.cuda.memory_allocated(idx),
                "peak": torch.cuda.max_memory_allocated(idx),
                "free": free, "total": total}
    if device_id.startswith("xpu"):
        idx = torch.device(device_id).index or 0
        return {"allocated": torch.xpu.memory_allocated(idx),
                "peak": torch.xpu.max_memory_allocated(idx), "free": None, "total": None}
    return {}


def resolve_dtype(precision: str):
    return {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}[precision]


def to_torch_device(device_id: str):
    if device_id.startswith("privateuseone"):
        import torch_directml  # type: ignore
        return torch_directml.device(int(device_id.split(":")[1]))
    return device_id
