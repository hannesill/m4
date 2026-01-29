"""Built-in derived table definitions.

Provides execution order parsing and listing for vendored mimic-code SQL.
The SQL files are organized by clinical category and executed in dependency
order as specified by the upstream duckdb.sql orchestrator.
"""

from __future__ import annotations

import re
from pathlib import Path

# Directory containing vendored SQL files per dataset
_BUILTINS_DIR = Path(__file__).parent

# Mapping from dataset name to builtins subdirectory
_DATASET_DIRS: dict[str, str] = {
    "mimic-iv": "mimic_iv",
}


def get_execution_order(dataset_name: str) -> list[Path]:
    """Parse the duckdb.sql orchestrator to get SQL files in dependency order.

    Reads the vendored duckdb.sql, extracts .read directives,
    and returns the corresponding file paths in execution order.

    Args:
        dataset_name: Name of the dataset (e.g., "mimic-iv").

    Returns:
        List of Path objects pointing to SQL files in execution order.

    Raises:
        ValueError: If the dataset has no built-in derived tables.
        FileNotFoundError: If expected SQL files are missing.
    """
    subdir = _DATASET_DIRS.get(dataset_name)
    if subdir is None:
        supported = ", ".join(sorted(_DATASET_DIRS.keys()))
        raise ValueError(
            f"No built-in derived tables for dataset '{dataset_name}'. "
            f"Supported datasets: {supported}"
        )

    dataset_dir = _BUILTINS_DIR / subdir
    orchestrator = dataset_dir / "duckdb.sql"

    if not orchestrator.exists():
        raise FileNotFoundError(f"Orchestrator file not found: {orchestrator}")

    # Parse .read directives from the orchestrator file
    read_pattern = re.compile(r"^\.read\s+(.+)$")
    sql_files: list[Path] = []

    for line in orchestrator.read_text().splitlines():
        match = read_pattern.match(line.strip())
        if match:
            relative_path = match.group(1).strip()
            sql_path = dataset_dir / relative_path
            if not sql_path.exists():
                raise FileNotFoundError(
                    f"SQL file referenced in orchestrator not found: {sql_path}"
                )
            sql_files.append(sql_path)

    return sql_files


def list_builtins(dataset_name: str) -> list[str]:
    """Return names of available built-in derived tables for a dataset.

    Args:
        dataset_name: Name of the dataset (e.g., "mimic-iv").

    Returns:
        List of table names (e.g., ["age", "sofa", "sepsis3"]).

    Raises:
        ValueError: If the dataset has no built-in derived tables.
    """
    return [path.stem for path in get_execution_order(dataset_name)]
