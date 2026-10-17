from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from shlex import quote
from typing import Any

from m4.config import (
    ensure_custom_datasets_loaded,
    get_active_backend,
    get_dataset_parquet_root,
    get_default_database_path,
    set_active_dataset,  # noqa: F401 - retained for compatibility patch targets
)
from m4.console import console
from m4.core.datasets import DatasetDefinition, DatasetRegistry
from m4.core.derived.builtins import has_derived_support
from m4.core.derived.materializer import get_derived_table_count, materialize_all
from m4.core.raw_files import has_raw_files
from m4.data_io import (
    CONVERSION_NOTE,
    DOWNLOAD_NOTE,
    PHYSIONET_URL_PREFIX,
    CsvConversionError,
    DatasetDownloadError,
    PhysioNetCredentials,
    conversion_out_of_reach,
    convert_csv_to_parquet,
    download_dataset,
    find_raw_root,
    find_unconverted,
    fitting_raw_roots,
    folders_without_tables,
    init_duckdb_from_parquet,
    mark_dataset_prepared,
    unfinished_conversion,
    unfinished_download,
    verify_table_rowcount,
)
from m4.services.download import expected_raw_subdirectories
from m4.services.events import EventReporter, get_event_reporter
from m4.services.results import (
    ERROR_DATASET_NOT_FOUND,
    ERROR_INVALID_OPTION,
    CommandError,
    CommandResult,
)
from m4.services.status import is_ready

STEP_STATUSES = {"skipped", "completed", "blocked", "failed"}


def _step(
    name: str,
    status: str,
    message: str | None = None,
) -> dict[str, str]:
    if status not in STEP_STATUSES:
        raise ValueError(f"Invalid init step status: {status}")
    result = {"name": name, "status": status}
    if message:
        result["message"] = message
    return result


@contextmanager
def _silence_console_output():
    previous_quiet = console.quiet
    console.quiet = True
    try:
        yield
    finally:
        console.quiet = previous_quiet


def _build_data(
    dataset_key: str,
    db_path: Path | None,
    pq_root: Path | None,
    raw_root: Path | None,
    steps: list[dict[str, str]],
    *,
    prepared: bool,
) -> dict:
    return {
        "dataset": dataset_key,
        "db_path": str(db_path.resolve()) if db_path else None,
        "parquet_root": str(pq_root.resolve()) if pq_root else None,
        "raw_root": str(raw_root.resolve()) if raw_root else None,
        "steps": steps,
        "prepared": prepared,
    }


def _download_command(ds: DatasetDefinition, target: Path | None = None) -> str | None:
    """The command that has M4 download `ds`, or None where M4 cannot.

    A PhysioNet login goes to PhysioNet only, so a credentialed dataset that
    lives anywhere else is not M4's to download.
    """
    url = ds.file_listing_url
    if not url or (
        ds.requires_authentication and not url.startswith(PHYSIONET_URL_PREFIX)
    ):
        return None
    command = f"m4 download {ds.name}"
    if target is not None:
        command += f" --target {quote(str(target))}"
    if ds.requires_authentication:
        command += " --physionet-credentials-file <file>"
    return command


def _download_unfinished(
    ds: DatasetDefinition, csv_root: Path, left_behind: str, *, src_given: bool
) -> CommandError:
    """The refusal of raw files whose download did not finish.

    `left_behind` is what says so, as `unfinished_download` names it.
    """
    command = _download_command(ds, csv_root if src_given else None)
    steps = [f"Finish it with: {command}."] if command else []
    if left_behind == DOWNLOAD_NOTE:
        steps.append(
            "If the files have all arrived another way, delete "
            f"{csv_root / DOWNLOAD_NOTE}."
        )
    elif not command:
        steps.append(f"Finish the download of {left_behind.removesuffix('.part')}.")
    return CommandError(
        command="init",
        code="raw_files_missing",
        message=(
            f"The download of '{ds.name}' into {csv_root} did not finish: "
            f"{left_behind} is still there."
        ),
        hint=" ".join(steps),
    )


def _named(tables: list[str] | None, limit: int = 3) -> str:
    """A few of `tables` by name, for a message that speaks of them."""
    if not tables:
        return ""
    names = [table.removesuffix(".parquet") for table in tables[:limit]]
    more = len(tables) - limit
    return f" ({', '.join(names)}{f' and {more} more' if more > 0 else ''})"


