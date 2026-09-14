"""Claude Desktop configuration discovery using synthetic installation paths."""

import importlib
import json
from pathlib import Path

import pytest

setup = importlib.import_module("m4.mcp_client_configs.setup_claude_desktop")
CONFIG_NAME = "claude_desktop_config.json"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    return tmp_path


def msix_config(local, package="Claude_pzs8sxrjxfjjc"):
    return (
        local / "Packages" / package / "LocalCache" / "Roaming" / "Claude" / CONFIG_NAME
    )


@pytest.mark.parametrize(
    "relative",
    ["Library/Application Support/Claude", "AppData/Roaming/Claude", ".config/Claude"],
)
def test_existing_installation_locations(home, relative):
    directory = home / relative
    directory.mkdir(parents=True)
    assert setup.get_claude_config_path() == directory / CONFIG_NAME


def test_windows_roaming_environment_path(home, monkeypatch):
    roaming = home / "redirected-roaming"
    monkeypatch.setenv("APPDATA", str(roaming))
    (roaming / "Claude").mkdir(parents=True)
    assert setup.get_claude_config_path() == roaming / "Claude" / CONFIG_NAME


@pytest.mark.parametrize("package", ["Claude_pzs8sxrjxfjjc", "Claude_anotherpublisher"])
def test_msix_discovery_uses_local_appdata(home, monkeypatch, package):
    local = home / "redirected-local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    config = msix_config(local, package)
    config.parent.mkdir(parents=True)
    assert setup.get_claude_config_path() == config


def test_msix_preferred_over_traditional_configuration(home):
    traditional = home / "AppData" / "Roaming" / "Claude" / CONFIG_NAME
    traditional.parent.mkdir(parents=True)
    traditional.write_text('{"traditional": true}')
    config = msix_config(home / "AppData" / "Local")
    config.parent.mkdir(parents=True)
    config.write_text("{}")
    assert setup.get_claude_config_path() == config


def test_existing_msix_file_preferred_over_empty_package_directory(home):
    local = home / "AppData" / "Local"
    empty = msix_config(local, "Claude_empty")
    empty.parent.mkdir(parents=True)
    config = msix_config(local)
    config.parent.mkdir(parents=True)
    config.write_text("{}")
    assert setup.get_claude_config_path() == config


@pytest.mark.parametrize("with_files", [False, True])
def test_ambiguous_msix_installations_are_not_modified(home, with_files):
    for package in ["Claude_first", "Claude_second"]:
        config = msix_config(home / "AppData" / "Local", package)
        config.parent.mkdir(parents=True)
        if with_files:
            config.write_text("{}")
    with pytest.raises(FileNotFoundError, match="Multiple Claude Desktop MSIX"):
        setup.get_claude_config_path()


def test_unrelated_packages_and_incomplete_msix_paths_are_ignored(home):
    local = home / "AppData" / "Local"
    msix_config(local, "Other_package").parent.mkdir(parents=True)
    (local / "Packages" / "Claude_incomplete").mkdir()
    with pytest.raises(FileNotFoundError, match="Could not find"):
        setup.get_claude_config_path()


def test_setup_preserves_other_settings_and_leaves_traditional_file_untouched(
    home, monkeypatch
):
    config = msix_config(home / "AppData" / "Local")
    config.parent.mkdir(parents=True)
    existing = {
        "mcpServers": {"other": {"command": "other-server"}},
        "preferences": {"theme": "dark"},
    }
    config.write_text(json.dumps(existing))
    traditional = home / "AppData" / "Roaming" / "Claude" / CONFIG_NAME
    traditional.parent.mkdir(parents=True)
    traditional.write_text('{"leave": "unchanged"}')
    monkeypatch.setattr(
        setup,
        "create_mcp_config",
        lambda *args, **kwargs: {"mcpServers": {"m4": {"command": "m4-mcp"}}},
    )
    assert setup.setup_claude_desktop() is True
    assert json.loads(config.read_text()) == {
        **existing,
        "mcpServers": {**existing["mcpServers"], "m4": {"command": "m4-mcp"}},
    }
    assert traditional.read_text() == '{"leave": "unchanged"}'
