import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from m4.cli import app
from m4.skills.catalog import (
    CATALOG_SCHEMA_VERSION,
    MANIFEST_FILE_NAME,
    _account_home,
    _atomic_publish_directory,
    _is_link,
    _reject_symlink_components,
    _validated_relative_path,
    build_catalog,
    materialize_catalog,
    verify_materialized_bundle,
)

runner = CliRunner()
CATALOG_V1_FIXTURE_ROOT = Path("tests/fixtures/skills_catalog_v1")
CATALOG_V1_FIXTURE_PATH = Path("tests/fixtures/skills_catalog_v1.json")


@pytest.mark.parametrize(
    "value",
    ["../escape", "clinical/../escape", "clinical//escape", "clinical\\escape"],
)
def test_catalog_rejects_noncanonical_relative_paths(value: str):
    with pytest.raises(ValueError, match="Unsafe relative skill path"):
        _validated_relative_path(value)


def test_catalog_is_deterministic_and_covers_every_packaged_skill():
    first = build_catalog()
    second = build_catalog()

    assert first == second
    assert first["schemaVersion"] == CATALOG_SCHEMA_VERSION
    assert first["publisher"] == "m4"
    assert first["bundleDigest"].startswith("sha256:")

    skill_files = sorted(
        path for path in Path("src/m4/skills").rglob("SKILL.md") if path.is_file()
    )
    assert len(first["skills"]) == len(skill_files)
    assert {skill["id"] for skill in first["skills"]} == {
        f"m4:{path.parent.name}" for path in skill_files
    }

    for skill in first["skills"]:
        assert skill["kind"] in {
            "domain",
            "methodology",
            "integration",
            "workflow",
            "maintenance",
            "authoring",
        }
        assert skill["contentDigest"].startswith("sha256:")
        assert skill["treeDigest"].startswith("sha256:")
        assert skill["files"]
        assert any(file["path"] == "SKILL.md" for file in skill["files"])
        for file in skill["files"]:
            packaged = Path("src/m4/skills") / skill["relativeRoot"] / file["path"]
            assert packaged.is_file()
            assert file["size"] == packaged.stat().st_size
            assert file["contentDigest"].startswith("sha256:")


def test_catalog_v1_compatibility_fixture_matches_publisher_output(
    monkeypatch: pytest.MonkeyPatch,
):
    import m4.skills.catalog as catalog

    expected = json.loads(CATALOG_V1_FIXTURE_PATH.read_text(encoding="utf-8"))
    monkeypatch.setattr(catalog, "__version__", expected["packageVersion"])

    assert build_catalog(CATALOG_V1_FIXTURE_ROOT) == expected


def test_catalog_rejects_symlinks(tmp_path: Path):
    skill = tmp_path / "clinical" / "unsafe"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\n"
        "name: unsafe\n"
        "description: Unsafe fixture.\n"
        "tier: community\n"
        "category: clinical\n"
        "kind: domain\n"
        "---\n",
        encoding="utf-8",
    )
    outside = tmp_path / "outside.sql"
    outside.write_text("select 1", encoding="utf-8")
    (skill / "scripts").mkdir()
    (skill / "scripts" / "escape.sql").symlink_to(outside)

    with pytest.raises(ValueError, match="symlinks"):
        build_catalog(tmp_path)


def test_materialize_catalog_is_verified_atomic_and_reusable(tmp_path: Path):
    target = tmp_path / "managed" / "bundle"

    first = materialize_catalog(target)
    assert first["reused"] is False
    assert first["target"] == str(target.resolve())

    manifest = json.loads((target / MANIFEST_FILE_NAME).read_text(encoding="utf-8"))
    verify_materialized_bundle(target, manifest)

    second = materialize_catalog(target)
    assert second == {**first, "reused": True}


