"""The raw files M4 converts into tables: CSV, gzipped (.csv.gz) or plain (.csv).

PhysioNet ships .csv.gz, and M4 downloads only those; a researcher's own
export is often plain .csv. Every place that looks for raw files asks here, so
that conversion, resuming it, and reporting a dataset's state agree.
"""

from pathlib import Path

RAW_SUFFIXES = (".csv.gz", ".csv")


def raw_files(root: Path) -> list[Path]:
    """The raw files at or below `root`, sorted."""
    return sorted(
        path
        for suffix in RAW_SUFFIXES
        for path in root.rglob(f"*{suffix}")
        if path.is_file()
    )


def has_raw_files(root: Path) -> bool:
    """Whether any raw file lies at or below `root`."""
    return any(
        path.is_file() for suffix in RAW_SUFFIXES for path in root.rglob(f"*{suffix}")
    )


def raw_stem(name: str) -> str:
    """`name` without its raw-file suffix: labs for labs.csv.gz and for labs.csv."""
    for suffix in RAW_SUFFIXES:
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return name
