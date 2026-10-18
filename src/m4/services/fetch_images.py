"""Fetch the images of a cohort from an imaging dataset, never the whole dataset.

PhysioNet serves MIMIC-CXR-JPG's half a terabyte at 1-17 KB/s per connection,
stalls or answers 502 now and then, and was seen refusing every connection for
minutes. So a run fetches the images a list names, four at a time, retries
what fails with a growing pause until an image has had no byte for ten
minutes, and leaves a .part file that the next run resumes. An image that is there is not fetched
again: it only gets its final name once it is complete.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any
from urllib.parse import quote

import duckdb
import pandas as pd
import requests

from m4.config import ensure_custom_datasets_loaded
from m4.core.datasets import DatasetDefinition, DatasetRegistry
from m4.core.exceptions import M4Error
from m4.core.images import IMAGE_PATH_COLUMN
from m4.data_io import (
    PARTIAL_SUFFIX,
    DatasetDownloadError,
    PhysioNetCredentials,
    _download_error_for_response,
    physionet_session,
)
from m4.services.download import access_forbidden_hint, default_raw_root
from m4.services.events import EventReporter, get_event_reporter
from m4.services.results import ERROR_DATASET_NOT_FOUND, CommandError, CommandResult

COMMAND = "fetch-images"

CONNECTIONS = 4
# An image is given up once no byte of it arrived for this long, so a slow
# transfer goes on and a server that is away for minutes is waited for.
PATIENCE_SECONDS = 600
BACKOFF_SECONDS = 5.0  # before the second attempt; doubled for each one after
MAX_BACKOFF_SECONDS = 60.0
TIMEOUT_SECONDS = 60  # without a byte from PhysioNet, the attempt has stalled
PROGRESS_SECONDS = 1.0
# requests hands a piece over only once all of it has arrived, and what a
# broken connection had read of the next piece is lost: PhysioNet breaks
# connections every few tens of KB at its slowest, so pieces stay small.
CHUNK_BYTES = 8 * 1024
# A guard against fetching a whole split by mistake (the training split of
# MIMIC-CXR-JPG has 368,960 images), not a judgement of what a study needs:
# the test split's 5,159 fit.
MAX_IMAGES = 10_000

ERROR_NOT_AN_IMAGING_DATASET = "not_an_imaging_dataset"
ERROR_IMAGE_LIST_INVALID = "image_list_invalid"
ERROR_TOO_MANY_IMAGES = "too_many_images"
ERROR_DATASET_NOT_INITIALIZED = "dataset_not_initialized"
ERROR_IMAGES_INCOMPLETE = "images_incomplete"
ERROR_IMAGE_NOT_FOUND = "image_not_found"

# Failures that every other image would meet too, so the run stops
FATAL_CODES = frozenset(
    {
        "physionet_auth_failed",
        "physionet_access_forbidden",
        "physionet_url_required",
        "download_filesystem_failed",
    }
)
RETRY_STATUSES = frozenset({408, 425, 429})
PATH_COLUMNS = (IMAGE_PATH_COLUMN, "path")
NAMED = 3  # how many offending rows an error message names


class _Retry(Exception):
    """A failure that another attempt may not meet."""


class _Stopped(Exception):
    """The run is stopping; the .part file stays for the next one."""


def _error(
    code: str, message: str, hint: str | None = None, data: dict | None = None
) -> CommandError:
    return CommandError(
        command=COMMAND, code=code, message=message, hint=hint, data=data
    )


def _listed(items: list[str]) -> str:
    more = len(items) - NAMED
    return ", ".join(items[:NAMED]) + (f" and {more} more" if more > 0 else "")


def _content_range(header: str | None) -> tuple[int | None, int | None]:
    """The first byte and the total size in `bytes 100-199/2000` or `bytes */2000`."""
    match = re.fullmatch(r"bytes (?:(\d+)-\d+|\*)/(\d+|\*)", (header or "").strip())
    if not match:
        return None, None
    start, total = match.groups()
    return (
        int(start) if start is not None else None,
        int(total) if total != "*" else None,
    )


def _fetch_once(
    session: requests.Session,
    url: str,
    target: Path,
    part: Path,
    stop: threading.Event,
    on_start: Callable[[int, int | None], None],
    on_bytes: Callable[[int], None],
) -> None:
    """One attempt at `url`, resumed from `part`; renames `part` to `target` when whole.

    `on_start` gets the bytes there are before the first new one and the
    image's size, if known; `on_bytes` the size of each piece that arrives.
    """
    resume_from = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}
    try:
        response = session.get(
            url, stream=True, timeout=TIMEOUT_SECONDS, headers=headers
        )
    except requests.exceptions.RequestException as exc:
        raise _Retry(f"{type(exc).__name__}: {exc}") from exc
    with response:
        status = response.status_code
        if status in {401, 403}:
            raise _download_error_for_response(response, url)
        if status == 404:
            raise DatasetDownloadError(
                ERROR_IMAGE_NOT_FOUND, f"PhysioNet has no file at {url}."
            )
        if status == 416 and resume_from:
            _, total = _content_range(response.headers.get("content-range"))
            if total == resume_from:
                part.replace(target)  # The last attempt got every byte
                return
            part.unlink()
            raise _Retry("the partial file is longer than the image")
        if status in RETRY_STATUSES or status >= 500:
            raise _Retry(f"HTTP {status}")
        if status not in {200, 206}:
            raise _download_error_for_response(response, url)
        if status == 206:
            start, expected = _content_range(response.headers.get("content-range"))
            if start != resume_from:
                part.unlink()
                raise _Retry("PhysioNet resumed at another byte")
            mode = "ab"
        else:
            # The whole file, whether or not a part of it was asked for
            length = response.headers.get("content-length", "")
            expected = int(length) if length.isdigit() else None
            resume_from = 0
            mode = "wb"
        target.parent.mkdir(parents=True, exist_ok=True)
        on_start(resume_from, expected)
        try:
            with open(part, mode) as handle:
                for chunk in response.iter_content(chunk_size=CHUNK_BYTES):
                    if stop.is_set():
                        raise _Stopped
                    handle.write(chunk)
                    on_bytes(len(chunk))
        except requests.exceptions.RequestException as exc:
            raise _Retry(f"{type(exc).__name__}: {exc}") from exc
    if expected is not None and part.stat().st_size != expected:
        raise _Retry("the connection closed before the image was complete")
    part.replace(target)


def _present(target: Path) -> bool:
    """Whether the image is there: it gets its name only once it is complete."""
    return target.is_file() and target.stat().st_size > 0


def _fetch_image(
    session: requests.Session,
    url: str,
    target: Path,
    *,
    stop: threading.Event,
    on_start: Callable[[int, int | None], None],
    on_bytes: Callable[[int], None],
    patience_seconds: float,
    backoff_seconds: float,
) -> str:
    """Fetch one image: "fetched", "skipped" when it is there, or "stopped"."""
    if _present(target):
        return "skipped"
    part = target.with_name(target.name + PARTIAL_SUFFIX)
    last_byte = time.monotonic()

    def arrived(count: int) -> None:
        nonlocal last_byte
        last_byte = time.monotonic()
        on_bytes(count)

    pause = backoff_seconds
    while not stop.is_set():
        before = last_byte
        try:
            _fetch_once(session, url, target, part, stop, on_start, arrived)
            return "fetched"
        except _Stopped:
            return "stopped"
        except _Retry as exc:
            if time.monotonic() - last_byte >= patience_seconds:
                raise DatasetDownloadError(
                    "download_network_failed",
                    f"Gave up on {url}: no byte of it arrived for "
                    f"{patience_seconds:.0f} s. Last error: {exc}",
                ) from exc
            # The pause grows only while PhysioNet sends nothing: an image
            # whose connections break every few tens of KB may need dozens.
            pause = backoff_seconds if last_byte != before else pause
            stop.wait(pause)
            pause = min(pause * 2, MAX_BACKOFF_SECONDS)
        except OSError as exc:
            raise DatasetDownloadError(
                "download_filesystem_failed",
                f"File system error writing {target}: {exc}",
            ) from exc
    return "stopped"


def _account(
    ds: DatasetDefinition,
    root: Path,
    paths: list[str],
    *,
    fetched: int = 0,
    skipped: int = 0,
    failed: list[dict[str, str]] | None = None,
    bytes_downloaded: int = 0,
) -> dict[str, Any]:
    """What a run did, as its result and its errors report it."""
    return {
        "dataset": ds.name,
        "root": str(root),
        "image_count": len(paths),
        "fetched": fetched,
        "skipped": skipped,
        "failed": failed or [],
        "bytes_downloaded": bytes_downloaded,
    }


def _fetch_all(
    ds: DatasetDefinition,
    paths: list[str],
    root: Path,
    credentials: PhysioNetCredentials | None,
    reporter: EventReporter,
    *,
    connections: int,
    patience_seconds: float,
    backoff_seconds: float,
) -> tuple[dict[str, Any], DatasetDownloadError | None]:
    """Fetch `paths` below `root`: the run's account and the error that stopped it.

    The events are `m4 download`'s, one download_file_* series per image.
    They are emitted here only, on the calling thread, so that the workers'
    events never interleave: a worker records how far its image is, and this
    loop reports it about once a second.
    """
    base = ds.file_listing_url or ""
    base = base if base.endswith("/") else base + "/"
    stop = threading.Event()
    lock = threading.Lock()
    received = [0]
    # Image path -> [bytes there, size or None], while it is being fetched
    loading: dict[str, list] = {}
    local = threading.local()
    sessions: list[requests.Session] = []

    def work(path: str) -> str:
        def on_start(there: int, size: int | None) -> None:
            with lock:
                loading[path] = [there, size]

        def on_bytes(count: int) -> None:
            with lock:
                loading[path][0] += count
                received[0] += count

        session = getattr(local, "session", None)
        if session is None:
            session = local.session = physionet_session(credentials)
            with lock:
                sessions.append(session)
        return _fetch_image(
            session,
            base + quote(path),
            root / path,
            stop=stop,
            on_start=on_start,
            on_bytes=on_bytes,
            patience_seconds=patience_seconds,
            backoff_seconds=backoff_seconds,
        )

    fetched = skipped = 0
    failed: list[dict[str, str]] = []
    fatal: DatasetDownloadError | None = None
    reported: dict[str, int] = {}  # Image path -> bytes last reported
    reporter.emit("download_started", dataset=ds.name, file_count=len(paths))
    pool = ThreadPoolExecutor(max_workers=connections)
    try:
        futures = {pool.submit(work, path): path for path in paths}
        pending = set(futures)
        last_tick = time.monotonic()
        while pending:
            done, pending = wait(
                pending, timeout=PROGRESS_SECONDS, return_when=FIRST_COMPLETED
            )
            for future in done:
                path = futures[future]
                target = root / path
                with lock:
                    loading.pop(path, None)
                reported.pop(path, None)
                try:
                    outcome = future.result()
                except DatasetDownloadError as exc:
                    if exc.code in FATAL_CODES:
                        fatal = fatal or exc
                        stop.set()
                        continue
                    failed.append(
                        {"image_path": path, "code": exc.code, "message": exc.message}
                    )
                    reporter.emit(
                        "download_file_failed",
                        path=str(target),
                        code=exc.code,
                        message=exc.message,
                    )
                    continue
                if outcome == "fetched":
                    fetched += 1
                    size = target.stat().st_size
                    reporter.emit(
                        "download_file_completed",
                        path=str(target),
                        bytes_downloaded=size,
                        bytes_total=size,
                    )
                elif outcome == "skipped":
                    skipped += 1
                    reporter.emit(
                        "download_file_skipped",
                        path=str(target),
                        bytes_total=target.stat().st_size,
                        reason="complete",
                    )
            now = time.monotonic()
            tick = now - last_tick >= PROGRESS_SECONDS
            if tick:
                last_tick = now
            with lock:
                snapshot = {path: list(state) for path, state in loading.items()}
            for path, (there, size) in snapshot.items():
                if path not in reported:
                    event = "download_file_started"
                    extra = {"url": base + quote(path)}
                elif tick and reported[path] != there:
                    event, extra = "download_file_progress", {}
                else:
                    continue
                reporter.emit(
                    event,
                    **extra,
                    path=str(root / path),
                    bytes_downloaded=there,
                    bytes_total=size,
                )
                reported[path] = there
    except KeyboardInterrupt:
        stop.set()
        fatal = fatal or DatasetDownloadError(
            "download_interrupted", "Fetching the images was interrupted."
        )
    finally:
        stop.set()  # Whatever ended the loop, the workers end too
        pool.shutdown(wait=True, cancel_futures=True)
        for session in sessions:
            session.close()

    account = _account(
        ds,
        root,
        paths,
        fetched=fetched,
        skipped=skipped,
        failed=failed,
        bytes_downloaded=received[0],
    )
    if fatal is None:
        reporter.emit(
            "download_completed",
            dataset=ds.name,
            file_count=fetched + skipped,
            failed_count=len(failed),
        )
    return account, fatal


def _paths_for_ids(
    ds: DatasetDefinition, ids: list[str]
) -> tuple[dict[str, str], CommandError | None]:
    """The image path of each id the dataset's images view knows."""
    from m4.core.backends.duckdb import DuckDBBackend

    images = ds.images
    assert images is not None
    try:
        con = DuckDBBackend()._connect(ds)
    except M4Error as exc:
        return {}, _error(
            ERROR_DATASET_NOT_INITIALIZED,
            f"M4 looks {images.id_column} values up in {images.view}, and "
            f"cannot open '{ds.name}': {exc}",
            f"Run m4 init {ds.name}, or give the {IMAGE_PATH_COLUMN} column instead.",
        )
    try:
        rows = con.execute(
            f"SELECT CAST(i.{images.id_column} AS VARCHAR), i.{IMAGE_PATH_COLUMN} "
            f"FROM {images.view} i "
            "JOIN (SELECT unnest($ids) AS wanted) w "
            f"ON CAST(i.{images.id_column} AS VARCHAR) = w.wanted",
            {"ids": ids},
        ).fetchall()
    except duckdb.Error as exc:
        return {}, _error(
            ERROR_DATASET_NOT_INITIALIZED,
            f"M4 could not look the images up in {images.view}: "
            f"{str(exc).splitlines()[0]}",
            f"Initialize the dataset again: m4 init {ds.name}",
        )
    finally:
        con.close()
    return {image_id: path for image_id, path in rows if path}, None