def source_problem(
    ds: DatasetDefinition,
    csv_root: Path,
    pq_root: Path,
    *,
    raw_present: bool,
    src_given: bool,
) -> CommandError | None:
    """Why the files at hand cannot become the whole dataset, or None if they can.

    Raw files must sit where the dataset's tables are mapped from and be all
    of the dataset as far as M4 can tell, and Parquet files left by an
    interrupted conversion need the raw files of the tables that are missing.
    """
    source = conversion_out_of_reach(pq_root, csv_root)
    if source is not None:
        unfinished = unfinished_conversion(pq_root)
        return CommandError(
            command="init",
            code="raw_files_missing",
            message=(
                f"The conversion of '{ds.name}' did not finish, and the raw files "
                f"of the tables that are missing{_named(unfinished and unfinished[1])} "
                f"were not found in {csv_root}."
            ),
            hint=(
                f"The conversion read from {source}. Run: m4 init {ds.name} "
                "--src <folder with the raw CSV.gz files>. To go on without "
                f"those tables, delete {pq_root / CONVERSION_NOTE} first."
            ),
        )
    if not raw_present:
        return None

    located = find_raw_root(csv_root, ds.schema_mapping)
    if located is None:
        several = fitting_raw_roots(csv_root, ds.schema_mapping)
        if several:
            return CommandError(
                command="init",
                code="raw_files_missing",
                message=(
                    f"More than one folder in {csv_root} is laid out as "
                    f"'{ds.name}' is, and M4 cannot tell which of them holds it."
                ),
                hint="Choose one of: " + ", ".join(str(folder) for folder in several),
            )
        folders = expected_raw_subdirectories(ds) or [
            folder for folder in ds.schema_mapping if folder
        ]
        return CommandError(
            command="init",
            code="raw_files_missing",
            message=(
                f"The CSV files in {csv_root} are not in the folders "
                f"'{ds.name}' keeps its tables in."
            ),
            hint=(
                "Choose the folder that contains "
                + " and ".join(f"{folder}/" for folder in folders)
                + "."
            ),
        )
    if located != csv_root:
        return CommandError(
            command="init",
            code="raw_files_missing",
            message=f"The '{ds.name}' files are not directly in {csv_root}.",
            hint=(
                f"Choose {located} instead."
                if src_given
                else f"Run: m4 init {ds.name} --src {quote(str(located))}"
            ),
        )

    # The folder is the right one. It must also hold all of the dataset.
    left_behind = unfinished_download(csv_root)
    if left_behind:
        return _download_unfinished(ds, csv_root, left_behind, src_given=src_given)
    if src_given:
        # A folder that was chosen is taken as it is: the dataset may be meant
        # to hold less than all of it.
        return None
    # M4's own raw folder is filled by a download. A folder of the dataset
    # without a file in it, and without tables from an earlier run, is taken
    # for a download that stopped short of it and left nothing to say so.
    empty = folders_without_tables(
        expected_raw_subdirectories(ds), ds.schema_mapping, csv_root, pq_root
    )
    if empty:
        command = _download_command(ds)
        return CommandError(
            command="init",
            code="raw_files_missing",
            message=(
                f"The files in {csv_root} are not all of '{ds.name}': there are "
                "none for " + " and ".join(f"{folder}/" for folder in empty) + "."
            ),
            hint=(
                (f"Fetch them with: {command}. " if command else "")
                + "If these files are all the dataset is to hold, run: "
                f"m4 init {ds.name} --src {quote(str(csv_root))}"
            ),
        )
    return None


