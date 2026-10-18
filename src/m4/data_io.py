import glob
import gzip
import json
import os
import re
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
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
from m4.core.images import IMAGE_PATH_COLUMN, ImageFiles
from m4.core.raw_files import RAW_SUFFIXES, has_raw_files, raw_files, raw_stem
from m4.services.events import EventReporter, get_event_reporter
from m4.services.redaction import redact_sensitive, register_sensitive_value

########################################################
# Download functionality
########################################################

COMMON_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

# PhysioNet reads a login only from the programs it lists, and it recognises
# them by user agent: `Wget/` or `libwfdb/` at the start (HTTP_AUTH_USER_AGENT
# in physionet-build's project/utility.py). From any other client, a browser's
# user agent included, it ignores the login and answers 403, as if the account
# had no access. So a download that carries a login presents itself as
# Wget-compatible, and names M4 after that.
PHYSIONET_LOGIN_USER_AGENT = (
    "Wget/1.21.4 (compatible; m4-infra; +https://github.com/hannesill/m4)"
)


@dataclass(frozen=True)
class PhysioNetCredentials:
    username: str
    # Kept out of the repr, which is what logs and tracebacks print.
    password: str = field(repr=False)

    @classmethod
    def from_json_text(cls, text: str) -> "PhysioNetCredentials":
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("PhysioNet credentials must be a JSON object.")
        username = payload.get("username") or payload.get("user")
        password = payload.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            raise ValueError(
                "PhysioNet credentials must contain string username and password fields."
            )
        register_sensitive_value(password)
        return cls(username=username, password=password)

    @classmethod
    def from_json_bytes(cls, data: bytes) -> "PhysioNetCredentials":
        """Read a login sent as UTF-8 JSON, whatever the system's own encoding.

        Decoded here rather than by a text stream, which on Windows uses the
        ANSI code page and turns a password with "ü" or "€" into another one.
        """
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            # Its message quotes a byte of the login.
            raise ValueError("PhysioNet credentials must be UTF-8 text.") from None
        return cls.from_json_text(text)

    @classmethod
    def from_json_file(cls, path: Path) -> "PhysioNetCredentials":
        return cls.from_json_bytes(path.read_bytes())


class DatasetDownloadError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(redact_sensitive(message))
        self.code = code
        self.message = str(self)


# The only address a PhysioNet login is ever sent to. Compared as a prefix of
# the URL that is about to be requested, so that no way of spelling a host or a
# port can pass for it.
PHYSIONET_URL_PREFIX = "https://physionet.org/"


class _PhysioNetAuth(requests.auth.HTTPBasicAuth):
    """HTTP basic auth that gives the PhysioNet login to physionet.org only.

    requests calls this for every request a session prepares, so a dataset
    address or a scraped link that points anywhere else is refused before
    anything is sent. When a response redirects to another host or away from
    HTTPS, requests itself leaves the login out of the next request.
    """

    def __init__(self, username: str, password: str):
        # PhysioNet decodes the header as UTF-8 (check_http_auth in
        # physionet-build's project/utility.py). requests would encode a str
        # as Latin-1, which fails on "€" and sends "ü" as a byte PhysioNet
        # cannot decode, so it gets bytes.
        super().__init__(username.encode("utf-8"), password.encode("utf-8"))

    def __call__(self, request):
        if not str(request.url).startswith(PHYSIONET_URL_PREFIX):
            raise DatasetDownloadError(
                "physionet_url_required",
                f"Refusing to send the PhysioNet login to {request.url}. "
                f"M4 only sends it to {PHYSIONET_URL_PREFIX}",
            )
        return super().__call__(request)


