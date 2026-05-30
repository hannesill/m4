from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m4.config import (
    get_active_backend,
    get_bigquery_project_id,
    set_active_backend,
    set_bigquery_project_id,
)
from m4.mcp_client_configs.dynamic_mcp_config import MCPConfigGenerator
from m4.mcp_client_configs.setup_claude_desktop import setup_claude_desktop
from m4.services.results import CommandError, CommandResult


@dataclass(frozen=True)
class MCPConfigRequest:
    client: str | None = None
    backend: str | None = None
    db_path: str | None = None
    project_id: str | None = None
    python_path: str | None = None
    working_directory: str | None = None
    server_name: str = "m4"
    output: str | None = None
    quick: bool = False


def _resolve_backend_and_project(
    request: MCPConfigRequest,
) -> tuple[str, str | None, bool, bool, CommandError | None]:
    backend_explicit = request.backend is not None
    project_id_explicit = request.project_id is not None
    backend = request.backend or get_active_backend()
    project_id = request.project_id

    if backend not in {"duckdb", "bigquery"}:
        return (
            backend,
            project_id,
            backend_explicit,
            project_id_explicit,
            CommandError(
                command="config",
                code="invalid_backend",
                message="Unsupported backend. Use duckdb or bigquery.",
            ),
        )

    if backend == "bigquery" and not project_id:
        project_id = get_bigquery_project_id()

    if backend_explicit:
        if backend == "duckdb" and project_id:
            return (
                backend,
                project_id,
                backend_explicit,
                project_id_explicit,
                CommandError(
                    command="config",
                    code="invalid_option",
                    message="--project-id can only be used with --backend bigquery",
                ),
            )
        if backend == "bigquery" and request.db_path:
            return (
                backend,
                project_id,
                backend_explicit,
                project_id_explicit,
                CommandError(
                    command="config",
                    code="invalid_option",
                    message="--db-path can only be used with --backend duckdb",
                ),
            )
        if backend == "bigquery" and not project_id:
            return (
                backend,
                project_id,
                backend_explicit,
                project_id_explicit,
                CommandError(
                    command="config",
                    code="invalid_option",
                    message="--project-id is required when using --backend bigquery",
                ),
            )

    if backend == "bigquery" and not project_id:
        return (
            backend,
            project_id,
            backend_explicit,
            project_id_explicit,
            CommandError(
                command="config",
                code="project_id_required",
                message=(
                    "BigQuery backend requires a project ID. "
                    "Set it with: m4 backend bigquery --project-id <ID>"
                ),
            ),
        )

    return backend, project_id, backend_explicit, project_id_explicit, None


def _persist_explicit_config(
    *,
    backend: str,
    project_id: str | None,
    backend_explicit: bool,
    project_id_explicit: bool,
) -> None:
    if backend_explicit:
        set_active_backend(backend)
    if project_id_explicit and project_id:
        set_bigquery_project_id(project_id)


def _install_skills_for_tools(tool_names: list[str]) -> list[dict[str, str]]:
    from m4.skills import AI_TOOLS, install_skills

    installed: list[dict[str, str]] = []
    results = install_skills(tools=tool_names)
    for tool_name, paths in results.items():
        tool = AI_TOOLS[tool_name]
        for skill_path in paths:
            installed.append(
                {
                    "tool": tool_name,
                    "tool_display_name": tool.display_name,
                    "skill": skill_path.name,
                    "path": str(skill_path),
                }
            )
    return installed


def install_config_skills_service(
    tool_names: list[str],
) -> CommandResult | CommandError:
    try:
        installed = _install_skills_for_tools(tool_names)
    except Exception as exc:
        return CommandError(
            command="config skills",
            code="skills_install_failed",
            message=str(exc),
        )
    return CommandResult(command="config skills", data={"installed": installed})


def configure_mcp_service(
    request: MCPConfigRequest,
) -> CommandResult | CommandError:
    backend, project_id, backend_explicit, project_id_explicit, validation_error = (
        _resolve_backend_and_project(request)
    )
    if validation_error:
        return validation_error

    if request.client == "claude":
        db_path = None
        if backend == "duckdb" and request.db_path:
            db_path = str(Path(request.db_path).expanduser().resolve())

        try:
            configured = setup_claude_desktop(
                backend=backend,
                db_path=db_path,
                project_id=project_id if backend == "bigquery" else None,
            )
        except Exception as exc:
            return CommandError(
                command="config",
                code="claude_setup_failed",
                message=str(exc),
            )

        if not configured:
            return CommandError(
                command="config",
                code="claude_setup_failed",
                message="Claude Desktop setup failed.",
            )

        _persist_explicit_config(
            backend=backend,
            project_id=project_id,
            backend_explicit=backend_explicit,
            project_id_explicit=project_id_explicit,
        )
        return CommandResult(
            command="config",
            data={
                "client": "claude",
                "backend": backend,
                "project_id": project_id,
                "status": "completed",
            },
        )

    generator = MCPConfigGenerator()
    try:
        if request.quick:
            config = generator.generate_config(
                server_name=request.server_name,
                python_path=request.python_path,
                working_directory=request.working_directory,
                backend=backend,
                db_path=request.db_path if backend == "duckdb" else None,
                project_id=project_id if backend == "bigquery" else None,
                module_name="m4.mcp_server",
            )
        else:
            config = generator.interactive_config()
    except Exception as exc:
        return CommandError(
            command="config",
            code="config_generation_failed",
            message=str(exc),
        )

    json_output = json.dumps(config, indent=2)
    output_path = None
    if request.output:
        output_path = str(Path(request.output).expanduser().resolve())
        Path(output_path).write_text(json_output)

    _persist_explicit_config(
        backend=backend,
        project_id=project_id,
        backend_explicit=backend_explicit,
        project_id_explicit=project_id_explicit,
    )
    return CommandResult(
        command="config",
        data={
            "client": request.client or "generic",
            "backend": backend,
            "project_id": project_id,
            "status": "completed",
            "config": config,
            "config_json": json_output,
            "output": output_path,
            "quick": request.quick,
        },
    )


def summarize_generated_config(config: dict[str, Any], backend: str) -> list[str]:
    server_name = next(iter(config["mcpServers"].keys()))
    server_config = config["mcpServers"][server_name]
    lines = [
        "Configuration Summary:",
        f"Server name: {server_name}",
        f"Python path: {server_config['command']}",
        f"Working directory: {server_config['cwd']}",
        f"Backend: {backend} (from m4_data/config.json)",
    ]
    env = server_config["env"]
    if "M4_DB_PATH" in env:
        lines.append(f"Database path: {env['M4_DB_PATH']}")
    if "M4_PROJECT_ID" in env:
        lines.append(f"Project ID: {env['M4_PROJECT_ID']}")
    return lines
