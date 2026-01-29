"""
Rich-based console utilities for the M4 CLI.

Provides consistent, beautiful terminal output with:
- M4 logo/branding
- Styled messages (info, success, warning, error)
- Progress bars and spinners
- Formatted panels and tables
"""

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# Custom theme for M4
M4_THEME = Theme(
    {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "red bold",
        "highlight": "magenta",
        "muted": "dim",
        "brand": "bold blue",
        "path": "cyan underline",
        "command": "bold green",
    }
)

# Global console instance with custom theme
console = Console(theme=M4_THEME)

# M4 ASCII Logo - compact and modern
M4_LOGO = r"""
    __  __ _  _
   |  \/  | || |
   | |\/| | || |_
   | |  | |__   _|
   |_|  |_|  |_|
"""

M4_LOGO_SMALL = r"[bold blue]M4[/bold blue]"

# Tagline
M4_TAGLINE = "Medical Data Made Accessible"


def print_logo(show_tagline: bool = True, show_version: bool = True) -> None:
    """
    Print the M4 logo with optional tagline and version.

    Use cases:
    - CLI startup (m4 --version)
    - After successful initialization
    - Help screen header
    """
    from m4 import __version__

    logo_text = Text(M4_LOGO, style="bold blue")

    if show_tagline:
        tagline = Text(f"\n  {M4_TAGLINE}", style="italic cyan")
        logo_text.append(tagline)

    if show_version:
        version = Text(f"\n  v{__version__}", style="dim")
        logo_text.append(version)

    console.print(logo_text)


def print_banner(title: str, subtitle: str | None = None) -> None:
    """Print a styled banner for section headers."""
    content = f"[bold]{title}[/bold]"
    if subtitle:
        content += f"\n[dim]{subtitle}[/dim]"
    console.print(Panel(content, style="blue", padding=(0, 2)))


def info(message: str, prefix: str = "info") -> None:
    """Print an info message."""
    console.print(f"[info]{prefix}:[/info] {message}")


def success(message: str, prefix: str = "done") -> None:
    """Print a success message with checkmark."""
    console.print(f"[success]{prefix}:[/success] {message}")


def warning(message: str, prefix: str = "warning") -> None:
    """Print a warning message."""
    console.print(f"[warning]{prefix}:[/warning] {message}")


def error(message: str, prefix: str = "error") -> None:
    """Print an error message."""
    console.print(f"[error]{prefix}:[/error] {message}")


def print_step(step: int, total: int, message: str) -> None:
    """Print a numbered step in a multi-step process."""
    console.print(f"[brand]({step}/{total})[/brand] {message}")


def print_path(label: str, path: Any) -> None:
    """Print a labeled path."""
    console.print(f"  [muted]{label}:[/muted] [path]{path}[/path]")


def print_command(command: str) -> None:
    """Print a command that the user can run."""
    console.print(f"  [command]$ {command}[/command]")


def print_key_value(key: str, value: Any, indent: int = 2) -> None:
    """Print a key-value pair."""
    spaces = " " * indent
    console.print(f"{spaces}[muted]{key}:[/muted] {value}")


def print_status_icon(present: bool) -> str:
    """Return a status icon string."""
    return "[success]OK[/success]" if present else "[error]NO[/error]"


def create_status_table(title: str | None = None) -> Table:
    """Create a styled table for status display."""
    table = Table(
        title=title,
        show_header=True,
        header_style="bold",
        border_style="dim",
        padding=(0, 1),
    )
    return table


