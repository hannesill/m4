import json
import logging
import math
import os
import subprocess
import sys
from contextlib import contextmanager, nullcontext
from dataclasses import is_dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import typer

from m4.client import M4Client
from m4.config import (
    get_active_backend,
    get_active_dataset,
    get_bigquery_project_id,
    get_dataset_parquet_root,
    get_default_database_path,
    get_telemetry_dir,
    logger,
    resolve_runtime_context,
    set_active_backend,
    set_active_dataset,
    set_bigquery_project_id,
)
from m4.console import (
    console,
    error,
    info,
    print_banner,
    print_command,
    print_dataset_status,
    print_datasets_table,
    print_derived_detail,
    print_error_panel,
    print_init_complete,
    print_key_value,
    print_logo,
    print_step,
    success,
    warning,
)
from m4.core.datasets import DatasetRegistry
from m4.core.derived.builtins import (
    get_tables_by_category,
    has_derived_support,
    list_builtins,
)
from m4.core.derived.materializer import (
    get_derived_table_count,
    list_materialized_tables,
    materialize_all,
)
from m4.core.exceptions import DatasetError, M4Error
from m4.core.tools import init_tools
from m4.data_io import (
    PhysioNetCredentials,
    convert_csv_to_parquet,
    download_dataset,
    init_duckdb_from_parquet,
    verify_table_rowcount,
)
from m4.services.backend import set_active_backend_service
from m4.services.download import build_wget_command, download_dataset_service
from m4.services.events import NdjsonEventReporter
from m4.services.init import initialize_dataset_service
from m4.services.results import CommandError, CommandResult
from m4.services.setup import doctor_service, quickstart_service, setup_agent_service
from m4.services.status import collect_status_snapshot
from m4.services.use import set_active_dataset_service

app = typer.Typer(
    name="m4",
    help="M4 CLI: Initialize local clinical datasets like MIMIC-IV Demo.",
    add_completion=False,
    rich_markup_mode="markdown",
)

provenance_app = typer.Typer(help="Inspect and export M4 provenance events.")
app.add_typer(provenance_app, name="provenance")


def version_callback(value: bool):
    if value:
        print_logo(show_tagline=True, show_version=True)
        raise typer.Exit()


@contextmanager
def _silence_m4_logging():
    """Temporarily silence m4 logging so machine output stays parseable."""
    previous_disable_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous_disable_level)


def _emit_json(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(_jsonable(payload), indent=2, allow_nan=False))


def _emit_command_json(result: CommandResult | CommandError) -> None:
    _emit_json(result.to_json_dict())


def _dotenv_lines(values: dict[str, Any]) -> list[str]:
    lines = []
    for key, value in values.items():
        if value is None:
            continue
        text = str(value).replace("\n", "\\n")
        lines.append(f"{key}={text}")
    return lines


def _json_error(command: str, code: str, message: str, hint: str | None = None) -> None:
    _emit_command_json(
        CommandError(command=command, code=code, message=message, hint=hint)
    )
    raise typer.Exit(code=1)


def _agent_error_payload(
    command: str,
    code: str,
    message: str,
    *,
    hint: str | None = None,
    context: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    error_payload: dict[str, Any] = {"code": code, "message": message}
    if hint:
        error_payload["hint"] = hint
    return {
        "version": 1,
        "ok": False,
        "command": command,
        "context": context or {},
        "error": error_payload,
        "warnings": warnings or [],
    }


def _agent_success_payload(
    command: str,
    data: dict[str, Any],
    *,
    context: dict[str, Any],
    warnings: list[str] | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "version": 1,
        "ok": True,
        "command": command,
        "context": context,
        "data": data,
        "warnings": warnings or [],
        "provenance": provenance or {},
    }


def _emit_agent_error(
    command: str,
    code: str,
    message: str,
    *,
    hint: str | None = None,
    context: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> None:
    message = _redact_known_paths(message)
    hint = _redact_known_paths(hint) if hint else None
    _emit_json(
        _agent_error_payload(
            command,
            code,
            message,
            hint=hint,
            context=context,
            warnings=warnings,
        )
    )
    raise typer.Exit(code=1)


def _path_disclosure_enabled() -> bool:
    return os.getenv("M4_PATH_DISCLOSURE", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
        "paths",
    }


def _redact_known_paths(message: str) -> str:
    if _path_disclosure_enabled():
        return message

    replacements: dict[str, str] = {}
    for env_name, label in (
        ("M4_DATA_DIR", "<M4_DATA_DIR>"),
        ("M4_HOME", "<M4_HOME>"),
        ("M4_TELEMETRY_DIR", "<M4_TELEMETRY_DIR>"),
    ):
        value = os.getenv(env_name)
        if value:
            path = str(Path(value).expanduser().resolve())
            replacements[path] = label

    for raw_path, label in sorted(
        replacements.items(), key=lambda item: len(item[0]), reverse=True
    ):
        message = message.replace(raw_path, label)
    return message


def _dataframe_payload(df: pd.DataFrame | None) -> dict[str, Any] | None:
    if df is None:
        return None
    return {
        "columns": [str(column) for column in df.columns],
        "rows": _jsonable(df.to_dict(orient="records")),
        "row_count": len(df),
    }


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, pd.DataFrame):
        return _dataframe_payload(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(item) for item in value]
    if is_dataclass(value):
        return _jsonable(value.__dict__)
    if _is_missing_value(value):
        return None
    if isinstance(value, datetime | date | time | pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "tolist"):
        try:
            return _jsonable(value.tolist())
        except (TypeError, ValueError):
            pass
    if hasattr(value, "item"):
        try:
            return _jsonable(value.item())
        except (AttributeError, TypeError, ValueError):
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        return str(value)
    return value


def _is_missing_value(value: Any) -> bool:
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if isinstance(missing, bool):
        return missing
    if getattr(missing, "shape", None) == ():
        return bool(missing)
    return False


@contextmanager
def _runtime_env_override(*, dataset: str | None = None, backend: str | None = None):
    previous: dict[str, str | None] = {
        "M4_DATASET": os.environ.get("M4_DATASET"),
        "M4_BACKEND": os.environ.get("M4_BACKEND"),
    }
    try:
        if dataset:
            os.environ["M4_DATASET"] = dataset
        if backend:
            os.environ["M4_BACKEND"] = backend
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _resolve_agent_dataset(
    command: str, dataset_name: str | None, context: dict[str, Any]
):
    from m4.core.datasets import DatasetRegistry

    try:
        effective = dataset_name or get_active_dataset()
    except DatasetError:
        _emit_agent_error(
            command,
            "dataset_required",
            "No dataset was provided and no active dataset is configured.",
            hint=f"Use: m4 {command} --dataset <dataset> --json",
            context=context,
        )

    dataset = DatasetRegistry.get(effective)
    if dataset is None:
        supported = ", ".join(ds.name for ds in DatasetRegistry.list_all())
        _emit_agent_error(
            command,
            "dataset_not_found",
            f"Dataset '{effective}' is not supported or not configured.",
            hint=f"Supported datasets: {supported}",
            context=context,
        )
    return dataset


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            callback=version_callback,
            is_eager=True,
            help="Show CLI version.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose", "-V", help="Enable DEBUG level logging for m4 components."
        ),
    ] = False,
):
    """
    Main callback for the M4 CLI. Sets logging level.
    """
    m4_logger = logging.getLogger("m4")  # Get the logger from config.py
    if verbose:
        m4_logger.setLevel(logging.DEBUG)
        for handler in m4_logger.handlers:  # Ensure handlers also respect the new level
            handler.setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled via CLI flag.")
    else:
        # Default to INFO as set in config.py
        m4_logger.setLevel(logging.INFO)
        for handler in m4_logger.handlers:
            handler.setLevel(logging.INFO)


@app.command("capabilities")
def capabilities_cmd(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the stable capability manifest as JSON."),
    ] = False,
):
    """Show M4 interfaces, commands, tools, datasets, limits, and policies."""
    manifest = M4Client.from_active(
        interface="cli", allow_missing_dataset=True
    ).capabilities()
    if json_output:
        _emit_json(manifest)
        return

    console.print("[bold]M4 capabilities[/bold]")
    console.print(f"Schema version: {manifest['schema_version']}")
    console.print(
        "Interfaces: "
        + ", ".join(
            sorted(key for key in manifest["interfaces"] if key != "output_formats")
        )
    )
    console.print("Datasets: " + ", ".join(ds["name"] for ds in manifest["datasets"]))
    console.print("Tools: " + ", ".join(tool["name"] for tool in manifest["tools"]))
    console.print("Machine output: [command]m4 capabilities --json[/command]")


