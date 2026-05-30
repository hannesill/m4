#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "src" / "m4" / "apps" / "cohort_builder" / "ui"
PACKAGED_HTML = ROOT / "src" / "m4" / "apps" / "cohort_builder" / "mcp-app.html"


def normalize_html(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that the packaged cohort-builder app matches a fresh Vite build."
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Replace the tracked packaged HTML with a fresh build.",
    )
    args = parser.parse_args()

    if shutil.which("npm") is None:
        print("npm is required to check the cohort-builder UI bundle.", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="m4-cohort-builder-") as tmp:
        out_dir = Path(tmp)
        env = os.environ.copy()
        env["M4_COHORT_BUILDER_OUT_DIR"] = str(out_dir)
        subprocess.run(["npm", "run", "build"], cwd=UI_DIR, env=env, check=True)
        built_html = out_dir / "mcp-app.html"
        if not built_html.exists():
            print(f"Vite build did not create {built_html}", file=sys.stderr)
            return 1

        built = normalize_html(built_html.read_text())
        packaged = normalize_html(PACKAGED_HTML.read_text())
        if args.update:
            PACKAGED_HTML.write_text(built)
            return 0
        if built != packaged:
            print(
                "Packaged cohort-builder HTML is stale. "
                "Run: uv run python scripts/check_cohort_builder_bundle.py --update",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
