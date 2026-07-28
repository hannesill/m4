"""Versioned catalog and materialization contract for bundled M4 skills."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from m4 import __version__
from m4.config import logger

CATALOG_SCHEMA_VERSION = 1
CATALOG_PUBLISHER = "m4"
MANIFEST_FILE_NAME = ".m4-skills-manifest.json"

VALID_TIERS = {"validated", "expert", "community"}
VALID_CATEGORIES = {"clinical", "system"}
VALID_KINDS = {
    "domain",
    "methodology",
    "integration",
    "workflow",
    "maintenance",
    "authoring",
}


@dataclass(frozen=True)
class SkillInfo:
    """Metadata for a bundled skill parsed from SKILL.md frontmatter."""

    name: str
    description: str
    tier: str
    category: str
    path: Path
    kind: str | None = None


def get_skills_source() -> Path:
    """Return the package directory containing bundled skills."""
    return Path(__file__).parent


def discover_skills(source: Path | None = None) -> list[Path]:
    """Find skill directories recursively in deterministic order."""
    root = source or get_skills_source()
    return sorted(path.parent for path in root.rglob("SKILL.md"))


def parse_skill_metadata(skill_dir: Path) -> SkillInfo | None:
    """Parse supported scalar YAML frontmatter from a skill's SKILL.md."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None

    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        logger.debug(f"No frontmatter in {skill_md}")
        return None

    end = text.find("---", 3)
    if end == -1:
        logger.debug(f"Unclosed frontmatter in {skill_md}")
        return None

    fields: dict[str, str] = {}
    for line in text[3:end].strip().splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()

    required = {"name", "description", "tier", "category"}
    missing = required - fields.keys()
    if missing:
        logger.debug(f"Missing frontmatter fields {missing} in {skill_md}")
        return None

    kind = fields.get("kind")
    return SkillInfo(
        name=fields["name"],
        description=fields["description"],
        tier=fields["tier"],
        category=fields["category"],
        path=skill_dir,
        kind=kind or None,
    )


def get_available_skills(
    tier: list[str] | None = None,
    category: list[str] | None = None,
    names: list[str] | None = None,
) -> list[SkillInfo]:
    """List bundled skills, optionally filtered with AND semantics."""
    all_skills = []
    for skill_dir in discover_skills():
        info = parse_skill_metadata(skill_dir)
        if info is not None:
            all_skills.append(info)

    if names is not None:
        name_set = {name.lower() for name in names}
        all_skills = [skill for skill in all_skills if skill.name.lower() in name_set]
    if tier is not None:
        tier_set = {value.lower() for value in tier}
        all_skills = [skill for skill in all_skills if skill.tier.lower() in tier_set]
    if category is not None:
        category_set = {value.lower() for value in category}
        all_skills = [
            skill for skill in all_skills if skill.category.lower() in category_set
        ]

    return sorted(all_skills, key=lambda skill: skill.name)


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validated_relative_path(value: str) -> PurePosixPath:
    relative = PurePosixPath(value)
    if (
        "\\" in value
        or relative.is_absolute()
        or not relative.parts
        or ".." in relative.parts
        or relative.as_posix() != value
    ):
        raise ValueError(f"Unsafe relative skill path: {value}")
    return relative


def _skill_files(skill: SkillInfo) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for candidate in sorted(skill.path.rglob("*")):
        if candidate.is_symlink():
            raise ValueError(f"Skill bundles may not contain symlinks: {candidate}")
        if not candidate.is_file():
            continue
        relative_path = candidate.relative_to(skill.path).as_posix()
        _validated_relative_path(relative_path)
        contents = candidate.read_bytes()
        files.append(
            {
                "path": relative_path,
                "size": len(contents),
                "contentDigest": _sha256(contents),
            }
        )
    if not any(file["path"] == "SKILL.md" for file in files):
        raise ValueError(f"Skill is missing SKILL.md: {skill.path}")
    return files


def _validate_skill(skill: SkillInfo, source: Path) -> None:
    if skill.name != skill.path.name:
        raise ValueError(
            f"Skill name '{skill.name}' must match directory '{skill.path.name}'"
        )
    if skill.tier not in VALID_TIERS:
        raise ValueError(f"Unsupported tier '{skill.tier}' for skill '{skill.name}'")
    if skill.category not in VALID_CATEGORIES:
        raise ValueError(
            f"Unsupported category '{skill.category}' for skill '{skill.name}'"
        )
    if skill.kind is not None and skill.kind not in VALID_KINDS:
        raise ValueError(f"Unsupported kind '{skill.kind}' for skill '{skill.name}'")
    try:
        skill.path.relative_to(source)
    except ValueError as error:
        raise ValueError(f"Skill path escapes bundle root: {skill.path}") from error


