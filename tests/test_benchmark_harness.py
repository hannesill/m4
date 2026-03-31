from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_refresh_oauth_token_seeds_when_env_missing(monkeypatch):
    run = _load_module("benchmark_run_refresh", "benchmark/run.py")

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    run._token_last_refresh = 0.0

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["security", "find-generic-password"]:
            return SimpleNamespace(
                returncode=0,
                stdout='{"claudeAiOauth":{"accessToken":"sk-ant-oat-test"}}',
            )
        if cmd[:2] == ["python3", "-c"]:
            return SimpleNamespace(returncode=0, stdout="sk-ant-oat-test\n")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    monkeypatch.setattr(run.subprocess, "run", fake_run)

    run._refresh_oauth_token()

    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-oat-test"


def test_setup_isolated_workdir_uses_requested_schema(monkeypatch, tmp_path):
    run = _load_module("benchmark_run_isolated", "benchmark/run.py")

    cached_db = tmp_path / "cached.duckdb"
    cached_db.write_text("db")
    seen: dict[str, str] = {}

    monkeypatch.setattr(run, "ISOLATED_BASE", tmp_path / "isolated")

    def fake_get_cached_db(task_name: str, schema: str = "native") -> Path:
        seen["task_name"] = task_name
        seen["schema"] = schema
        return cached_db

    monkeypatch.setattr(run, "_get_cached_db", fake_get_cached_db)
    monkeypatch.setattr(run, "_create_isolated_settings", lambda workdir: workdir)

    workdir = run.setup_isolated_workdir(
        "mimic-sirs-24h-raw", "run123", schema="obfuscated"
    )

    assert seen == {"task_name": "mimic-sirs-24h-raw", "schema": "obfuscated"}
    assert (workdir / "database.duckdb").read_text() == "db"


def test_prepare_run_home_copies_minimal_auth_files(monkeypatch, tmp_path):
    run = _load_module("benchmark_run_home", "benchmark/run.py")

    auth_root = tmp_path / "auth"
    (auth_root / ".codex").mkdir(parents=True)
    (auth_root / ".gemini").mkdir(parents=True)
    (auth_root / ".codex" / "auth.json").write_text("{}")
    (auth_root / ".codex" / "config.toml").write_text('model = "gpt-5"')
    (auth_root / ".gemini" / "oauth_creds.json").write_text("{}")
    (auth_root / ".gemini" / "google_accounts.json").write_text("[]")
    (auth_root / ".gemini" / "state.json").write_text("{}")
    (auth_root / ".gemini" / "settings.json").write_text("{}")
    (auth_root / ".gemini" / "installation_id").write_text("abc")
    (auth_root / ".gemini" / "trustedFolders.json").write_text("[]")

    monkeypatch.setenv("M4BENCH_AUTH_ROOT", str(auth_root))

    codex_home = tmp_path / "codex-home"
    copied_codex = run.prepare_run_home("codex", codex_home)
    assert copied_codex == [".codex/auth.json"]
    assert (codex_home / ".codex" / "auth.json").exists()
    assert not (codex_home / ".codex" / "config.toml").exists()

    gemini_home = tmp_path / "gemini-home"
    copied_gemini = run.prepare_run_home("gemini", gemini_home)
    assert copied_gemini == [
        ".gemini/oauth_creds.json",
        ".gemini/google_accounts.json",
        ".gemini/state.json",
        ".gemini/settings.json",
        ".gemini/installation_id",
    ]
    assert (gemini_home / ".gemini" / "oauth_creds.json").exists()
    assert not (gemini_home / ".gemini" / "trustedFolders.json").exists()


def test_setup_parser_allows_schema_with_all():
    setup = _load_module("benchmark_setup_cli", "benchmark/setup.py")

    parser = setup.build_parser()
    args = parser.parse_args(["--schema", "obfuscated", "--all"])

    assert args.schema == "obfuscated"
    assert args.all is True
