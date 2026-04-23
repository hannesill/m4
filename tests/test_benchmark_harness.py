from __future__ import annotations

import importlib.util
import json
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


# ── Token refresh ────────────────────────────────────────────────────────


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


def test_detect_agent_failure_reason_identifies_claude_auth(tmp_path):
    run = _load_module("benchmark_run_failure_auth", "benchmark/run.py")

    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        '{"type":"result","subtype":"success","is_error":true,'
        '"result":"Invalid API key · Fix external API key"}\n'
    )

    reason = run._detect_agent_failure_reason(
        "claude",
        {
            "stdout": "Invalid API key · Fix external API key",
            "stderr": "",
            "trace_file": str(trace),
        },
    )

    assert reason == "auth"


def test_extract_claude_rate_limit_reset_at(tmp_path):
    run = _load_module("benchmark_run_rate_reset", "benchmark/run.py")

    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        '{"type":"rate_limit_event","rate_limit_info":{"status":"blocked",'
        '"resetsAt":1775545200,"rateLimitType":"five_hour"}}\n'
    )

    assert run._extract_claude_rate_limit_reset_at(trace) == 1775545200


# ── Isolated workdir ────────────────────────────────────────────────────


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


# ── Per-run HOME seeding ────────────────────────────────────────────────


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
    assert (gemini_home / ".gemini" / "projects.json").exists()
    gemini_settings = json.loads(
        (gemini_home / ".gemini" / "settings.json").read_text()
    )
    assert gemini_settings["security"]["auth"]["selectedType"] == "oauth-personal"
    assert gemini_settings["security"]["blockGitExtensions"] is True
    assert gemini_settings["admin"]["extensions"]["enabled"] is False
    assert gemini_settings["admin"]["skills"]["enabled"] is True
    assert not (gemini_home / ".gemini" / "trustedFolders.json").exists()


def test_resolve_results_root_uses_override(tmp_path):
    run = _load_module("benchmark_run_results_root", "benchmark/run.py")

    resolved = run.resolve_results_root(str(tmp_path / "paper-run"))
    assert resolved == (tmp_path / "paper-run").resolve()


def test_trial_numbers_start_at_requested_trial():
    run = _load_module("benchmark_run_trials", "benchmark/run.py")

    assert run._trial_numbers(3, 2) == [3, 4]


def test_codex_command_disables_plugins():
    run = _load_module("benchmark_run_codex_cmd", "benchmark/run.py")

    codex_cmd = run.AGENT_COMMANDS["codex"]["cmd"]

    assert "--dangerously-bypass-approvals-and-sandbox" in codex_cmd
    assert "--disable" in codex_cmd
    assert "plugins" in codex_cmd


def test_gemini_command_uses_external_sandbox():
    run = _load_module("benchmark_run_gemini_cmd", "benchmark/run.py")

    gemini_cmd = run.AGENT_COMMANDS["gemini"]["cmd"]

    assert "--sandbox" not in gemini_cmd
    assert "--approval-mode" in gemini_cmd
    assert "yolo" in gemini_cmd


def test_reasoning_auto_policy_resolves_by_agent():
    run = _load_module("benchmark_run_reasoning_policy", "benchmark/run.py")

    assert run._resolve_reasoning_effort("codex", "auto") == "medium"
    assert run._resolve_reasoning_effort("claude", "auto") == "medium"
    assert run._resolve_reasoning_effort("gemini", "auto") == "provider-default"


def test_reasoning_args_match_supported_agent_clis():
    run = _load_module("benchmark_run_reasoning_args", "benchmark/run.py")

    assert run._reasoning_args_for_agent("codex", "medium") == [
        "-c",
        'model_reasoning_effort="medium"',
    ]
    assert run._reasoning_args_for_agent("claude", "medium") == [
        "--effort",
        "medium",
    ]
    assert run._reasoning_args_for_agent("gemini", "provider-default") == []


def test_named_reasoning_rejects_unsupported_agent_scale():
    run = _load_module("benchmark_run_reasoning_invalid", "benchmark/run.py")

    try:
        run._resolve_reasoning_effort("gemini", "high")
    except ValueError as exc:
        assert "does not support named reasoning effort" in str(exc)
    else:
        raise AssertionError("expected ValueError for Gemini named effort")