def physionet_session(
    credentials: PhysioNetCredentials | None = None,
) -> requests.Session:
    """A session for PhysioNet's files: with `credentials`, one that sends them."""
    session = requests.Session()
    session.headers.update({"User-Agent": COMMON_USER_AGENT})
    if credentials:
        session.headers["User-Agent"] = PHYSIONET_LOGIN_USER_AGENT
        session.auth = _PhysioNetAuth(credentials.username, credentials.password)
    return session


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
    before_fetch: Callable[[], None] | None = None,
) -> bool:
    """Downloads a single file with progress tracking.

    `before_fetch` is called once the file is known not to be complete, before
    any of it is requested.
    """
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

        if before_fetch is not None:
            before_fetch()
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
    page_url: str,
    session: requests.Session,
    file_suffix: str | tuple[str, ...] = RAW_SUFFIXES,
) -> list[str]:
    """Scrapes a webpage for links ending with a specific suffix.

    By default the raw files M4 converts, .csv.gz and plain .csv, such as
    MIMIC-CXR-JPG's radiologist labels. Links to folders are not followed, so
    the image folders beside an imaging dataset's tables are left alone.
    """
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
    session = physionet_session(credentials)

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
            logger.warning(f"No CSV files found in location: {listing_url}")
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
            f"No CSV download links found for dataset '{dataset_name}'.",
        )

    # Deduplicate and sort for consistent processing order
    unique_files_to_process = sorted(
        list(set(all_files_to_process)), key=lambda x: x[1]
    )

    total_files = len(unique_files_to_process)
    info(f"Found {total_files} files to download")
    reporter.emit("download_started", dataset=dataset_name, file_count=total_files)

    download_note = raw_files_root_dir / DOWNLOAD_NOTE

    def note_unfinished() -> None:
        # From the first file that has to be fetched, the folder holds part of
        # a dataset. The note says so until every file has arrived, whatever
        # ends this run before that. A run that finds every file complete
        # writes nothing.
        if not download_note.exists():
            raw_files_root_dir.mkdir(parents=True, exist_ok=True)
            _write_marker(download_note, dataset=dataset_name, file_count=total_files)

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
                before_fetch=note_unfinished,
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
    try:
        # (Checked first: the folder may not be writable.)
        if download_note.exists():
            download_note.unlink()
    except OSError as e:
        raise DatasetDownloadError(
            "download_filesystem_failed",
            f"File system error removing {download_note}: {e}",
        ) from e
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
# Preparation markers
########################################################

# Three small files say how far the preparation of a dataset got:
# - In a raw folder: a download into it that has not finished. Only M4's own
#   download writes it, and removes it when every file has arrived. Of other
#   downloads, the file that was being written says the same without a note.
# - Next to the Parquet files: the raw folder of a conversion that has not
#   finished, and the tables it set out to make. Only a conversion writes it,
#   and removes it when it is done.
# - Next to a database: the Parquet files its views were created and verified
#   over. An initialization writes it last, and only with it is a dataset ready.
DOWNLOAD_NOTE = ".m4-downloading.json"
CONVERSION_NOTE = ".m4-converting.json"
PREPARED_SUFFIX = ".m4-prepared.json"


def _read_marker(path: Path) -> dict[str, Any]:
    try:
        marker = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(marker, dict) or marker.get("version") != 1:
        return {}
    return marker


def _write_marker(path: Path, **facts: Any) -> None:
    scratch = path.with_name(f"{path.name}.tmp")
    scratch.write_text(json.dumps({"version": 1, **facts}, indent=2))
    os.replace(scratch, path)


def _prepared_marker(db_path: Path) -> Path:
    # Next to the database file itself. A database may be reached through a
    # link, and init and status do not spell the path to it the same way.
    db_path = db_path.resolve()
    return db_path.with_name(db_path.name + PREPARED_SUFFIX)


def _parquet_listing(parquet_root: Path) -> list[list[str | int]]:
    """Each table below `parquet_root` as [path, size, modified], sorted.

    Size and modification time, not only the name, so that a table replaced
    or cut short under the same name is a different listing. A false alarm
    costs little: initializing again only recreates the views.
    """
    listing: list[list[str | int]] = []
    for path in parquet_root.rglob("*.parquet"):
        try:
            stat = path.stat()
        except OSError:
            continue
        listing.append(
            [path.relative_to(parquet_root).as_posix(), stat.st_size, stat.st_mtime_ns]
        )
    return sorted(listing)


