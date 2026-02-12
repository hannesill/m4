"""Standalone vitrine CLI — independent of the m4 command.

Usage:
    vitrine restart [--port PORT] [--no-open]
    vitrine start   [--port PORT] [--no-open]
    vitrine stop
    vitrine status
"""

from __future__ import annotations

import sys
import time

import typer
from rich.console import Console

app = typer.Typer(
    name="vitrine",
    help="Manage the vitrine display server.",
    no_args_is_help=True,
)
console = Console()


def _info(msg: str) -> None:
    console.print(f"[dim]>[/dim] {msg}")


def _success(msg: str) -> None:
    console.print(f"[green]✓[/green] {msg}")


def _error(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")


@app.command()
def restart(
    port: int = typer.Option(7741, "--port", "-p", help="Port to bind to."),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open browser."),
) -> None:
    """Stop the running vitrine server and start a fresh one."""
    from m4.vitrine import server_status, stop_server

    info = server_status()
    if info:
        _info(f"Stopping server (pid={info.get('pid')}, port={info.get('port')})...")
        if stop_server():
            _success("Server stopped.")
        else:
            _error("Failed to stop server. Try killing the process manually.")
            raise typer.Exit(1)
    else:
        _info("No running server found — starting fresh.")

    _start_background(port=port, no_open=no_open)


@app.command()
def start(
    port: int = typer.Option(7741, "--port", "-p", help="Port to bind to."),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open browser."),
    foreground: bool = typer.Option(
        False, "--foreground", "-f", help="Run in foreground (blocks)."
    ),
) -> None:
    """Start the vitrine server."""
    from m4.vitrine import server_status

    info = server_status()
    if info:
        _info(
            f"Server already running (pid={info.get('pid')}, "
            f"port={info.get('port')}, url={info.get('url')})"
        )
        return

    if foreground:
        from m4.vitrine.server import _run_standalone

        _info(f"Starting vitrine server on port {port}...")
        _run_standalone(port=port, no_open=no_open)
    else:
        _start_background(port=port, no_open=no_open)


@app.command()
def stop() -> None:
    """Stop the running vitrine server."""
    from m4.vitrine import stop_server

    if stop_server():
        _success("Server stopped.")
    else:
        _info("No running server found.")


@app.command()
def status() -> None:
    """Show status of the vitrine server."""
    from m4.vitrine import server_status

    info = server_status()
    if info:
        _success("Server is running")
        console.print(f"  [bold]URL:[/bold]        {info.get('url')}")
        console.print(f"  [bold]PID:[/bold]        {info.get('pid')}")
        console.print(f"  [bold]Port:[/bold]       {info.get('port')}")
        console.print(f"  [bold]Session:[/bold]    {info.get('session_id')}")
        console.print(f"  [bold]Started:[/bold]    {info.get('started_at')}")
    else:
        _info("No running server found.")


def _start_background(port: int = 7741, no_open: bool = False) -> None:
    """Start the server as a background process and wait for it to come up."""
    import subprocess

    cmd = [
        sys.executable,
        "-m",
        "m4.vitrine.server",
        "--port",
        str(port),
    ]
    if no_open:
        cmd.append("--no-open")

    _info(f"Starting vitrine server on port {port}...")
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Wait for server to come up
    from m4.vitrine import server_status

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        info = server_status()
        if info:
            _success(f"Server started (pid={info.get('pid')}, url={info.get('url')})")
            return
        time.sleep(0.2)

    _error("Server process started but didn't become healthy within 5s.")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
