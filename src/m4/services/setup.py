from __future__ import annotations

import importlib.util
import os
import platform
import sys
from pathlib import Path
from typing import Any

from m4.config import (
    ensure_custom_datasets_loaded,
    get_active_backend,
    get_active_dataset,  # noqa: F401 - retained for compatibility patch targets
    get_bigquery_project_id,
    resolve_runtime_context,
    set_active_backend,
    set_active_dataset,  # noqa: F401 - retained for compatibility patch targets
    set_bigquery_project_id,
)
from m4.core.datasets import DatasetRegistry
from m4.services.download import default_raw_root, validate_raw_layout
from m4.services.init import initialize_dataset_service
from m4.services.results import (
    ERROR_INVALID_BACKEND,
    ERROR_INVALID_OPTION,
    CommandError,
    CommandResult,
)
from m4.services.status import collect_status_snapshot


def _check(
    name: str, ok: bool, message: str, hint: str | None = None
) -> dict[str, Any]:
    result = {"name": name, "ok": ok, "message": message}
    if hint:
        result["hint"] = hint
    return result


def doctor_service(*, include_paths: bool = False) -> CommandResult:
    ensure_custom_datasets_loaded()
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    checks.append(
        _check(
            "python_version",
            sys.version_info >= (3, 10),
            platform.python_version(),
            "Use Python 3.10 or newer.",
        )
    )
    checks.append(
        _check(
            "m4_import",
            importlib.util.find_spec("m4") is not None,
            "m4 package is importable",
            "Run commands through uv run from the M4 project environment.",
        )
    )
    checks.append(
        _check(
            "duckdb_import",
            importlib.util.find_spec("duckdb") is not None,
            "duckdb package is importable",
            "Install project dependencies before using local DuckDB.",
        )
    )

    backend = get_active_backend()
    checks.append(
        _check(
            "backend",
            backend in {"duckdb", "bigquery"},
            backend,
            "Run m4 backend duckdb or m4 backend bigquery.",
        )
    )

    snapshot = collect_status_snapshot(show_all=True, include_paths=include_paths)

    for ds in snapshot["datasets"]:
        warnings.extend(ds.get("warnings", []))

    if backend == "bigquery":
        project_id = get_bigquery_project_id()
        checks.append(
            _check(
                "bigquery_project_id",
                bool(project_id),
                "configured" if project_id else "missing",
                "Run m4 setup-agent --backend bigquery --project-id YOUR_PROJECT_ID.",
            )
        )
        checks.append(
            _check(
                "google_application_credentials",
                bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
                or Path.home()
                .joinpath(".config/gcloud/application_default_credentials.json")
                .exists(),
                "ambient credentials detected",
                "Run gcloud auth application-default login.",
            )
        )

    ctx = resolve_runtime_context(path_disclosure=include_paths)
    checks.append(
        _check(
            "mcp_config_hint",
            True,
            "Use m4 setup-agent --client claude or m4 config for MCP client setup.",
        )
    )

    return CommandResult(
        command="doctor",
        data={
            "summary": {
                "ok": all(check["ok"] for check in checks),
                "failed": [check["name"] for check in checks if not check["ok"]],
            },
            "context": ctx.public_context(),
            "data_dir": str(ctx.data_dir) if include_paths else None,
            "checks": checks,
            "status": snapshot,
        },
        warnings=sorted(set(warnings)),
    )


