import logging
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from m4.config import (
    detect_available_local_datasets,
    get_active_dataset,
    get_dataset_parquet_root,
    get_default_database_path,
    logger,
    set_active_dataset,
)
from m4.console import (
    console,
    error,
    info,
    print_banner,
    print_command,
    print_dataset_status,
    print_error_panel,
    print_init_complete,
    print_key_value,
    print_logo,
    print_step,
    success,
    warning,
)
from m4.core.datasets import DatasetRegistry
from m4.data_io import (
    compute_parquet_dir_size,
    convert_csv_to_parquet,
    download_dataset,
    init_duckdb_from_parquet,
    verify_table_rowcount,
)

app = typer.Typer(
    name="m4",
    help="M4 CLI: Initialize local clinical datasets like MIMIC-IV Demo.",
    add_completion=False,
    rich_markup_mode="markdown",
)


def version_callback(value: bool):
    if value:
        print_logo(show_tagline=True, show_version=True)
        raise typer.Exit()


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
            wget_cmd = f"wget -r -N -c -np --user YOUR_USERNAME --ask-password {base_url} -P {csv_root}"
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


@app.command("use")
def use_cmd(
    target: Annotated[
        str,
        typer.Argument(
            help="Select active dataset: name (e.g., mimic-iv-full)", metavar="TARGET"
        ),
    ],
):
    """Set the active dataset selection for the project."""
    target = target.lower()

    # 1. Check if dataset is registered
    availability = detect_available_local_datasets().get(target)

    if not availability:
        supported = ", ".join([ds.name for ds in DatasetRegistry.list_all()])
        print_error_panel(
            "Dataset Not Found",
            f"Dataset '{target}' not found or not registered.",
            hint=f"Supported datasets: {supported}",
        )
        raise typer.Exit(code=1)

    # 2. Set it active immediately (don't block on files)
    set_active_dataset(target)
    success(f"Active dataset set to '{target}'")

    # 3. Warn if local files are missing (helpful info, not a blocker)
    if not availability["parquet_present"]:
        warning(f"Local Parquet files not found at {availability['parquet_root']}")
        console.print(
            "  [muted]This is fine if you are using the BigQuery backend.[/muted]"
        )
        console.print(
            "  [muted]For DuckDB (local), run:[/muted] [command]m4 init[/command]"
        )
    else:
        info("Local: Available", prefix="status")

    # 4. Check BigQuery support
    ds_def = DatasetRegistry.get(target)
    if ds_def:
        if not ds_def.bigquery_dataset_ids:
            warning("This dataset is not configured for BigQuery")
            console.print(
                "  [muted]If you're using the BigQuery backend, queries will fail.[/muted]"
            )
        else:
            info(
                f"BigQuery: Available (Project: {ds_def.bigquery_project_id})",
                prefix="status",
            )


@app.command("status")
def status_cmd():
    """Show active dataset, local DB path, Parquet presence, quick counts and sizes."""
    print_logo(show_tagline=False, show_version=True)
    console.print()

    active = get_active_dataset() or "(unset)"
    if active != "(unset)":
        console.print(f"[bold]Active dataset:[/bold] [success]{active}[/success]")
    else:
        console.print(f"[bold]Active dataset:[/bold] [warning]{active}[/warning]")

    availability = detect_available_local_datasets()
    if not availability:
        console.print("\n[muted]No datasets detected.[/muted]")
        return

    for label, ds_info in availability.items():
        is_active = label == active

        # Get size if parquet present
        parquet_size_gb = None
        if ds_info["parquet_present"]:
            try:
                size_bytes = compute_parquet_dir_size(Path(ds_info["parquet_root"]))
                parquet_size_gb = float(size_bytes) / (1024**3)
            except Exception:
                pass

        # Get dataset definition for BigQuery status and verification
        ds_def = DatasetRegistry.get(label)
        bigquery_available = bool(ds_def and ds_def.bigquery_dataset_ids)

        # Get row count if possible
        row_count = None
        if ds_info["db_present"] and ds_def and ds_def.primary_verification_table:
            try:
                row_count = verify_table_rowcount(
                    Path(ds_info["db_path"]), ds_def.primary_verification_table
                )
            except Exception as e:
                # Show hint if it looks like a path mismatch
                if "No files found" in str(e) or "no such file" in str(e).lower():
                    warning("Database views may point to wrong parquet location")
                    console.print(
                        f"  [muted]Try:[/muted] [command]m4 init {label} --force[/command]"
                    )

        print_dataset_status(
            name=label,
            parquet_present=ds_info["parquet_present"],
            db_present=ds_info["db_present"],
            parquet_root=str(ds_info["parquet_root"]),
            db_path=str(ds_info["db_path"]),
            parquet_size_gb=parquet_size_gb,
            bigquery_available=bigquery_available,
            row_count=row_count,
            is_active=is_active,
        )


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
        str,
        typer.Option(
            "--backend",
            "-b",
            help="Backend to use (duckdb or bigquery). Default: duckdb",
        ),
    ] = "duckdb",
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

    # Validate backend-specific arguments
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
                success("Claude Desktop configuration completed!")
        except subprocess.CalledProcessError as e:
            error(f"Claude Desktop setup failed with exit code {e.returncode}")
            raise typer.Exit(code=e.returncode)
        except FileNotFoundError:
            error("Python interpreter not found. Please ensure Python is installed.")
            raise typer.Exit(code=1)

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
            if result.returncode == 0 and quick:
                success("Configuration generated successfully!")
        except subprocess.CalledProcessError as e:
            error(f"Configuration generation failed with exit code {e.returncode}")
            raise typer.Exit(code=e.returncode)
        except FileNotFoundError:
            error("Python interpreter not found. Please ensure Python is installed.")
            raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