def unfinished_download(raw_root: Path) -> str | None:
    """The file below `raw_root` that says a download into it did not finish.

    That is the note of M4's own download. A download by M4 0.5.5 or earlier
    left none, and neither does a browser. Of those, the file that was being
    written says the same: it still carries the suffix it is downloaded under,
    and no finished file lies beside it. None when nothing says so.
    """
    if (raw_root / DOWNLOAD_NOTE).exists():
        return DOWNLOAD_NOTE
    partials = (
        partial
        for suffix in RAW_SUFFIXES
        for partial in raw_root.rglob(f"*{suffix}{PARTIAL_SUFFIX}")
    )
    for partial in sorted(partials):
        if not partial.with_name(partial.name[: -len(PARTIAL_SUFFIX)]).exists():
            return partial.relative_to(raw_root).as_posix()
    return None


def unfinished_conversion(parquet_root: Path) -> tuple[str, list[str] | None] | None:
    """What a conversion into `parquet_root` that did not finish still owes.

    Returns the raw folder it read from and the tables it has yet to finish,
    as paths below `parquet_root`. The tables are None for a note that does
    not list them, as M4 wrote it for a short time. None when nothing is owed.
    """
    note = _read_marker(parquet_root / CONVERSION_NOTE)
    source = note.get("source")
    if not isinstance(source, str):
        return None
    tables = note.get("tables")
    if not isinstance(tables, list):
        return source, None
    owed = [
        table
        for table in tables
        if isinstance(table, str) and not _is_complete_parquet(parquet_root / table)
    ]
    return (source, owed) if owed else None


def conversion_out_of_reach(parquet_root: Path, csv_root: Path) -> str | None:
    """The raw folder an unfinished conversion read from, if `csv_root` cannot finish it.

    None when no conversion into `parquet_root` is unfinished, when `csv_root`
    is the folder that conversion read from, or when it holds the raw file of
    every table the conversion still owes.
    """
    unfinished = unfinished_conversion(parquet_root)
    if unfinished is None:
        return None
    source, owed = unfinished
    if str(csv_root.resolve()) == source:
        # The folder the conversion read from finishes it with the raw files
        # it holds now: one that could not be converted may have been taken
        # out since.
        within_reach = has_raw_files(csv_root)
    else:
        # Any other folder has to bring every table that is still missing.
        # Which those are is only known where the note lists them.
        within_reach = owed is not None and all(
            any((csv_root / table).with_suffix(s).is_file() for s in RAW_SUFFIXES)
            for table in owed
        )
    return None if within_reach else source


def mark_dataset_prepared(parquet_root: Path, db_path: Path) -> None:
    """Record that `db_path` has verified views over the tables in `parquet_root`.

    Call it last in an initialization: only then is the dataset reported ready.
    """
    _write_marker(
        _prepared_marker(db_path),
        parquet_root=str(parquet_root.resolve()),
        parquet_files=_parquet_listing(parquet_root),
    )


def is_dataset_prepared(parquet_root: Path, db_path: Path) -> bool:
    """Whether an initialization of these Parquet files into `db_path` finished.

    No longer true once the Parquet files differ from the ones it finished
    with, as after a later conversion whose new tables have no views yet.
    """
    marker = _read_marker(_prepared_marker(db_path))
    return (
        marker.get("parquet_root") == str(parquet_root.resolve())
        and marker.get("parquet_files") == _parquet_listing(parquet_root)
        and unfinished_conversion(parquet_root) is None
    )


########################################################
# CSV to Parquet conversion
########################################################

# A table is written under this suffix and renamed once it is complete, so a
# conversion that is killed never leaves a file that passes for a table.
PARTIAL_SUFFIX = ".part"
PARQUET_MAGIC = b"PAR1"


class CsvConversionError(Exception):
    """A raw file M4 cannot convert, with the code and hint a caller reports."""

    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


ERROR_CSV_ENCODING_UNSUPPORTED = "csv_encoding_unsupported"
ERROR_TABLE_NAME_COLLISION = "table_name_collision"
WARNING_CSV_READ_AS_LATIN1 = "csv_read_as_latin1"
WARNING_DECIMAL_COMMA_COLUMNS = "decimal_comma_columns_kept_as_text"
_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")
# A number written with a decimal comma, or a whole number among them
_DECIMAL_COMMA = r"-?\d+(,\d+)?"