def setup_agent_service(
    *,
    mode: str,
    client: str,
    dataset: str | None,
    backend: str | None,
    project_id: str | None,
    apply_config: bool = False,
) -> CommandResult | CommandError:
    ensure_custom_datasets_loaded()
    if mode not in {"local", "protected"}:
        return CommandError(
            command="setup-agent",
            code=ERROR_INVALID_OPTION,
            message=f"Unsupported mode '{mode}'.",
            hint="Use --mode local or --mode protected.",
        )
    if client not in {"claude", "generic"}:
        return CommandError(
            command="setup-agent",
            code=ERROR_INVALID_OPTION,
            message=f"Unsupported client '{client}'.",
            hint="Use --client claude or --client generic.",
        )

    resolved_backend = (backend or get_active_backend()).lower()
    if resolved_backend not in {"duckdb", "bigquery"}:
        return CommandError(
            command="setup-agent",
            code=ERROR_INVALID_BACKEND,
            message=f"Unsupported backend '{resolved_backend}'.",
        )
    if dataset and not DatasetRegistry.get(dataset):
        supported = ", ".join(ds.name for ds in DatasetRegistry.list_all())
        return CommandError(
            command="setup-agent",
            code=ERROR_INVALID_OPTION,
            message=f"Dataset '{dataset}' is not registered.",
            hint=f"Supported datasets: {supported}",
        )

    if apply_config:
        if backend:
            set_active_backend(resolved_backend)
        if project_id:
            set_bigquery_project_id(project_id)

    ctx = resolve_runtime_context(dataset=dataset, backend=resolved_backend)
    env = {
        "M4_HOME": str(ctx.home),
        "M4_BACKEND": resolved_backend,
        "M4_TELEMETRY_DIR": str(ctx.telemetry_dir),
    }
    if mode == "local":
        env["M4_DATA_DIR"] = str(ctx.data_dir)
    if resolved_backend == "bigquery" and (project_id or ctx.project_id):
        env["M4_PROJECT_ID"] = project_id or ctx.project_id

    commands = [
        "m4 doctor",
        f"m4 status --all{' --json' if client == 'generic' else ''}",
    ]
    if client == "claude":
        commands.append(
            "m4 config claude"
            + (f" --backend {resolved_backend}" if resolved_backend else "")
            + (f" --project-id {project_id}" if project_id else "")
        )
    else:
        commands.append("m4-infra")

    warnings = []
    if mode == "protected":
        warnings.append("protected_mode_omits_data_dir")
    if resolved_backend == "bigquery" and not (project_id or ctx.project_id):
        warnings.append("bigquery_project_id_missing")

    return CommandResult(
        command="setup-agent",
        data={
            "mode": mode,
            "client": client,
            "applied": apply_config,
            "environment": {
                key: value for key, value in env.items() if value is not None
            },
            "recommended_commands": commands,
            "notes": [
                "Use protected mode when an agent should not see local data paths.",
                "M4 telemetry is non-PHI operational provenance.",
            ],
        },
        warnings=warnings,
    )


def quickstart_service(
    *,
    workflow: str,
    dataset: str | None = None,
    backend: str | None = None,
    project_id: str | None = None,
    apply_config: bool = False,
) -> CommandResult | CommandError:
    ensure_custom_datasets_loaded()
    if workflow not in {"demo", "local", "bigquery"}:
        return CommandError(
            command="quickstart",
            code=ERROR_INVALID_OPTION,
            message=f"Unsupported workflow '{workflow}'.",
            hint="Use --workflow demo, local, or bigquery.",
        )

    resolved_dataset = dataset or (
        "mimic-iv-demo" if workflow == "demo" else "mimic-iv"
    )
    resolved_backend = backend or ("bigquery" if workflow == "bigquery" else "duckdb")
    steps: list[dict[str, Any]] = []

    if workflow == "demo":
        steps.append({"command": "m4 init mimic-iv-demo", "mutates": True})
        if apply_config:
            init_result = initialize_dataset_service("mimic-iv-demo")
            steps.append({"result": init_result.to_json_dict()})
    elif workflow == "local":
        raw_root = default_raw_root(resolved_dataset)
        steps.extend(
            [
                {"command": f"m4 download {resolved_dataset}", "mutates": False},
                {
                    "command": f"m4 init {resolved_dataset}",
                    "mutates": True,
                    "layout": validate_raw_layout(resolved_dataset, raw_root),
                },
            ]
        )
    else:
        steps.extend(
            [
                {"command": "gcloud auth application-default login", "mutates": True},
                {
                    "command": f"m4 backend bigquery --project-id {project_id or 'YOUR_PROJECT_ID'}",
                    "mutates": True,
                },
                {
                    "command": f"m4 status --dataset {resolved_dataset}",
                    "mutates": False,
                },
            ]
        )

    if apply_config:
        set_active_backend(resolved_backend)
        if project_id:
            set_bigquery_project_id(project_id)

    return CommandResult(
        command="quickstart",
        data={
            "workflow": workflow,
            "dataset": resolved_dataset,
            "backend": resolved_backend,
            "applied": apply_config,
            "steps": steps,
        },
        warnings=(
            ["bigquery_project_id_missing"]
            if workflow == "bigquery" and not (project_id or get_bigquery_project_id())
            else []
        ),
    )
