from m4.services.results import CommandError, CommandResult


def test_command_result_serializes_envelope_with_data_and_warnings():
    result = CommandResult(
        command="use",
        data={"active_dataset": "mimic-iv", "backend": "duckdb"},
        warnings=["local_db_missing"],
    )

    assert result.to_json_dict() == {
        "version": 1,
        "ok": True,
        "command": "use",
        "active_dataset": "mimic-iv",
        "backend": "duckdb",
        "warnings": ["local_db_missing"],
    }


def test_command_error_serializes_without_empty_hint():
    error = CommandError(
        command="backend",
        code="invalid_backend",
        message="Backend 'mysql' is not valid.",
    )

    assert error.to_json_dict() == {
        "version": 1,
        "ok": False,
        "command": "backend",
        "error": {
            "code": "invalid_backend",
            "message": "Backend 'mysql' is not valid.",
        },
    }


def test_command_error_serializes_hint_when_present():
    error = CommandError(
        command="backend",
        code="project_id_required",
        message="BigQuery backend requires a project ID.",
        hint="Set it with: m4 backend bigquery --project-id <ID>",
    )

    assert error.to_json_dict()["error"]["hint"] == (
        "Set it with: m4 backend bigquery --project-id <ID>"
    )
