#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "TOOLS.md"
START = "<!-- BEGIN GENERATED DERIVED TABLES -->"
END = "<!-- END GENERATED DERIVED TABLES -->"

CATEGORY_LABELS = {
    "score": "Scores",
    "sepsis": "Sepsis",
    "organfailure": "Organ Failure",
    "medication": "Medications",
    "measurement": "Measurements",
    "demographics": "Demographics",
    "firstday": "First Day",
    "treatment": "Treatment",
    "comorbidity": "Comorbidity",
}

CATEGORY_DESCRIPTIONS = {
    "score": "Severity and mortality prediction scores",
    "sepsis": "Sepsis-3 cohort identification and suspected infection events",
    "organfailure": "KDIGO AKI staging and MELD liver score",
    "medication": "Individual vasopressors, equivalents, and other drug classes",
    "measurement": "Labs, vitals, and clinical measurements",
    "demographics": "Patient demographics and ICU stay metadata",
    "firstday": "Aggregated values from the first 24 hours of ICU admission",
    "treatment": "Mechanical ventilation, renal replacement therapy, and lines",
    "comorbidity": "Charlson comorbidity index",
}


def generated_block() -> str:
    sys.path.insert(0, str(ROOT / "src"))
    from m4.core.derived.builtins import get_tables_by_category

    categories = get_tables_by_category("mimic-iv")
    lines = [
        START,
        "| Category | Tables | Description |",
        "|----------|--------|-------------|",
    ]
    for category, tables in categories.items():
        label = CATEGORY_LABELS.get(category, category.replace("_", " ").title())
        table_list = ", ".join(f"`{table}`" for table in tables)
        description = CATEGORY_DESCRIPTIONS.get(category, "")
        lines.append(f"| **{label}** | {table_list} | {description} |")
    lines.append(END)
    return "\n".join(lines)


def replace_block(text: str, block: str) -> str:
    if START not in text or END not in text:
        raise SystemExit(f"Missing generated derived table markers in {DOC_PATH}")
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    return before + block + after


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update or check the generated derived table docs block."
    )
    parser.add_argument("--check", action="store_true", help="Fail if docs are stale.")
    args = parser.parse_args()

    current = DOC_PATH.read_text()
    expected = replace_block(current, generated_block())
    if args.check:
        if current != expected:
            print(
                "docs/TOOLS.md derived table block is stale. "
                "Run: uv run python scripts/update_derived_docs.py",
                file=sys.stderr,
            )
            return 1
        return 0

    DOC_PATH.write_text(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
