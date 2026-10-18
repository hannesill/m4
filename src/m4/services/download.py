from __future__ import annotations

from pathlib import Path
from shlex import quote
from typing import Any
from urllib.parse import urlparse

from m4.config import ensure_custom_datasets_loaded, resolve_runtime_context
from m4.console import console
from m4.core.datasets import DatasetDefinition, DatasetRegistry
from m4.core.raw_files import RAW_SUFFIXES, raw_files
from m4.data_io import (
    PHYSIONET_URL_PREFIX,
    DatasetDownloadError,
    PhysioNetCredentials,
    download_dataset,
    unfinished_download,
)
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


def access_forbidden_hint(ds: DatasetDefinition) -> str | None:
    """What to do when PhysioNet refuses the login for `ds` (HTTP 403)."""
    url = ds.dua_url or ds.dataset_page_url
    if not url:
        return None
    return (
        f"Sign the data use agreement on {url}. PhysioNet asks for one per "
        "dataset, also of an account with access to others; if it offers none "
        "there, the account first needs credentialing and the required training."
    )


def build_wget_command(ds: DatasetDefinition, target: Path) -> str:
    """The wget command that downloads `ds` into `target`, or "" if M4 has none.

    The command asks for the PhysioNet password, so there is one only for an
    address the PhysioNet login may go to.
    """
    if not ds.file_listing_url or not ds.file_listing_url.startswith(
        PHYSIONET_URL_PREFIX
    ):
        return ""
    path_parts = [
        part for part in urlparse(ds.file_listing_url).path.split("/") if part
    ]
    cut_dirs = len(path_parts)
    # An imaging dataset's listing also holds its images, half a terabyte for
    # MIMIC-CXR-JPG: the command takes the tables beside them only, as M4's
    # own download does. Images are fetched per cohort (m4 fetch-images).
    tables_only = "-l 1 -A '*.csv.gz,*.csv' " if ds.images is not None else ""
    return (
        f"wget -r -N -c -np {tables_only}--cut-dirs={cut_dirs} -nH "
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

    # What `wget -r` leaves without -nH (physionet.org/files/...), or with -nH
    # but without --cut-dirs (files/<project>/...).
    nested_markers = [root / "physionet.org" / "files"]
    listing_parts = [
        part for part in urlparse(ds.file_listing_url or "").path.split("/") if part
    ]
    if len(listing_parts) >= 2:
        nested_markers.append(root / listing_parts[0] / listing_parts[1])
    if any(path.exists() for path in nested_markers):
        warnings.append("nested_physionet_layout")
        recovery.append(
            "Move the dataset contents up to the raw root or rerun wget with the generated --cut-dirs and -nH flags."
        )

    # .csv.gz and plain .csv, as M4 downloads and converts both. The keys keep
    # their names (csv_gz_count, empty_csv_gz) for the wrappers that read them.
    csv_files = raw_files(root)
    empty_files = [str(path) for path in csv_files if path.stat().st_size == 0]
    if empty_files:
        warnings.append("empty_csv_gz")
        recovery.append("Delete empty CSV files and rerun the resumable download.")

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

    if "" in ds.schema_mapping:
        # A dataset without folders of its own, such as eICU or MIMIC-III
        root_csv_count = sum(len(list(root.glob(f"*{s}"))) for s in RAW_SUFFIXES)
        if root_csv_count == 0 and csv_files:
            warnings.append("wrong_root_layout")
            recovery.append(
                f"{ds.name} CSV files should be directly under its raw root, "
                "not nested."
            )

    if not csv_files:
        errors.append("No CSV files (.csv.gz or .csv) found.")
        recovery.append("Download the raw CSV files before initializing DuckDB.")

    if expected_dirs and csv_files and missing_dirs:
        warnings.append("partial_download")

    left_behind = unfinished_download(root)
    if left_behind:
        warnings.append("partial_download")
        errors.append(
            f"A download into this folder did not finish: {left_behind} is still there."
        )
        recovery.append("Finish the download before initializing the dataset.")

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
            (
                "Run the generated wget command yourself, or pass --physionet-credentials-file to let M4 download."
                if data["wget_command"]
                else f"Download the raw CSV.gz files yourself and place them in {target_root}."
            ),
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
            hint=(
                access_forbidden_hint(ds)
                if exc.code == "physionet_access_forbidden"
                else None
            ),
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