def test_network_lock_allows_subscription_backed_codex_hosts():
    script = (ROOT / "benchmark" / "network_lock.sh").read_text()

    assert "api.openai.com" in script
    assert "auth.openai.com" in script
    assert "chatgpt.com" in script


def test_task_discovery_uses_repo_relative_paths(monkeypatch):
    monkeypatch.chdir(ROOT / "benchmark")
    db = _load_module("benchmark_db_paths", "benchmark/lib/db.py")

    task_dirs = db.list_task_dirs()

    assert task_dirs
    assert task_dirs[0].is_absolute()
    assert (task_dirs[0] / "task.toml").exists()


def test_publishable_environment_requires_container_and_agent_user(monkeypatch):
    run = _load_module("benchmark_run_publishable", "benchmark/run.py")

    monkeypatch.setattr(run, "_running_in_container", lambda: True)
    monkeypatch.setattr(run, "_resolve_agent_creds", lambda: (123, 456))
    assert run._publishable_environment(True) == (
        True,
        "docker + benchagent isolation active",
    )

    monkeypatch.setattr(run, "_running_in_container", lambda: False)
    ok, reason = run._publishable_environment(True)
    assert ok is False
    assert reason == "not running inside benchmark Docker container"


# ── Agent user isolation ────────────────────────────────────────────────


def test_resolve_agent_creds_returns_none_when_user_missing(monkeypatch):
    """Outside Docker (no benchagent user), _resolve_agent_creds returns None."""
    run = _load_module("benchmark_run_creds", "benchmark/run.py")

    import pwd

    original = pwd.getpwnam

    def fake_getpwnam(name):
        if name == "benchagent":
            raise KeyError(name)
        return original(name)

    monkeypatch.setattr(pwd, "getpwnam", fake_getpwnam)
    assert run._resolve_agent_creds() is None


def test_chown_recursive(tmp_path):
    """_chown_recursive changes ownership of all files and dirs."""
    run = _load_module("benchmark_run_chown", "benchmark/run.py")

    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "file.txt").write_text("data")

    # Just verify it doesn't crash with current uid/gid
    uid = os.getuid()
    gid = os.getgid()
    run._chown_recursive(tmp_path, uid, gid)

    # Verify ownership
    assert (tmp_path / "sub" / "file.txt").stat().st_uid == uid


# ── CLI flag: isolation is default ──────────────────────────────────────


def test_isolation_is_default():
    """Verify --no-isolation is required to disable isolation."""
    import argparse

    # Simulate the parser creation from main()
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-isolation", action="store_true")
    parser.add_argument("--isolated", action="store_true")

    # Default: isolated
    args = parser.parse_args([])
    assert not args.no_isolation

    # Explicit disable
    args = parser.parse_args(["--no-isolation"])
    assert args.no_isolation


# ── Sandbox hook: blocked substrings ────────────────────────────────────


def test_sandbox_hook_blocks_ground_truth_paths():
    hook = _load_module("sandbox_hook_test", "benchmark/lib/sandbox_hook.py")

    assert (
        hook._check_blocked_substrings("/benchmark/ground_truth/sofa.csv") is not None
    )
    assert hook._check_blocked_substrings("cat ground_truth/foo.sql") is not None
    assert hook._check_blocked_substrings("/benchmark/evaluate.py") is not None
    assert hook._check_blocked_substrings("/benchmark/lib/compare.py") is not None
    # Allowed paths should not trigger
    assert hook._check_blocked_substrings("./output.csv") is None
    assert hook._check_blocked_substrings("./database.duckdb") is None


def test_sandbox_hook_extracts_quoted_paths():
    hook = _load_module("sandbox_hook_paths", "benchmark/lib/sandbox_hook.py")

    paths = hook.extract_paths_from_command("python3 -c \"open('/benchmark/foo')\"")
    assert any("/benchmark/foo" in p for p in paths)


# ── setup.py CLI ────────────────────────────────────────────────────────


def test_setup_parser_allows_schema_with_all():
    setup = _load_module("benchmark_setup_cli", "benchmark/setup.py")

    parser = setup.build_parser()
    args = parser.parse_args(["--schema", "obfuscated", "--all"])

    assert args.schema == "obfuscated"
    assert args.all is True