def build_catalog(source: Path | None = None) -> dict[str, Any]:
    """Build the deterministic, machine-readable catalog manifest."""
    root = (source or get_skills_source()).resolve()
    skill_dirs = discover_skills(root)
    skills: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for skill_dir in skill_dirs:
        if skill_dir.is_symlink():
            raise ValueError(f"Skill directories may not be symlinks: {skill_dir}")
        info = parse_skill_metadata(skill_dir)
        if info is None:
            raise ValueError(f"Invalid skill metadata: {skill_dir / 'SKILL.md'}")
        _validate_skill(info, root)
        if info.name in seen_names:
            raise ValueError(f"Duplicate skill name: {info.name}")
        seen_names.add(info.name)

        files = _skill_files(info)
        skill_md = next(file for file in files if file["path"] == "SKILL.md")
        tree_digest = _sha256(_canonical_json(files))
        relative_root = info.path.relative_to(root).as_posix()
        descriptor: dict[str, Any] = {
            "id": f"{CATALOG_PUBLISHER}:{info.name}",
            "publisher": CATALOG_PUBLISHER,
            "name": info.name,
            "description": info.description,
            "category": info.category,
            "tier": info.tier,
            "bundleVersion": __version__,
            "contentDigest": skill_md["contentDigest"],
            "treeDigest": tree_digest,
            "relativeRoot": relative_root,
            "files": files,
        }
        if info.kind is not None:
            descriptor["kind"] = info.kind
        skills.append(descriptor)

    bundle_digest = _sha256(
        _canonical_json(
            {
                "schemaVersion": CATALOG_SCHEMA_VERSION,
                "publisher": CATALOG_PUBLISHER,
                "packageVersion": __version__,
                "skills": skills,
            }
        )
    )
    return {
        "schemaVersion": CATALOG_SCHEMA_VERSION,
        "publisher": CATALOG_PUBLISHER,
        "packageVersion": __version__,
        "bundleDigest": bundle_digest,
        "skills": skills,
    }


def _absolute_path_without_symlink_resolution(path: Path) -> Path:
    """Return an absolute lexical path without following filesystem symlinks."""
    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return Path(os.path.abspath(os.fspath(expanded)))


def _reject_symlink_components(path: Path) -> None:
    """Reject symlinks in every existing component, including dangling targets."""
    absolute = _absolute_path_without_symlink_resolution(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        is_windows_reparse_point = os.name == "nt" and bool(
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x00000400)
        )
        if stat.S_ISLNK(metadata.st_mode) or is_windows_reparse_point:
            raise ValueError(f"Managed bundle path may not contain symlinks: {current}")
        if current != absolute and not stat.S_ISDIR(metadata.st_mode):
            raise NotADirectoryError(
                f"Managed bundle parent is not a directory: {current}"
            )


def _raise_atomic_publish_error(target: Path, error_number: int) -> None:
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(
            f"Refusing to replace concurrently created target: {target}"
        )
    raise OSError(error_number, os.strerror(error_number), target)


def _atomic_publish_directory(source: Path, target: Path) -> None:
    """Atomically rename SOURCE to an absent TARGET without replacement."""
    if source.parent != target.parent:
        raise ValueError("Atomic publication requires source and target to be siblings")

    if os.name == "nt":
        move_file_ex = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        move_file_ex.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        move_file_ex.restype = ctypes.c_int
        if not move_file_ex(str(source), str(target), 0):
            error_number = ctypes.get_last_error()
            if error_number in {80, 183}:  # ERROR_FILE_EXISTS, ERROR_ALREADY_EXISTS
                raise FileExistsError(
                    f"Refusing to replace concurrently created target: {target}"
                )
            raise ctypes.WinError(error_number)
        return

    open_flags = os.O_RDONLY
    open_flags |= getattr(os, "O_DIRECTORY", 0)
    open_flags |= getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(target.parent, open_flags)
    try:
        parent_stat = os.fstat(parent_fd)
        current_parent_stat = target.parent.stat(follow_symlinks=False)
        if (
            parent_stat.st_dev,
            parent_stat.st_ino,
        ) != (
            current_parent_stat.st_dev,
            current_parent_stat.st_ino,
        ):
            raise OSError("Managed bundle parent changed during materialization")

        libc = ctypes.CDLL(None, use_errno=True)
        source_name = os.fsencode(source.name)
        target_name = os.fsencode(target.name)

        if sys.platform == "darwin":
            rename = libc.renameatx_np
            rename.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            rename.restype = ctypes.c_int
            result = rename(
                parent_fd,
                source_name,
                parent_fd,
                target_name,
                0x00000004,  # RENAME_EXCL
            )
        elif sys.platform.startswith("linux"):
            try:
                rename = libc.renameat2
            except AttributeError as error:
                raise RuntimeError(
                    "Atomic no-replace publication requires renameat2 on Linux"
                ) from error
            rename.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            rename.restype = ctypes.c_int
            result = rename(
                parent_fd,
                source_name,
                parent_fd,
                target_name,
                0x00000001,  # RENAME_NOREPLACE
            )
        else:
            raise RuntimeError(
                f"Atomic no-replace publication is unsupported on {sys.platform}"
            )

        if result != 0:
            _raise_atomic_publish_error(target, ctypes.get_errno())
    finally:
        os.close(parent_fd)