def initialize_dataset_service(
    dataset_name: str,
    src: str | None = None,
    db_path_str: str | None = None,
    force: bool = False,
    download: bool = False,
    physionet_credentials: PhysioNetCredentials | None = None,
    event_reporter: EventReporter | None = None,
) -> CommandResult | CommandError:
    """Run the non-interactive dataset initialization workflow."""
    reporter = get_event_reporter(event_reporter)
    dataset_key = dataset_name.lower()
    ensure_custom_datasets_loaded()
    ds = DatasetRegistry.get(dataset_key)
    if not ds:
        supported = ", ".join([d.name for d in DatasetRegistry.list_all()])
        return CommandError(
            command="init",
            code=ERROR_DATASET_NOT_FOUND,
            message=f"Dataset '{dataset_name}' is not supported or not configured.",
            hint=f"Supported datasets: {supported}",
        )

    with _silence_console_output():
        pq_root = get_dataset_parquet_root(dataset_key)
        if pq_root is None:
            return CommandError(
                command="init",
                code=ERROR_INVALID_OPTION,
                message="Could not determine dataset directories.",
            )

        csv_root_default = pq_root.parent.parent / "raw_files" / dataset_key
        csv_root = Path(src).resolve() if src else csv_root_default
        final_db_path = (
            Path(db_path_str).resolve()
            if db_path_str
            else get_default_database_path(dataset_key)
        )

        steps: list[dict[str, str]] = []
        parquet_present = any(pq_root.rglob("*.parquet"))
        raw_present = has_raw_files(csv_root)
        # A download into M4's own raw folder that was cut short is finished
        # before anything is made of the files that did arrive, where the
        # dataset is one M4 downloads. The downloader skips every file that is
        # complete.
        left_behind = unfinished_download(csv_root) if raw_present and not src else None
        finish_download = bool(left_behind and _download_command(ds))
        # Asked to download, M4 also goes over raw files that look whole, where
        # it can.
        resume_download = (
            download
            and raw_present
            and not src
            and bool(ds.file_listing_url)
            and (not ds.requires_authentication or physionet_credentials is not None)
        )

        if (
            finish_download
            or resume_download
            or (not raw_present and not parquet_present)
        ):
            if ds.requires_authentication:
                if not download:
                    if left_behind:
                        return _download_unfinished(
                            ds, csv_root, left_behind, src_given=False
                        )
                    return CommandError(
                        command="init",
                        code="raw_files_missing",
                        message=(
                            f"Files not found for credentialed dataset '{dataset_key}'. "
                            "Pass --download with --physionet-credentials-file or place raw "
                            "CSV.gz files in the expected location."
                        ),
                    )
                if physionet_credentials is None:
                    return CommandError(
                        command="init",
                        code="missing_credentials",
                        message=(
                            f"Dataset '{dataset_key}' requires PhysioNet credentials "
                            "for download."
                        ),
                        hint="Provide --physionet-credentials-file with username and password fields.",
                    )

            listing_url = ds.file_listing_url
            if not listing_url:
                steps.extend(
                    [
                        _step(
                            "raw_files",
                            "blocked",
                            (
                                f"Auto-download is not available for '{dataset_key}'. "
                                "Place raw CSV.gz files in the expected location or use --src."
                            ),
                        ),
                        _step("parquet", "skipped", "Raw files are not available."),
                        _step(
                            "database", "skipped", "Parquet files are not available."
                        ),
                        _step(
                            "derived",
                            "skipped",
                            "Database initialization did not run.",
                        ),
                    ]
                )
                return CommandResult(
                    command="init",
                    data=_build_data(
                        dataset_key,
                        final_db_path,
                        pq_root,
                        csv_root,
                        steps,
                        prepared=False,
                    ),
                    warnings=[],
                )

            csv_root_default.mkdir(parents=True, exist_ok=True)
            try:
                downloaded = download_dataset(
                    dataset_key,
                    csv_root_default,
                    credentials=physionet_credentials,
                    event_reporter=reporter if event_reporter is not None else None,
                )
            except DatasetDownloadError as exc:
                return CommandError(
                    command="init",
                    code=exc.code,
                    message=exc.message,
                )
            if not downloaded:
                return CommandError(
                    command="init",
                    code="download_network_failed",
                    message="Download failed. Please check logs for details.",
                )
            csv_root = csv_root_default
            raw_present = True
            steps.append(_step("raw_files", "completed", "Downloaded raw files."))
        elif raw_present:
            steps.append(_step("raw_files", "completed", "Raw files are present."))
        else:
            steps.append(
                _step("raw_files", "skipped", "Parquet files are already present.")
            )

        problem = source_problem(
            ds, csv_root, pq_root, raw_present=raw_present, src_given=bool(src)
        )
        if problem:
            return problem

        # Conversion is decided per file: Parquet left by an earlier run says
        # nothing about the raw files that run did not get to.
        to_convert = find_unconverted(csv_root, pq_root) if raw_present else []
        conversion_warnings: list[dict[str, Any]] = []
        try:
            converted = not raw_present or convert_csv_to_parquet(
                dataset_key,
                csv_root,
                pq_root,
                event_reporter=reporter if event_reporter is not None else None,
                warnings=conversion_warnings,
            )
        except CsvConversionError as exc:
            return CommandError(
                command="init", code=exc.code, message=exc.message, hint=exc.hint
            )
        if not converted:
            return CommandError(
                command="init",
                code="conversion_failed",
                message="Conversion failed. Please check logs for details.",
            )
        if to_convert:
            steps.append(_step("parquet", "completed", "Converted CSV to Parquet."))
        else:
            steps.append(_step("parquet", "skipped", "Parquet files are present."))

        if not final_db_path:
            return CommandError(
                command="init",
                code=ERROR_INVALID_OPTION,
                message=f"Could not determine database path for '{dataset_name}'.",
            )

        final_db_path.parent.mkdir(parents=True, exist_ok=True)
        if force and final_db_path.exists():
            final_db_path.unlink()

        if not pq_root.exists():
            return CommandError(
                command="init",
                code=ERROR_INVALID_OPTION,
                message=f"Parquet directory not found at {pq_root}",
            )

        init_kwargs = {
            "dataset_name": dataset_key,
            "db_target_path": final_db_path,
        }
        if event_reporter is not None:
            init_kwargs["event_reporter"] = reporter
        try:
            views_created = init_duckdb_from_parquet(**init_kwargs)
        except Exception as exc:
            return CommandError(
                command="init",
                code="duckdb_init_failed",
                message=f"Could not create the views for '{dataset_name}': {exc}",
                hint=(
                    None
                    if raw_present
                    else (
                        "If a Parquet file is damaged, convert it again: "
                        f"m4 init {dataset_key} --src <folder with the raw CSV.gz files>"
                    )
                ),
            )
        if not views_created:
            return CommandError(
                command="init",
                code="duckdb_init_failed",
                message=(
                    f"Dataset '{dataset_name}' initialization FAILED. "
                    "Please check logs for details."
                ),
            )
        steps.append(_step("database", "completed", "Created DuckDB views."))

        verification_table_name = ds.primary_verification_table
        if verification_table_name:
            try:
                record_count = verify_table_rowcount(
                    final_db_path, verification_table_name
                )
                reporter.emit(
                    "verification_completed",
                    table=verification_table_name,
                    row_count=record_count,
                )
                steps.append(
                    _step(
                        "verification",
                        "completed",
                        f"Verified {record_count} records in '{verification_table_name}'.",
                    )
                )
            except Exception as exc:
                steps.append(
                    _step("verification", "failed", f"Verification failed: {exc}")
                )
                return CommandError(
                    command="init",
                    code="verification_failed",
                    message=f"Verification failed: {exc}",
                )
        else:
            steps.append(
                _step("verification", "skipped", "No verification table configured.")
            )

        # Every raw file has its table and the views answer: only now is the
        # dataset reported as ready.
        try:
            mark_dataset_prepared(pq_root, final_db_path)
        except OSError as exc:
            return CommandError(
                command="init",
                code="duckdb_init_failed",
                message=f"Could not record that '{dataset_name}' is ready: {exc}",
            )

        if has_derived_support(dataset_key) and get_active_backend() == "duckdb":
            try:
                existing_derived = get_derived_table_count(final_db_path)
            except Exception as exc:
                steps.append(
                    _step(
                        "derived", "failed", f"Could not inspect derived tables: {exc}"
                    )
                )
            else:
                if existing_derived > 0 and force:
                    try:
                        created = materialize_all(dataset_key, final_db_path)
                        steps.append(
                            _step(
                                "derived",
                                "completed",
                                f"Materialized {len(created)} derived tables.",
                            )
                        )
                    except Exception as exc:
                        steps.append(
                            _step(
                                "derived",
                                "failed",
                                f"Derived table materialization failed: {exc}",
                            )
                        )
                elif existing_derived > 0:
                    steps.append(
                        _step(
                            "derived",
                            "skipped",
                            (
                                f"Derived tables already materialized "
                                f"({existing_derived} tables)."
                            ),
                        )
                    )
                else:
                    steps.append(
                        _step(
                            "derived",
                            "skipped",
                            "Derived materialization is skipped in non-interactive mode.",
                        )
                    )
        else:
            steps.append(
                _step(
                    "derived",
                    "skipped",
                    "Derived materialization is not available for this configuration.",
                )
            )

        return CommandResult(
            command="init",
            data={
                **_build_data(
                    dataset_key,
                    final_db_path,
                    pq_root,
                    csv_root,
                    steps,
                    # As status reports it, which is not always true by now: M4
                    # reads a dataset from its default database, not from one
                    # made with --db-path, and a raw file may have come into its
                    # own raw folder that this run did not convert.
                    prepared=is_ready(dataset_key),
                ),
                # How files of this run were read where it was not plain UTF-8
                # CSV: each has `code`, `file`, and for decimal commas `columns`
                "conversion_warnings": conversion_warnings,
            },
            warnings=sorted({warning["code"] for warning in conversion_warnings}),
        )
