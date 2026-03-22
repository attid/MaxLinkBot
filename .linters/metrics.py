#!/usr/bin/env python3
"""Basic project metrics: file count, line counts per layer."""

from pathlib import Path

ROOT = Path(__file__).parent.parent


def count_lines(p: Path) -> int:
    try:
        return len(p.read_text().splitlines())
    except Exception:
        return 0


layers = {
    "domain": list((ROOT / "src" / "domain").rglob("*.py")),
    "application": list((ROOT / "src" / "application").rglob("*.py")),
    "infrastructure": list((ROOT / "src" / "infrastructure").rglob("*.py")),
    "interface": list((ROOT / "src" / "interface").rglob("*.py")),
}

total_lines = 0
for layer, files in layers.items():
    lc = sum(count_lines(f) for f in files)
    total_lines += lc
    print(f"  {layer:20s}: {len(files):3d} files, {lc:5d} lines")

print(f"  {'TOTAL':20s}: {sum(len(v) for v in layers.values()):3d} files, {total_lines:5d} lines")
