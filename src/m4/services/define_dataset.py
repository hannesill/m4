"""Define a custom dataset from a folder of the user's own CSV.gz files.

The definition is inferred from the folder so that `m4 init NAME --src DIR`
builds exactly the tables it names: one schema for files directly in the
folder, one per subfolder that holds files directly, and one table per file.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from collections import defaultdict
from pathlib import Path
from shlex import quote
from typing import Any

import duckdb

from m4.config import get_custom_datasets_dir
from m4.core.datasets import DatasetDefinition, DatasetRegistry
from m4.services.results import CommandError, CommandResult

COMMAND = "define-dataset"

ERROR_INVALID_DATASET_NAME = "invalid_dataset_name"
ERROR_BUILTIN_DATASET = "builtin_dataset"
ERROR_DATASET_EXISTS = "dataset_exists"
ERROR_SOURCE_NOT_FOUND = "source_not_found"
ERROR_SOURCE_NOT_A_DIRECTORY = "source_not_a_directory"
ERROR_RAW_FILES_MISSING = "raw_files_missing"
ERROR_UNCOMPRESSED_CSV_FILES = "uncompressed_csv_files"
ERROR_UNSUPPORTED_LAYOUT = "unsupported_layout"
ERROR_INVALID_TABLE_NAME = "invalid_table_name"
ERROR_TABLE_NAME_COLLISION = "table_name_collision"
ERROR_DEFINITION_WRITE_FAILED = "definition_write_failed"
WARNING_UNCOMPRESSED_CSV_IGNORED = "uncompressed_csv_files_ignored"

DATASET_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
# `m4 init` names a view `schema.table` without quoting it, so a table name
# must be a plain SQL identifier. (A reserved word is fine after the dot.)
TABLE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
CSV_GZ = ".csv.gz"
NAMED = 3  # how many offending files an error message names


def _error(code: str, message: str, hint: str | None = None) -> CommandError:
    return CommandError(command=COMMAND, code=code, message=message, hint=hint)


def _listed(paths: list[str]) -> str:
    more = len(paths) - NAMED
    return ", ".join(paths[:NAMED]) + (f" and {more} more" if more > 0 else "")


def _schema_name(text: str, dataset_name: str) -> str:
    """`text` as a lower-case SQL identifier that DuckDB accepts unquoted.

    It must also differ from the name DuckDB gives the dataset's database,
    its file name up to the first dot (my_export for my_export.duckdb):
    `my_export.admissions` would be ambiguous between the two.
    """
    name = re.sub(r"[^a-z0-9_]", "_", text.lower()) or "_"
    if name[0].isdigit():
        name = f"_{name}"
    with duckdb.connect() as con:
        try:
            con.extract_statements(f"SELECT * FROM {name}.t")
        except duckdb.ParserException:
            name = f"{name}_"  # A reserved word, such as `order`
    database = DatasetDefinition(name=dataset_name).default_duckdb_filename
    if name == database.split(".")[0]:
        name = f"{name}_data"
    return name


def _table_name(csv_gz: Path) -> str:
    """The table `m4 init` makes of `csv_gz`: its lower-case name less .csv.gz."""
    return csv_gz.name[: -len(CSV_GZ)].lower()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _existing_definition_problem(
    name: str, target: Path, force: bool
) -> tuple[CommandError | None, bool]:
    """Whether a definition of `name` is in the way, and whether one is replaced.

    One that `define-dataset` wrote is replaced, so that running it again on a
    corrected folder works. A hand-written one is replaced only with --force.
    One in a file of another name is never replaced: two files defining the
    same dataset would leave it to chance which one M4 reads.
    """
    folder = target.parent
    if not folder.is_dir():
        return None, False
    replaces = False
    for path in sorted(folder.glob("*.json")):
        data = _read_json(path)
        same_file = target.exists() and path.samefile(target)
        defines_name = (
            isinstance(data, dict) and str(data.get("name", "")).lower() == name
        )
        if same_file:
            written_here = isinstance(data, dict) and bool(data.get("defined_from"))
            if not (written_here or force):
                return (
                    _error(
                        ERROR_DATASET_EXISTS,
                        f"{path} holds a definition that was not made by "
                        "m4 define-dataset.",
                        "Pass --force to replace it, or choose another name.",
                    ),
                    False,
                )
            replaces = True
        elif defines_name:
            return (
                _error(
                    ERROR_DATASET_EXISTS,
                    f"'{name}' is already defined by {path}.",
                    "Remove or rename that file, or choose another name.",
                ),
                False,
            )
    return None, replaces


def _deeper_hint(src: Path, files: list[Path]) -> str:
    common = Path(os.path.commonpath([str(path.parent) for path in files]))
    if common != src and all(
        len(path.relative_to(common).parent.parts) <= 1 for path in files
    ):
        return f"Choose {common} instead."
    return (
        "Choose the folder that holds the files, or whose subfolders hold "
        "them, or move the deeper files up."
    )


def _write_atomically(target: Path, definition: dict[str, Any]) -> None:
    """Write `definition` to `target` so that no reader sees half of it.

    The temporary file does not end in .json, so M4 never loads it.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.stem}.{uuid.uuid4().hex}.tmp")
    try:
        with open(temporary, "x", encoding="utf-8") as handle:
            json.dump(definition, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def define_dataset_service(
    dataset_name: str,
    src: str,
    *,
    title: str | None = None,
    summary: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> CommandResult | CommandError:
    """Infer a custom dataset from the CSV.gz files in `src` and save it.

    Writes `<M4 data dir>/datasets/<name>.json` and registers the dataset in
    this process, unless `dry_run`. The files are not converted: that is
    `m4 init <name> --src <src>`.
    """
    name = dataset_name.lower()
    if not DATASET_NAME.match(name):
        return _error(
            ERROR_INVALID_DATASET_NAME,
            f"'{dataset_name}' cannot name a dataset.",
            "Use letters, digits, '.', '_' and '-', starting with a letter or digit.",
        )
    if DatasetRegistry.is_builtin(name):
        return _error(
            ERROR_BUILTIN_DATASET,
            f"'{name}' is one of M4's built-in datasets.",
            "Choose another name.",
        )

    target = get_custom_datasets_dir() / f"{name}.json"
    problem, replaces = _existing_definition_problem(name, target, force)
    if problem:
        return problem

    folder = Path(src).expanduser()
    if not folder.exists():
        return _error(
            ERROR_SOURCE_NOT_FOUND,
            f"{folder} does not exist.",
            "Choose the folder that holds the .csv.gz files.",
        )
    if not folder.is_dir():
        return _error(
            ERROR_SOURCE_NOT_A_DIRECTORY,
            f"{folder} is not a folder.",
            "Choose the folder that holds the .csv.gz files.",
        )
    folder = folder.resolve()

    # The same files `m4 init --src` converts
    csv_gz = sorted(path for path in folder.rglob(f"*{CSV_GZ}") if path.is_file())
    plain_csv = [
        path
        for path in folder.rglob("*")
        if path.name.lower().endswith(".csv") and path.is_file()
    ]
    if not csv_gz:
        if plain_csv:
            return _error(
                ERROR_UNCOMPRESSED_CSV_FILES,
                f"{folder} holds {len(plain_csv)} .csv file(s) but no .csv.gz "
                "files, and M4 converts only .csv.gz files.",
                "Compress them first, for example with: gzip -k *.csv in each "
                "folder, then run this again.",
            )
        return _error(
            ERROR_RAW_FILES_MISSING,
            f"{folder} holds no .csv.gz files.",
            "Choose the folder that holds the .csv.gz files.",
        )

    def relative(path: Path) -> str:
        return path.relative_to(folder).as_posix()

    # `m4 init` makes views of files in the folder and in its subfolders only;
    # it would convert deeper files without making a table of them.
    deeper = [path for path in csv_gz if len(path.relative_to(folder).parts) > 2]
    if deeper:
        return _error(
            ERROR_UNSUPPORTED_LAYOUT,
            f"{len(deeper)} .csv.gz file(s) in {folder} are more than one folder "
            f"deep ({_listed([relative(path) for path in deeper])}), and M4 "
            "makes tables only of files in the folder and in its subfolders.",
            _deeper_hint(folder, csv_gz),
        )

    badly_named = [path for path in csv_gz if not TABLE_NAME.match(_table_name(path))]
    if badly_named:
        return _error(
            ERROR_INVALID_TABLE_NAME,
            f"{len(badly_named)} file name(s) cannot become a table name "
            f"({_listed([relative(path) for path in badly_named])}).",
            "Rename them to letters, digits and underscores, starting with a "
            "letter or underscore (lab results.csv.gz to lab_results.csv.gz), "
            "then run this again.",
        )

    # Mapping keys are folder names as on disk; "" is the folder itself.
    folders = sorted({path.relative_to(folder).parent.as_posix() for path in csv_gz})
    schema_mapping = {
        ("" if key == "." else key): _schema_name(name if key == "." else key, name)
        for key in folders
    }
    tables: dict[str, list[Path]] = defaultdict(list)
    for path in csv_gz:
        key = path.relative_to(folder).parent.as_posix()
        schema = schema_mapping["" if key == "." else key]
        tables[f"{schema}.{_table_name(path)}"].append(path)
    collisions = [paths for paths in tables.values() if len(paths) > 1]
    if collisions:
        return _error(
            ERROR_TABLE_NAME_COLLISION,
            "These files would become the same table: "
            + "; ".join(
                " and ".join(relative(path) for path in paths)
                for paths in collisions[:NAMED]
            )
            + ".",
            "Rename or remove one of each, then run this again.",
        )

    table_names = sorted(tables)
    schemas: dict[str, int] = defaultdict(int)
    for table in table_names:
        schemas[table.split(".", 1)[0]] += 1
    definition = {
        "name": name,
        "title": (title or "").strip() or name,
        "summary": (summary or "").strip() or None,
        "version": None,
        "defined_from": str(folder),
        "modalities": ["TABULAR"],
        "requires_authentication": False,
        "primary_verification_table": table_names[0],
        "schema_mapping": schema_mapping,
        # Not on BigQuery. (Left out, the project would default to physionet-data.)
        "bigquery_project_id": None,
        "bigquery_dataset_ids": [],
        "bigquery_schema_mapping": {},
    }

    if not dry_run:
        try:
            _write_atomically(target, definition)
        except OSError as exc:
            return _error(
                ERROR_DEFINITION_WRITE_FAILED,
                f"Could not write {target}: {exc}",
            )
        DatasetRegistry.load_custom_datasets(target.parent)

    return CommandResult(
        command=COMMAND,
        data={
            "name": name,
            "title": definition["title"],
            "summary": definition["summary"],
            "definition_path": str(target),
            "defined_from": str(folder),
            "schemas": dict(sorted(schemas.items())),
            "tables": table_names,
            "table_count": len(table_names),
            "primary_verification_table": definition["primary_verification_table"],
            "dry_run": dry_run,
            "replaced": replaces,
            "init_command": f"m4 init {name} --src {quote(str(folder))}",
            "definition": definition,
        },
        warnings=[WARNING_UNCOMPRESSED_CSV_IGNORED] if plain_csv else [],
    )