@app.command("doctor")
def doctor_cmd(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print diagnostics as JSON."),
    ] = False,
    include_paths: Annotated[
        bool,
        typer.Option("--paths", help="Disclose raw local paths in diagnostics."),
    ] = False,
):
    """Run non-mutating diagnostics for local, BigQuery, and MCP setup."""
    result = doctor_service(include_paths=include_paths)
    if json_output:
        _emit_command_json(result)
        return

    summary = result.data["summary"]
    if summary["ok"]:
        success("Doctor checks passed")
    else:
        warning("Doctor found setup issues")
    for check in result.data["checks"]:
        marker = "OK" if check["ok"] else "FAIL"
        console.print(f"{marker} {check['name']}: {check['message']}")
        if not check["ok"] and check.get("hint"):
            console.print(f"  Hint: {check['hint']}")


@app.command("download")
def download_cmd(
    dataset_name: Annotated[
        str,
        typer.Argument(help="Dataset to download or prepare download guidance for."),
    ],
    target: Annotated[
        str | None,
        typer.Option("--target", help="Raw CSV.gz destination root."),
    ] = None,
    command_only: Annotated[
        bool,
        typer.Option("--command-only", help="Only print/generated command guidance."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print result as JSON."),
    ] = False,
    events: Annotated[
        str | None,
        typer.Option(
            "--events",
            help="Emit structured progress events. Supported: ndjson.",
        ),
    ] = None,
    physionet_credentials_file: Annotated[
        str | None,
        typer.Option(
            "--physionet-credentials-file",
            help="JSON file containing PhysioNet username and password fields.",
        ),
    ] = None,
):
    """Download public datasets or generate credentialed PhysioNet commands."""
    if events and events != "ndjson":
        _json_error(
            "download",
            "invalid_option",
            f"Unsupported event format '{events}'.",
            hint="Use: --events ndjson",
        )
    if events and not json_output:
        _json_error(
            "download",
            "invalid_option",
            "--events requires --json.",
            hint="Use: m4 download DATASET --json --events ndjson",
        )

    reporter = NdjsonEventReporter(command="download") if events == "ndjson" else None
    credentials = None
    if physionet_credentials_file:
        try:
            credentials = PhysioNetCredentials.from_json_file(
                Path(physionet_credentials_file).expanduser().resolve()
            )
        except Exception as exc:
            result = CommandError(
                command="download",
                code="missing_credentials",
                message=f"Could not read PhysioNet credentials file: {exc}",
            )
            if reporter:
                reporter.operation_failed(result.to_json_dict()["error"])
            elif json_output:
                _emit_command_json(result)
            else:
                print_error_panel("Download Failed", result.message, hint=result.hint)
            raise typer.Exit(code=1)

    if reporter:
        reporter.operation_started(
            dataset=dataset_name,
            command_only=command_only,
            credentials=bool(credentials),
        )

    with _silence_m4_logging() if json_output else nullcontext():
        result = download_dataset_service(
            dataset_name,
            target=target,
            command_only=command_only,
            physionet_credentials=credentials,
            event_reporter=reporter,
        )

    if json_output:
        if reporter:
            if isinstance(result, CommandError):
                reporter.operation_failed(result.to_json_dict()["error"])
            else:
                reporter.operation_completed(result.to_json_dict())
        else:
            _emit_command_json(result)
        if isinstance(result, CommandError):
            raise typer.Exit(code=1)
        return

    if isinstance(result, CommandError):
        print_error_panel("Download Failed", result.message, hint=result.hint)
        raise typer.Exit(code=1)

    data = result.data
    status = data.get("status")
    if status == "completed":
        success(f"Downloaded {data['dataset']} to {data['target']}")
    elif status == "blocked":
        warning(f"Credentialed dataset '{data['dataset']}' requires credentials")
    else:
        info(f"Download guidance for {data['dataset']}")

    if data.get("wget_command"):
        console.print()
        print_command(data["wget_command"])
    layout = data.get("layout", {})
    if layout.get("warnings") or layout.get("errors"):
        console.print()
        warning("Layout validation reported issues")
        for item in layout.get("errors", []):
            console.print(f"  {item}")
        for hint in layout.get("recovery", []):
            console.print(f"  Hint: {hint}")


@app.command("setup-agent")
def setup_agent_cmd(
    mode: Annotated[
        str, typer.Option("--mode", help="Agent mode: local or protected.")
    ] = "local",
    client: Annotated[
        str, typer.Option("--client", help="Client: claude or generic.")
    ] = "generic",
    dataset_name: Annotated[
        str | None, typer.Option("--dataset", help="Default dataset.")
    ] = None,
    backend_name: Annotated[
        str | None, typer.Option("--backend", help="Backend: duckdb or bigquery.")
    ] = None,
    project_id: Annotated[
        str | None, typer.Option("--project-id", help="BigQuery billing project ID.")
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: json, dotenv, or text."),
    ] = "text",
    apply_config: Annotated[
        bool,
        typer.Option("--apply", help="Apply dataset/backend/project configuration."),
    ] = False,
):
    """Emit or apply agent environment and MCP client recommendations."""
    if output_format not in {"json", "dotenv", "text"}:
        _json_error(
            "setup-agent",
            "invalid_format",
            f"Unsupported format '{output_format}'.",
            "Use --format json, dotenv, or text.",
        )
    result = setup_agent_service(
        mode=mode,
        client=client,
        dataset=dataset_name,
        backend=backend_name,
        project_id=project_id,
        apply_config=apply_config,
    )
    if isinstance(result, CommandError):
        if output_format == "json":
            _emit_command_json(result)
        else:
            print_error_panel("Setup Agent Failed", result.message, hint=result.hint)
        raise typer.Exit(code=1)

    if output_format == "json":
        _emit_command_json(result)
        return
    if output_format == "dotenv":
        typer.echo("\n".join(_dotenv_lines(result.data["environment"])))
        return

    console.print("[bold]Agent environment[/bold]")
    for line in _dotenv_lines(result.data["environment"]):
        typer.echo(line)
    console.print()
    console.print("[bold]Recommended commands[/bold]")
    for command in result.data["recommended_commands"]:
        console.print(f"  [command]{command}[/command]")


@app.command("quickstart")
def quickstart_cmd(
    workflow: Annotated[
        str,
        typer.Option("--workflow", help="Workflow: demo, local, or bigquery."),
    ] = "demo",
    dataset_name: Annotated[
        str | None, typer.Option("--dataset", help="Dataset name.")
    ] = None,
    backend_name: Annotated[
        str | None, typer.Option("--backend", help="Backend name.")
    ] = None,
    project_id: Annotated[
        str | None, typer.Option("--project-id", help="BigQuery billing project ID.")
    ] = None,
    apply_config: Annotated[
        bool,
        typer.Option("--apply", help="Apply the quickstart configuration."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print result as JSON."),
    ] = False,
):
    """Show or run the guided happy path for demo, local, or BigQuery use."""
    result = quickstart_service(
        workflow=workflow,
        dataset=dataset_name,
        backend=backend_name,
        project_id=project_id,
        apply_config=apply_config,
    )
    if json_output:
        _emit_command_json(result)
        if isinstance(result, CommandError):
            raise typer.Exit(code=1)
        return
    if isinstance(result, CommandError):
        print_error_panel("Quickstart Failed", result.message, hint=result.hint)
        raise typer.Exit(code=1)

    console.print(f"[bold]Quickstart: {result.data['workflow']}[/bold]")
    for step in result.data["steps"]:
        if "command" in step:
            console.print(f"  [command]{step['command']}[/command]")
    if result.warnings:
        for item in result.warnings:
            warning(item)


@app.command("init")
def dataset_init_cmd(
    dataset_name: Annotated[
        str,
        typer.Argument(
            help=(
                "Dataset to initialize (local). Default: 'mimic-iv-demo'. "
                f"Supported: {', '.join([ds.name for ds in DatasetRegistry.list_all()])}"
            ),
            metavar="DATASET_NAME",
        ),
    ] = "mimic-iv-demo",
    src: Annotated[
        str | None,
        typer.Option(
            "--src",
            help=(
                "Path to existing raw CSV.gz root (hosp/, icu/). If provided, download is skipped."
            ),
        ),
    ] = None,
    db_path_str: Annotated[
        str | None,
        typer.Option(
            "--db-path",
            "-p",
            help="Custom path for the DuckDB file. Uses a default if not set.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Force recreation of DuckDB even if it exists.",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Print result as JSON for scripts and automation.",
        ),
    ] = False,
    events: Annotated[
        str | None,
        typer.Option(
            "--events",
            help="Emit structured progress events. Supported: ndjson.",
        ),
    ] = None,
    no_interactive: Annotated[
        bool,
        typer.Option(
            "--no-interactive",
            help="Accepted for automation; JSON init never prompts.",
        ),
    ] = False,
    download_requested: Annotated[
        bool,
        typer.Option(
            "--download",
            help="Download missing raw files when a dataset listing URL is configured.",
        ),
    ] = False,
    physionet_credentials_file: Annotated[
        str | None,
        typer.Option(
            "--physionet-credentials-file",
            help="JSON file containing PhysioNet username and password fields.",
        ),
    ] = None,
):
    """
    Initialize a local dataset in one step by detecting what's already present:
    - If Parquet exists: only initialize DuckDB views
    - If raw CSV.gz exists but Parquet is missing: convert then initialize
    - If neither exists: download (demo only), convert, then initialize

    Notes:
    - Auto-download is based on the dataset definition URL.
    - For datasets without a download URL (e.g. mimic-iv-full), you must provide the --src path or place files in the expected location.
    """
    if events and events != "ndjson":
        _json_error(
            "init",
            "invalid_option",
            f"Unsupported event format '{events}'.",
            hint="Use: --events ndjson",
        )
    if events and not json_output:
        _json_error(
            "init",
            "invalid_option",
            "--events requires --json.",
            hint="Use: m4 init DATASET --json --events ndjson",
        )

    if json_output:
        reporter = NdjsonEventReporter(command="init") if events == "ndjson" else None
        credentials = None
        if physionet_credentials_file:
            try:
                credentials = PhysioNetCredentials.from_json_file(
                    Path(physionet_credentials_file).expanduser().resolve()
                )
            except Exception as exc:
                result = CommandError(
                    command="init",
                    code="missing_credentials",
                    message=f"Could not read PhysioNet credentials file: {exc}",
                )
                if reporter:
                    reporter.operation_failed(result.to_json_dict()["error"])
                else:
                    _emit_command_json(result)
                raise typer.Exit(code=1)

        if reporter:
            reporter.operation_started(
                dataset=dataset_name,
                download=download_requested,
                no_interactive=no_interactive,
            )
        with _silence_m4_logging():
            result = initialize_dataset_service(
                dataset_name,
                src=src,
                db_path_str=db_path_str,
                force=force,
                download=download_requested,
                physionet_credentials=credentials,
                event_reporter=reporter,
            )
        if reporter:
            if isinstance(result, CommandError):
                reporter.operation_failed(result.to_json_dict()["error"])
            else:
                reporter.operation_completed(result.to_json_dict())
        else:
            _emit_command_json(result)
        if isinstance(result, CommandError):
            raise typer.Exit(code=1)
        return

    logger.info(f"CLI 'init' called for dataset: '{dataset_name}'")

    dataset_key = dataset_name.lower()
    ds = DatasetRegistry.get(dataset_key)
    if not ds:
        supported = ", ".join([d.name for d in DatasetRegistry.list_all()])
        print_error_panel(
            "Dataset Not Found",
            f"Dataset '{dataset_name}' is not supported or not configured.",
            hint=f"Supported datasets: {supported}",
        )
        raise typer.Exit(code=1)

    # Check if m4_data exists in a parent directory
    from m4.config import _find_project_root_from_cwd

    cwd = Path.cwd()
    found_root = _find_project_root_from_cwd()

    # If we found m4_data in a parent directory, ask user what to do
    if found_root != cwd:
        existing_data_dir = found_root / "m4_data"
        console.print()
        warning(f"Found existing m4_data at: {existing_data_dir}")
        print_key_value("Current directory", cwd)
        console.print()
        console.print("  [bold]1.[/bold] Use existing location")
        console.print("  [bold]2.[/bold] Create new m4_data in current directory")

        choice = typer.prompt(
            "\nWhich location would you like to use?", type=str, default="1"
        )

        if choice == "2":
            # Force use of current directory by setting env var temporarily
            import os

            os.environ["M4_DATA_DIR"] = str(cwd / "m4_data")
            success(f"Will create new m4_data in {cwd / 'm4_data'}")
        else:
            success(f"Will use existing m4_data at {existing_data_dir}")

    # Resolve roots (now respects the choice made above)
    pq_root = get_dataset_parquet_root(dataset_key)
    if pq_root is None:
        error("Could not determine dataset directories.")
        raise typer.Exit(code=1)

    csv_root_default = pq_root.parent.parent / "raw_files" / dataset_key
    csv_root = Path(src).resolve() if src else csv_root_default

    # Presence detection (check for any parquet or csv.gz files)
    parquet_present = any(pq_root.rglob("*.parquet"))
    raw_present = any(csv_root.rglob("*.csv.gz"))

    console.print()
    print_banner(f"Initializing {dataset_key}", "Checking existing files...")
    print_key_value(
        "Raw CSV root",
        f"{csv_root} [{'[success]found[/]' if raw_present else '[muted]missing[/]'}]",
    )
    print_key_value(
        "Parquet root",
        f"{pq_root} [{'[success]found[/]' if parquet_present else '[muted]missing[/]'}]",
    )

    # Step 1: Ensure raw dataset exists (download if missing, for requires_authentication datasets, inform and return)
    if not raw_present and not parquet_present:
        requires_auth = ds.requires_authentication

        if requires_auth:
            base_url = ds.file_listing_url

            console.print()
            error(f"Files not found for credentialed dataset '{dataset_key}'")
            console.print()
            console.print("[bold]To download this credentialed dataset:[/bold]")
            console.print(
                f"  [bold]1.[/bold] Sign the DUA at: [link]{base_url or 'https://physionet.org'}[/link]"
            )
            console.print(
                "  [bold]2.[/bold] Run this command (you'll be prompted for your PhysioNet password):"
            )
            console.print()

            # Wget command tailored to the user's path
            wget_cmd = build_wget_command(ds, csv_root)
            print_command(wget_cmd)
            console.print()
            console.print(
                f"  [bold]3.[/bold] Re-run: [command]m4 init {dataset_key}[/command]"
            )
            return

        listing_url = ds.file_listing_url
        if listing_url:
            out_dir = csv_root_default
            out_dir.mkdir(parents=True, exist_ok=True)

            console.print()
            print_step(1, 3, f"Downloading dataset '{dataset_key}'")
            print_key_value("Source", listing_url)
            print_key_value("Destination", out_dir)

            ok = download_dataset(dataset_key, out_dir)
            if not ok:
                error("Download failed. Please check logs for details.")
                raise typer.Exit(code=1)
            success("Download complete")

            # Point csv_root to the downloaded location
            csv_root = out_dir
            raw_present = True
        else:
            console.print()
            warning(f"Auto-download is not available for '{dataset_key}'")
            console.print()
            console.print("[bold]To initialize this dataset:[/bold]")
            console.print("  [bold]1.[/bold] Download the raw data manually")
            console.print(
                f"  [bold]2.[/bold] Place the raw CSV.gz files under: [path]{csv_root_default}[/path]"
            )
            console.print("       (or use --src to point to their location)")
            console.print(
                f"  [bold]3.[/bold] Re-run: [command]m4 init {dataset_key}[/command]"
            )
            return

    # Step 2: Ensure Parquet exists (convert if missing)
    if not parquet_present:
        console.print()
        print_step(2, 3, "Converting CSV to Parquet")
        print_key_value("Source", csv_root)
        print_key_value("Destination", pq_root)
        ok = convert_csv_to_parquet(dataset_key, csv_root, pq_root)
        if not ok:
            error("Conversion failed. Please check logs for details.")
            raise typer.Exit(code=1)
        success("Conversion complete")

    # Step 3: Initialize DuckDB over Parquet
    final_db_path = (
        Path(db_path_str).resolve()
        if db_path_str
        else get_default_database_path(dataset_key)
    )
    if not final_db_path:
        error(f"Could not determine database path for '{dataset_name}'")
        raise typer.Exit(code=1)

    final_db_path.parent.mkdir(parents=True, exist_ok=True)

    # Handle force flag - delete existing database if requested
    if force and final_db_path.exists():
        warning(f"Deleting existing database at {final_db_path}")
        final_db_path.unlink()

    console.print()
    print_step(3, 3, "Creating DuckDB views")
    print_key_value("Database", final_db_path)
    print_key_value("Parquet root", pq_root)

    if not pq_root or not pq_root.exists():
        error(f"Parquet directory not found at {pq_root}")
        raise typer.Exit(code=1)

    init_successful = init_duckdb_from_parquet(
        dataset_name=dataset_key, db_target_path=final_db_path
    )
    if not init_successful:
        error(
            f"Dataset '{dataset_name}' initialization FAILED. Please check logs for details."
        )
        raise typer.Exit(code=1)

    logger.info(
        f"Dataset '{dataset_name}' initialization seems complete. "
        "Verifying database integrity..."
    )

    verification_table_name = ds.primary_verification_table
    if not verification_table_name:
        logger.warning(
            f"No 'primary_verification_table' configured for '{dataset_name}'. Skipping DB query test."
        )
        print_init_complete(dataset_name, str(final_db_path), str(pq_root))
    else:
        try:
            record_count = verify_table_rowcount(final_db_path, verification_table_name)
            success(
                f"Verified: {record_count:,} records in '{verification_table_name}'"
            )
            print_init_complete(dataset_name, str(final_db_path), str(pq_root))
        except Exception as e:
            logger.error(
                f"Unexpected error during database verification: {e}", exc_info=True
            )
            error(f"Verification failed: {e}")

    # Set active dataset to match init target
    set_active_dataset(dataset_key)

    # Offer to materialize derived tables for supported datasets
    if has_derived_support(dataset_key) and get_active_backend() == "duckdb":
        existing_derived = get_derived_table_count(final_db_path)

        if existing_derived > 0 and not force:
            # Already materialized — skip prompt, just notify
            console.print()
            info(
                f"Derived tables already materialized ({existing_derived} tables). "
                "Use --force to recreate."
            )
        else:
            # No existing tables → prompt; --force → recreate without prompt
            if force and existing_derived > 0:
                do_materialize = True
            else:
                console.print()
                do_materialize = typer.confirm(
                    "Materialize derived tables? "
                    "(SOFA, sepsis3, KDIGO, scores, medications, etc.)",
                    default=False,
                )

            if do_materialize:
                try:
                    materialize_all(dataset_key, final_db_path)
                except RuntimeError as e:
                    if "locked by another process" in str(e):
                        print_error_panel(
                            "Database Locked",
                            str(e),
                            hint="If the M4 MCP server is running, stop it "
                            "before materializing derived tables.",
                        )
                    else:
                        error(f"Derived table materialization failed: {e}")
                    console.print(
                        "  [muted]You can retry later with:[/muted] "
                        f"[command]m4 init-derived {dataset_key}[/command]"
                    )
                except Exception as e:
                    error(f"Derived table materialization failed: {e}")
                    console.print(
                        "  [muted]You can retry later with:[/muted] "
                        f"[command]m4 init-derived {dataset_key}[/command]"
                    )


@app.command("init-derived")
def init_derived_cmd(
    dataset_name: Annotated[
        str,
        typer.Argument(
            help="Dataset to materialize derived tables for.",
            metavar="DATASET_NAME",
        ),
    ],
    list_only: Annotated[
        bool,
        typer.Option(
            "--list",
            "-l",
            help="List available derived tables without materializing.",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Force re-materialization even if derived tables already exist.",
        ),
    ] = False,
):
    """Materialize built-in derived tables for a dataset.

    Creates clinically validated concept tables (SOFA scores, sepsis cohorts,
    KDIGO staging, etc.) from vendored mimic-code SQL. These tables become
    queryable as mimiciv_derived.* via standard SQL.

    On BigQuery, derived tables already exist — no materialization needed.
    """
    dataset_key = dataset_name.lower()
    ds = DatasetRegistry.get(dataset_key)

    if not ds:
        supported = ", ".join([d.name for d in DatasetRegistry.list_all()])
        print_error_panel(
            "Dataset Not Found",
            f"Dataset '{dataset_name}' is not supported or not configured.",
            hint=f"Supported datasets: {supported}",
        )
        raise typer.Exit(code=1)

    # Block unsupported datasets
    if dataset_key in ("mimic-iv-demo",):
        print_error_panel(
            "Not Supported",
            f"Derived tables are not supported for '{dataset_key}'.",
            hint=(
                "The demo dataset has only 100 patients; many derived concepts "
                "produce empty or unreliable results. Use the full mimic-iv dataset."
            ),
        )
        raise typer.Exit(code=1)

    # Block if BigQuery backend
    if get_active_backend() == "bigquery":
        info(
            "BigQuery backend active — built-in derived tables are already available "
            "on physionet-data.mimiciv_derived. No materialization needed."
        )
        return

    if list_only:
        try:
            names = list_builtins(dataset_key)
            console.print(f"\n[bold]Available derived tables for {dataset_key}:[/bold]")
            console.print(f"[muted]({len(names)} tables)[/muted]\n")
            for name in names:
                console.print(f"  {name}")
        except ValueError as e:
            error(str(e))
            raise typer.Exit(code=1)
        return

    db_path = get_default_database_path(dataset_key)
    if not db_path or not db_path.exists():
        print_error_panel(
            "Database Not Found",
            f"No DuckDB database found for '{dataset_key}'.",
            hint=f"Initialize first: m4 init {dataset_key}",
        )
        raise typer.Exit(code=1)

    # Skip if derived tables already exist (unless --force)
    existing_count = get_derived_table_count(db_path)
    if existing_count > 0 and not force:
        info(
            f"Derived tables already materialized ({existing_count} tables). "
            "Use --force to recreate."
        )
        return

    try:
        created = materialize_all(dataset_key, db_path)
        success(f"Created {len(created)} derived tables in mimiciv_derived schema")
    except ValueError as e:
        error(str(e))
        raise typer.Exit(code=1)
    except RuntimeError as e:
        if "locked by another process" in str(e):
            print_error_panel(
                "Database Locked",
                str(e),
                hint="If the M4 MCP server is running, stop it before "
                "materializing derived tables.",
            )
        else:
            error(f"Materialization failed: {e}")
            logger.error(f"Derived table materialization error: {e}", exc_info=True)
        raise typer.Exit(code=1)
    except Exception as e:
        error(f"Materialization failed: {e}")
        logger.error(f"Derived table materialization error: {e}", exc_info=True)
        raise typer.Exit(code=1)


@app.command("use")
def use_cmd(
    target: Annotated[
        str,
        typer.Argument(
            help="Select active dataset: name (e.g., mimic-iv-full)", metavar="TARGET"
        ),
    ],
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Print result as JSON for scripts and automation.",
        ),
    ] = False,
):
    """Set the active dataset selection for the project."""
    with _silence_m4_logging() if json_output else nullcontext():
        result = set_active_dataset_service(target)

    if isinstance(result, CommandError):
        if json_output:
            _emit_command_json(result)
            raise typer.Exit(code=1)

        title = {
            "dataset_not_found": "Dataset Not Found",
            "backend_incompatible": "Backend Incompatible",
        }.get(result.code, "Command Failed")
        print_error_panel(title, result.message, hint=result.hint)
        raise typer.Exit(code=1)

    if json_output:
        _emit_command_json(result)
        return

    target = result.data["active_dataset"]
    dataset = result.data["dataset"]
    success(f"Active dataset set to '{target}'")

    if not dataset["parquet_present"]:
        warning(f"Local Parquet files not found at {dataset['parquet_root']}")
        console.print(
            "  [muted]This is fine if you are using the BigQuery backend.[/muted]"
        )
        console.print(
            "  [muted]For DuckDB (local), run:[/muted] [command]m4 init[/command]"
        )
    else:
        info("Local: Available", prefix="status")

    if dataset["bigquery_available"]:
        ds_def = DatasetRegistry.get(target)
        info(
            f"BigQuery: Available (Project: {ds_def.bigquery_project_id if ds_def else None})",
            prefix="status",
        )


