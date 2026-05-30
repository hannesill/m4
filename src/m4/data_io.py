import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import duckdb
import requests
from bs4 import BeautifulSoup

from m4.config import (
    get_dataset_parquet_root,
    get_default_database_path,
    logger,
)
from m4.console import (
    console,
    create_download_progress,
    create_task_progress,
    info,
    success,
)
from m4.core.datasets import DatasetRegistry
from m4.services.events import EventReporter, get_event_reporter
from m4.services.redaction import redact_sensitive, register_sensitive_value

########################################################
# Download functionality
########################################################

COMMON_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)


@dataclass(frozen=True)
class PhysioNetCredentials:
    username: str
    password: str

    @classmethod
    def from_json_file(cls, path: Path) -> "PhysioNetCredentials":
        import json

        payload = json.loads(path.read_text())
        username = payload.get("username") or payload.get("user")
        password = payload.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            raise ValueError(
                "PhysioNet credentials file must contain string username and password fields."
            )
        register_sensitive_value(password)
        return cls(username=username, password=password)


class DatasetDownloadError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(redact_sensitive(message))
        self.code = code
        self.message = str(self)


def _download_error_for_response(
    response: requests.Response, url: str
) -> DatasetDownloadError:
    if response.status_code == 401:
        return DatasetDownloadError(
            "physionet_auth_failed",
            f"PhysioNet authentication failed while accessing {url}.",
        )
    if response.status_code == 403:
        return DatasetDownloadError(
            "physionet_access_forbidden",
            f"PhysioNet access is forbidden for {url}. Confirm DUA access.",
        )
    return DatasetDownloadError(
        "download_network_failed",
        f"HTTP {response.status_code} while downloading {url}: {response.reason}",
    )


def _remote_content_length(
    url: str, session: requests.Session
) -> tuple[int | None, bool]:
    try:
        response = session.head(url, allow_redirects=True, timeout=30)
    except requests.exceptions.RequestException:
        return None, False
    if response.status_code in {401, 403}:
        raise _download_error_for_response(response, url)
    if not (200 <= response.status_code < 300):
        return None, False
    content_length = response.headers.get("content-length")
    accept_ranges = response.headers.get("accept-ranges", "").lower() == "bytes"
    return (
        int(content_length) if content_length and content_length.isdigit() else None
    ), accept_ranges


def _download_single_file(
    url: str,
    target_filepath: Path,
    session: requests.Session,
    progress=None,
    task_id=None,
    event_reporter: EventReporter | None = None,
) -> bool:
    """Downloads a single file with progress tracking."""
    reporter = get_event_reporter(event_reporter)
    logger.debug(f"Attempting to download {url} to {target_filepath}...")
    part_path = target_filepath.with_name(f"{target_filepath.name}.part")
    try:
        remote_size, range_supported = _remote_content_length(url, session)
        if remote_size is not None and target_filepath.exists():
            if target_filepath.stat().st_size == remote_size:
                reporter.emit(
                    "download_file_skipped",
                    url=url,
                    path=str(target_filepath),
                    bytes_total=remote_size,
                    reason="complete",
                )
                return True

        resume_from = part_path.stat().st_size if part_path.exists() else 0
        headers = {}
        mode = "wb"
        if resume_from and range_supported:
            headers["Range"] = f"bytes={resume_from}-"
            mode = "ab"

        response = session.get(url, stream=True, timeout=60, headers=headers)
        if response.status_code in {401, 403}:
            raise _download_error_for_response(response, url)
        if (
            response.status_code == 416
            and remote_size is not None
            and resume_from >= remote_size
        ):
            part_path.replace(target_filepath)
            return True
        if response.status_code == 200 and headers.get("Range"):
            resume_from = 0
            mode = "wb"
        if not (200 <= response.status_code < 300):
            raise _download_error_for_response(response, url)

        response_size = int(response.headers.get("content-length", 0))
        total_size = remote_size or (
            resume_from + response_size if response_size else 0
        )
        file_display_name = target_filepath.name

        target_filepath.parent.mkdir(parents=True, exist_ok=True)

        # Update task description and total if progress bar is provided
        if progress and task_id is not None:
            progress.update(task_id, total=total_size, description=file_display_name)

        reporter.emit(
            "download_file_started",
            url=url,
            path=str(target_filepath),
            bytes_downloaded=resume_from,
            bytes_total=total_size or None,
        )
        downloaded = resume_from
        last_emit = 0.0
        with open(part_path, mode) as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress and task_id is not None:
                        progress.update(task_id, advance=len(chunk))
                    now = time.monotonic()
                    if now - last_emit >= 0.15:
                        reporter.emit(
                            "download_file_progress",
                            path=str(target_filepath),
                            bytes_downloaded=downloaded,
                            bytes_total=total_size or None,
                        )
                        last_emit = now

        part_path.replace(target_filepath)
        reporter.emit(
            "download_file_completed",
            path=str(target_filepath),
            bytes_downloaded=downloaded,
            bytes_total=total_size or downloaded,
        )
        logger.info(f"Successfully downloaded: {file_display_name}")
        return True
    except KeyboardInterrupt as exc:
        raise DatasetDownloadError(
            "download_interrupted", "Download interrupted."
        ) from exc
    except DatasetDownloadError:
        raise
    except requests.exceptions.HTTPError as e:
        raise _download_error_for_response(e.response, url) from e
    except requests.exceptions.Timeout:
        raise DatasetDownloadError(
            "download_network_failed", f"Timeout occurred while downloading {url}."
        )
    except requests.exceptions.RequestException as e:
        raise DatasetDownloadError(
            "download_network_failed",
            f"A network or request error occurred downloading {url}: {e}",
        )
    except OSError as e:
        raise DatasetDownloadError(
            "download_filesystem_failed",
            f"File system error writing {target_filepath}: {e}",
        )

    # If download failed, attempt to remove partially downloaded file
    if target_filepath.exists():
        try:
            target_filepath.unlink()
        except OSError as e:
            logger.error(f"Could not remove incomplete file {target_filepath}: {e}")
    return False


