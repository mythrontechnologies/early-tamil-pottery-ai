"""Environment check for Early Tamil Pottery AI.

Reports what is installed, what is missing, and whether the GPU is usable.
Read-only: installs nothing, changes nothing.

Usage:
    python scripts/check_env.py
"""

from __future__ import annotations

import importlib.metadata as md
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (import name, distribution name, milestone it is needed for)
REQUIRED = [
    ("numpy", "numpy", "M2"),
    ("pandas", "pandas", "M2"),
    ("yaml", "PyYAML", "M1"),
    ("jsonschema", "jsonschema", "M1"),
    ("PIL", "pillow", "M3"),
    ("cv2", "opencv-python", "M3"),
    ("torch", "torch", "M4"),
    ("torchvision", "torchvision", "M4"),
    ("sklearn", "scikit-learn", "M5"),
    ("matplotlib", "matplotlib", "M5"),
    ("streamlit", "streamlit", "M12"),
]

OK, MISSING, WARN = "  OK  ", "MISSING", " WARN "


def _version(dist: str) -> str | None:
    try:
        return md.version(dist)
    except md.PackageNotFoundError:
        return None


def main() -> int:
    print("=" * 68)
    print("Early Tamil Pottery AI - environment check")
    print("=" * 68)
    print(f"Python     : {sys.version.split()[0]}  ({platform.python_implementation()})")
    print(f"Executable : {sys.executable}")
    print(f"Platform   : {platform.platform()}")

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    print(f"Virtualenv : {'yes' if in_venv else 'NO - using a global interpreter'}")
    if not in_venv:
        print("             Recommended: python -m venv .venv && .venv\\Scripts\\activate")

    print("\n-- Packages " + "-" * 56)
    missing = []
    for mod, dist, milestone in REQUIRED:
        ver = _version(dist)
        if ver is None:
            print(f"[{MISSING}] {dist:<18} needed for {milestone}")
            missing.append((dist, milestone))
        else:
            print(f"[{OK}] {dist:<18} {ver}")

    print("\n-- GPU " + "-" * 61)
    try:
        import torch

        cuda = torch.cuda.is_available()
        print(f"torch build     : {torch.__version__}")
        print(f"CUDA available  : {cuda}")
        if cuda:
            print(f"Device          : {torch.cuda.get_device_name(0)}")
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(f"VRAM            : {total:.1f} GiB")
        else:
            if "+cpu" in torch.__version__:
                print("                  This is a CPU-ONLY torch build.")
                print("                  If an NVIDIA GPU is present, reinstall from the CUDA index:")
                print("                  pip install torch torchvision \\")
                print("                      --index-url https://download.pytorch.org/whl/cu126")
            print("                  CPU is fine for M1-M3; M4 training will be slow.")
    except ImportError:
        print("torch not installed - skipped")

    print("\n-- Project " + "-" * 57)
    schema_path = ROOT / "data" / "metadata" / "schema" / "image_record.schema.json"
    if schema_path.exists():
        try:
            from jsonschema import Draft202012Validator

            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            print(
                f"[{OK}] schema valid      v{schema.get('schema_version')}, "
                f"{len(schema['properties'])} fields, {len(schema['required'])} required"
            )
        except ImportError:
            print(f"[{WARN}] schema present but jsonschema not installed - cannot validate")
        except Exception as exc:  # noqa: BLE001 - surface any schema problem verbatim
            print(f"[{MISSING}] schema INVALID: {exc}")
    else:
        print(f"[{MISSING}] schema not found at {schema_path}")

    raw = ROOT / "data" / "raw"
    images = [
        p
        for p in raw.rglob("*")
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
    ]
    records = ROOT / "data" / "metadata" / "records.jsonl"
    n_records = (
        sum(1 for line in records.read_text(encoding="utf-8").splitlines() if line.strip())
        if records.exists()
        else 0
    )
    print(f"[ INFO ] images in data/raw : {len(images)}")
    print(f"[ INFO ] records.jsonl      : {n_records} record(s)")
    if not images:
        print("         Dataset is empty - see docs/DATA_INVENTORY.md. This is expected at M1.")

    print("\n" + "=" * 68)
    if missing:
        print(f"{len(missing)} package(s) missing: " + ", ".join(d for d, _ in missing))
        print("Install with: pip install -r requirements.txt")
        print("(Read the PyTorch/CUDA note at the top of requirements.txt first.)")
    else:
        print("All listed packages present.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