@app.command("backend")
def backend_cmd(
    target: Annotated[
        str,
        typer.Argument(help="Backend to use: duckdb or bigquery", metavar="BACKEND"),
    ],
    project_id: Annotated[
        str | None,
        typer.Option(
            "--project-id",
            help="Google Cloud project ID for billing (bigquery only)",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Print result as JSON for scripts and automation.",
        ),
    ] = False,
):
    """Set the active backend (duckdb or bigquery)."""
    with _silence_m4_logging() if json_output else nullcontext():
        result = set_active_backend_service(target, project_id=project_id)

    if isinstance(result, CommandError):
        if json_output:
            _emit_command_json(result)
            raise typer.Exit(code=1)

        if result.code == "invalid_option":
            error(result.message.removesuffix("."))
        else:
            title = {
                "invalid_backend": "Invalid Backend",
                "dataset_incompatible": "Dataset Incompatible",
                "project_id_required": "Project ID Required",
            }.get(result.code, "Command Failed")
            print_error_panel(title, result.message, hint=result.hint)
        raise typer.Exit(code=1)

    if json_output:
        _emit_command_json(result)
        return

    target = result.data["backend"]
    success(f"Active backend set to '{target}'")

    # Show helpful context
    if target == "bigquery":
        info("BigQuery requires valid Google Cloud credentials")
        console.print(
            "  [muted]Ensure GOOGLE_APPLICATION_CREDENTIALS is set or run:[/muted]"
        )
        console.print("  [command]gcloud auth application-default login[/command]")
    else:
        info("DuckDB uses local database files")
        console.print(
            "  [muted]Run[/muted] [command]m4 init[/command] [muted]if you haven't initialized your dataset[/muted]"
        )