def _scrape_urls_from_html_page(
    page_url: str, session: requests.Session, file_suffix: str = ".csv.gz"
) -> list[str]:
    """Scrapes a webpage for links ending with a specific suffix."""
    found_urls = []
    logger.debug(f"Scraping for '{file_suffix}' links on page: {page_url}")
    try:
        page_response = session.get(page_url, timeout=30)
        if page_response.status_code in {401, 403}:
            raise _download_error_for_response(page_response, page_url)
        if not (200 <= page_response.status_code < 300):
            raise _download_error_for_response(page_response, page_url)
        soup = BeautifulSoup(page_response.content, "html.parser")
        for link_tag in soup.find_all("a", href=True):
            href_path = link_tag["href"]
            # Basic validation of the link
            if (
                href_path.endswith(file_suffix)
                and not href_path.startswith(("?", "#"))
                and ".." not in href_path
            ):
                absolute_url = urljoin(page_url, href_path)
                found_urls.append(absolute_url)
    except DatasetDownloadError:
        raise
    except requests.exceptions.RequestException as e:
        raise DatasetDownloadError(
            "download_network_failed",
            f"Could not access or parse page {page_url} for scraping: {e}",
        ) from e
    return found_urls


def _download_dataset_files(
    dataset_name: str,
    dataset_config: dict,
    raw_files_root_dir: Path,
    *,
    credentials: PhysioNetCredentials | None = None,
    event_reporter: EventReporter | None = None,
) -> bool:
    """Downloads all relevant files for a dataset based on its configuration."""
    reporter = get_event_reporter(event_reporter)
    base_listing_url = dataset_config["file_listing_url"]
    subdirs_to_scan = dataset_config.get("subdirectories_to_scan", [])

    logger.info(
        f"Preparing to download {dataset_name} files from base URL: {base_listing_url}"
    )
    session = requests.Session()
    session.headers.update({"User-Agent": COMMON_USER_AGENT})
    if credentials:
        session.auth = (credentials.username, credentials.password)

    all_files_to_process = []  # List of (url, local_target_path)

    # Prepare list of (subdir_name, listing_url)
    # If subdirs_to_scan is empty, we scan the base_listing_url directly (root)
    scan_targets = []
    if not subdirs_to_scan:
        scan_targets.append(("", base_listing_url))
    else:
        for subdir in subdirs_to_scan:
            # Ensure slash for directory joining
            subdir_url = urljoin(base_listing_url, f"{subdir}/")
            scan_targets.append((subdir, subdir_url))

    for subdir_name, listing_url in scan_targets:
        logger.info(f"Scanning for CSVs: {listing_url}")
        reporter.emit("download_listing_started", dataset=dataset_name, url=listing_url)
        csv_urls_in_subdir = _scrape_urls_from_html_page(listing_url, session)
        reporter.emit(
            "download_listing_completed",
            dataset=dataset_name,
            url=listing_url,
            file_count=len(csv_urls_in_subdir),
        )

        if not csv_urls_in_subdir:
            logger.warning(f"No .csv.gz files found in location: {listing_url}")
            continue

        for file_url in csv_urls_in_subdir:
            url_path_obj = Path(urlparse(file_url).path)
            base_listing_url_path_obj = Path(urlparse(base_listing_url).path)
            relative_file_path: Path

            try:
                # Attempt to make file path relative to base URL's path part
                if url_path_obj.as_posix().startswith(
                    base_listing_url_path_obj.as_posix()
                ):
                    relative_file_path = url_path_obj.relative_to(
                        base_listing_url_path_obj
                    )
                else:
                    # Fallback if URL structure is unexpected
                    # (e.g., flat list of files not matching base structure)
                    logger.warning(
                        f"Path calculation fallback for {url_path_obj} vs "
                        f"{base_listing_url_path_obj}. "
                        f"Using {Path(subdir_name) / url_path_obj.name}"
                    )
                    relative_file_path = Path(subdir_name) / url_path_obj.name
            except (
                ValueError
            ) as e_rel:  # Handles cases where relative_to is not possible
                logger.error(
                    f"Path relative_to error for {url_path_obj} from "
                    f"{base_listing_url_path_obj}: {e_rel}. "
                    f"Defaulting to {Path(subdir_name) / url_path_obj.name}"
                )
                relative_file_path = Path(subdir_name) / url_path_obj.name

            local_target_path = raw_files_root_dir / relative_file_path
            all_files_to_process.append((file_url, local_target_path))

    if not all_files_to_process:
        raise DatasetDownloadError(
            "raw_files_missing",
            f"No '.csv.gz' download links found for dataset '{dataset_name}'.",
        )

    # Deduplicate and sort for consistent processing order
    unique_files_to_process = sorted(
        list(set(all_files_to_process)), key=lambda x: x[1]
    )

    total_files = len(unique_files_to_process)
    info(f"Found {total_files} files to download")
    reporter.emit("download_started", dataset=dataset_name, file_count=total_files)

    downloaded_count = 0
    with create_download_progress() as progress:
        # Create overall progress task
        overall_task = progress.add_task(
            f"[cyan]Overall ({downloaded_count}/{total_files})", total=total_files
        )
        # Create file download task
        file_task = progress.add_task("Starting...", total=0)

        for file_url, target_filepath in unique_files_to_process:
            if not _download_single_file(
                file_url,
                target_filepath,
                session,
                progress,
                file_task,
                event_reporter=reporter,
            ):
                logger.error(
                    f"Critical download failed for '{target_filepath.name}'. "
                    "Aborting dataset download."
                )
                return False  # Stop if any single download fails
            downloaded_count += 1
            progress.update(
                overall_task,
                advance=1,
                description=f"[cyan]Overall ({downloaded_count}/{total_files})",
            )
            # Reset file task for next file
            progress.reset(file_task)

    # Success only if all identified files were downloaded
    reporter.emit(
        "download_completed", dataset=dataset_name, file_count=downloaded_count
    )
    return downloaded_count == len(unique_files_to_process)


