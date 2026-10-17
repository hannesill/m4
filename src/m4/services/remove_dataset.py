"""Remove what M4 made of a dataset, inside its data directory and nowhere else.

That is the dataset's DuckDB file with what DuckDB and M4 keep beside it, its
Parquet folder, and its raw files where M4 keeps them (`raw_files/<name>`,
which `m4 download` fills; `m4 init --src` reads another folder in place and
copies nothing there). For a custom dataset also its definition. Every path is
resolved, links included, before it is removed: one that leads out of the data
directory, into the folder a dataset was defined from, or to a file another
dataset shares is skipped and reported, never deleted. A database made with
`m4 init --db-path` is recorded nowhere, so it is neither found nor removed.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import duckdb

from m4.config import (
    ensure_custom_datasets_loaded,
    get_custom_datasets_dir,
    get_dataset_storage,
)
from m4.core.datasets import DatasetRegistry
from m4.data_io import _prepared_marker
from m4.services.results import ERROR_DATASET_NOT_FOUND, CommandError, CommandResult

COMMAND = "remove-dataset"

ERROR_INVALID_DATASET_NAME = "invalid_dataset_name"
ERROR_DATASET_IN_USE = "dataset_in_use"
ERROR_REMOVE_FAILED = "remove_failed"

SKIPPED_OUTSIDE_DATA_DIR = "outside_data_dir"
SKIPPED_DATASET_SOURCE = "dataset_source"
SKIPPED_SHARED = "shared_with_another_dataset"
SKIPPED_CONFIGURED = "configured_path"
SKIPPED_NOT_A_DATABASE_FILE = "not_a_database_file"

IN_USE_HINT = (
    "Close the agents, notebooks and M4 servers that use the dataset, then run "
    "this again."
)


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _size(path: Path) -> int:
    """Bytes `path` takes, not following links."""
    if path.is_symlink():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for folder, _, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                total += os.lstat(os.path.join(folder, name)).st_size
            except OSError:
                pass
    return total


def _holds_nothing(path: Path) -> bool:
    """A folder without a file in it, as `m4 status` leaves for every dataset."""
    if path.is_symlink() or not path.is_dir():
        return False
    return not any(files for _, _, files in os.walk(path, followlinks=False))


def _delete(path: Path) -> None:
    # rmtree removes a link it meets inside the folder, not what it leads to
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _definition_files(name: str) -> list[Path]:
    folder = get_custom_datasets_dir()
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and str(data.get("name", "")).lower() == name:
            found.append(path)
    return found


def _locked(db_path: Path) -> bool:
    """Whether another process has the DuckDB file open."""
    try:
        duckdb.connect(str(db_path)).close()
    except duckdb.IOException as exc:
        return "lock" in str(exc).lower()
    except duckdb.Error:
        pass  # Not a database M4 can open: nothing holds it for M4
    return False


def remove_dataset_service(
    dataset_name: str,
    *,
    keep_definition: bool = False,
    dry_run: bool = False,
) -> CommandResult | CommandError:
    """Remove the files M4 made of `dataset_name`, and a custom one's definition.

    A dataset with nothing on disk is removed without error, so a client can
    always clear one that was prepared halfway.
    """
    name = dataset_name.lower()
    if name in {"", ".", ".."} or "/" in name or "\\" in name:
        return CommandError(
            command=COMMAND,
            code=ERROR_INVALID_DATASET_NAME,
            message=f"'{dataset_name}' cannot name a dataset.",
        )
    ensure_custom_datasets_loaded()
    ds = DatasetRegistry.get(name)
    if ds is None:
        return CommandError(
            command=COMMAND,
            code=ERROR_DATASET_NOT_FOUND,
            message=f"There is no dataset '{dataset_name}'.",
            hint="m4 list-datasets --json lists the datasets.",
        )
    builtin = DatasetRegistry.is_builtin(name)
    storage = get_dataset_storage(name)
    data_dir = storage.data_dir.resolve()
    source = Path(ds.defined_from).resolve() if ds.defined_from else None

    planned: list[Path] = []
    skipped: list[dict[str, str]] = []

    def consider(path: Path) -> None:
        if not os.path.lexists(path):
            return
        real = path.resolve()
        if not _inside(real, data_dir):
            reason = SKIPPED_OUTSIDE_DATA_DIR
        elif source and (_inside(source, real) or _inside(real, source)):
            reason = SKIPPED_DATASET_SOURCE
        else:
            planned.append(path)
            return
        skipped.append({"path": str(path), "reason": reason, "resolves_to": str(real)})

    databases = storage.databases_dir.resolve()

    def consider_database_file(path: Path) -> None:
        # Only ever a file of its own in the databases folder, never a folder
        # or a link, whatever the definition names
        if not os.path.lexists(path):
            return
        real = path.resolve()
        if not _inside(real, data_dir):
            reason = SKIPPED_OUTSIDE_DATA_DIR
        elif path.is_symlink() or not path.is_file() or real.parent != databases:
            reason = SKIPPED_NOT_A_DATABASE_FILE
        else:
            planned.append(path)
            return
        skipped.append({"path": str(path), "reason": reason, "resolves_to": str(real)})

    # The database first: it is what another process is most likely to hold.
    db_path = storage.db_path
    sharing = [
        other.name
        for other in DatasetRegistry.list_all()
        if other.name != ds.name
        and other.default_duckdb_filename == ds.default_duckdb_filename
    ]
    if db_path is not None and sharing:
        if os.path.lexists(db_path):
            skipped.append(
                {
                    "path": str(db_path),
                    "reason": SKIPPED_SHARED,
                    "resolves_to": str(db_path.resolve()),
                }
            )
    elif db_path is not None:
        marker = _prepared_marker(db_path)
        for path in (
            db_path,
            db_path.with_name(db_path.name + ".wal"),
            marker,
            marker.with_name(marker.name + ".tmp"),
        ):
            consider_database_file(path)
    consider(storage.parquet_root)
    consider(storage.raw_root)
    for kind, configured in sorted(storage.configured.items()):
        path = Path(configured).expanduser()
        if os.path.lexists(path):
            skipped.append(
                {
                    "path": str(path),
                    "reason": SKIPPED_CONFIGURED,
                    "resolves_to": str(path.resolve()),
                }
            )
    for path in [] if builtin or keep_definition else _definition_files(name):
        consider(path)
    definitions = [path for path in planned if path.parent == get_custom_datasets_dir()]

    def data(removed: list[dict[str, Any]]) -> dict[str, Any]:
        gone = {item["path"] for item in removed}
        return {
            "name": ds.name,
            "builtin": builtin,
            "removed": removed,
            "freed_bytes": sum(item["bytes"] for item in removed),
            "definition_removed": bool(definitions)
            and all(str(path) in gone for path in definitions),
            "source_kept": str(source) if source else None,
            "skipped": skipped,
            "dry_run": dry_run,
        }

    # An empty folder is removed, but it is not something to report
    empty = {path for path in planned if _holds_nothing(path)}
    if dry_run:
        return CommandResult(
            command=COMMAND,
            data=data(
                [{"path": str(p), "bytes": _size(p)} for p in planned if p not in empty]
            ),
        )

    if db_path is not None and db_path in planned and db_path.is_file():
        if _locked(db_path):
            return CommandError(
                command=COMMAND,
                code=ERROR_DATASET_IN_USE,
                message=f"Another process has {db_path} open.",
                hint=IN_USE_HINT,
                data=data([]),
            )

    removed: list[dict[str, Any]] = []
    for path in planned:
        size = _size(path)
        try:
            _delete(path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            # Windows does not remove a file another process has open
            in_use = isinstance(exc, PermissionError) and os.name == "nt"
            return CommandError(
                command=COMMAND,
                code=ERROR_DATASET_IN_USE if in_use else ERROR_REMOVE_FAILED,
                message=(
                    f"Could not remove {path}: {exc}. Removed before it: "
                    f"{len(removed)} path(s)."
                ),
                hint=IN_USE_HINT if in_use else None,
                data=data(removed),
            )
        if path not in empty:
            removed.append({"path": str(path), "bytes": size})

    result = data(removed)
    if result["definition_removed"]:
        DatasetRegistry.unregister(name)
    return CommandResult(command=COMMAND, data=result)