def test_materialize_refuses_existing_unverified_target(tmp_path: Path):
    target = tmp_path / "bundle"
    target.mkdir()
    marker = target / "owned.txt"
    marker.write_text("preserve me", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Refusing to replace"):
        materialize_catalog(target)

    assert marker.read_text(encoding="utf-8") == "preserve me"


def test_materialize_rejects_dangling_target_symlink(tmp_path: Path):
    managed = tmp_path / "managed"
    managed.mkdir()
    redirected = tmp_path / "redirected"
    target = managed / "bundle"
    target.symlink_to(redirected, target_is_directory=True)

    with pytest.raises(ValueError, match="may not contain symlinks"):
        materialize_catalog(target)

    assert target.is_symlink()
    assert not redirected.exists()


def test_materialize_rejects_symlinked_parent(tmp_path: Path):
    redirected = tmp_path / "redirected"
    redirected.mkdir()
    managed = tmp_path / "managed"
    managed.symlink_to(redirected, target_is_directory=True)

    with pytest.raises(ValueError, match="may not contain symlinks"):
        materialize_catalog(managed / "bundle")

    assert not (redirected / "bundle").exists()


# What lstat reports on Windows. A junction keeps S_IFDIR; only its reparse tag
# says it is a link. A OneDrive placeholder is a reparse point too, but its tag
# is not a link's, and after Python opens it as the folder itself it can be 0.
# (The stat module has the tags only on Windows.)
IO_REPARSE_TAG_SYMLINK = 0xA000000C
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
IO_REPARSE_TAG_CLOUD_6 = 0x9000601A
WINDOWS_LSTAT = {
    "symlink": (stat.S_IFLNK, IO_REPARSE_TAG_SYMLINK),
    "junction": (stat.S_IFDIR, IO_REPARSE_TAG_MOUNT_POINT),
    "onedrive-placeholder": (stat.S_IFDIR, IO_REPARSE_TAG_CLOUD_6),
    "onedrive-placeholder-opened": (stat.S_IFDIR, 0),
    "folder": (stat.S_IFDIR, 0),
}


@pytest.mark.parametrize(
    ("kind", "is_link"),
    [
        ("symlink", True),
        ("junction", True),
        ("onedrive-placeholder", False),
        ("onedrive-placeholder-opened", False),
        ("folder", False),
    ],
)
def test_links_are_told_from_other_reparse_points(kind: str, is_link: bool):
    mode, tag = WINDOWS_LSTAT[kind]
    metadata = SimpleNamespace(st_mode=mode | 0o755, st_reparse_tag=tag)

    assert _is_link(metadata) is is_link


def _pretend_windows_reparse_point(
    monkeypatch: pytest.MonkeyPatch, path: Path, kind: str
) -> None:
    """Make lstat report PATH, a real folder, as Windows reports KIND."""
    real_lstat = Path.lstat
    mode, tag = WINDOWS_LSTAT[kind]

    def lstat(self: Path):
        if self == path:
            return SimpleNamespace(st_mode=mode | 0o755, st_reparse_tag=tag)
        return real_lstat(self)

    monkeypatch.setattr(Path, "lstat", lstat)


@pytest.mark.parametrize(
    ("reparse_point", "kind"),
    [
        ("", "junction"),  # C:\Users\name moved to another drive
        ("..", "junction"),
        ("OneDrive", "onedrive-placeholder"),
        ("OneDrive", "onedrive-placeholder-opened"),
    ],
)
def test_junctions_in_the_home_path_and_onedrive_placeholders_are_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reparse_point: str, kind: str
):
    home = tmp_path / "profile"
    target = home / "OneDrive" / "lincei" / "skills"
    target.parent.mkdir(parents=True)
    monkeypatch.setattr("m4.skills.catalog._account_home", lambda: home)
    _pretend_windows_reparse_point(
        monkeypatch, Path(os.path.normpath(home / reparse_point)), kind
    )

    _reject_symlink_components(target)


@pytest.mark.parametrize("kind", ["junction", "symlink"])
def test_links_below_the_home_folder_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
):
    home = tmp_path / "profile"
    target = home / "lincei" / "skills"
    target.parent.mkdir(parents=True)
    monkeypatch.setattr("m4.skills.catalog._account_home", lambda: home)
    _pretend_windows_reparse_point(monkeypatch, home / "lincei", kind)

    with pytest.raises(ValueError, match="may not contain symlinks"):
        _reject_symlink_components(target)


def test_materialize_through_a_linked_home_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    home = tmp_path / "home"
    home.symlink_to(real_home, target_is_directory=True)
    monkeypatch.setattr("m4.skills.catalog._account_home", lambda: home)

    first = materialize_catalog(home / "skills")

    assert first["reused"] is False
    assert first["target"] == str(real_home / "skills")
    assert (real_home / "skills" / MANIFEST_FILE_NAME).is_file()
    assert materialize_catalog(home / "skills") == {**first, "reused": True}

    redirected = tmp_path / "redirected"
    redirected.mkdir()
    (home / "managed").symlink_to(redirected, target_is_directory=True)
    with pytest.raises(ValueError, match="may not contain symlinks"):
        materialize_catalog(home / "managed" / "skills")
    assert not (redirected / "skills").exists()