def download_dataset(
    dataset_name: str,
    output_root: Path,
    *,
    credentials: PhysioNetCredentials | None = None,
    event_reporter: EventReporter | None = None,
) -> bool:
    """
    Public wrapper to download a supported dataset's CSV files.
    - Currently intended for 'mimic-iv-demo' (public demo); extendable for others.
    - Downloads into output_root preserving subdirectory structure (e.g., hosp/, icu/).
    """
    ds = DatasetRegistry.get(dataset_name.lower())
    if not ds:
        raise DatasetDownloadError(
            "dataset_not_found", f"Unsupported dataset: {dataset_name}"
        )

    # Prevent accidental scraping of credentialed datasets
    if ds.requires_authentication and credentials is None:
        raise DatasetDownloadError(
            "missing_credentials",
            (
                f"Dataset '{dataset_name}' requires PhysioNet credentials. "
                "Provide --physionet-credentials-file."
            ),
        )

    if not ds.file_listing_url:
        raise DatasetDownloadError(
            "raw_files_missing",
            f"Dataset '{dataset_name}' does not have a configured listing URL.",
        )

    output_root.mkdir(parents=True, exist_ok=True)

    # Build config dict for _download_dataset_files (kept for minimal changes)
    dataset_config = {
        "file_listing_url": ds.file_listing_url,
        "subdirectories_to_scan": ds.subdirectories_to_scan,
    }
    return _download_dataset_files(
        dataset_name,
        dataset_config,
        output_root,
        credentials=credentials,
        event_reporter=event_reporter,
    )