def _copy_csv_to_parquet(
    con: duckdb.DuckDBPyConnection,
    raw: Path,
    destination: Path,
    encoding: str | None = None,
) -> None:
    """Stream `raw` into the Parquet file `destination`.

    Without `encoding` this is the statement M4 has always converted
    PhysioNet's files with; DuckDB detects the delimiter, a UTF-8 BOM, and
    whether the file is gzipped.
    """
    encoding_option = f", encoding='{encoding}'" if encoding else ""
    con.execute(
        f"""
        COPY (
          SELECT * FROM read_csv_auto(
            '{raw.as_posix()}',
            sample_size=-1,
            auto_detect=true,
            nullstr=['', 'NULL', 'NA', 'N/A', '___'],
            ignore_errors=false{encoding_option}
          )
        )
        TO '{destination.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """
    )


def _first_line(raw: Path) -> bytes:
    """The first line of `raw`, decompressed, as bytes; b"" if unreadable."""
    try:
        with (gzip.open if raw.name.endswith(".gz") else open)(raw, "rb") as handle:
            return handle.readline(65536)
    except OSError:
        return b""


def _decimal_comma_columns(
    con: duckdb.DuckDBPyConnection, raw: Path, parquet: Path
) -> list[str]:
    """Text columns of a ;-separated `raw` file that hold numbers like 3,5.

    DuckDB reads them as text, and M4 keeps them so rather than guess what the
    commas mean. Only a file whose header line holds a ; is looked at, which
    no PhysioNet file does.
    """
    if b";" not in _first_line(raw):
        return []
    source = f"read_parquet('{parquet.as_posix()}')"
    columns = [
        row[0]
        for row in con.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()
        if row[1] == "VARCHAR"
    ]
    if not columns:
        return []
    checks = []
    for column in columns:
        quoted = '"' + column.replace('"', '""') + '"'
        checks.append(
            f"coalesce(bool_and(regexp_full_match({quoted}, $1)) "
            f"AND bool_or(contains({quoted}, ',')), false)"
        )
    row = con.execute(
        f"SELECT {', '.join(checks)} FROM {source}", [_DECIMAL_COMMA]
    ).fetchone()
    return [column for column, hit in zip(columns, row) if hit]


def _convert_csv(
    con: duckdb.DuckDBPyConnection, raw: Path, destination: Path
) -> list[dict[str, Any]]:
    """Convert `raw` into `destination` and return warnings about how it was read.

    A file that is not UTF-8 is read again as UTF-16 when it starts with that
    byte order mark, as Excel's Unicode text export does, and as Latin-1
    otherwise, which every byte decodes as; the latter is a guess, and says so.
    """
    warnings: list[dict[str, Any]] = []
    try:
        _copy_csv_to_parquet(con, raw, destination)
    except duckdb.InvalidInputException as exc:
        if "invalid unicode" not in str(exc).lower():
            raise
        destination.unlink(missing_ok=True)
        encoding = "utf-16" if _first_line(raw)[:2] in _UTF16_BOMS else "latin-1"
        try:
            _copy_csv_to_parquet(con, raw, destination, encoding)
        except duckdb.Error as retry:
            raise CsvConversionError(
                ERROR_CSV_ENCODING_UNSUPPORTED,
                f"{raw} is not UTF-8, and M4 could not read it as {encoding} "
                f"either: {str(retry).splitlines()[0]}",
                "Save it as UTF-8 (in Excel: CSV UTF-8), then run m4 init again.",
            ) from retry
        if encoding == "latin-1":
            warnings.append({"code": WARNING_CSV_READ_AS_LATIN1, "file": str(raw)})
    columns = _decimal_comma_columns(con, raw, destination)
    if columns:
        warnings.append(
            {
                "code": WARNING_DECIMAL_COMMA_COLUMNS,
                "file": str(raw),
                "columns": columns,
            }
        )
    return warnings


def _parquet_path_for(raw: Path, src_root: Path, parquet_root: Path) -> Path:
    rel = raw.relative_to(src_root)
    if rel.name.endswith(".csv.gz"):
        # As M4 has always named the tables of .csv.gz files
        return parquet_root / rel.with_suffix("").with_suffix(".parquet")
    return parquet_root / rel.with_name(raw_stem(rel.name) + ".parquet")


