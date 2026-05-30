from unittest.mock import patch

from m4.services.agent_env import build_agent_env_service
from m4.services.config import MCPConfigRequest, configure_mcp_service


def test_agent_env_local_includes_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("M4_DATA_DIR", str(tmp_path / "m4_data"))

    result = build_agent_env_service(
        mode="local", dataset="mimic-iv-demo", backend="duckdb"
    )

    assert result.command == "agent-env"
    assert "M4_DATASET" not in result.data["environment"]
    assert result.data["defaults"]["dataset"] == "mimic-iv-demo"
    assert result.data["environment"]["M4_BACKEND"] == "duckdb"
    assert "M4_DATA_DIR" in result.data["environment"]
    assert result.data["raw_paths_hidden"] is True


def test_agent_env_protected_omits_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("M4_DATA_DIR", str(tmp_path / "m4_data"))

    result = build_agent_env_service(mode="protected")

    assert "M4_DATA_DIR" not in result.data["environment"]
    assert result.warnings


def test_agent_env_invalid_mode_returns_command_error():
    result = build_agent_env_service(mode="bad")

    assert result.ok is False
    assert result.code == "invalid_mode"


@patch("m4.services.config.setup_claude_desktop", return_value=True)
@patch("m4.services.config.set_bigquery_project_id")
@patch("m4.services.config.set_active_backend")
def test_config_claude_persists_explicit_backend(
    mock_set_backend, mock_set_project, mock_setup
):
    result = configure_mcp_service(
        MCPConfigRequest(
            client="claude",
            backend="bigquery",
            project_id="billing-project",
        )
    )

    assert result.ok is True
    mock_setup.assert_called_once_with(
        backend="bigquery", db_path=None, project_id="billing-project"
    )
    mock_set_backend.assert_called_once_with("bigquery")
    mock_set_project.assert_called_once_with("billing-project")


@patch("m4.services.config.get_active_backend", return_value="bigquery")
@patch("m4.services.config.get_bigquery_project_id", return_value=None)
def test_config_bigquery_without_project_returns_command_error(
    mock_get_project, mock_get_backend
):
    result = configure_mcp_service(MCPConfigRequest(client="claude"))

    assert result.ok is False
    assert result.code == "project_id_required"


@patch("m4.services.config.MCPConfigGenerator")
@patch("m4.services.config.get_active_backend", return_value="duckdb")
def test_config_quick_generates_config_without_subprocess(
    mock_get_backend, mock_generator_cls
):
    mock_generator = mock_generator_cls.return_value
    mock_generator.generate_config.return_value = {
        "mcpServers": {
            "m4": {
                "command": "python",
                "args": ["-m", "m4.mcp_server"],
                "cwd": ".",
                "env": {},
            }
        }
    }

    result = configure_mcp_service(MCPConfigRequest(quick=True))

    assert result.ok is True
    assert result.data["config"]["mcpServers"]["m4"]["args"] == [
        "-m",
        "m4.mcp_server",
    ]
    mock_generator.generate_config.assert_called_once()
