from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
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


def test_codex_run_home_keeps_shell_writes_in_workdir(monkeypatch, tmp_path):
    run = _load_module("benchmark_run_codex_env", "benchmark/run.py")

    workdir = tmp_path / "work"
    run_home = tmp_path / "home"
    workdir.mkdir()
    (run_home / ".codex").mkdir(parents=True)
    (run_home / ".codex" / "auth.json").write_text("{}")
    captured = {}

    class FakeProcess:
        def __init__(self):
            self.stdout = io.StringIO('{"type":"turn.completed","usage":{}}\n')
            self.returncode = 0

        def wait(self, timeout):
            return 0

        def kill(self):
            raise AssertionError("process should not be killed")

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(run.subprocess, "Popen", fake_popen)

    result = run.run_agent(
        "write ./output.csv",
        "codex",
        workdir,
        model="gpt-5.4-mini",
        run_home=run_home,
    )

    env = captured["kwargs"]["env"]
    assert result["returncode"] == 0
    assert captured["kwargs"]["cwd"] == str(workdir)
    assert env["HOME"] == str(workdir)
    assert env["CODEX_HOME"] == str(workdir / ".codex")
    assert env["TMPDIR"] == str(run_home / "tmp")
    assert captured["cmd"][captured["cmd"].index("-C") + 1] == str(workdir)
    assert (workdir / ".codex" / "auth.json").read_text() == "{}"
    assert (workdir / "trace.jsonl").exists()


def test_resolve_results_root_uses_override(tmp_path):
    run = _load_module("benchmark_run_results_root", "benchmark/run.py")

    resolved = run.resolve_results_root(str(tmp_path / "paper-run"))
    assert resolved == (tmp_path / "paper-run").resolve()


def test_trial_numbers_start_at_requested_trial():
    run = _load_module("benchmark_run_trials", "benchmark/run.py")

    assert run._trial_numbers(3, 2) == [3, 4]


def test_bench_sh_handles_empty_mount_array_with_bash_nounset(tmp_path):
    fake_docker = tmp_path / "docker"
    docker_log = tmp_path / "docker.log"
    fake_docker.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$FAKE_DOCKER_LOG"
if [[ "${1:-}" == "context" && "${2:-}" == "show" ]]; then
    echo default
    exit 0
fi
if [[ "${1:-}" == "image" && "${2:-}" == "inspect" ]]; then
    exit 0
fi
if [[ "${1:-}" == "ps" ]]; then
    exit 0