def _is_complete_parquet(path: Path) -> bool:
    """Whether `path` is a finished Parquet file.

    A Parquet file starts and ends with the bytes PAR1. A writer that was killed
    leaves a file without the closing ones (M4 0.5.5 and earlier wrote straight
    to the final name).
    """
    try:
        with open(path, "rb") as f:
            if f.read(4) != PARQUET_MAGIC:
                return False
            return f.seek(-4, os.SEEK_END) >= 8 and f.read(4) == PARQUET_MAGIC
    except OSError:
        return False


def find_unconverted(csv_root: Path, parquet_root: Path) -> list[Path]:
    """Raw CSV files under `csv_root` that have no finished Parquet file."""
    return [
        raw
        for raw in raw_files(csv_root)
        if not _is_complete_parquet(_parquet_path_for(raw, csv_root, parquet_root))
    ]


def _csv_to_parquet_all(
    src_root: Path,
    parquet_root: Path,
    event_reporter: EventReporter | None = None,
    warnings: list[dict[str, Any]] | None = None,
) -> bool:
    """
    Convert the CSV files in the source directory that have no finished Parquet
    file yet, so a run that was interrupted is continued rather than repeated.
    - Streams via DuckDB COPY to keep memory low
    - Low concurrency to avoid parallel memory spikes
    - Tunable via env:
        M4_CONVERT_MAX_WORKERS (default: 4)
        M4_DUCKDB_MEM         (default: 3GB)
        M4_DUCKDB_THREADS     (default: 2)
    Warnings about how files were read are appended to `warnings`. Raises
    CsvConversionError for a file M4 cannot convert and can say why.
    """
    parquet_paths: list[Path] = []
    all_raw = raw_files(src_root)
    if not all_raw:
        logger.error(f"No CSV files found in {src_root}")
        return False
    # labs.csv next to labs.csv.gz, or names that differ only in case, would
    # be written to one Parquet file and one view
    tables: dict[str, list[Path]] = {}
    for raw in all_raw:
        key = str(_parquet_path_for(raw, src_root, parquet_root)).casefold()
        tables.setdefault(key, []).append(raw)
    clashes = [paths for paths in tables.values() if len(paths) > 1]
    if clashes:
        raise CsvConversionError(
            ERROR_TABLE_NAME_COLLISION,
            "These files would become the same table: "
            + "; ".join(" and ".join(str(path) for path in paths) for paths in clashes)
            + ".",
            "Keep one file of each, then run m4 init again.",
        )
    conversion_note = parquet_root / CONVERSION_NOTE
    # A conversion from another folder may be unfinished, with tables this
    # folder holds no raw file for. Whatever this run converts, those tables
    # stay missing, so the note that lists them is left as it is.
    keeps_note = conversion_out_of_reach(parquet_root, src_root) is not None
    csv_files = find_unconverted(src_root, parquet_root)
    if not csv_files:
        # Whatever an earlier run left unfinished, these raw files are all
        # converted. (Checked first: the folder may not be writable.)
        if conversion_note.exists() and not keeps_note:
            conversion_note.unlink()
        return True
    skipped_count = len(all_raw) - len(csv_files)
    reporter = get_event_reporter(event_reporter)

    # Optional: process small files first so progress moves smoothly
    try:
        csv_files.sort(key=lambda p: p.stat().st_size)
    except Exception:
        pass

    def _convert_one(
        raw: Path,
    ) -> tuple[Path | None, float, str, list[dict[str, Any]]]:
        """Convert one CSV file: the output path, time taken, filename, warnings."""
        start = time.time()
        out = _parquet_path_for(raw, src_root, parquet_root)
        out.parent.mkdir(parents=True, exist_ok=True)
        # The table is written under a name no other run uses: two runs at
        # once would otherwise publish what the other has written so far. What
        # earlier runs left of the table is cleared first, to give the disk
        # back. That takes the file of a run that is still going too, which
        # then fails when it comes to publish it, instead of going wrong.
        for leftover in out.parent.glob(f"{glob.escape(out.name)}*{PARTIAL_SUFFIX}"):
            try:
                leftover.unlink(missing_ok=True)
            except OSError:
                pass  # Held open by a run that is still writing it (Windows)
        partial = out.with_name(f"{out.name}.{uuid.uuid4().hex}{PARTIAL_SUFFIX}")

        con = duckdb.connect()
        try:
            mem_limit = os.environ.get("M4_DUCKDB_MEM", "3GB")
            threads = int(os.environ.get("M4_DUCKDB_THREADS", "2"))
            con.execute(f"SET memory_limit='{mem_limit}'")
            con.execute(f"PRAGMA threads={threads}")
            notes = _convert_csv(con, raw, partial)
        except Exception:
            # A failed conversion keeps no half-written file, which matters most
            # when the reason is a full disk. Closing first releases the file.
            con.close()
            partial.unlink(missing_ok=True)
            raise
        finally:
            con.close()
        os.replace(partial, out)
        elapsed = time.time() - start
        return out, elapsed, raw.name, notes

    start_time = time.time()
    max_workers = max(1, int(os.environ.get("M4_CONVERT_MAX_WORKERS", "4")))

    total_files = len(csv_files)
    completed = 0

    logger.info(
        f"Converting {total_files} CSV files to Parquet using {max_workers} workers"
        f" ({skipped_count} already converted)..."
    )
    # Until every file is converted, the Parquet folder is not a whole dataset.
    # The tables are listed, so that only their being there settles the note.
    if not keeps_note:
        try:
            _write_marker(
                conversion_note,
                source=str(src_root.resolve()),
                tables=sorted(
                    _parquet_path_for(raw, src_root, parquet_root)
                    .relative_to(parquet_root)
                    .as_posix()
                    for raw in csv_files
                ),
            )
        except OSError as e:
            # A full disk, most likely. Nothing has been converted yet.
            logger.error(f"Could not note the conversion in {parquet_root}: {e}")
            return False
    reporter.emit(
        "conversion_started",
        source=str(src_root),
        destination=str(parquet_root),
        file_count=total_files,
        skipped_count=skipped_count,
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
                    result_path, _, filename, notes = fut.result()
                    for note in notes:
                        logger.warning(f"{filename}: {note['code']}")
                        reporter.emit("conversion_warning", **note)
                        if warnings is not None:
                            warnings.append(note)
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
                    if isinstance(e, CsvConversionError):
                        raise
                    return False

    if not keeps_note:
        conversion_note.unlink(missing_ok=True)
    elapsed_time = time.time() - start_time
    success(f"Converted {len(parquet_paths)} files in {elapsed_time:.1f}s")
    reporter.emit(
        "conversion_completed",
        destination=str(parquet_root),
        file_count=len(parquet_paths),
        skipped_count=skipped_count,
        elapsed_seconds=elapsed_time,
    )
    return True


def convert_csv_to_parquet(
    dataset_name: str,
    csv_root: Path,
    parquet_root: Path,
    event_reporter: EventReporter | None = None,
    warnings: list[dict[str, Any]] | None = None,
) -> bool:
    """
    Public wrapper to convert CSV files (.csv.gz or .csv) to Parquet for a dataset.
    - csv_root: root folder containing the raw files, e.g. hosp/ and icu/
    - parquet_root: destination root for Parquet files mirroring structure
    - warnings: receives a dict for each file read with a fallback
    Raises CsvConversionError for a file M4 cannot convert and can say why.
    """
    if not csv_root.exists():
        logger.error(f"CSV root not found: {csv_root}")
        return False
    parquet_root.mkdir(parents=True, exist_ok=True)
    return _csv_to_parquet_all(
        csv_root, parquet_root, event_reporter=event_reporter, warnings=warnings
    )


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
        db_target_path,
        parquet_root,
        mapping,
        event_reporter=event_reporter,
        table_names=ds.table_names,
        images=ds.images,
    )


