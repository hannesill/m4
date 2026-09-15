"""Verify wheel/sdist package payloads against tracked source files."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tracked = (
        subprocess.check_output(["git", "ls-files", "-z", "src/m4"], cwd=root)
        .decode()
        .split("\0")
    )
    expected = {
        name.removeprefix("src/"): (root / name).read_bytes()
        for name in tracked
        if name
    }
    assert expected, "No tracked package files found"
    wheels = list(args.dist.glob("*.whl"))
    sdists = list(args.dist.glob("*.tar.gz"))
    assert len(wheels) == len(sdists) == 1, "Expected one wheel and one sdist"
    wheel, sdist = wheels[0], sdists[0]
    with zipfile.ZipFile(wheel) as archive:
        payload = {
            name: archive.read(name)
            for name in archive.namelist()
            if name.startswith("m4/") and not name.endswith("/")
        }
        metadata = archive.read(
            next(name for name in archive.namelist() if name.endswith("/METADATA"))
        )
        assert any(name.endswith("/LICENSE") for name in archive.namelist())
        assert any(name.endswith("/entry_points.txt") for name in archive.namelist())
    assert payload == expected, "Wheel package differs from tracked source"
    with tarfile.open(sdist) as archive:
        payload = {}
        sdist_metadata = None
        for member in archive.getmembers():
            if not member.isfile():
                continue
            relative = member.name.split("/", 1)[1]
            stream = archive.extractfile(member)
            assert stream is not None
            if relative.startswith("src/m4/"):
                payload[relative.removeprefix("src/")] = stream.read()
            elif relative == "PKG-INFO":
                sdist_metadata = stream.read()
    assert payload == expected, "Sdist package differs from tracked source"
    assert sdist_metadata == metadata, "Wheel/sdist metadata differs"
    version = BytesParser().parsebytes(metadata)["Version"]
    assert f'__version__ = "{version}"' in expected["m4/__init__.py"].decode()
    print(
        json.dumps(
            {
                "version": version,
                "package_files": len(expected),
                "artifacts": {
                    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (wheel, sdist)
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
