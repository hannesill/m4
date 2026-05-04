"""Run benchmark diagnostics without invoking pytest in the hot path."""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

try:
    from .compare import (
        compare_derived_frames,
        read_benchmark_csv,
        scored_value_columns,
    )
except ImportError:  # pragma: no cover - supports direct script-style imports.
    from compare import (
        compare_derived_frames,
        read_benchmark_csv,
        scored_value_columns,
    )


def _format_status(name: str, passed: bool, detail: str = "") -> str:
    status = "PASSED" if passed else "FAILED"
    return f"{name:<52s} {status}{(': ' + detail) if detail else ''}"


def _empty_result(error: str) -> dict:
    return {
        "passed": 0,
        "failed": 0,
        "errors": 1,
        "total": 1,
        "reward": 0.0,
        "pytest_output": f"Benchmark diagnostics errored: {error}",
        "pytest_stderr": "",
    }


def run_tests(
    task_dir: str | Path,
    output_path: str | Path,
    ground_truth_path: str | Path,
) -> dict:
    """Run task diagnostics and return pytest-compatible result fields.

    The benchmark used to shell out to pytest for these checks. This in-process
    runner preserves the same pass/fail semantics while reading and comparing
    large output tables once per evaluation.
    """
    task_dir = Path(task_dir)
    output_path = Path(output_path)
    ground_truth_path = Path(ground_truth_path)

    try:
        with open(task_dir / "task.toml", "rb") as f:
            config = tomllib.load(f)
        eval_config = config["evaluation"]
        key_columns = eval_config["key_columns"]
        value_columns = eval_config["value_columns"]
        score_columns = scored_value_columns(eval_config)
        required_columns = eval_config.get(
            "required_columns", key_columns + value_columns
        )
        row_coverage_threshold = eval_config.get("row_coverage_threshold", 0.95)
        accuracy_threshold = eval_config.get("accuracy_threshold", 0.90)
        tolerance = eval_config.get("tolerance", {})
    except Exception as exc:
        return _empty_result(str(exc))

    checks: list[tuple[str, bool, str]] = []
    comparison: dict | None = None

    exists = output_path.exists()
    checks.append(
        (
            "test_output_exists",
            exists,
            "" if exists else f"Output file not found: {output_path}",
        )
    )
    if not exists:
        output = "\n".join(_format_status(*check) for check in checks)
        failed = sum(not passed for _, passed, _ in checks)
        return {
            "passed": 0,
            "failed": failed,
            "errors": 0,
            "total": len(checks),
            "reward": 0.0,
            "pytest_output": output,
            "pytest_stderr": "",
        }

    try:
        agent_df = read_benchmark_csv(str(output_path))
        truth_df = read_benchmark_csv(str(ground_truth_path))
    except Exception as exc:
        return _empty_result(f"CSV read failed: {exc}")

    nonempty = len(agent_df) > 0
    checks.append(
        (
            "test_output_is_valid_csv",
            nonempty,
            "" if nonempty else "Output CSV is empty",
        )
    )

    missing_required = [col for col in required_columns if col not in agent_df.columns]
    checks.append(
        (
            "test_has_required_columns",
            not missing_required,
            ""
            if not missing_required
            else f"Missing columns: {missing_required}. Got: {list(agent_df.columns)}",
        )
    )

    try:
        comparison = compare_derived_frames(
            agent_df,
            truth_df,
            key_columns=key_columns,
            value_columns=score_columns,
            tolerance=tolerance,
        )
    except Exception as exc:
        return _empty_result(f"Comparison failed: {exc}")

    meta = comparison.get("__meta__", {})
    truth_rows = int(meta.get("truth_rows", 0))
    matched_keys = int(meta.get("agent_keys_in_truth", 0))
    coverage = matched_keys / truth_rows if truth_rows else 0.0
    checks.append(
        (
            "test_row_coverage",
            coverage >= row_coverage_threshold,
            ""
            if coverage >= row_coverage_threshold
            else (
                f"Only {coverage:.1%} of ground truth keys matched "
                f"({matched_keys}/{truth_rows}). "
                f"Need >= {row_coverage_threshold:.0%}."
            ),
        )
    )

    if comparison is None:
        return _empty_result("Comparison did not produce results")

    for column in score_columns:
        result = comparison[column]
        rate = result["match_rate"]
        passed = rate >= accuracy_threshold
        detail = ""
        if not passed:
            detail = (
                f"{column}: {rate:.1%} match rate "
                f"({result['matched']}/{result['total']}). "
                f"Need >= {accuracy_threshold:.0%}. "
                f"Examples: {result['mismatched_examples']}"
            )
            if "error" in result:
                detail = f"{detail} Error: {result['error']}"
        checks.append((f"test_score_accuracy[{column}]", passed, detail))

    passed_count = sum(1 for _, passed, _ in checks if passed)
    failed_count = len(checks) - passed_count
    reward = passed_count / len(checks) if checks else 0.0
    output_lines = [
        "Benchmark diagnostics",
        f"task_dir={task_dir}",
        f"output={output_path}",
        f"ground_truth={ground_truth_path}",
        "",
        *(_format_status(*check) for check in checks),
        "",
        f"{passed_count} passed, {failed_count} failed, 0 errors",
    ]

    return {
        "passed": passed_count,
        "failed": failed_count,
        "errors": 0,
        "total": len(checks),
        "reward": round(reward, 4),
        "pytest_output": "\n".join(output_lines),
        "pytest_stderr": "",
        "_comparison": comparison,
    }