def _row_paths(
    ds: DatasetDefinition, frame: pd.DataFrame
) -> tuple[list[str | None], CommandError | None]:
    """The path of the image each row of `frame` names, by path or by id.

    None for a row whose path or id is empty.
    """
    images = ds.images
    assert images is not None
    columns = {str(column).strip().lower(): column for column in frame.columns}
    path_column = next((columns[c] for c in PATH_COLUMNS if c in columns), None)
    if path_column is not None:
        paths = [
            None if pd.isna(value) else str(value).strip()
            for value in frame[path_column]
        ]
        wrong = [path for path in paths if path and not images.is_image_path(path)]
        if wrong:
            return [], _error(
                ERROR_IMAGE_LIST_INVALID,
                f"{len(wrong)} {path_column} value(s) are not paths of "
                f"'{ds.name}' images ({_listed(wrong)}).",
                f"Take the paths from {images.view}.{IMAGE_PATH_COLUMN}, "
                f"which follow {images.path_template}.",
            )
        return [path or None for path in paths], None
    if images.id_column not in columns:
        return [], _error(
            ERROR_IMAGE_LIST_INVALID,
            f"The image list has neither an {IMAGE_PATH_COLUMN} nor a "
            f"{images.id_column} column.",
            f"Select {images.id_column} or {IMAGE_PATH_COLUMN} from {images.view}.",
        )
    ids = [
        None if pd.isna(value) else str(value).strip()
        for value in frame[columns[images.id_column]]
    ]
    wanted = list(dict.fromkeys(image_id for image_id in ids if image_id))
    found, problem = _paths_for_ids(ds, wanted) if wanted else ({}, None)
    if problem:
        return [], problem
    unknown = [image_id for image_id in wanted if image_id not in found]
    if unknown:
        return [], _error(
            ERROR_IMAGE_LIST_INVALID,
            f"{len(unknown)} {images.id_column} value(s) are not in "
            f"{images.view} ({_listed(unknown)}).",
        )
    # A custom dataset's table could hold anything
    wrong = [path for path in found.values() if not images.is_image_path(path)]
    if wrong:
        return [], _error(
            ERROR_IMAGE_LIST_INVALID,
            f"{images.view} gives {len(wrong)} path(s) that do not follow "
            f"{images.path_template} ({_listed(wrong)}).",
        )
    return [found[image_id] if image_id else None for image_id in ids], None


