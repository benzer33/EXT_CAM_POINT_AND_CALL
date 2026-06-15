"""
utils/device_check.py — safe CUDA probe via subprocess.
"""
from __future__ import annotations
import subprocess, sys, textwrap

_CACHED: dict | None = None


def _probe_torch() -> dict:
    code = textwrap.dedent("""
        import json, sys
        try:
            import torch
            cuda_ok = False
            cuda_err = None
            count = 0
            try:
                cuda_ok = torch.cuda.is_available()
                count   = torch.cuda.device_count()
            except Exception as ce:
                cuda_err = str(ce)
            info = {
                "torch": torch.__version__,
                "cuda_available": cuda_ok,
                "cuda_version": torch.version.cuda or "",
                "device_count": count,
                "devices": [{"index": i, "name": torch.cuda.get_device_name(i)} for i in range(count)],
                "cuda_error": cuda_err, "error": None,
            }
        except Exception as e:
            info = {"torch": None, "cuda_available": False, "cuda_version": "",
                    "device_count": 0, "devices": [], "cuda_error": None, "error": str(e)}
        print(json.dumps(info))
    """).strip()
    try:
        result = subprocess.run([sys.executable, "-c", code],
                                capture_output=True, text=True, timeout=30)
        import json
        text = result.stdout.strip()
        if not text:
            return {"torch": None, "cuda_available": False, "cuda_version": "",
                    "device_count": 0, "devices": [], "cuda_error": None,
                    "error": result.stderr.strip() or "no output"}
        return json.loads(text)
    except Exception as e:
        return {"torch": None, "cuda_available": False, "cuda_version": "",
                "device_count": 0, "devices": [], "cuda_error": None,
                "error": f"probe failed: {e}"}


def torch_info(force_refresh: bool = False) -> dict:
    global _CACHED
    if _CACHED is None or force_refresh:
        _CACHED = _probe_torch()
    return _CACHED


def list_devices() -> list[dict]:
    info  = torch_info()
    items = [{"value": "cpu", "label": "CPU  (always available)"}]
    if info.get("cuda_available"):
        for d in info.get("devices", []):
            items.append({"value": f"cuda:{d['index']}",
                          "label": f"CUDA {d['index']}  —  {d['name']}"})
    return items


def install_command_for_gpu() -> str:
    return ("pip install --upgrade torch torchvision torchaudio "
            "--index-url https://download.pytorch.org/whl/cu128")