def create_download_progress() -> Progress:
    """
    Create a progress bar for file downloads.

    Shows: spinner, filename, progress bar, percentage, download speed, size
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=console,
    )


def create_task_progress(
    description_width: int = 40, show_speed: bool = False
) -> Progress:
    """
    Create a progress bar for general tasks (file conversion, view creation, etc.).

    Shows: spinner, description, progress bar, percentage, elapsed time, ETA
    """
    columns = [
        SpinnerColumn(),
        TextColumn(f"[bold blue]{{task.description:<{description_width}}}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TextColumn("[muted]/[/muted]"),
        TimeRemainingColumn(),
    ]
    return Progress(*columns, console=console)


def create_spinner_progress() -> Progress:
    """
    Create a simple spinner for indeterminate tasks.

    Shows: spinner, description, elapsed time
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    )


def print_derived_status_line(
    materialized: int,
    total: int,
    dataset_name: str,
    has_support: bool,
    is_bigquery: bool = False,
) -> None:
    """Print a single-line derived table status.

    Renders one of:
    - ``Derived: OK (60/60)``
    - ``Derived: PARTIAL (43/60 — run m4 init-derived mimic-iv --force)``
    - ``Derived: NO (0/60 — run m4 init-derived mimic-iv)``
    - ``Derived: - `` (unsupported dataset)
    - ``Derived: OK (BigQuery)`` (BigQuery backend)
    """
    if is_bigquery:
        console.print(
            "  [muted]Derived:[/muted]       [success]OK[/success] (BigQuery)"
        )
        return

    if not has_support:
        console.print("  [muted]Derived:[/muted]       [muted]-[/muted]")
        return

    if materialized == total:
        console.print(
            f"  [muted]Derived:[/muted]       [success]OK[/success] ({materialized}/{total})"
        )
    elif materialized == 0:
        console.print(
            f"  [muted]Derived:[/muted]       [error]NO[/error] "
            f"(0/{total} — run m4 init-derived {dataset_name})"
        )
    else:
        console.print(
            f"  [muted]Derived:[/muted]       [warning]PARTIAL[/warning] "
            f"({materialized}/{total} — run m4 init-derived {dataset_name} --force)"
        )


def print_derived_detail(
    dataset_name: str,
    categories: dict[str, list[str]],
    materialized: set[str],
) -> None:
    """Print grouped per-table derived status.

    Example output::

        Derived tables for mimic-iv: 60/60 materialized

          demographics (5/5)
            OK  age
            OK  icustay_detail
            ...
    """
    total = sum(len(tables) for tables in categories.values())
    mat_count = sum(
        1 for tables in categories.values() for t in tables if t in materialized
    )

    console.print(
        f"\n[bold]Derived tables for {dataset_name}:[/bold] "
        f"{mat_count}/{total} materialized\n"
    )

    for category, tables in categories.items():
        cat_ok = sum(1 for t in tables if t in materialized)
        console.print(f"  [bold]{category}[/bold] ({cat_ok}/{len(tables)})")
        for table in tables:
            if table in materialized:
                console.print(f"    [success]OK[/success]  {table}")
            else:
                console.print(f"    [error]--[/error]  {table}")
        console.print()


def print_dataset_status(
    name: str,
    parquet_present: bool,
    db_present: bool,
    parquet_root: str,
    db_path: str,
    parquet_size_gb: float | None = None,
    bigquery_available: bool = False,
    row_count: int | None = None,
    is_active: bool = False,
    derived_materialized: int | None = None,
    derived_total: int | None = None,
    derived_has_support: bool = False,
    derived_is_bigquery: bool = False,
) -> None:
    """Print formatted dataset status information."""
    # Header with active indicator
    status_indicator = "[success] (active)[/success]" if is_active else ""
    console.print(f"\n[brand]{name.upper()}[/brand]{status_indicator}")

    # Status icons
    pq_status = print_status_icon(parquet_present)
    db_status = print_status_icon(db_present)
    bq_status = print_status_icon(bigquery_available)

    console.print(f"  [muted]Local Parquet:[/muted] {pq_status}")
    console.print(f"  [muted]Local DuckDB:[/muted]  {db_status}")
    console.print(f"  [muted]BigQuery:[/muted]      {bq_status}")

    # Derived status line
    print_derived_status_line(
        materialized=derived_materialized or 0,
        total=derived_total or 0,
        dataset_name=name,
        has_support=derived_has_support,
        is_bigquery=derived_is_bigquery,
    )

    if parquet_present:
        console.print(f"  [muted]Parquet path:[/muted]  [path]{parquet_root}[/path]")
        if parquet_size_gb is not None:
            console.print(f"  [muted]Parquet size:[/muted]  {parquet_size_gb:.2f} GB")

    if db_present:
        console.print(f"  [muted]Database path:[/muted] [path]{db_path}[/path]")
        if row_count is not None:
            console.print(f"  [muted]Row count:[/muted]     {row_count:,}")