def _image_paths(
    ds: DatasetDefinition, frame: pd.DataFrame
) -> tuple[list[str], CommandError | None]:
    """The paths of the images `frame` names, each once."""
    rows, problem = _row_paths(ds, frame)
    if problem:
        return [], problem
    paths = list(dict.fromkeys(path for path in rows if path))
    if not paths:
        return [], _error(ERROR_IMAGE_LIST_INVALID, "The image list names no images.")
    return paths, None


def _imaging_dataset(dataset_name: str) -> DatasetDefinition | CommandError:
    ensure_custom_datasets_loaded()
    ds = DatasetRegistry.get(dataset_name.lower())
    if not ds:
        imaging = [d.name for d in DatasetRegistry.list_all() if d.images]
        return _error(
            ERROR_DATASET_NOT_FOUND,
            f"Dataset '{dataset_name}' is not supported or not configured.",
            f"Imaging datasets: {', '.join(imaging) or 'none'}",
        )
    if ds.images is None or not ds.file_listing_url:
        return _error(
            ERROR_NOT_AN_IMAGING_DATASET,
            f"'{ds.name}' has no image files for M4 to fetch.",
        )
    return ds


def _image_root(ds: DatasetDefinition, target: str | Path | None) -> Path:
    return Path(target).expanduser().resolve() if target else default_raw_root(ds.name)