def test_a_home_set_in_the_environment_allows_no_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    redirected = tmp_path / "redirected"
    redirected.mkdir()
    link = tmp_path / "link"
    link.symlink_to(redirected, target_is_directory=True)
    monkeypatch.setenv("HOME", str(link / "below"))
    monkeypatch.setenv("USERPROFILE", str(link / "below"))

    with pytest.raises(ValueError, match="may not contain symlinks"):
        materialize_catalog(link / "skills")
    assert not (redirected / "skills").exists()


def test_the_account_home_is_not_read_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Also run on Windows, where it asks the system for the profile folder."""
    home = Path.home()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    assert _account_home() == home


def test_verify_rejects_a_linked_folder_inside_the_bundle(tmp_path: Path):
    target = tmp_path / "bundle"
    materialize_catalog(target)
    manifest = json.loads((target / MANIFEST_FILE_NAME).read_text(encoding="utf-8"))
    (target / "linked").symlink_to(tmp_path, target_is_directory=True)

    with pytest.raises(ValueError, match="contains symlink"):
        verify_materialized_bundle(target, manifest)


def test_materialize_does_not_replace_concurrently_claimed_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import m4.skills.catalog as catalog

    target = tmp_path / "bundle"

    def claim_then_publish(source: Path, destination: Path) -> None:
        destination.mkdir()
        _atomic_publish_directory(source, destination)

    monkeypatch.setattr(catalog, "_atomic_publish_directory", claim_then_publish)

    with pytest.raises(FileExistsError, match="concurrently created target"):
        materialize_catalog(target)

    assert target.is_dir()
    assert list(target.iterdir()) == []
    assert not list(tmp_path.glob(".bundle-*"))


def test_verify_rejects_undeclared_empty_directory(tmp_path: Path):
    target = tmp_path / "bundle"
    materialize_catalog(target)
    manifest = json.loads((target / MANIFEST_FILE_NAME).read_text(encoding="utf-8"))
    (target / "undeclared-empty").mkdir()

    with pytest.raises(ValueError, match="directory set mismatch"):
        verify_materialized_bundle(target, manifest)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is unsupported")
def test_verify_rejects_special_file(tmp_path: Path):
    target = tmp_path / "bundle"
    materialize_catalog(target)
    manifest = json.loads((target / MANIFEST_FILE_NAME).read_text(encoding="utf-8"))
    os.mkfifo(target / "undeclared-fifo")

    with pytest.raises(ValueError, match="special file"):
        verify_materialized_bundle(target, manifest)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is unsupported")
def test_verify_rejects_declared_file_replaced_with_fifo(tmp_path: Path):
    target = tmp_path / "bundle"
    materialize_catalog(target)
    manifest = json.loads((target / MANIFEST_FILE_NAME).read_text(encoding="utf-8"))
    skill = manifest["skills"][0]
    declared = target / skill["relativeRoot"] / skill["files"][0]["path"]
    declared.unlink()
    os.mkfifo(declared)

    with pytest.raises(ValueError, match="special file"):
        verify_materialized_bundle(target, manifest)


def test_materialize_refuses_manifest_tampering_with_unchanged_bundle_digest(
    tmp_path: Path,
):
    target = tmp_path / "bundle"
    materialize_catalog(target)
    manifest_path = target / MANIFEST_FILE_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["skills"][0]["description"] = "Tampered"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(FileExistsError, match="Refusing to replace"):
        materialize_catalog(target)


def test_skills_catalog_cli_emits_json():
    result = runner.invoke(app, ["skills", "catalog", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schemaVersion"] == CATALOG_SCHEMA_VERSION
    assert payload["publisher"] == "m4"
    assert payload["skills"]


def test_skills_materialize_cli_emits_json(tmp_path: Path):
    target = tmp_path / "bundle"
    result = runner.invoke(
        app,
        ["skills", "materialize", "--target", str(target), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["target"] == str(target.resolve())
    assert (target / MANIFEST_FILE_NAME).is_file()