def _folder_key(directory: Path) -> str:
    """How a schema mapping names `directory`, given relative to the dataset root."""
    dir_key = str(directory)
    return "" if dir_key == "." else dir_key


def _schema_for(directory: Path, schema_mapping: dict[str, str]) -> str | None:
    """The schema for files in `directory`, given relative to the dataset root."""
    dir_key = _folder_key(directory)
    schema_name = schema_mapping.get(dir_key)
    if schema_name is None:
        # Fallback: flat files with a single-schema mapping
        # (e.g. mimic-iv-note parquets at root instead of note/)
        unique_schemas = set(schema_mapping.values())
        if dir_key == "" and len(unique_schemas) == 1:
            schema_name = next(iter(unique_schemas))
    return schema_name


def fitting_raw_roots(csv_root: Path, schema_mapping: dict[str, str]) -> list[Path]:
    """The folders at or below `csv_root` whose CSV.gz files would become tables.

    A folder fits when files lie below it in a folder the dataset names. Only
    where no folder fits that way do folders count that hold bare files, which
    a dataset of one schema also takes: next to another dataset's files, every
    folder would otherwise pass for such a dataset.
    """
    named: set[Path] = set()
    bare: set[Path] = set()
    for raw in raw_files(csv_root):
        folders = raw.relative_to(csv_root).parent.parts
        for depth in range(len(folders) + 1):
            below = Path(*folders[depth:])
            root = csv_root.joinpath(*folders[:depth])
            if _folder_key(below) in schema_mapping:
                named.add(root)
            elif _schema_for(below, schema_mapping) is not None:
                bare.add(root)
    return sorted(named or bare)


