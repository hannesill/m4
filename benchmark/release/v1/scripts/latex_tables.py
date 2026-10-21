"""Write the booktabs LaTeX tables used by the release metadata script."""

from __future__ import annotations

from pathlib import Path


class LatexCell(str):
    """A table cell that is already valid LaTeX and must not be escaped."""


def latex_escape(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def write_table(
    path: Path, headers: list[str], rows: list[list[object]], align: str
) -> None:
    lines = [rf"\begin{{tabular}}{{{align}}}", r"\toprule"]
    lines.append(" & ".join(latex_escape(h) for h in headers) + r" \\")
    lines.append(r"\midrule")
    for row in rows:
        lines.append(" & ".join(latex_escape(cell) for cell in row) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    path.write_text("\n".join(lines))


def write_transposed_table(
    path: Path, fields: list[str], campaigns: list[list[object]]
) -> None:
    """Write one row per field and one column per campaign.

    Each campaign list starts with its label. Two campaigns with many fields
    fit the text width this way without scaling the type down.
    """
    header = ["", *(campaign[0] for campaign in campaigns)]
    rows = [
        [field, *(campaign[i] for campaign in campaigns)]
        for i, field in enumerate(fields, start=1)
    ]
    write_table(path, header, rows, "l" + "r" * len(campaigns))