########################################################
# CSV to Parquet conversion
########################################################


def _csv_to_parquet_all(
    src_root: Path, parquet_root: Path, event_reporter: EventReporter | None = None
) -> bool:
    """
    Convert all CSV files in the source directory to Parquet files.
    - Streams via DuckDB COPY to keep memory low
    - Low concurrency to avoid parallel memory spikes
    - Tunable via env:
        M4_CONVERT_MAX_WORKERS (default: 4)
        M4_DUCKDB_MEM         (default: 3GB)
        M4_DUCKDB_THREADS     (default: 2)
    """
    parquet_paths: list[Path] = []
    csv_files = list(src_root.rglob("*.csv.gz"))
    if not csv_files:
        logger.error(f"No CSV files found in {src_root}")
        return False
    reporter = get_event_reporter(event_reporter)

    # Optional: process small files first so progress moves smoothly
    try:
        csv_files.sort(key=lambda p: p.stat().st_size)
    except Exception:
        pass

    def _convert_one(csv_gz: Path) -> tuple[Path | None, float, str]:
        """Convert one CSV file and return the output path, time taken, and filename."""
        start = time.time()
        rel = csv_gz.relative_to(src_root)
        out = parquet_root / rel.with_suffix("").with_suffix(".parquet")
        out.parent.mkdir(parents=True, exist_ok=True)

        con = duckdb.connect()
        try:
            mem_limit = os.environ.get("M4_DUCKDB_MEM", "3GB")
            threads = int(os.environ.get("M4_DUCKDB_THREADS", "2"))
            con.execute(f"SET memory_limit='{mem_limit}'")
            con.execute(f"PRAGMA threads={threads}")

            # Streamed CSV -> Parquet conversion with robust parsing
            sql = f"""
                COPY (
                  SELECT * FROM read_csv_auto(
                    '{csv_gz.as_posix()}',
                    sample_size=-1,
                    auto_detect=true,
                    nullstr=['', 'NULL', 'NA', 'N/A', '___'],
                    ignore_errors=false
                  )
                )
                TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD);
            """
            con.execute(sql)
            elapsed = time.time() - start
            return out, elapsed, csv_gz.name
        finally:
            con.close()

    start_time = time.time()
    max_workers = max(1, int(os.environ.get("M4_CONVERT_MAX_WORKERS", "4")))

    total_files = len(csv_files)
    completed = 0

    logger.info(
        f"Converting {total_files} CSV files to Parquet using {max_workers} workers..."
    )
    reporter.emit(
        "conversion_started",
        source=str(src_root),
        destination=str(parquet_root),
        file_count=total_files,
    )

    console.print()
    with create_task_progress() as progress:
        task = progress.add_task(
            f"Converting CSV files ({max_workers} workers)...", total=total_files
        )

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_convert_one, f): f for f in csv_files}

            for fut in as_completed(futures):
                csv_file = futures[fut]
                try:
                    result_path, _, filename = fut.result()
                    if result_path is not None:
                        parquet_paths.append(result_path)
                        completed += 1
                        progress.update(
                            task,
                            advance=1,
                            description=f"Converted {filename} ({max_workers} workers)",
                        )
                        logger.debug(f"Converted: {filename}")
                        reporter.emit(
                            "conversion_file_completed",
                            path=str(result_path),
                            source=str(csv_file),
                            completed=completed,
                            file_count=total_files,
                        )
                except Exception as e:
                    logger.error(f"Parquet conversion failed for {csv_file}: {e}")
                    ex.shutdown(cancel_futures=True)
                    return False

    elapsed_time = time.time() - start_time
    success(f"Converted {len(parquet_paths)} files in {elapsed_time:.1f}s")
    reporter.emit(
        "conversion_completed",
        destination=str(parquet_root),
        file_count=len(parquet_paths),
        elapsed_seconds=elapsed_time,
    )
    return True