def image_locations(
    dataset_name: str,
    images: pd.DataFrame,
    *,
    target: str | Path | None = None,
) -> pd.DataFrame | CommandError:
    """`images` with each row's `image_path`, `local_path`, and whether it is `present`.

    Fetches nothing. `local_path` is where `m4 fetch-images` puts the image;
    both are None for a row that names no image.
    """
    ds = _imaging_dataset(dataset_name)
    if isinstance(ds, CommandError):
        return ds
    rows, problem = _row_paths(ds, images)
    if problem:
        return problem
    root = _image_root(ds, target)
    located = images.copy()

    def column(values: list) -> pd.Series:
        # Object columns keep None: pandas 3 makes NaN of it in a text column
        return pd.Series(values, index=located.index, dtype=object)

    located[IMAGE_PATH_COLUMN] = column(rows)
    located["local_path"] = column(
        [str(root / path) if path else None for path in rows]
    )
    located["present"] = [bool(path) and _present(root / path) for path in rows]
    return located


def read_image_list(path: str | Path) -> pd.DataFrame:
    """A CSV file of images, every value read as text (ids keep leading zeros)."""
    return pd.read_csv(Path(path).expanduser(), dtype=str)


def fetch_images_service(
    dataset_name: str,
    images: pd.DataFrame | None = None,
    *,
    from_csv: str | Path | None = None,
    target: str | None = None,
    physionet_credentials: PhysioNetCredentials | None = None,
    max_images: int = MAX_IMAGES,
    event_reporter: EventReporter | None = None,
    connections: int = CONNECTIONS,
    patience_seconds: float = PATIENCE_SECONDS,
    backoff_seconds: float = BACKOFF_SECONDS,
) -> CommandResult | CommandError:
    """Fetch the images that `images` or the CSV file `from_csv` names.

    The list names each image by its path below the raw folder
    (`image_path`, or `path`) or by the dataset's image id (`dicom_id` for
    MIMIC-CXR-JPG), which M4 looks up in the initialized dataset. Images land
    at that path below `target`, by default the dataset's raw folder.
    """
    ds = _imaging_dataset(dataset_name)
    if isinstance(ds, CommandError):
        return ds
    if images is None:
        if from_csv is None:
            return _error(ERROR_IMAGE_LIST_INVALID, "No image list was given.")
        try:
            images = read_image_list(from_csv)
        except (OSError, ValueError) as exc:
            return _error(
                ERROR_IMAGE_LIST_INVALID,
                f"Could not read the image list {from_csv}: {exc}",
            )
    paths, problem = _image_paths(ds, images)
    if problem:
        return problem
    root = _image_root(ds, target)
    missing = [path for path in paths if not _present(root / path)]
    if len(missing) > max_images:
        return _error(
            ERROR_TOO_MANY_IMAGES,
            f"{len(missing):,} of the images are not on disk, more than the "
            f"{max_images:,} M4 fetches in one run. PhysioNet sends 1-17 KB/s per "
            "connection, so that many would take days.",
            "Fetch a smaller cohort, or allow this many with --max-images.",
        )
    # Images that are all there need no login, so a caller can try without
    # one first and ask for it only when this says so.
    if missing and ds.requires_authentication and physionet_credentials is None:
        return _error(
            "missing_credentials",
            f"{len(missing)} of {len(paths)} images of '{ds.name}' are not on disk, "
            "and fetching them needs a PhysioNet login.",
            "Pass --physionet-credentials-stdin or --physionet-credentials-file.",
            _account(ds, root, paths, skipped=len(paths) - len(missing)),
        )

    account, fatal = _fetch_all(
        ds,
        paths,
        root,
        physionet_credentials,
        get_event_reporter(event_reporter),
        connections=connections,
        patience_seconds=patience_seconds,
        backoff_seconds=backoff_seconds,
    )
    if fatal is not None:
        hint = (
            access_forbidden_hint(ds)
            if fatal.code == "physionet_access_forbidden"
            else None
        )
        return _error(fatal.code, fatal.message, hint, account)
    if account["failed"]:
        return _error(
            ERROR_IMAGES_INCOMPLETE,
            f"{len(account['failed'])} of {len(paths)} images could not be fetched "
            f"({_listed([f['image_path'] for f in account['failed']])}).",
            "Run the same command again: M4 keeps the images it has and resumes "
            "the others.",
            account,
        )
    return CommandResult(command=COMMAND, data={**account, "status": "completed"})
