"""Tests for m4.vitrine.cli — standalone vitrine CLI commands.

Tests cover:
- status command: running and no-server states
- stop command: successful stop and no-server-found
- start command: already running, background start
- restart command: stop + start flow
"""

from unittest.mock import patch

from typer.testing import CliRunner

from m4.vitrine.cli import app

runner = CliRunner()

# The CLI functions use lazy imports like:
#   from m4.vitrine import server_status, stop_server
# So we patch on the m4.vitrine module itself.


class TestStatusCommand:
    def test_status_no_server(self):
        with patch("m4.vitrine.server_status", return_value=None):
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "No running server" in result.output

    def test_status_server_running(self):
        info = {
            "pid": 12345,
            "port": 7741,
            "url": "http://127.0.0.1:7741",
            "session_id": "sess-123",
            "started_at": "2024-01-01T00:00:00",
        }
        with patch("m4.vitrine.server_status", return_value=info):
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "running" in result.output.lower()
        assert "12345" in result.output
        assert "7741" in result.output


class TestStopCommand:
    def test_stop_no_server(self):
        with patch("m4.vitrine.stop_server", return_value=False):
            result = runner.invoke(app, ["stop"])
        assert result.exit_code == 0
        assert "No running server" in result.output

    def test_stop_success(self):
        with patch("m4.vitrine.stop_server", return_value=True):
            result = runner.invoke(app, ["stop"])
        assert result.exit_code == 0
        assert "stopped" in result.output.lower()


class TestStartCommand:
    def test_start_already_running(self):
        info = {"pid": 12345, "port": 7741, "url": "http://127.0.0.1:7741"}
        with patch("m4.vitrine.server_status", return_value=info):
            result = runner.invoke(app, ["start"])
        assert result.exit_code == 0
        assert "already running" in result.output.lower()

    def test_start_background_success(self):
        # First call: no server running; subsequent calls: server is up
        call_count = 0

        def mock_server_status():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None  # Not running initially
            return {"pid": 12345, "port": 7741, "url": "http://127.0.0.1:7741"}

        with (
            patch("m4.vitrine.server_status", side_effect=mock_server_status),
            patch("subprocess.Popen") as mock_popen,
            patch("m4.vitrine.cli.time.sleep"),
        ):
            result = runner.invoke(app, ["start", "--port", "7741"])

        assert result.exit_code == 0
        assert "started" in result.output.lower()
        mock_popen.assert_called_once()

    def test_start_background_timeout(self):
        """Server doesn't come up within deadline — exit code 1."""

        # Make time.monotonic advance past the 5s deadline
        clock = [0.0]

        def mock_monotonic():
            clock[0] += 3.0  # Jump 3s each call
            return clock[0]

        with (
            patch("m4.vitrine.server_status", return_value=None),
            patch("subprocess.Popen"),
            patch("m4.vitrine.cli.time.monotonic", side_effect=mock_monotonic),
            patch("m4.vitrine.cli.time.sleep"),
        ):
            result = runner.invoke(app, ["start"])

        assert result.exit_code == 1
        assert "didn't become healthy" in result.output.lower()


class TestRestartCommand:
    def test_restart_no_existing_server(self):
        call_count = 0

        def mock_server_status():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return None  # No server at initial check
            return {"pid": 99, "port": 7741, "url": "http://127.0.0.1:7741"}

        with (
            patch("m4.vitrine.server_status", side_effect=mock_server_status),
            patch("subprocess.Popen"),
            patch("m4.vitrine.cli.time.sleep"),
        ):
            result = runner.invoke(app, ["restart"])

        assert result.exit_code == 0
        assert "starting fresh" in result.output.lower()

    def test_restart_stops_existing_server(self):
        call_count = 0

        def mock_server_status():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"pid": 111, "port": 7741, "url": "http://127.0.0.1:7741"}
            if call_count == 2:
                return None  # After stop, not started yet
            return {"pid": 222, "port": 7741, "url": "http://127.0.0.1:7741"}

        with (
            patch("m4.vitrine.server_status", side_effect=mock_server_status),
            patch("m4.vitrine.stop_server", return_value=True) as mock_stop,
            patch("subprocess.Popen"),
            patch("m4.vitrine.cli.time.sleep"),
        ):
            result = runner.invoke(app, ["restart"])

        assert result.exit_code == 0
        mock_stop.assert_called_once()
        assert "stopped" in result.output.lower()

    def test_restart_stop_failure(self):
        """If stop fails, restart exits with error."""
        with (
            patch(
                "m4.vitrine.server_status",
                return_value={"pid": 111, "port": 7741},
            ),
            patch("m4.vitrine.stop_server", return_value=False),
        ):
            result = runner.invoke(app, ["restart"])

        assert result.exit_code == 1
        assert "failed to stop" in result.output.lower()