@app.command("status")
def status_cmd(
    show_all: Annotated[
        bool,
        typer.Option(
            "--all",
            "-a",
            help="Show all supported datasets in a table view.",
        ),
    ] = False,
    show_derived: Annotated[
        bool,
        typer.Option(
            "--derived",
            "-d",
            help="Show detailed derived table status grouped by category.",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Print status as JSON for scripts and automation.",
        ),
    ] = False,
    dataset_name: Annotated[
        str | None,
        typer.Option(
            "--dataset",
            help="Dataset to inspect without changing active config.",
        ),
    ] = None,
    backend_name: Annotated[
        str | None,
        typer.Option(
            "--backend",
            help="Backend to inspect without changing active config.",
        ),
    ] = None,
    no_interactive: Annotated[
        bool,
        typer.Option(
            "--no-interactive",
            help="Accepted for automation; status never prompts.",
        ),
    ] = False,
    include_paths: Annotated[
        bool,
        typer.Option(
            "--paths",
            help="Include raw local filesystem paths in output.",
        ),
    ] = False,
):
    """Show active dataset status. Use --all for all supported datasets."""
    if show_derived and json_output:
        _json_error(
            "status",
            "invalid_option",
            "--json cannot be combined with --derived.",
            hint="Run either: m4 status --json or m4 status --derived",
        )

    if json_output:
        with (
            _silence_m4_logging(),
            _runtime_env_override(dataset=dataset_name, backend=backend_name),
        ):
            snapshot = collect_status_snapshot(
                show_all=show_all, include_paths=include_paths
            )
        _emit_json(snapshot)
        return

    # --derived: detailed per-table view (early return)
    if show_derived:
        try:
            active = get_active_dataset()
        except DatasetError:
            active = None
        if not active:
            console.print("[warning]No active dataset set.[/warning]")
            raise typer.Exit()

        if not has_derived_support(active):
            console.print(
                f"[muted]Derived tables are not available for '{active}'.[/muted]"
            )
            raise typer.Exit()

        backend = get_active_backend()
        if backend == "bigquery":
            info(
                "BigQuery backend active — derived tables are available "
                "as physionet-data.mimiciv_derived.*"
            )
            raise typer.Exit()

        db_path = get_default_database_path(active)
        if not db_path or not db_path.exists():
            console.print(
                f"[warning]No DuckDB database found for '{active}'.[/warning]"
            )
            console.print(
                f"  [muted]Initialize with:[/muted] [command]m4 init {active}[/command]"
            )
            raise typer.Exit()

        categories = get_tables_by_category(active)
        materialized = list_materialized_tables(db_path)
        print_derived_detail(active, categories, materialized)
        return

    print_logo(show_tagline=False, show_version=True)
    console.print()

    with _runtime_env_override(dataset=dataset_name, backend=backend_name):
        snapshot = collect_status_snapshot(
            show_all=show_all, include_paths=include_paths
        )
    active = snapshot["active_dataset"]
    datasets = snapshot["datasets"]

    if show_all:
        # Table view of all datasets
        if not datasets:
            console.print("[muted]No datasets detected.[/muted]")
            return

        # Build dataset info list for table
        datasets_info = [
            {
                "name": dataset["name"],
                "parquet_present": dataset["parquet_present"],
                "db_present": dataset["db_present"],
                "bigquery_available": dataset["bigquery_available"],
                "parquet_size_gb": dataset["parquet_size_gb"],
                "derived_materialized": dataset["derived"]["materialized"],
                "derived_total": dataset["derived"]["total"],
            }
            for dataset in datasets
        ]

        print_datasets_table(datasets_info, active_dataset=active)
        return

    # Default: show only active dataset with full detail
    if not active:
        console.print("[warning]No active dataset set.[/warning]")
        console.print()
        console.print(
            "[muted]Set one with:[/muted] [command]m4 use <dataset>[/command]"
        )
        console.print(
            "[muted]List all with:[/muted] [command]m4 status --all[/command]"
        )
        return

    console.print(f"[bold]Active dataset:[/bold] [success]{active}[/success]")

    backend = snapshot["backend"]
    backend_label = backend
    if backend == "bigquery" and snapshot["bigquery_project_id"]:
        backend_label = f"{backend} ({snapshot['bigquery_project_id']})"
    console.print(f"[bold]Backend:[/bold] [success]{backend_label}[/success]")

    # Get info for active dataset
    dataset = datasets[0] if datasets else None
    if not dataset:
        console.print()
        warning(f"Dataset '{active}' is set but not found locally.")
        console.print(
            f"  [muted]Initialize with:[/muted] [command]m4 init {active}[/command]"
        )
        return

    if "parquet_path_mismatch" in dataset["warnings"]:
        warning("Database views may point to wrong parquet location")
        console.print(
            f"  [muted]Try:[/muted] [command]m4 init {active} --force[/command]"
        )

    print_dataset_status(
        name=active,
        parquet_present=dataset["parquet_present"],
        db_present=dataset["db_present"],
        parquet_root=dataset.get("parquet_root") or "",
        db_path=dataset.get("db_path") or "",
        parquet_size_gb=dataset["parquet_size_gb"],
        bigquery_available=dataset["bigquery_available"],
        row_count=dataset["row_count"],
        is_active=True,
        derived_materialized=dataset["derived"]["materialized"],
        derived_total=dataset["derived"]["total"],
        derived_has_support=dataset["derived"]["supported"],
        derived_is_bigquery=dataset["derived"]["bigquery"],
    )


