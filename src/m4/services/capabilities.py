from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path
from typing import Any

from m4.config import (
    ensure_custom_datasets_loaded,
    get_active_backend,
    get_bigquery_project_id,
)
from m4.core.datasets import DatasetDefinition, DatasetRegistry
from m4.core.derived.builtins import has_derived_support, list_builtins
from m4.core.tools import ToolRegistry, init_tools

CAPABILITIES_SCHEMA_VERSION = 1


def _field_default(field: Any) -> Any:
    if field.default is not MISSING:
        return field.default
    if field.default_factory is not MISSING:  # type: ignore[attr-defined]
        return field.default_factory()  # type: ignore[misc]
    return None


def _input_fields(input_model: type) -> list[dict[str, Any]]:
    if not is_dataclass(input_model):
        return []
    result = []
    for field in fields(input_model):
        result.append(
            {
                "name": field.name,
                "type": str(field.type),
                "required": (
                    field.default is MISSING and field.default_factory is MISSING  # type: ignore[attr-defined]
                ),
                "default": _field_default(field),
            }
        )
    return result


def _dataset_payload(ds: DatasetDefinition) -> dict[str, Any]:
    return {
        "name": ds.name,
        "description": ds.description,
        "version": ds.version,
        "requires_authentication": ds.requires_authentication,
        "modalities": sorted(modality.name for modality in ds.modalities),
        "dataset_page_url": ds.dataset_page_url,
        "dua_url": ds.dua_url,
        "file_listing_url": ds.file_listing_url,
        "bigquery": {
            "available": bool(ds.bigquery_dataset_ids),
            "project_id": ds.bigquery_project_id,
            "dataset_ids": list(ds.bigquery_dataset_ids),
            "schema_mapping": dict(ds.bigquery_schema_mapping),
            "access_url": ds.bigquery_access_url,
        },
        "verification_table": ds.primary_verification_table,
        "schema_mapping": dict(ds.schema_mapping),
        "expected_local_layout": {
            "recommended_raw_root": ds.recommended_local_target_root,
            "raw_subdirectories": list(ds.expected_raw_subdirectories),
            "parquet_root": f"m4_data/parquet/{ds.name}",
            "duckdb_filename": ds.default_duckdb_filename,
        },
        "related_datasets": dict(ds.related_datasets),
    }


def _tool_payloads() -> list[dict[str, Any]]:
    init_tools()
    datasets = DatasetRegistry.list_all()
    result = []
    for tool in ToolRegistry.list_all():
        required_modalities = sorted(
            modality.name for modality in getattr(tool, "required_modalities", [])
        )
        compatible = []
        for ds in datasets:
            try:
                if tool.is_compatible(ds):
                    compatible.append(ds.name)
            except Exception:
                continue
        result.append(
            {
                "name": tool.name,
                "description": tool.description,
                "input_fields": _input_fields(tool.input_model),
                "required_modalities": required_modalities,
                "compatible_datasets": sorted(compatible),
                "supported_datasets": (
                    sorted(tool.supported_datasets)
                    if tool.supported_datasets is not None
                    else None
                ),
            }
        )
    return sorted(result, key=lambda item: item["name"])


def _skill_inventory() -> list[dict[str, Any]]:
    skills_dir = Path(__file__).resolve().parents[1] / "skills"
    if not skills_dir.exists():
        return []

    inventory = []
    for skill_file in sorted(skills_dir.glob("*/*/SKILL.md")):
        skill_dir = skill_file.parent
        category = skill_dir.parent.name
        description = ""
        try:
            for line in skill_file.read_text(encoding="utf-8").splitlines()[:40]:
                if line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()
                    break
        except OSError:
            pass
        inventory.append(
            {
                "name": skill_dir.name,
                "category": category,
                "description": description,
                "packaged": True,
            }
        )
    return inventory


def _derived_inventory() -> dict[str, Any]:
    datasets: dict[str, Any] = {}
    for ds in DatasetRegistry.list_all():
        if not has_derived_support(ds.name):
            datasets[ds.name] = {"available": False, "tables": []}
            continue
        try:
            tables = list_builtins(ds.name)
        except Exception:
            tables = []
        datasets[ds.name] = {"available": True, "tables": tables}
    return datasets


def build_capabilities_manifest() -> dict[str, Any]:
    """Return the stable M4 capability manifest."""
    ensure_custom_datasets_loaded()

    commands = [
        {"name": "capabilities", "flags": ["--json"], "mutates": False},
        {"name": "doctor", "flags": ["--json", "--paths"], "mutates": False},
        {"name": "status", "flags": ["--all", "--derived", "--json"], "mutates": False},
        {
            "name": "schema",
            "flags": ["--dataset", "--backend", "--json"],
            "mutates": False,
        },
        {
            "name": "query",
            "flags": ["--dataset", "--backend", "--sql", "--json"],
            "mutates": False,
        },
        {
            "name": "download",
            "flags": [
                "--target",
                "--json",
                "--command-only",
                "--physionet-credentials-file",
                "--events",
            ],
            "mutates": True,
        },
        {
            "name": "init",
            "flags": [
                "--src",
                "--db-path",
                "--force",
                "--json",
                "--download",
                "--physionet-credentials-file",
                "--events",
            ],
            "mutates": True,
        },
        {"name": "config", "flags": ["--backend", "--project-id"], "mutates": True},
        {
            "name": "agent-env",
            "flags": [
                "--mode",
                "--dataset",
                "--backend",
                "--project-id",
                "--json",
                "--format",
                "--paths",
            ],
            "mutates": False,
        },
        {
            "name": "setup-agent",
            "flags": [
                "--mode",
                "--client",
                "--dataset",
                "--backend",
                "--project-id",
                "--format",
                "--apply",
            ],
            "mutates": False,
            "mutates_with": ["--apply"],
        },
        {
            "name": "quickstart",
            "flags": [
                "--workflow",
                "--dataset",
                "--backend",
                "--project-id",
                "--apply",
                "--json",
            ],
            "mutates": False,
            "mutates_with": ["--apply"],
        },
    ]

    return {
        "schema_version": CAPABILITIES_SCHEMA_VERSION,
        "interfaces": {
            "cli": {"entrypoint": "m4"},
            "python_api": {"function": "m4.get_capabilities"},
            "mcp": {"tool": "capabilities", "resource": "m4://capabilities"},
            "apps": ["cohort_builder"],
            "output_formats": ["text", "json", "dotenv"],
        },
        "runtime": {
            "backend": get_active_backend(),
            "bigquery_project_id_configured": bool(get_bigquery_project_id()),
            "dataset_selection": "explicit",
        },
        "commands": commands,
        "tools": _tool_payloads(),
        "datasets": [_dataset_payload(ds) for ds in DatasetRegistry.list_all()],
        "limits": {
            "query_row_limit_default": 100,
            "path_redaction_default": True,
            "supported_backends": ["duckdb", "bigquery"],
            "conversion_env": [
                "M4_CONVERT_MAX_WORKERS",
                "M4_DUCKDB_MEM",
                "M4_DUCKDB_THREADS",
            ],
        },
        "concepts": {
            "derived_tables": _derived_inventory(),
            "skills": _skill_inventory(),
        },
        "provenance_policy": {
            "telemetry_destination": "M4_TELEMETRY_DIR or <M4_HOME>/telemetry",
            "path_redaction": "Machine-facing output hides raw paths unless --paths or M4_PATH_DISCLOSURE=1 is used.",
            "event_export_command": "m4 provenance export --json",
            "non_phi_policy": "M4 telemetry is intended for operational provenance only and must not include PHI.",
        },
    }