def convert_csv_to_parquet(
    dataset_name: str,
    csv_root: Path,
    parquet_root: Path,
    event_reporter: EventReporter | None = None,
) -> bool:
    """
    Public wrapper to convert CSV.gz files to Parquet for a dataset.
    - csv_root: root folder containing hosp/ and icu/ CSV.gz files
    - parquet_root: destination root for Parquet files mirroring structure
    """
    if not csv_root.exists():
        logger.error(f"CSV root not found: {csv_root}")
        return False
    parquet_root.mkdir(parents=True, exist_ok=True)
    return _csv_to_parquet_all(csv_root, parquet_root, event_reporter=event_reporter)


########################################################
# DuckDB functions
########################################################


def init_duckdb_from_parquet(
    dataset_name: str,
    db_target_path: Path,
    event_reporter: EventReporter | None = None,
) -> bool:
    """
    Initialize or refresh a DuckDB for the dataset by creating views over Parquet.

    Parquet root must exist under:
    <project_root>/m4_data/parquet/<dataset_name>/
    """
    ds = DatasetRegistry.get(dataset_name.lower())
    if not ds:
        logger.error(f"Configuration for dataset '{dataset_name}' not found.")
        return False

    parquet_root = get_dataset_parquet_root(dataset_name)
    if not parquet_root or not parquet_root.exists():
        logger.error(
            f"Missing Parquet directory for '{dataset_name}' at {parquet_root}. "
            "Place Parquet files under the expected path or run the future download command."
        )
        return False

    logger.info(
        f"Creating or refreshing views in {db_target_path} for Parquet under {parquet_root}"
    )
    mapping = ds.schema_mapping if ds.schema_mapping else None
    return _create_duckdb_with_views(
        db_target_path, parquet_root, mapping, event_reporter=event_reporter
    )