@app.command("list-datasets")
def list_datasets_cmd(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print result as JSON for automation."),
    ] = False,
    dataset_name: Annotated[
        str | None,
        typer.Option("--dataset", help="Dataset to mark as active in this result."),
    ] = None,
    backend_name: Annotated[
        str | None,
        typer.Option("--backend", help="Backend to use for compatibility checks."),
    ] = None,
    no_interactive: Annotated[
        bool,
        typer.Option("--no-interactive", help="Accepted for automation."),
    ] = False,
    include_paths: Annotated[
        bool,
        typer.Option("--paths", help="Include raw local filesystem paths."),
    ] = False,
):
    """List available datasets without mutating active config."""
    with _silence_m4_logging() if json_output else nullcontext():
        with _runtime_env_override(dataset=dataset_name, backend=backend_name):
            ctx = resolve_runtime_context(
                dataset=dataset_name,
                backend=backend_name,
                path_disclosure=include_paths,
            )
            snapshot = collect_status_snapshot(
                show_all=True, include_paths=include_paths
            )

    if json_output:
        _emit_json(
            _agent_success_payload(
                "list-datasets",
                {
                    "active_dataset": snapshot["active_dataset"],
                    "backend": snapshot["backend"],
                    "datasets": snapshot["datasets"],
                    "raw_paths_hidden": not include_paths,
                },
                context=ctx.public_context(),
            )
        )
        return

    datasets_info = [
        {
            "name": dataset["name"],
            "parquet_present": dataset["parquet_present"],
            "db_present": dataset["db_present"],
            "bigquery_available": dataset["bigquery_available"],
            "parquet_size_gb": dataset["parquet_size_gb"],
            "derived_materialized": dataset["derived"]["materialized"],
            "derived_total": dataset["derived"]["total"],
        }
        for dataset in snapshot["datasets"]
    ]
    print_datasets_table(datasets_info, active_dataset=snapshot["active_dataset"])


