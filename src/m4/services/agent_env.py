from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from m4.config import resolve_runtime_context
from m4.core.datasets import DatasetRegistry
from m4.services.results import CommandError


@dataclass(frozen=True)
class AgentEnvResult:
    command: str
    data: dict[str, Any]
    context: dict[str, Any]
    warnings: list[str]


def build_agent_env_service(
    *,
    mode: str = "local",
    dataset: str | None = None,
    backend: str | None = None,
    project_id: str | None = None,
    include_paths: bool = False,
) -> AgentEnvResult | CommandError:
    if mode not in {"local", "protected"}:
        return CommandError(
            command="agent-env",
            code="invalid_mode",
            message=f"Unsupported mode '{mode}'.",
            hint="Use --mode local or --mode protected.",
        )

    ctx = resolve_runtime_context(
        dataset=dataset, backend=backend, path_disclosure=include_paths
    )
    env = {
        "M4_HOME": str(ctx.home),
        "M4_BACKEND": ctx.backend,
        "M4_STUDY_ID": ctx.study_id,
        "M4_SESSION_ID": ctx.session_id,
        "M4_ACTOR": ctx.actor,
        "M4_TELEMETRY_DIR": str(ctx.telemetry_dir),
    }
    if project_id or ctx.project_id:
        env["M4_PROJECT_ID"] = project_id or ctx.project_id
    if mode == "local":
        env["M4_DATA_DIR"] = str(ctx.data_dir)

    warnings: list[str] = []
    if ctx.dataset and not DatasetRegistry.get(ctx.dataset):
        warnings.append(f"Dataset '{ctx.dataset}' is not registered.")
    if ctx.backend == "bigquery" and ctx.dataset:
        ds = DatasetRegistry.get(ctx.dataset)
        if ds and not ds.bigquery_dataset_ids:
            warnings.append(
                f"Dataset '{ctx.dataset}' is not available on the BigQuery backend."
            )
    if mode == "protected":
        warnings.append(
            "Protected mode omits M4_DATA_DIR; expose only an M4 service, socket, MCP server, or gateway to agents."
        )

    data = {
        "mode": mode,
        "environment": {key: value for key, value in env.items() if value is not None},
        "path_recommendations": {
            "python": sys.executable,
            "cli": "m4",
        },
        "defaults": {
            "dataset": ctx.dataset,
            "backend": ctx.backend,
        },
        "telemetry_destination": str(ctx.telemetry_dir),
        "raw_paths_hidden": not include_paths,
        "recommended_commands": [
            "m4 status --json --no-interactive",
            "m4 list-datasets --json --no-interactive",
            "m4 schema --dataset <dataset> --backend <backend> --json --no-interactive",
            "m4 describe-table <table> --dataset <dataset> --backend <backend> --json --no-interactive",
            "m4 query --dataset <dataset> --backend <backend> --sql <sql> --json --no-interactive",
        ],
    }

    return AgentEnvResult(
        command="agent-env",
        data=data,
        context=ctx.public_context(),
        warnings=warnings,
    )
