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
        r"\begin{tabular}{p{0.38\textwidth}p{0.28\textwidth}rr}",
        r"\toprule",
        r"Archive & Contents & Runs & Bytes \\",
    ]
    for stem, contents in PACKAGES:
        sidecar = json.loads(
            (args.package_dir / f"{stem}.tar.zst.manifest.json").read_text()
        )
        archive = sidecar["archive"]
        # Monospace names do not hyphenate; split them explicitly. The digest
        # gets a row of its own so that it stays on one line at text size.
        head, tail = archive["filename"].split("-evidence-")
        lines += [
            r"\midrule",
            rf"\texttt{{{head}-evidence-}}\newline\texttt{{{tail}}} & \raggedright {contents} & "
            rf"{sidecar['counts']['run directories']:,} & {archive['size_bytes']:,} \\",
            rf"\multicolumn{{4}}{{l}}{{SHA-256: \texttt{{{archive['sha256']}}}}} \\",
        ]
    lines += [r"\bottomrule", r"\end{tabular}", ""]
    output = PAPER_DIR / "tables" / "evidence_packages.tex"
    output.write_text("\n".join(lines))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