def find_raw_root(csv_root: Path, schema_mapping: dict[str, str] | None) -> Path | None:
    """The folder at or below `csv_root` whose CSV.gz files become the dataset's tables.

    That is `csv_root` itself when it is laid out as the dataset expects. When
    the files sit deeper, as under physionet.org/files/<dataset>/<version>/
    after a plain `wget -r`, it is that deeper folder. None when no folder
    fits, and when several do: M4 cannot tell which of them holds this dataset,
    and the wrong one would fill it with another dataset's tables.
    """
    if not schema_mapping:
        return csv_root  # Flat naming gives every file a table
    fitting = fitting_raw_roots(csv_root, schema_mapping)
    if csv_root in fitting:
        return csv_root
    return fitting[0] if len(fitting) == 1 else None


def raw_files_left_to_convert(
    raw_root: Path, parquet_root: Path, schema_mapping: dict[str, str] | None
) -> list[Path]:
    """Raw files in M4's own raw folder `raw_root` that have no finished table.

    They are looked for where `m4 init` reads them: in `raw_root`, or in the
    one folder below it that init names when the files lie deeper. Files that
    init cannot place at all are not counted: no run of it converts them.
    """
    located = find_raw_root(raw_root, schema_mapping)
    return find_unconverted(located, parquet_root) if located else []


def folders_without_tables(
    folders: list[str],
    schema_mapping: dict[str, str] | None,
    csv_root: Path,
    parquet_root: Path,
) -> list[str]:
    """Those of the dataset's `folders` that converting `csv_root` leaves empty.

    A folder has tables when a raw file under `csv_root` or a Parquet file
    under `parquet_root` belongs to its schema.
    """
    if not schema_mapping:
        return []  # Flat naming knows no folders
    filled = {
        _schema_for(path.relative_to(root).parent, schema_mapping)
        for root, paths in (
            (csv_root, raw_files(csv_root)),
            (parquet_root, parquet_root.rglob("*.parquet")),
        )
        for path in paths
    }
    return [
        folder
        for folder in folders
        if folder in schema_mapping and schema_mapping[folder] not in filled
    ]


def _drop_views_over_missing_files(con, parquet_root: Path) -> None:
    """Drop the views that read a Parquet file of this dataset that is gone.

    Initializing replaces the views of the tables that are there; without
    this, the view of a table that was deleted would stay in a database
    marked prepared, and fail when queried. Only a view that reads a file
    below `parquet_root`, as the ones M4 creates do, is dropped.
    """
    root = parquet_root.as_posix().rstrip("/") + "/"
    views = con.execute(
        "SELECT schema_name, view_name, sql FROM duckdb_views() WHERE NOT internal"
    ).fetchall()
    for schema_name, view_name, sql in views:
        source = re.search(r"read_parquet\('([^']*)'\)", sql or "")
        if (
            source
            and source.group(1).startswith(root)
            and not Path(source.group(1)).exists()
        ):
            con.execute(f'DROP VIEW IF EXISTS "{schema_name}"."{view_name}"')


