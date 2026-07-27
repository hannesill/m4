import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from m4.cli import app
from m4.skills.catalog import (
    CATALOG_SCHEMA_VERSION,
    MANIFEST_FILE_NAME,
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


def test_catalog_v1_compatibility_fixture_matches_publisher_output():
    expected = json.loads(CATALOG_V1_FIXTURE_PATH.read_text(encoding="utf-8"))

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