def print_welcome() -> None:
    """Print a welcome message with the M4 logo. Use for first-time setup."""
    print_logo()
    console.print()


def print_init_complete(dataset_name: str, db_path: str, parquet_root: str) -> None:
    """Print completion message after successful initialization."""
    console.print()
    panel_content = (
        f"[success]Dataset '[bold]{dataset_name}[/bold]' initialized successfully![/success]\n\n"
        f"[muted]Database:[/muted]  [path]{db_path}[/path]\n"
        f"[muted]Parquet:[/muted]   [path]{parquet_root}[/path]\n\n"
        f"[dim]Run [command]m4 status[/command] to verify, or start querying with your MCP client.[/dim]"
    )
    console.print(
        Panel(panel_content, title="[bold blue]M4[/bold blue]", padding=(1, 2))
    )


def print_error_panel(title: str, message: str, hint: str | None = None) -> None:
    """Print an error in a styled panel."""
    content = f"[error]{message}[/error]"
    if hint:
        content += f"\n\n[dim]Hint: {hint}[/dim]"
    console.print(Panel(content, title=f"[error]{title}[/error]", padding=(1, 2)))


def print_datasets_table(
    datasets: list[dict],
    active_dataset: str | None = None,
) -> None:
    """
    Print a compact table of all datasets.

    Args:
        datasets: List of dicts with keys: name, parquet_present, db_present,
                  bigquery_available, parquet_size_gb (optional)
        active_dataset: Name of the currently active dataset
    """
    table = Table(
        show_header=True,
        header_style="bold",
        border_style="dim",
        padding=(0, 1),
    )

    table.add_column("Dataset", style="bold")
    table.add_column("Active", justify="center")
    table.add_column("Local", justify="center")
    table.add_column("BigQuery", justify="center")
    table.add_column("Derived", justify="center")
    table.add_column("Size", justify="right")

    for ds in datasets:
        name = ds["name"]
        is_active = name == active_dataset

        # Active indicator
        active_str = "[success]*[/success]" if is_active else "[muted]-[/muted]"

        # Local status (combine parquet + duckdb)
        pq = ds.get("parquet_present", False)
        db = ds.get("db_present", False)
        if pq and db:
            local_str = "[success]OK[/success]"
        elif pq:
            local_str = "[warning]Parquet[/warning]"
        elif db:
            local_str = "[warning]DB only[/warning]"
        else:
            local_str = "[muted]-[/muted]"

        # BigQuery status
        bq = ds.get("bigquery_available", False)
        bq_str = "[success]OK[/success]" if bq else "[muted]-[/muted]"

        # Derived status
        derived_mat = ds.get("derived_materialized")
        derived_tot = ds.get("derived_total")
        if derived_mat is not None and derived_tot is not None:
            derived_str = f"{derived_mat}/{derived_tot}"
        else:
            derived_str = "[muted]-[/muted]"

        # Size
        size_gb = ds.get("parquet_size_gb")
        if size_gb is not None:
            size_str = f"{size_gb:.2f} GB"
        else:
            size_str = "[muted]-[/muted]"

        table.add_row(name, active_str, local_str, bq_str, derived_str, size_str)

    console.print(table)
