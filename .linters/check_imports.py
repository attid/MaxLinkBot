#!/usr/bin/env python3
"""
Architecture boundary test: verifies import direction rules.

Rules:
- domain/ may not import from application/, infrastructure/, interface/
- application/ may not import from infrastructure/, interface/
- infrastructure/ may import from other infrastructure/ only
- interface/ may import from application/ and infrastructure/
"""

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent / "src"

# Layer name -> allowed parent layers
LAYER_RULES = {
    "domain": {"domain"},
    "application": {"domain", "application"},
    "infrastructure": {"application", "infrastructure"},
    "interface": {"application", "infrastructure", "interface"},
}

LAYER_ALIASES = {
    "src/domain": "domain",
    "src/application": "application",
    "src/infrastructure": "infrastructure",
    "src/interface": "interface",
}


def detect_layer(path: Path) -> str | None:
    rel = str(path.relative_to(PROJECT_ROOT.parent))
    for prefix, layer in LAYER_ALIASES.items():
        if f"/{prefix}/" in rel or rel.startswith(prefix + "/") or rel == prefix:
            return layer
    return None


def check_file(filepath: Path) -> list[str]:
    errors = []
    try:
        source = filepath.read_text()
        tree = ast.parse(source, filename=str(filepath))
    except Exception as e:
        return [f"PARSE ERROR {filepath}: {e}"]

    current_layer = detect_layer(filepath)
    if current_layer is None:
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                if mod in ("src", "domain", "application", "infrastructure", "interface"):
                    target_layer = mod if mod != "src" else None
                    if target_layer and target_layer not in LAYER_RULES.get(current_layer, set()):
                        errors.append(
                            f"VIOLATION: {filepath}: {current_layer} imports {target_layer}. "
                            f"Not allowed."
                        )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            first = mod.split(".")[0]
            if first in ("src", "domain", "application", "infrastructure", "interface"):
                target_layer = first if first != "src" else None
                if target_layer and target_layer not in LAYER_RULES.get(current_layer, set()):
                    errors.append(
                        f"VIOLATION: {filepath}: {current_layer} imports from {target_layer}. "
                        f"Not allowed."
                    )

    return errors


def main() -> int:
    errors = []
    for src_file in PROJECT_ROOT.rglob("*.py"):
        errors.extend(check_file(src_file))

    if errors:
        print("ARCHITECTURE VIOLATIONS FOUND:")
        for e in errors:
            print(f"  {e}")
        return 1

    print("OK: No architecture violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
