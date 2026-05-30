from __future__ import annotations

from pathlib import Path
from shlex import quote
from typing import Any

from m4.config import ensure_custom_datasets_loaded, resolve_runtime_context
from m4.console import console
from m4.core.datasets import DatasetDefinition, DatasetRegistry
from m4.data_io import DatasetDownloadError, PhysioNetCredentials, download_dataset
from m4.services.events import EventReporter, get_event_reporter
from m4.services.results import (
    ERROR_DATASET_NOT_FOUND,
    ERROR_INVALID_OPTION,
    CommandError,
    CommandResult,
)


class _quiet_console:
    def __enter__(self) -> None:
        self.previous_quiet = console.quiet
        console.quiet = True

    def __exit__(self, *args: object) -> None:
        console.quiet = self.previous_quiet


def default_raw_root(dataset_name: str) -> Path:
    ctx = resolve_runtime_context()
    return ctx.data_dir / "raw_files" / dataset_name.lower()


def expected_raw_subdirectories(ds: DatasetDefinition) -> list[str]:
    return list(ds.expected_raw_subdirectories or ds.subdirectories_to_scan)


def build_wget_command(ds: DatasetDefinition, target: Path) -> str:
    if not ds.file_listing_url:
        return ""
    return (
        "wget -r -N -c -np --cut-dirs=2 -nH "
        "--user YOUR_USERNAME --ask-password "
        f"{quote(ds.file_listing_url)} -P {quote(str(target))}"
    )


def validate_raw_layout(dataset_name: str, root: Path) -> dict[str, Any]:
    ensure_custom_datasets_loaded()
    ds = DatasetRegistry.get(dataset_name.lower())
    warnings: list[str] = []
    errors: list[str] = []
    recovery: list[str] = []

    if not ds:
        return {
            "ok": False,
            "warnings": [],
            "errors": [f"Unknown dataset: {dataset_name}"],
            "csv_gz_count": 0,
            "empty_csv_gz": [],
            "recovery": [],
        }

    if not root.exists():
        return {
            "ok": False,
            "warnings": [],
            "errors": [f"Raw root does not exist: {root}"],
            "csv_gz_count": 0,
            "empty_csv_gz": [],
            "recovery": ["Run the generated wget command, then retry m4 download."],
        }

    nested_markers = [
        root / "physionet.org" / "files",
        root / "files" / "mimiciv",
        root / "files" / "mimic-iv-note",
        root / "files" / "eicu-crd",
    ]
    if any(path.exists() for path in nested_markers):
        warnings.append("nested_physionet_layout")
        recovery.append(
            "Move the dataset contents up to the raw root or rerun wget with --cut-dirs=2 -nH."
        )

    csv_files = sorted(root.rglob("*.csv.gz"))
    empty_files = [str(path) for path in csv_files if path.stat().st_size == 0]
    if empty_files:
        warnings.append("empty_csv_gz")
        recovery.append("Delete empty *.csv.gz files and rerun the resumable download.")

    expected_dirs = expected_raw_subdirectories(ds)
    missing_dirs = [name for name in expected_dirs if not (root / name).is_dir()]
    if missing_dirs:
        warnings.append("missing_required_subdirectories")
        errors.append(
            "Missing required raw subdirectories: " + ", ".join(sorted(missing_dirs))
        )
        recovery.append(
            "Confirm the target root and rerun the dataset-specific wget command."
        )

    if ds.name == "eicu":
        root_csv_count = len(list(root.glob("*.csv.gz")))
        if root_csv_count == 0 and csv_files:
            warnings.append("wrong_eicu_root_layout")
            recovery.append(
                "eICU CSV files should be directly under the eicu raw root, not nested."
            )

    if not csv_files:
        errors.append("No *.csv.gz files found.")
        recovery.append("Download the raw CSV files before initializing DuckDB.")

    if expected_dirs and csv_files and missing_dirs:
        warnings.append("partial_download")

    return {
        "ok": not errors and not empty_files,
        "warnings": sorted(set(warnings)),
        "errors": errors,
        "csv_gz_count": len(csv_files),
        "empty_csv_gz": empty_files,
        "recovery": recovery,
    }


def _download_guidance_data(
    ds: DatasetDefinition, dataset_key: str, target_root: Path
) -> dict[str, Any]:
    access_url = ds.dua_url or ds.dataset_page_url or ds.file_listing_url
    return {
        "dataset": dataset_key,
        "target": str(target_root),
        "requires_authentication": ds.requires_authentication,
        "file_listing_url": ds.file_listing_url,
        "wget_command": build_wget_command(ds, target_root) or None,
        "layout": validate_raw_layout(dataset_key, target_root),
        "recovery_hints": [
            "If conversion fails, rerun m4 download and then m4 init with --force.",
            "If DuckDB is locked, stop MCP servers or notebooks using the database.",
            "For BigQuery errors, verify gcloud application-default credentials and M4_PROJECT_ID.",
        ],
        "access_url": access_url,
    }


def download_dataset_service(
    dataset_name: str,
    *,
    target: str | None = None,
    command_only: bool = False,
    physionet_credentials: PhysioNetCredentials | None = None,
    event_reporter: EventReporter | None = None,
) -> CommandResult | CommandError:
    dataset_key = dataset_name.lower()
    ensure_custom_datasets_loaded()
    ds = DatasetRegistry.get(dataset_key)
    if not ds:
        supported = ", ".join(ds.name for ds in DatasetRegistry.list_all())
        return CommandError(
            command="download",
            code=ERROR_DATASET_NOT_FOUND,
            message=f"Dataset '{dataset_name}' is not supported or not configured.",
            hint=f"Supported datasets: {supported}",
        )

    target_root = (
        Path(target).expanduser().resolve() if target else default_raw_root(dataset_key)
    )
    data = _download_guidance_data(ds, dataset_key, target_root)

    if command_only:
        data["status"] = "command_only"
        return CommandResult(command="download", data=data)

    if ds.requires_authentication and physionet_credentials is None:
        access_url = data["access_url"] or "the dataset provider"
        data["status"] = "blocked"
        data["next_steps"] = [
            f"Confirm PhysioNet access: {access_url}",
            "Run the generated wget command yourself, or pass --physionet-credentials-file to let M4 download.",
            f"Then run: m4 init {dataset_key}",
        ]
        return CommandResult(
            command="download", data=data, warnings=["credentialed_dataset"]
        )

    if not ds.file_listing_url:
        return CommandError(
            command="download",
            code=ERROR_INVALID_OPTION,
            message=f"Dataset '{dataset_key}' does not have a configured download URL.",
        )

    target_root.mkdir(parents=True, exist_ok=True)
    reporter = get_event_reporter(event_reporter)
    try:
        with _quiet_console():
            downloaded = download_dataset(
                dataset_key,
                target_root,
                credentials=physionet_credentials,
                event_reporter=reporter if event_reporter is not None else None,
            )
    except DatasetDownloadError as exc:
        return CommandError(
            command="download",
            code=exc.code,
            message=exc.message,
        )

    if not downloaded:
        return CommandError(
            command="download",
            code=ERROR_INVALID_OPTION,
            message="Download failed. Please check logs for details.",
            hint="Retry the command; downloads are resumable.",
        )

    data["status"] = "completed"
    data["layout"] = validate_raw_layout(dataset_key, target_root)
    return CommandResult(command="download", data=data)