fi
exit 0
"""
    )
    fake_docker.chmod(0o755)

    env = {
        **os.environ,
        "DOCKER_BIN": str(fake_docker),
        "FAKE_DOCKER_LOG": str(docker_log),
        "HOME": str(tmp_path / "home"),
        "M4BENCH_CONTAINER_NAME": "m4bench-test",
        "M4BENCH_M4_DATA_DIR": str(tmp_path / "m4_data"),
    }

    result = subprocess.run(
        [
            "bash",
            "benchmark/bench.sh",
            "--task",
            "eicu-gcs",
            "--condition",
            "with-skill",
            "--agent",
            "codex",
            "--results-root",
            "/benchmark/results/fake",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "unbound variable" not in result.stderr
    assert "python3 /benchmark/run.py" in docker_log.read_text()


def test_codex_command_disables_plugins():
    run = _load_module("benchmark_run_codex_cmd", "benchmark/run.py")

    codex_cmd = run.AGENT_COMMANDS["codex"]["cmd"]

    assert "--dangerously-bypass-approvals-and-sandbox" in codex_cmd
    assert "--disable" in codex_cmd
    assert "plugins" in codex_cmd
    assert 'web_search="disabled"' in codex_cmd
    assert "tools.web_search=false" in codex_cmd


def test_rewrite_m4_data_sql_path_points_at_container_mount():
    run = _load_module("benchmark_run_rewrite_sql", "benchmark/run.py")

    sql = (
        "CREATE VIEW patient AS SELECT * FROM "
        "read_parquet('/Users/example/m4_data/parquet/eicu/patient.parquet');"
    )

    rewritten = run._rewrite_m4_data_sql_path(sql, "/m4_data")

    assert "/Users/example/m4_data" not in rewritten
    assert "read_parquet('/m4_data/parquet/eicu/patient.parquet')" in rewritten


def test_detect_external_tool_use_flags_web_search(tmp_path):
    run = _load_module("benchmark_run_external_tools", "benchmark/run.py")

    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"type":"item.started","item":{"type":"web_search","id":"x"}}\n')

    assert run._detect_external_tool_use(trace) == ["web_search"]


def test_detect_external_tool_use_flags_shell_network_attempt(tmp_path):
    run = _load_module("benchmark_run_external_shell", "benchmark/run.py")

    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        json.dumps(
            {
                "type": "item.started",
                "item": {
                    "type": "command_execution",
                    "command": (
                        'python3 -c "from urllib.request import urlopen; '
                        "urlopen('https://example.com')\""
                    ),
                },
            }
        )
        + "\n"
    )

    assert run._detect_external_tool_use(trace) == ["external_network_command"]


def test_gemini_command_uses_external_sandbox():
    run = _load_module("benchmark_run_gemini_cmd", "benchmark/run.py")

    gemini_cmd = run.AGENT_COMMANDS["gemini"]["cmd"]

    assert "--sandbox" not in gemini_cmd
    assert "--approval-mode" in gemini_cmd
    assert "yolo" in gemini_cmd


def test_pi_ollama_command_disables_context_discovery():
    run = _load_module("benchmark_run_pi_ollama_cmd", "benchmark/run.py")

    pi_cmd = run.AGENT_COMMANDS["pi-ollama"]["cmd"]

    assert pi_cmd[0] == "pi"
    assert pi_cmd[-1] == "-p"
    assert "--no-context-files" in pi_cmd
    assert "--no-themes" in pi_cmd
    assert "--no-prompt-templates" in pi_cmd
    assert "--no-extensions" in pi_cmd
    assert "--provider" in pi_cmd
    assert "ollama" in pi_cmd
    assert ".pi/skills" in pi_cmd


def test_pi_ollama_model_flag_precedes_prompt_flag(monkeypatch, tmp_path):
    run = _load_module("benchmark_run_pi_ollama_model_cmd", "benchmark/run.py")
    seen: dict[str, list[str]] = {}

    class FakeProcess:
        returncode = 0
        stdout = iter(["ok\n"])

        def wait(self, timeout=None):
            return 0

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        return FakeProcess()

    monkeypatch.setattr(run.subprocess, "Popen", fake_popen)

    result = run.run_agent(
        "double the scores",
        "pi-ollama",
        tmp_path,
        model="qwen3:4b",
    )

    cmd = seen["cmd"]
    assert result["returncode"] == 0
    assert cmd[-2:] == ["-p", "double the scores"]
    assert cmd[cmd.index("--model") + 1] == "qwen3:4b"
    assert cmd.index("--model") < cmd.index("-p")


def test_prepare_run_home_pi_ollama_seeds_only_models_json(monkeypatch, tmp_path):
    run = _load_module("benchmark_run_pi_home", "benchmark/run.py")

    auth_root = tmp_path / "auth"
    (auth_root / ".pi" / "agent").mkdir(parents=True)
    (auth_root / ".pi" / "agent" / "models.json").write_text("{}")
    (auth_root / ".pi" / "agent" / "auth.json").write_text("{}")

    monkeypatch.setenv("M4BENCH_AUTH_ROOT", str(auth_root))

    pi_home = tmp_path / "pi-home"
    copied = run.prepare_run_home("pi-ollama", pi_home)

    assert copied == [".pi/agent/models.json"]
    assert (pi_home / ".pi" / "agent" / "models.json").exists()
    assert not (pi_home / ".pi" / "agent" / "auth.json").exists()


def test_prepare_run_home_pi_ollama_rewrites_docker_ollama_url(monkeypatch, tmp_path):
    run = _load_module("benchmark_run_pi_home_ollama_url", "benchmark/run.py")

    auth_root = tmp_path / "auth"
    models_path = auth_root / ".pi" / "agent" / "models.json"
    models_path.parent.mkdir(parents=True)
    models_path.write_text(
        json.dumps(
            {
                "providers": {
                    "ollama": {
                        "baseUrl": "http://localhost:11434/v1",
                        "api": "openai-completions",
                        "apiKey": "ollama",
                        "models": [{"id": "qwen3:4b"}],
                    }
                }
            }
        )
    )

    monkeypatch.setenv("M4BENCH_AUTH_ROOT", str(auth_root))
    monkeypatch.setenv(
        "M4BENCH_OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1"
    )

    pi_home = tmp_path / "pi-home"
    run.prepare_run_home("pi-ollama", pi_home)

    copied = json.loads((pi_home / ".pi" / "agent" / "models.json").read_text())
    assert (
        copied["providers"]["ollama"]["baseUrl"]
        == "http://host.docker.internal:11434/v1"
    )


def test_reasoning_auto_policy_resolves_by_agent():
    run = _load_module("benchmark_run_reasoning_policy", "benchmark/run.py")

    assert run._resolve_reasoning_effort("codex", "auto") == "medium"
    assert run._resolve_reasoning_effort("claude", "auto") == "medium"
    assert run._resolve_reasoning_effort("gemini", "auto") == "provider-default"
    assert run._resolve_reasoning_effort("pi-ollama", "auto") == "provider-default"


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
    assert run._reasoning_args_for_agent("pi-ollama", "provider-default") == []


def test_named_reasoning_rejects_unsupported_agent_scale():
    run = _load_module("benchmark_run_reasoning_invalid", "benchmark/run.py")

    try:
        run._resolve_reasoning_effort("gemini", "high")
    except ValueError as exc:
        assert "does not support named reasoning effort" in str(exc)
    else:
        raise AssertionError("expected ValueError for Gemini named effort")

    try:
        run._resolve_reasoning_effort("pi-ollama", "high")
    except ValueError as exc:
        assert "does not support named reasoning effort" in str(exc)
    else:
        raise AssertionError("expected ValueError for pi-ollama named effort")


def test_network_lock_allows_subscription_backed_codex_hosts():
    script = (ROOT / "benchmark" / "network_lock.sh").read_text()

    assert "api.openai.com" in script
    assert "auth.openai.com" in script
    assert "chatgpt.com" in script


def test_network_lock_allows_configured_ollama_for_pi():
    script = (ROOT / "benchmark" / "network_lock.sh").read_text()

    assert "M4BENCH_ALLOW_OLLAMA" in script
    assert "M4BENCH_OLLAMA_HOST" in script
    assert "M4BENCH_OLLAMA_PORT" in script
    assert '--dport "$OLLAMA_PORT"' in script


def test_benchmark_dockerfile_installs_pi_cli():
    dockerfile = (ROOT / "benchmark" / "Dockerfile").read_text()

    assert "PI_CODING_AGENT_VERSION=0.70.2" in dockerfile
    assert "@mariozechner/pi-coding-agent@${PI_CODING_AGENT_VERSION}" in dockerfile


def test_bench_sh_mounts_pi_config_and_configures_ollama_endpoint():
    bench = (ROOT / "benchmark" / "bench.sh").read_text()

    assert 'AGENT" == "pi-ollama"' in bench
    assert "command -v pi" in bench
    assert "M4BENCH_OLLAMA_BASE_URL" in bench
    assert "--add-host=host.docker.internal:host-gateway" in bench
    assert "$HOME/.pi:$AUTH_ROOT/.pi:ro" in bench


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