def verify_materialized_bundle(target: Path, manifest: dict[str, Any]) -> None:
    """Verify the manifest and exact materialized filesystem tree."""
    root = _absolute_path_without_symlink_resolution(target)
    _reject_symlink_components(root)
    declared_paths: set[Path] = set()
    declared_directories: set[Path] = {root}

    for skill in manifest["skills"]:
        relative_root = _validated_relative_path(skill["relativeRoot"])
        skill_root = root.joinpath(*relative_root.parts)
        for file in skill["files"]:
            relative_file = _validated_relative_path(file["path"])
            file_path = skill_root.joinpath(*relative_file.parts)
            file_metadata = file_path.lstat()
            if stat.S_ISLNK(file_metadata.st_mode):
                raise ValueError(f"Materialized bundle contains symlink: {file_path}")
            if not stat.S_ISREG(file_metadata.st_mode):
                raise ValueError(
                    f"Materialized bundle contains special file: {file_path}"
                )
            resolved = file_path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ValueError(f"Materialized file escapes bundle root: {file_path}")
            contents = resolved.read_bytes()
            if len(contents) != file["size"]:
                raise ValueError(f"Materialized file size mismatch: {file_path}")
            if _sha256(contents) != file["contentDigest"]:
                raise ValueError(f"Materialized file digest mismatch: {file_path}")
            declared_paths.add(resolved)
            parent = resolved.parent
            while parent != root:
                declared_directories.add(parent)
                parent = parent.parent

    actual_paths: set[Path] = set()
    actual_directories: set[Path] = {root}
    manifest_path = root / MANIFEST_FILE_NAME
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                candidate = Path(entry.path)
                if entry.is_symlink():
                    raise ValueError(
                        f"Materialized bundle contains symlink: {candidate}"
                    )
                if entry.is_dir(follow_symlinks=False):
                    actual_directories.add(candidate)
                    pending.append(candidate)
                elif entry.is_file(follow_symlinks=False):
                    if candidate == manifest_path:
                        continue
                    actual_paths.add(candidate)
                else:
                    raise ValueError(
                        f"Materialized bundle contains special file: {candidate}"
                    )

    try:
        materialized_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid materialized manifest: {manifest_path}") from error
    if materialized_manifest != manifest:
        raise ValueError(f"Materialized manifest mismatch: {manifest_path}")

    if actual_paths != declared_paths:
        missing = sorted(str(path) for path in declared_paths - actual_paths)
        extra = sorted(str(path) for path in actual_paths - declared_paths)
        raise ValueError(
            f"Materialized file set mismatch; missing={missing}, extra={extra}"
        )
    if actual_directories != declared_directories:
        missing = sorted(
            str(path) for path in declared_directories - actual_directories
        )
        extra = sorted(str(path) for path in actual_directories - declared_directories)
        raise ValueError(
            f"Materialized directory set mismatch; missing={missing}, extra={extra}"
        )


def materialize_catalog(target: Path) -> dict[str, Any]:
    """Atomically copy the verified skill bundle into an explicit target."""
    manifest = build_catalog()
    target = _absolute_path_without_symlink_resolution(target)
    _reject_symlink_components(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(target)

    if target.exists():
        manifest_path = target / MANIFEST_FILE_NAME
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing != manifest:
                raise ValueError(
                    "Existing bundle manifest does not match current catalog"
                )
            verify_materialized_bundle(target, manifest)
        except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
            raise FileExistsError(
                f"Refusing to replace existing target with an unverified bundle: {target}"
            ) from error
        return {
            "schemaVersion": CATALOG_SCHEMA_VERSION,
            "publisher": CATALOG_PUBLISHER,
            "packageVersion": manifest["packageVersion"],
            "bundleDigest": manifest["bundleDigest"],
            "skillCount": len(manifest["skills"]),
            "target": str(target),
            "manifestPath": str(manifest_path),
            "reused": True,
        }

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{target.name}-", dir=str(target.parent))
    )
    try:
        source = get_skills_source().resolve()
        for skill in manifest["skills"]:
            relative_root = _validated_relative_path(skill["relativeRoot"])
            source_skill = source.joinpath(*relative_root.parts)
            target_skill = temporary.joinpath(*relative_root.parts)
            target_skill.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_skill, target_skill, symlinks=False)

        manifest_path = temporary / MANIFEST_FILE_NAME
        manifest_path.write_text(
            f"{json.dumps(manifest, indent=2, ensure_ascii=False)}\n",
            encoding="utf-8",
        )
        verify_materialized_bundle(temporary, manifest)
        _atomic_publish_directory(temporary, target)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return {
        "schemaVersion": CATALOG_SCHEMA_VERSION,
        "publisher": CATALOG_PUBLISHER,
        "packageVersion": manifest["packageVersion"],
        "bundleDigest": manifest["bundleDigest"],
        "skillCount": len(manifest["skills"]),
        "target": str(target),
        "manifestPath": str(target / MANIFEST_FILE_NAME),
        "reused": False,
    }