def _create_duckdb_with_views(
    db_path: Path,
    parquet_root: Path,
    schema_mapping: dict[str, str] | None = None,
    event_reporter: EventReporter | None = None,
) -> bool:
    """
    Create a DuckDB database and define one view per Parquet file.

    If schema_mapping is provided, creates real DuckDB schemas and
    schema-qualified views:
    - hosp/admissions.parquet with {"hosp": "mimiciv_hosp"}
      → CREATE SCHEMA mimiciv_hosp; CREATE VIEW mimiciv_hosp.admissions AS ...
    - patient.parquet with {"": "eicu_crd"}
      → CREATE SCHEMA eicu_crd; CREATE VIEW eicu_crd.patient AS ...

    If schema_mapping is None (backward compat for custom datasets),
    uses flat naming: hosp/admissions.parquet → hosp_admissions
    """
    try:
        con = duckdb.connect(str(db_path))
    except duckdb.IOException as e:
        if "Could not set lock" in str(e):
            logger.error(
                f"Database '{db_path.name}' is locked by another process. "
                "Close any running M4 servers or other DuckDB connections "
                "to this database and try again."
            )
            return False
        raise

    try:
        reporter = get_event_reporter(event_reporter)
        # Find all parquet files
        parquet_files = list(parquet_root.rglob("*.parquet"))
        if not parquet_files:
            logger.error(f"No Parquet files found in {parquet_root}")
            return False

        # Optimize DuckDB settings
        cpu_count = os.cpu_count() or 4
        con.execute(f"PRAGMA threads={cpu_count}")
        con.execute("SET memory_limit='8GB'")  # adjust to your machine

        # Create schemas upfront if schema_mapping provided
        if schema_mapping:
            for schema_name in set(schema_mapping.values()):
                if schema_name == "mimiciv_derived":
                    continue  # Created by m4 init-derived
                con.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')

        logger.info(f"Creating {len(parquet_files)} views in DuckDB...")
        reporter.emit(
            "duckdb_init_started",
            database=str(db_path),
            parquet_root=str(parquet_root),
            file_count=len(parquet_files),
        )
        start_time = time.time()
        created = 0

        console.print()
        with create_task_progress() as progress:
            task = progress.add_task(
                f"Creating {len(parquet_files)} views...", total=len(parquet_files)
            )

            for pq in parquet_files:
                # Get relative path from parquet_root
                rel = pq.relative_to(parquet_root)

                if schema_mapping:
                    # Resolve directory to schema name
                    dir_key = str(rel.parent)
                    if dir_key == ".":
                        dir_key = ""
                    schema_name = schema_mapping.get(dir_key)
                    if schema_name is None:
                        # Fallback: flat files with a single-schema mapping
                        # (e.g. mimic-iv-note parquets at root instead of note/)
                        unique_schemas = set(schema_mapping.values())
                        if dir_key == "" and len(unique_schemas) == 1:
                            schema_name = next(iter(unique_schemas))
                            logger.debug(
                                f"Flat file '{pq.name}' mapped to sole "
                                f"schema '{schema_name}'"
                            )
                        else:
                            logger.warning(
                                f"No schema mapping for directory '{dir_key}', "
                                f"skipping {pq}"
                            )
                            continue
                    table_name = rel.stem.lower()
                    view_name = f"{schema_name}.{table_name}"
                else:
                    # Flat naming for backward compat
                    parts = [*list(rel.parent.parts), rel.stem]
                    view_name = "_".join(
                        p.lower().replace("-", "_").replace(".", "_")
                        for p in parts
                        if p != "."
                    )

                # Create view pointing to the specific parquet file
                sql = f"""
                    CREATE OR REPLACE VIEW {view_name} AS
                    SELECT * FROM read_parquet('{pq.as_posix()}');
                """

                try:
                    con.execute(sql)
                    created += 1
                    progress.update(
                        task, advance=1, description=f"Created view: {view_name}"
                    )
                    logger.debug(f"Created view: {view_name}")
                    reporter.emit(
                        "duckdb_view_created",
                        database=str(db_path),
                        view=view_name,
                        completed=created,
                        file_count=len(parquet_files),
                    )
                except Exception as e:
                    logger.error(f"Failed to create view {view_name} from {pq}: {e}")
                    raise

        con.commit()
        elapsed_time = time.time() - start_time
        success(f"Created {created} views in {elapsed_time:.1f}s")
        reporter.emit(
            "duckdb_init_completed",
            database=str(db_path),
            view_count=created,
            elapsed_seconds=elapsed_time,
        )

        # List all created views for verification
        views_result = con.execute(
            "SELECT table_schema || '.' || table_name "
            "FROM information_schema.tables "
            "WHERE table_type='VIEW' "
            "ORDER BY table_schema, table_name"
        ).fetchall()
        logger.info(
            f"Created views: {', '.join(v[0] for v in views_result[:10])}"
            f"{'...' if len(views_result) > 10 else ''}"
        )

        return True
    finally:
        con.close()


########################################################
# Verification and utilities
########################################################


def verify_table_rowcount(db_path: Path, table_name: str) -> int:
    con = duckdb.connect(str(db_path))
    try:
        row = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        if row is None:
            raise RuntimeError("No result")
        return int(row[0])
    finally:
        con.close()


def ensure_duckdb_for_dataset(
    dataset_key: str,
) -> tuple[bool, Path | None, Path | None]:
    """
    Ensure DuckDB exists and views are created for the dataset.
    Returns (ok, db_path, parquet_root).
    """
    db_path = get_default_database_path(dataset_key)
    parquet_root = get_dataset_parquet_root(dataset_key)
    if not parquet_root or not parquet_root.exists():
        logger.error(
            f"Parquet directory missing: {parquet_root}. Expected at <project_root>/m4_data/parquet/{dataset_key}/"
        )
        return False, db_path, parquet_root
    ds = DatasetRegistry.get(dataset_key)
    mapping = ds.schema_mapping if ds and ds.schema_mapping else None
    ok = _create_duckdb_with_views(db_path, parquet_root, mapping)
    return ok, db_path, parquet_root


def compute_parquet_dir_size(parquet_root: Path) -> int:
    total = 0
    for p in parquet_root.rglob("*.parquet"):
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total