def sql_table_name(name: str) -> str:
    """`name` as a table name that DuckDB takes unquoted after a schema.

    Lower case, with an underscore for each character other than a letter
    (é and ü included), a digit or an underscore, and before a leading digit.
    Names that are already so, as those of every PhysioNet table M4 ships but
    MIMIC-CXR-JPG's, stay as they are.
    """
    table = re.sub(r"[^\w]", "_", name.lower())
    return f"_{table}" if not table or table[0].isdigit() else table


def _quoted(name: str) -> str:
    """`schema.table` or `table`, quoted for SQL."""
    return ".".join('"' + part.replace('"', '""') + '"' for part in name.split("."))


def _create_duckdb_with_views(
    db_path: Path,
    parquet_root: Path,
    schema_mapping: dict[str, str] | None = None,
    event_reporter: EventReporter | None = None,
    *,
    table_names: dict[str, str] | None = None,
    images: ImageFiles | None = None,
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

    A table is named after its file, as `sql_table_name` makes it, unless
    `table_names` names it (by the file's path below `parquet_root` without
    .parquet). With `images`, a view of the image table with each image's
    path in an `image_path` column is made too.

    Returns False when the database is locked or no view could be created.
    """
    # A database that is only now created has no views, whatever was recorded
    # for one that used to be at this path.
    if not db_path.exists():
        _prepared_marker(db_path).unlink(missing_ok=True)

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

        # The views change from here on, now that the database is known not to
        # be locked. Whoever initializes the dataset marks it prepared again
        # once they are all there and verified.
        _prepared_marker(db_path).unlink(missing_ok=True)
        _drop_views_over_missing_files(con, parquet_root)

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

            views_made: dict[str, Path] = {}
            for pq in parquet_files:
                # Get relative path from parquet_root
                rel = pq.relative_to(parquet_root)
                named = (table_names or {}).get(rel.with_suffix("").as_posix())

                if schema_mapping:
                    # Resolve directory to schema name
                    schema_name = _schema_for(rel.parent, schema_mapping)
                    if schema_name is None:
                        logger.warning(
                            f"No schema mapping for directory '{rel.parent}', "
                            f"skipping {pq}"
                        )
                        continue
                    table_name = named or sql_table_name(rel.stem)
                    view_name = f"{schema_name}.{table_name}"
                else:
                    # Flat naming for backward compat
                    parts = [*list(rel.parent.parts), rel.stem]
                    view_name = named or sql_table_name(
                        "_".join(p for p in parts if p != ".")
                    )

                # Names that differ only in characters a table name cannot
                # hold, such as lab-results and lab_results, would make one
                # view, which shows only one of the files.
                if view_name in views_made:
                    first = views_made[view_name].relative_to(parquet_root)
                    raise ValueError(
                        f"{first.as_posix()} and {rel.as_posix()} would both "
                        f"become the table {view_name}."
                    )
                views_made[view_name] = pq

                # Create view pointing to the specific parquet file
                sql = f"""
                    CREATE OR REPLACE VIEW {_quoted(view_name)} AS
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

        if not created:
            logger.error(
                f"None of the Parquet files in {parquet_root} sits in a folder "
                "that this dataset maps to a schema, so no view was created."
            )
            return False

        if images is not None:
            if images.view in views_made:
                raise ValueError(
                    f"The images view {images.view} would replace the table of "
                    f"{views_made[images.view].relative_to(parquet_root).as_posix()}."
                )
            # Over the image table's view rather than its file, so the view
            # follows the table when it is converted again.
            schema_name = images.view.split(".")[0]
            con.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
            con.execute(
                f"CREATE OR REPLACE VIEW {_quoted(images.view)} AS "
                f"SELECT *, {images.path_sql()} AS {IMAGE_PATH_COLUMN} "
                f"FROM {_quoted(images.table)}"
            )
            logger.debug(f"Created view: {images.view}")

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
    ok = _create_duckdb_with_views(
        db_path,
        parquet_root,
        mapping,
        table_names=ds.table_names if ds else None,
        images=ds.images if ds else None,
    )
    return ok, db_path, parquet_root


def compute_parquet_dir_size(parquet_root: Path) -> int:
    total = 0
    for p in parquet_root.rglob("*.parquet"):
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total