@app.command("schema")
def schema_cmd(
    dataset_name: Annotated[
        str | None,
        typer.Option("--dataset", help="Dataset to inspect."),
    ] = None,
    backend_name: Annotated[
        str | None,
        typer.Option("--backend", help="Backend to use."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print result as JSON for automation."),
    ] = False,
    no_interactive: Annotated[
        bool,
        typer.Option("--no-interactive", help="Accepted for automation."),
    ] = False,
):
    """List tables for a dataset/backend pair without mutating active config."""
    command = "schema"
    init_tools()
    ctx = resolve_runtime_context(dataset=dataset_name, backend=backend_name)
    with _silence_m4_logging() if json_output else nullcontext():
        try:
            client = M4Client(
                dataset=dataset_name,
                backend=backend_name,
                interface="cli",
                project_id=ctx.project_id,
                path_disclosure=ctx.path_disclosure,
            )
            result = client.schema()
            ctx_public = client.context.public_context()
        except M4Error as exc:
            if json_output:
                _emit_agent_error(
                    command,
                    "schema_failed",
                    str(exc),
                    context=ctx.public_context(),
                )
            error(str(exc))
            raise typer.Exit(code=1)

    if json_output:
        _emit_json(
            _agent_success_payload(
                command,
                {"tables": result.get("tables", [])},
                context=ctx_public,
            )
        )
        return

    for table in result.get("tables", []):
        typer.echo(table)


@app.command("describe-table")
def describe_table_cmd(
    table_name: Annotated[
        str,
        typer.Argument(
            help="Table name to inspect, for example mimiciv_hosp.admissions."
        ),
    ],
    dataset_name: Annotated[
        str | None,
        typer.Option("--dataset", help="Dataset to inspect."),
    ] = None,
    backend_name: Annotated[
        str | None,
        typer.Option("--backend", help="Backend to use."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print result as JSON for automation."),
    ] = False,
    no_interactive: Annotated[
        bool,
        typer.Option("--no-interactive", help="Accepted for automation."),
    ] = False,
    show_sample: Annotated[
        bool,
        typer.Option("--sample/--no-sample", help="Include up to three sample rows."),
    ] = True,
):
    """Describe a single table without mutating active config."""
    command = "describe-table"
    init_tools()
    ctx = resolve_runtime_context(dataset=dataset_name, backend=backend_name)
    with _silence_m4_logging() if json_output else nullcontext():
        try:
            client = M4Client(
                dataset=dataset_name,
                backend=backend_name,
                interface="cli",
                project_id=ctx.project_id,
                path_disclosure=ctx.path_disclosure,
            )
            result = client.table_info(table_name, show_sample=show_sample)
            ctx_public = client.context.public_context()
        except M4Error as exc:
            if json_output:
                _emit_agent_error(
                    command,
                    "describe_table_failed",
                    str(exc),
                    context=ctx.public_context(),
                )
            error(str(exc))
            raise typer.Exit(code=1)

    if json_output:
        _emit_json(
            _agent_success_payload(
                command,
                {
                    "table_name": table_name,
                    "schema": _dataframe_payload(result.get("schema")),
                    "sample": _dataframe_payload(result.get("sample")),
                },
                context=ctx_public,
            )
        )
        return

    schema = result.get("schema")
    if isinstance(schema, pd.DataFrame):
        typer.echo(schema.to_string(index=False))
    sample = result.get("sample")
    if isinstance(sample, pd.DataFrame) and not sample.empty:
        typer.echo("\nSample:")
        typer.echo(sample.to_string(index=False))


@app.command("query")
def query_cmd(
    sql: Annotated[
        str,
        typer.Option("--sql", help="SQL SELECT query to execute."),
    ],
    dataset_name: Annotated[
        str | None,
        typer.Option("--dataset", help="Dataset to query."),
    ] = None,
    backend_name: Annotated[
        str | None,
        typer.Option("--backend", help="Backend to use."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print result as JSON for automation."),
    ] = False,
    no_interactive: Annotated[
        bool,
        typer.Option("--no-interactive", help="Accepted for automation."),
    ] = False,
):
    """Execute a read-only SQL query without mutating active config."""
    command = "query"
    init_tools()
    ctx = resolve_runtime_context(dataset=dataset_name, backend=backend_name)
    with _silence_m4_logging() if json_output else nullcontext():
        try:
            client = M4Client(
                dataset=dataset_name,
                backend=backend_name,
                interface="cli",
                project_id=ctx.project_id,
                path_disclosure=ctx.path_disclosure,
            )
            result = client.query(sql)
            ctx_public = client.context.public_context()
        except M4Error as exc:
            if json_output:
                _emit_agent_error(
                    command,
                    "query_failed",
                    str(exc),
                    context=ctx.public_context(),
                )
            error(str(exc))
            raise typer.Exit(code=1)

    if json_output:
        _emit_json(
            _agent_success_payload(
                command,
                {
                    "result": _dataframe_payload(result),
                },
                context=ctx_public,
            )
        )
        return

    typer.echo(
        result.to_string(index=False) if not result.empty else "No results found"
    )


@app.command("agent-env")
def agent_env_cmd(
    mode: Annotated[
        str,
        typer.Option("--mode", help="Agent mode: local or protected."),
    ] = "local",
    dataset_name: Annotated[
        str | None,
        typer.Option("--dataset", help="Default dataset for agent sessions."),
    ] = None,
    backend_name: Annotated[
        str | None,
        typer.Option("--backend", help="Default backend for agent sessions."),
    ] = None,
    project_id: Annotated[
        str | None,
        typer.Option("--project-id", help="BigQuery billing project ID."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print result as JSON."),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: dotenv, json, or text."),
    ] = "dotenv",
    include_paths: Annotated[
        bool,
        typer.Option("--paths", help="Disclose raw local paths in metadata."),
    ] = False,
):
    """Return environment variables and command recommendations for agents."""
    if json_output:
        output_format = "json"
    if output_format not in {"dotenv", "json", "text"}:
        if output_format == "json":
            _emit_agent_error(
                "agent-env",
                "invalid_format",
                f"Unsupported format '{output_format}'.",
                hint="Use --format dotenv, json, or text.",
            )
        error("Unsupported format. Use 'dotenv', 'json', or 'text'.")
        raise typer.Exit(code=1)

    if mode not in {"local", "protected"}:
        if output_format == "json":
            _emit_agent_error(
                "agent-env",
                "invalid_mode",
                f"Unsupported mode '{mode}'.",
                hint="Use --mode local or --mode protected.",
            )
        error("Unsupported mode. Use 'local' or 'protected'.")
        raise typer.Exit(code=1)

    ctx = resolve_runtime_context(
        dataset=dataset_name, backend=backend_name, path_disclosure=include_paths
    )
    env = {
        "M4_HOME": str(ctx.home),
        "M4_DATASET": ctx.dataset,
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
    else:
        env["M4_TELEMETRY_DIR"] = str(ctx.telemetry_dir)

    warnings_list: list[str] = []
    if ctx.dataset and not DatasetRegistry.get(ctx.dataset):
        warnings_list.append(f"Dataset '{ctx.dataset}' is not registered.")
    if ctx.backend == "bigquery" and ctx.dataset:
        ds = DatasetRegistry.get(ctx.dataset)
        if ds and not ds.bigquery_dataset_ids:
            warnings_list.append(
                f"Dataset '{ctx.dataset}' is not available on the BigQuery backend."
            )
    if mode == "protected":
        warnings_list.append(
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

    if output_format == "json":
        _emit_json(
            _agent_success_payload(
                "agent-env",
                data,
                context=ctx.public_context(),
                warnings=warnings_list,
            )
        )
        return

    if output_format == "dotenv":
        typer.echo("\n".join(_dotenv_lines(data["environment"])))
        return

    console.print("[bold]Agent environment[/bold]")
    for line in _dotenv_lines(data["environment"]):
        typer.echo(line)
    console.print()
    console.print("[bold]Recommended commands[/bold]")
    for command in data["recommended_commands"]:
        console.print(f"  [command]{command}[/command]")


@provenance_app.command("export")
def provenance_export_cmd(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print provenance as JSON."),
    ] = False,
):
    """Export telemetry/provenance events from the configured event log."""
    event_log = os.getenv("M4_EVENT_LOG")
    path = (
        Path(event_log).expanduser()
        if event_log
        else get_telemetry_dir() / "tool_calls.jsonl"
    )
    events: list[dict[str, Any]] = []
    warnings_list: list[str] = []

    if path.exists():
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                warnings_list.append(f"Skipped malformed JSONL line {line_number}.")
    else:
        warnings_list.append(f"Provenance log does not exist: {path}")

    ctx = resolve_runtime_context()
    data = {
        "event_log": str(path),
        "event_count": len(events),
        "events": _jsonable(events),
    }

    if json_output:
        _emit_json(
            _agent_success_payload(
                "provenance export",
                data,
                context=ctx.public_context(),
                warnings=warnings_list,
            )
        )
        return

    for event in events:
        typer.echo(json.dumps(event, default=str))


def _prompt_select_tools() -> list[str]:
    """Interactive prompt to select AI coding tools for skills installation.

    Returns:
        List of selected tool names.
    """
    from m4.skills import AI_TOOLS

    tools_list = list(AI_TOOLS.values())

    console.print()
    console.print("[bold]Which AI coding tools do you use?[/bold]")
    console.print("[muted](Enter comma-separated numbers, e.g., 1,2,3)[/muted]")
    console.print()

    for i, tool in enumerate(tools_list, 1):
        console.print(f"  [bold]{i}.[/bold] {tool.display_name}")

    console.print()

    # Default to Claude Code (index 1)
    selection = typer.prompt(
        "Select tools",
        default="1",
        show_default=True,
    )

    # Parse selection
    selected_tools = []
    try:
        indices = [int(x.strip()) for x in selection.split(",")]
        for idx in indices:
            if 1 <= idx <= len(tools_list):
                selected_tools.append(tools_list[idx - 1].name)
            else:
                warning(f"Invalid selection: {idx} (ignored)")
    except ValueError:
        warning(f"Could not parse selection: {selection}")
        warning("Defaulting to Claude Code only")
        selected_tools = ["claude"]

    if not selected_tools:
        selected_tools = ["claude"]

    return selected_tools


def _prompt_select_skills() -> tuple[
    list[str] | None, list[str] | None, list[str] | None
]:
    """Interactive prompt to filter which skills to install.

    Returns:
        Tuple of (skill_names, tiers, categories) — all None means install all.
    """
    from m4.skills import get_available_skills

    all_skills = get_available_skills()
    total = len(all_skills)

    # Collect category and tier counts
    cat_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    for s in all_skills:
        cat_counts[s.category] = cat_counts.get(s.category, 0) + 1
        tier_counts[s.tier] = tier_counts.get(s.tier, 0) + 1

    console.print()
    console.print("[bold]Install all skills or filter?[/bold]")
    console.print(f"  [bold]1.[/bold] All skills ({total} available)")
    console.print("  [bold]2.[/bold] Filter by category")
    console.print("  [bold]3.[/bold] Filter by tier")
    console.print("  [bold]4.[/bold] Select individual skills")
    console.print()

    choice = typer.prompt("Selection", default="1", show_default=True)

    if choice == "1":
        return None, None, None

    if choice == "2":
        # Show categories
        cats = sorted(cat_counts.keys())
        console.print()
        console.print("[bold]Select categories:[/bold]")
        console.print("[muted](Enter comma-separated numbers)[/muted]")
        console.print()
        for i, cat in enumerate(cats, 1):
            console.print(f"  [bold]{i}.[/bold] {cat} ({cat_counts[cat]} skills)")
        console.print()
        sel = typer.prompt("Categories", default="1")
        selected_cats = []
        try:
            for idx in (int(x.strip()) for x in sel.split(",")):
                if 1 <= idx <= len(cats):
                    selected_cats.append(cats[idx - 1])
        except ValueError:
            pass
        if selected_cats:
            return None, None, selected_cats
        return None, None, None

    if choice == "3":
        # Show tiers
        tiers = sorted(tier_counts.keys())
        console.print()
        console.print("[bold]Select tiers:[/bold]")
        console.print("[muted](Enter comma-separated numbers)[/muted]")
        console.print()
        for i, t in enumerate(tiers, 1):
            console.print(f"  [bold]{i}.[/bold] {t} ({tier_counts[t]} skills)")
        console.print()
        sel = typer.prompt("Tiers", default="1")
        selected_tiers = []
        try:
            for idx in (int(x.strip()) for x in sel.split(",")):
                if 1 <= idx <= len(tiers):
                    selected_tiers.append(tiers[idx - 1])
        except ValueError:
            pass
        if selected_tiers:
            return None, selected_tiers, None
        return None, None, None

    if choice == "4":
        # Show all skills
        console.print()
        console.print("[bold]Select skills:[/bold]")
        console.print("[muted](Enter comma-separated numbers)[/muted]")
        console.print()
        for i, s in enumerate(all_skills, 1):
            console.print(
                f"  [bold]{i:2d}.[/bold] {s.name:<30s} {s.category:<10s} {s.tier}"
            )
        console.print()
        sel = typer.prompt("Skills")
        selected_names = []
        try:
            for idx in (int(x.strip()) for x in sel.split(",")):
                if 1 <= idx <= len(all_skills):
                    selected_names.append(all_skills[idx - 1].name)
        except ValueError:
            pass
        if selected_names:
            return selected_names, None, None
        return None, None, None

    # Default: install all
    return None, None, None


@app.command("skills")
def skills_cmd(
    tools: Annotated[
        str | None,
        typer.Option(
            "--tools",
            "-t",
            help="Comma-separated list of tools (claude,cursor,cline,codex,gemini,copilot). Interactive if omitted.",
        ),
    ] = None,
    list_installed: Annotated[
        bool,
        typer.Option(
            "--list",
            "-l",
            help="List installed skills across all tools.",
        ),
    ] = False,
    skill_names: Annotated[
        str | None,
        typer.Option(
            "--skills",
            "-s",
            help="Comma-separated skill names to install (e.g., sofa-score,sepsis-3-cohort).",
        ),
    ] = None,
    tier_filter: Annotated[
        str | None,
        typer.Option(
            "--tier",
            help="Comma-separated tiers to install (validated,expert,community).",
        ),
    ] = None,
    category_filter: Annotated[
        str | None,
        typer.Option(
            "--category",
            "-c",
            help="Comma-separated categories to install (clinical,system).",
        ),
    ] = None,
):
    """
    Install M4 skills for AI coding tools.

    Skills teach AI assistants how to use M4's Python API effectively.
    Supports Claude Code, Cursor, Cline, Codex CLI, Gemini CLI, and GitHub Copilot.

    Examples:

    • m4 skills                              # Interactive selection

    • m4 skills --tools claude,cursor        # Install all skills for specific tools

    • m4 skills --tools claude --tier validated  # Only validated skills

    • m4 skills --tools claude --category clinical  # Only clinical skills

    • m4 skills --tools claude --skills sofa-score,m4-api  # Specific skills

    • m4 skills --list                       # Show installed skills
    """
    from m4.skills import (
        AI_TOOLS,
        get_all_installed_skills,
        get_available_skills,
        install_skills,
    )
    from m4.skills.installer import _parse_skill_metadata

    if list_installed:
        # Show installed skills with metadata
        installed = get_all_installed_skills()

        if not installed:
            console.print("[muted]No M4 skills installed.[/muted]")
            console.print()
            console.print("[muted]Install with:[/muted] [command]m4 skills[/command]")
            return

        console.print()
        console.print("[bold]Installed M4 skills:[/bold]")
        console.print()

        for tool_name, skill_name_list in installed.items():
            tool = AI_TOOLS[tool_name]
            console.print(
                f"  [success]●[/success] {tool.display_name} "
                f"({len(skill_name_list)} skills)"
            )
            # Parse metadata from installed skills for richer output
            skills_dir = Path.cwd() / tool.skills_dir
            for skill_name in sorted(skill_name_list):
                skill_dir = skills_dir / skill_name
                meta = _parse_skill_metadata(skill_dir)
                if meta:
                    console.print(
                        f"    [muted]└─[/muted] {meta.name:<30s} "
                        f"{meta.category:<10s} {meta.tier}"
                    )
                else:
                    console.print(f"    [muted]└─[/muted] {skill_name}")

        return

    # Parse filter flags
    skills_list = (
        [s.strip() for s in skill_names.split(",") if s.strip()]
        if skill_names
        else None
    )
    tier_list = (
        [t.strip().lower() for t in tier_filter.split(",") if t.strip()]
        if tier_filter
        else None
    )
    category_list = (
        [c.strip().lower() for c in category_filter.split(",") if c.strip()]
        if category_filter
        else None
    )

    has_cli_filters = skills_list or tier_list or category_list

    # Determine which tools to install for
    if tools:
        # Parse comma-separated list
        selected_tools = [t.strip().lower() for t in tools.split(",")]
        # Validate
        invalid = [t for t in selected_tools if t not in AI_TOOLS]
        if invalid:
            error(f"Unknown tools: {', '.join(invalid)}")
            console.print(f"[muted]Supported: {', '.join(AI_TOOLS.keys())}[/muted]")
            raise typer.Exit(code=1)
    else:
        # Interactive selection
        selected_tools = _prompt_select_tools()

    # Interactive skill filtering (only when no CLI filters provided)
    if not has_cli_filters and not tools:
        i_names, i_tiers, i_cats = _prompt_select_skills()
        if i_names:
            skills_list = i_names
        if i_tiers:
            tier_list = i_tiers
        if i_cats:
            category_list = i_cats

    # Show what will be installed
    selected = get_available_skills(
        tier=tier_list, category=category_list, names=skills_list
    )

    if not selected:
        warning("No skills match the given filters.")
        return

    # Install skills
    console.print()
    info(f"Installing {len(selected)} skill(s) for: {', '.join(selected_tools)}")

    try:
        results = install_skills(
            tools=selected_tools,
            skills=skills_list,
            tier=tier_list,
            category=category_list,
        )

        for tool_name, paths in results.items():
            tool = AI_TOOLS[tool_name]
            for skill_path in paths:
                success(f"Installed {skill_path.name} → {tool.display_name}")

        console.print()
        success("Skills installation complete!")

    except Exception as e:
        error(f"Skills installation failed: {e}")
        raise typer.Exit(code=1)


@app.command("config")
def config_cmd(
    client: Annotated[
        str | None,
        typer.Argument(
            help="MCP client to configure. Use 'claude' for Claude Desktop auto-setup, or omit for universal config generator.",
            metavar="CLIENT",
        ),
    ] = None,
    backend: Annotated[
        str | None,
        typer.Option(
            "--backend",
            "-b",
            help="Configure settings for backend (duckdb or bigquery). Note: Use 'm4 backend' to switch the active backend.",
        ),
    ] = None,
    db_path: Annotated[
        str | None,
        typer.Option(
            "--db-path",
            "-p",
            help="Path to DuckDB database (for duckdb backend)",
        ),
    ] = None,
    project_id: Annotated[
        str | None,
        typer.Option(
            "--project-id",
            help="Google Cloud project ID (required for bigquery backend)",
        ),
    ] = None,
    python_path: Annotated[
        str | None,
        typer.Option(
            "--python-path",
            help="Path to Python executable",
        ),
    ] = None,
    working_directory: Annotated[
        str | None,
        typer.Option(
            "--working-directory",
            help="Working directory for the server",
        ),
    ] = None,
    server_name: Annotated[
        str,
        typer.Option(
            "--server-name",
            help="Name for the MCP server",
        ),
    ] = "m4",
    output: Annotated[
        str | None,
        typer.Option(
            "--output",
            "-o",
            help="Save configuration to file instead of printing",
        ),
    ] = None,
    quick: Annotated[
        bool,
        typer.Option(
            "--quick",
            "-q",
            help="Use quick mode with provided arguments (non-interactive)",
        ),
    ] = False,
    skills: Annotated[
        bool,
        typer.Option(
            "--skills",
            help="Install M4 skills after config. Interactive tool selection, or Claude-only with 'claude' client.",
        ),
    ] = False,
):
    """
    Configure M4 MCP server for various clients.

    Examples:

    • m4 config                    # Interactive universal config generator

    • m4 config claude             # Auto-configure Claude Desktop

    • m4 config --quick            # Quick universal config with defaults

    • m4 config claude --backend bigquery --project-id my-project
    """
    try:
        from m4 import mcp_client_configs

        script_dir = Path(mcp_client_configs.__file__).parent
    except ImportError:
        error("Could not find m4.mcp_client_configs package")
        raise typer.Exit(code=1)

    # Track whether backend/project_id were explicitly provided by the user
    backend_explicit = backend is not None
    project_id_explicit = project_id is not None
    if backend is None:
        backend = get_active_backend()

    # Infer project_id from config when backend is bigquery and not explicitly passed
    if backend == "bigquery" and not project_id:
        project_id = get_bigquery_project_id()

    # Validate backend-specific arguments only when --backend is explicit
    if backend_explicit:
        # duckdb: db_path allowed, project_id not allowed
        if backend == "duckdb" and project_id:
            error("--project-id can only be used with --backend bigquery")
            raise typer.Exit(code=1)

        # bigquery: requires project_id, db_path not allowed
        if backend == "bigquery" and db_path:
            error("--db-path can only be used with --backend duckdb")
            raise typer.Exit(code=1)
        if backend == "bigquery" and not project_id:
            error("--project-id is required when using --backend bigquery")
            raise typer.Exit(code=1)

    # Even when inferred, bigquery still requires a project_id
    if backend == "bigquery" and not project_id:
        error(
            "BigQuery backend requires a project ID. "
            "Set it with: m4 backend bigquery --project-id <ID>"
        )
        raise typer.Exit(code=1)

    if client == "claude":
        # Run the Claude Desktop setup script
        script_path = script_dir / "setup_claude_desktop.py"

        if not script_path.exists():
            error(f"Claude Desktop setup script not found at {script_path}")
            raise typer.Exit(code=1)

        # Build command arguments with smart defaults inferred from runtime config
        cmd = [sys.executable, str(script_path)]

        # Always pass backend if not duckdb; duckdb is the script default
        if backend != "duckdb":
            cmd.extend(["--backend", backend])

        # For duckdb, pass db_path only if explicitly provided.
        # If omitted, the server will resolve it dynamically based on the active dataset.
        if backend == "duckdb" and db_path:
            inferred_db_path = Path(db_path).resolve()
            cmd.extend(["--db-path", str(inferred_db_path)])

        elif backend == "bigquery" and project_id:
            cmd.extend(["--project-id", project_id])

        try:
            result = subprocess.run(cmd, check=True, capture_output=False)
            if result.returncode == 0:
                # Persist backend and project_id only if explicitly provided
                if backend_explicit:
                    set_active_backend(backend)
                if project_id_explicit:
                    set_bigquery_project_id(project_id)
                success("Claude Desktop configuration completed!")
        except subprocess.CalledProcessError as e:
            error(f"Claude Desktop setup failed with exit code {e.returncode}")
            raise typer.Exit(code=e.returncode)
        except FileNotFoundError:
            error("Python interpreter not found. Please ensure Python is installed.")
            raise typer.Exit(code=1)

        # Install skills if requested (Claude-only for backwards compatibility)
        if skills:
            from m4.skills import AI_TOOLS, install_skills

            try:
                results = install_skills(tools=["claude"])
                for tool_name, paths in results.items():
                    tool = AI_TOOLS[tool_name]
                    for skill_path in paths:
                        success(f"Installed skill: {skill_path.name} → {skill_path}")
            except Exception as e:
                warning(f"Skills installation failed: {e}")

    else:
        # Run the dynamic config generator
        script_path = script_dir / "dynamic_mcp_config.py"

        if not script_path.exists():
            error(f"Dynamic config script not found at {script_path}")
            raise typer.Exit(code=1)

        # Build command arguments
        cmd = [sys.executable, str(script_path)]

        if quick:
            cmd.append("--quick")

        if backend != "duckdb":
            cmd.extend(["--backend", backend])

        if server_name != "m4":
            cmd.extend(["--server-name", server_name])

        if python_path:
            cmd.extend(["--python-path", python_path])

        if working_directory:
            cmd.extend(["--working-directory", working_directory])

        if backend == "duckdb" and db_path:
            cmd.extend(["--db-path", db_path])
        elif backend == "bigquery" and project_id:
            cmd.extend(["--project-id", project_id])

        if output:
            cmd.extend(["--output", output])

        if quick:
            info("Generating M4 MCP configuration...")
        else:
            info("Starting interactive M4 MCP configuration...")

        try:
            result = subprocess.run(cmd, check=True, capture_output=False)
            if result.returncode == 0:
                # Persist backend and project_id only if explicitly provided
                if backend_explicit:
                    set_active_backend(backend)
                if project_id_explicit:
                    set_bigquery_project_id(project_id)
                if quick:
                    success("Configuration generated successfully!")
        except subprocess.CalledProcessError as e:
            error(f"Configuration generation failed with exit code {e.returncode}")
            raise typer.Exit(code=e.returncode)
        except FileNotFoundError:
            error("Python interpreter not found. Please ensure Python is installed.")
            raise typer.Exit(code=1)

        # Install skills if requested (interactive tool selection)
        if skills:
            from m4.skills import AI_TOOLS, install_skills

            selected_tools = _prompt_select_tools()
            console.print()
            info(f"Installing skills for: {', '.join(selected_tools)}")

            try:
                results = install_skills(tools=selected_tools)
                for tool_name, paths in results.items():
                    tool = AI_TOOLS[tool_name]
                    for skill_path in paths:
                        success(
                            f"Installed skill: {skill_path.name} → {tool.display_name}"
                        )
            except Exception as e:
                warning(f"Skills installation failed: {e}")


if __name__ == "__main__":
    app()
