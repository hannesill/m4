"""Stream members out of retained release archives without extracting them.

Release archives are tens of gigabytes uncompressed, so verification and
repair scripts read selected members directly from the compressed stream.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tarfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def open_tar_stream(archive: Path) -> Iterator[tarfile.TarFile]:
    """Open a .tar, .tar.gz, or .tar.zst archive for sequential reading."""
    name = archive.name
    if not (name.endswith(".tar.zst") or name.endswith(".tzst")):
        with tarfile.open(archive, "r|*") as tar:
            yield tar
        return
    zstd = shutil.which("zstd")
    if not zstd:
        raise RuntimeError("zstd is required to read .tar.zst archives")
    proc = subprocess.Popen(
        [zstd, "-dc", "--long=31", str(archive)], stdout=subprocess.PIPE
    )
    assert proc.stdout is not None
    stream: IO[bytes] = proc.stdout
    try:
        with tarfile.open(fileobj=stream, mode="r|") as tar:
            yield tar
    finally:
        stream.close()
        returncode = proc.wait()
        if returncode not in (0, -13):  # -13: SIGPIPE when the reader stops early.
            raise RuntimeError(f"zstd exited with {returncode} for {archive}")


def iter_members(
    archive: Path, wanted: Callable[[str], bool]
) -> Iterator[tuple[tarfile.TarInfo, bytes]]:
    """Yield (member, payload) for regular-file members whose name is wanted."""
    with open_tar_stream(archive) as tar:
        for member in tar:
            if not member.isfile() or not wanted(member.name):
                continue
            handle = tar.extractfile(member)
            assert handle is not None
            yield member, handle.read()
