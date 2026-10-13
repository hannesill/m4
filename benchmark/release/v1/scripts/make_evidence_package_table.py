#!/usr/bin/env python3
"""Write the evidence-package checksum table from the archive sidecars."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

PAPER_DIR = Path(
    os.environ.get("M4BENCH_PAPER_DIR", Path(__file__).resolve().parents[1])
).resolve()
PACKAGES = [
    (
        "m4bench-evidence-submission",
        "Submitted campaigns (Codex primary, Codex follow-up, Claude sentinel, OSS)",
    ),
    ("m4bench-evidence-claude-replication", "Full-coverage Claude replication"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "package_dir", type=Path, help="Directory with the archive sidecars."
    )
    args = parser.parse_args()
    lines = [
        r"\begin{tabular}{p{0.38\textwidth}p{0.24\textwidth}rrl}",
        r"\toprule",
        r"Archive & Contents & Runs & Bytes & SHA-256 \\",
        r"\midrule",
    ]
    for stem, contents in PACKAGES:
        sidecar = json.loads(
            (args.package_dir / f"{stem}.tar.zst.manifest.json").read_text()
        )
        archive = sidecar["archive"]
        digest = archive["sha256"]
        # Monospace names and digests do not hyphenate; split them explicitly.
        head, tail = archive["filename"].split("-evidence-")
        lines.append(
            rf"\texttt{{{head}-evidence-}}\newline\texttt{{{tail}}} & {contents} & "
            rf"{sidecar['counts']['run directories']:,} & {archive['size_bytes']:,} & "
            rf"\shortstack[l]{{\texttt{{{digest[:32]}}}\\\texttt{{{digest[32:]}}}}} \\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", ""]
    output = PAPER_DIR / "tables" / "evidence_packages.tex"
    output.write_text("\n".join(lines))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
